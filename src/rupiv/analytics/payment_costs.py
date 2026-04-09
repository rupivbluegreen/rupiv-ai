"""PSP cost tracking — blended rates, per-method breakdown, cross-PSP comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
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
class MethodCost:
    """Cost breakdown for a single payment method within a PSP."""

    method: str
    count: int
    volume: Decimal
    fees: Decimal
    unit_fee: Decimal | None
    rate_pct: Decimal | None


@dataclass(frozen=True)
class PaymentCostSummary:
    """Aggregated cost summary for a PSP over a period."""

    psp: str
    period: str
    transaction_count: int
    total_volume: Decimal
    total_fees: Decimal
    blended_rate: Decimal
    by_method: dict[str, MethodCost]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def calculate_payment_costs(
    session: AsyncSession,
    psp: str,
    period_start: date,
    period_end: date,
) -> PaymentCostSummary:
    """Calculate aggregated payment costs for *psp* over the given period."""
    start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)

    period_label = f"{period_start.isoformat()}/{period_end.isoformat()}"

    q = select(PaymentCostRecord).where(
        and_(
            PaymentCostRecord.psp == psp,
            PaymentCostRecord.created_at >= start_dt,
            PaymentCostRecord.created_at < end_dt,
        )
    )
    result = await session.execute(q)
    records = result.scalars().all()

    # Aggregate by method
    method_data: dict[str, dict] = {}
    total_volume = Decimal("0")
    total_fees = Decimal("0")

    for rec in records:
        m = rec.payment_method
        if m not in method_data:
            method_data[m] = {"count": 0, "volume": Decimal("0"), "fees": Decimal("0")}
        method_data[m]["count"] += 1
        method_data[m]["volume"] += Decimal(str(rec.gross_amount))
        method_data[m]["fees"] += Decimal(str(rec.fee_amount))
        total_volume += Decimal(str(rec.gross_amount))
        total_fees += Decimal(str(rec.fee_amount))

    by_method: dict[str, MethodCost] = {}
    for method, data in method_data.items():
        count = data["count"]
        volume = data["volume"]
        fees = data["fees"]
        unit_fee = (fees / Decimal(str(count))).quantize(Decimal("0.0001")) if count else None
        rate_pct = (
            (fees / volume * Decimal("100")).quantize(Decimal("0.0001")) if volume > 0 else None
        )
        by_method[method] = MethodCost(
            method=method,
            count=count,
            volume=volume,
            fees=fees,
            unit_fee=unit_fee,
            rate_pct=rate_pct,
        )

    blended_rate = (
        (total_fees / total_volume * Decimal("100")).quantize(Decimal("0.0001"))
        if total_volume > 0
        else Decimal("0")
    )

    summary = PaymentCostSummary(
        psp=psp,
        period=period_label,
        transaction_count=len(records),
        total_volume=total_volume,
        total_fees=total_fees,
        blended_rate=blended_rate,
        by_method=by_method,
    )

    log.info(
        "analytics.payment_costs",
        psp=psp,
        period=period_label,
        transaction_count=len(records),
        total_volume=str(total_volume),
        total_fees=str(total_fees),
    )

    return summary


async def get_cost_comparison(
    session: AsyncSession,
    period_start: date,
    period_end: date,
) -> list[PaymentCostSummary]:
    """Compare costs across all PSPs for the given period."""
    start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc)

    # Get distinct PSPs in the period
    q = (
        select(PaymentCostRecord.psp)
        .where(
            and_(
                PaymentCostRecord.created_at >= start_dt,
                PaymentCostRecord.created_at < end_dt,
            )
        )
        .distinct()
    )
    result = await session.execute(q)
    psps = [row[0] for row in result.all()]

    summaries: list[PaymentCostSummary] = []
    for psp in sorted(psps):
        summary = await calculate_payment_costs(session, psp, period_start, period_end)
        summaries.append(summary)

    return summaries
