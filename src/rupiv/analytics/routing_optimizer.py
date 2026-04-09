"""Intelligent payment routing — select the cheapest PSP per transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.payment_cost import PaymentCostRecord

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PSPRoute:
    """A recommended payment route with estimated cost."""

    psp: str
    method: str
    estimated_fee: Decimal
    estimated_rate: Decimal
    reason: str


# ---------------------------------------------------------------------------
# Fee schedules — easily configurable dicts
# ---------------------------------------------------------------------------

# Each entry maps: method -> {"fixed": Decimal, "rate_pct": Decimal}
# fixed  = flat fee per transaction (EUR)
# rate_pct = percentage of transaction amount (e.g. 2.9 means 2.9%)

PSP_FEE_SCHEDULES: dict[str, dict[str, dict[str, Decimal]]] = {
    "mollie": {
        "ideal": {"fixed": Decimal("0.29"), "rate_pct": Decimal("0")},
        "card": {"fixed": Decimal("0.25"), "rate_pct": Decimal("2.9")},
        "sepa_dd": {"fixed": Decimal("0.35"), "rate_pct": Decimal("0")},
        "bancontact": {"fixed": Decimal("0.29"), "rate_pct": Decimal("0")},
    },
    "adyen": {
        "ideal": {"fixed": Decimal("0.22"), "rate_pct": Decimal("0")},
        "card": {"fixed": Decimal("0.20"), "rate_pct": Decimal("2.2")},
        "sepa_dd": {"fixed": Decimal("0.30"), "rate_pct": Decimal("0")},
    },
    "stripe": {
        "card": {"fixed": Decimal("0.30"), "rate_pct": Decimal("2.9")},
        "ach": {"fixed": Decimal("0.00"), "rate_pct": Decimal("0.8"), "cap": Decimal("5.00")},
        "sepa_dd": {"fixed": Decimal("0.50"), "rate_pct": Decimal("0")},
    },
}

# Default PSP when no better option is found
DEFAULT_PSP = "mollie"

# Methods available per country (used for auto-selection when method is None)
COUNTRY_PREFERRED_METHODS: dict[str, str] = {
    "NL": "ideal",
    "BE": "bancontact",
    "DE": "sepa_dd",
    "AT": "sepa_dd",
    "FR": "card",
    "ES": "card",
    "IT": "card",
    "US": "card",
}

# Countries where Stripe is the preferred PSP (US expansion)
STRIPE_PREFERRED_COUNTRIES: set[str] = {"US"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _estimate_fee(amount: Decimal, schedule: dict[str, Decimal]) -> Decimal:
    """Calculate estimated fee from a fee schedule entry.

    Supports an optional ``cap`` key for methods like ACH where the
    percentage-based fee is capped at a maximum amount.
    """
    fixed = schedule["fixed"]
    rate = schedule["rate_pct"]
    variable = amount * rate / Decimal("100")

    # Apply cap if present (e.g. ACH capped at $5.00)
    cap = schedule.get("cap")
    if cap is not None and variable > cap:
        variable = cap

    return (fixed + variable).quantize(Decimal("0.0001"))


def _estimate_rate(amount: Decimal, fee: Decimal) -> Decimal:
    """Calculate effective rate as a percentage."""
    if amount <= 0:
        return Decimal("0")
    return (fee / amount * Decimal("100")).quantize(Decimal("0.0001"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_cheapest_route(
    amount: Decimal,
    currency: str,
    country_code: str,
    payment_method: str | None = None,
) -> PSPRoute:
    """Find the cheapest PSP route for a payment.

    If *payment_method* is ``None``, the country's preferred method is used.
    Compares all PSPs that support the method and returns the cheapest.
    """
    method = payment_method or COUNTRY_PREFERRED_METHODS.get(country_code, "card")

    # For US customers, prefer Stripe as the regional PSP
    preferred_psp: str | None = None
    if country_code in STRIPE_PREFERRED_COUNTRIES:
        preferred_psp = "stripe"

    best_psp: str | None = None
    best_fee: Decimal | None = None
    best_schedule: dict[str, Decimal] | None = None

    for psp, methods in PSP_FEE_SCHEDULES.items():
        if method not in methods:
            continue
        schedule = methods[method]
        fee = _estimate_fee(amount, schedule)
        if best_fee is None or fee < best_fee:
            best_psp = psp
            best_fee = fee
            best_schedule = schedule

    # If a regional PSP is preferred and supports the method, use it
    # (even if not strictly cheapest) to ensure correct regional coverage.
    if (
        preferred_psp is not None
        and preferred_psp in PSP_FEE_SCHEDULES
        and method in PSP_FEE_SCHEDULES[preferred_psp]
    ):
        pref_schedule = PSP_FEE_SCHEDULES[preferred_psp][method]
        pref_fee = _estimate_fee(amount, pref_schedule)
        best_psp = preferred_psp
        best_fee = pref_fee
        best_schedule = pref_schedule

    # Fallback to default PSP with card if nothing matched
    if best_psp is None:
        fallback_schedule = PSP_FEE_SCHEDULES[DEFAULT_PSP].get(
            "card", {"fixed": Decimal("0.25"), "rate_pct": Decimal("2.9")}
        )
        best_psp = DEFAULT_PSP
        best_fee = _estimate_fee(amount, fallback_schedule)
        method = "card"
        reason = f"No PSP supports {method}; falling back to {DEFAULT_PSP} card"
    else:
        runner_up_fees = []
        for psp, methods in PSP_FEE_SCHEDULES.items():
            if psp != best_psp and method in methods:
                runner_up_fees.append(
                    (psp, _estimate_fee(amount, methods[method]))
                )

        if runner_up_fees:
            runner_up = min(runner_up_fees, key=lambda x: x[1])
            saving = runner_up[1] - best_fee
            reason = (
                f"{best_psp} {method} is cheapest at {best_fee} EUR "
                f"(saves {saving} EUR vs {runner_up[0]})"
            )
        else:
            reason = f"{best_psp} is the only PSP supporting {method}"

    rate = _estimate_rate(amount, best_fee)

    log.info(
        "routing.cheapest_route",
        psp=best_psp,
        method=method,
        amount=str(amount),
        estimated_fee=str(best_fee),
        reason=reason,
    )

    return PSPRoute(
        psp=best_psp,
        method=method,
        estimated_fee=best_fee,
        estimated_rate=rate,
        reason=reason,
    )


async def get_recommendations(
    session: AsyncSession,
    period_start: date,
    period_end: date,
) -> list[dict]:
    """Analyze recent payments and suggest routing changes with estimated savings.

    Returns a list of recommendation dicts, each with:
    - method, current_psp, recommended_psp, volume, current_fees,
      estimated_fees, estimated_savings
    """
    start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)

    q = select(PaymentCostRecord).where(
        and_(
            PaymentCostRecord.created_at >= start_dt,
            PaymentCostRecord.created_at < end_dt,
        )
    )
    result = await session.execute(q)
    records = result.scalars().all()

    # Group by (psp, method) to find potential savings
    grouped: dict[tuple[str, str], dict] = {}
    for rec in records:
        key = (rec.psp, rec.payment_method)
        if key not in grouped:
            grouped[key] = {
                "count": 0,
                "volume": Decimal("0"),
                "fees": Decimal("0"),
            }
        grouped[key]["count"] += 1
        grouped[key]["volume"] += Decimal(str(rec.gross_amount))
        grouped[key]["fees"] += Decimal(str(rec.fee_amount))

    recommendations: list[dict] = []
    for (current_psp, method), data in grouped.items():
        avg_amount = data["volume"] / Decimal(str(data["count"])) if data["count"] else Decimal("0")

        # Find cheapest alternative
        best_alt_psp: str | None = None
        best_alt_fee_total = Decimal("0")

        for psp, methods in PSP_FEE_SCHEDULES.items():
            if method not in methods:
                continue
            schedule = methods[method]
            # Estimate total fees for the entire volume at this PSP's rates
            total_est = sum(
                _estimate_fee(avg_amount, schedule) for _ in range(data["count"])
            )
            if best_alt_psp is None or total_est < best_alt_fee_total:
                best_alt_psp = psp
                best_alt_fee_total = total_est

        if best_alt_psp is None or best_alt_psp == current_psp:
            continue

        savings = data["fees"] - best_alt_fee_total
        if savings <= 0:
            continue

        recommendations.append(
            {
                "method": method,
                "current_psp": current_psp,
                "recommended_psp": best_alt_psp,
                "transaction_count": data["count"],
                "volume": data["volume"],
                "current_fees": data["fees"],
                "estimated_fees": best_alt_fee_total,
                "estimated_savings": savings,
            }
        )

    recommendations.sort(key=lambda r: r["estimated_savings"], reverse=True)

    log.info(
        "routing.recommendations",
        period=f"{period_start.isoformat()}/{period_end.isoformat()}",
        recommendation_count=len(recommendations),
    )

    return recommendations
