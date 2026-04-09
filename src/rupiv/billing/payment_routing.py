"""Payment routing integration — wraps routing_optimizer for billing use."""

from __future__ import annotations

from decimal import Decimal

import structlog

from rupiv.analytics.routing_optimizer import (
    DEFAULT_PSP,
    PSP_FEE_SCHEDULES,
    PSPRoute,
    STRIPE_PREFERRED_COUNTRIES,
    find_cheapest_route,
)

log = structlog.get_logger(__name__)


def route_payment(
    amount: Decimal,
    currency: str,
    country_code: str,
    preferred_method: str | None = None,
) -> PSPRoute:
    """Select the cheapest PSP route for a payment.

    Calls :func:`find_cheapest_route` and falls back to Mollie if no
    better option is found or the result is invalid.
    """
    try:
        route = find_cheapest_route(
            amount=amount,
            currency=currency,
            country_code=country_code,
            payment_method=preferred_method,
        )
    except Exception:
        log.exception(
            "routing.fallback_to_default",
            amount=str(amount),
            currency=currency,
            country_code=country_code,
        )
        # Fall back to Mollie card
        method = preferred_method or "card"
        schedule = PSP_FEE_SCHEDULES[DEFAULT_PSP].get(
            method, {"fixed": Decimal("0.25"), "rate_pct": Decimal("2.9")}
        )
        fixed = schedule["fixed"]
        rate_pct = schedule["rate_pct"]
        fee = (fixed + amount * rate_pct / Decimal("100")).quantize(Decimal("0.0001"))
        eff_rate = (
            (fee / amount * Decimal("100")).quantize(Decimal("0.0001"))
            if amount > 0
            else Decimal("0")
        )
        return PSPRoute(
            psp=DEFAULT_PSP,
            method=method,
            estimated_fee=fee,
            estimated_rate=eff_rate,
            reason=f"Fallback to {DEFAULT_PSP} due to routing error",
        )

    # If the selected PSP is not Mollie and Mollie would be equally cheap,
    # prefer Mollie as the established provider — but not for countries
    # where Stripe is the preferred regional PSP.
    if route.psp != DEFAULT_PSP and country_code not in STRIPE_PREFERRED_COUNTRIES:
        mollie_methods = PSP_FEE_SCHEDULES.get(DEFAULT_PSP, {})
        if route.method in mollie_methods:
            mollie_schedule = mollie_methods[route.method]
            mollie_fee = (
                mollie_schedule["fixed"]
                + amount * mollie_schedule["rate_pct"] / Decimal("100")
            ).quantize(Decimal("0.0001"))
            if mollie_fee <= route.estimated_fee:
                log.info(
                    "routing.prefer_default",
                    default_psp=DEFAULT_PSP,
                    method=route.method,
                    mollie_fee=str(mollie_fee),
                    alt_fee=str(route.estimated_fee),
                )
                return PSPRoute(
                    psp=DEFAULT_PSP,
                    method=route.method,
                    estimated_fee=mollie_fee,
                    estimated_rate=(
                        (mollie_fee / amount * Decimal("100")).quantize(Decimal("0.0001"))
                        if amount > 0
                        else Decimal("0")
                    ),
                    reason=f"{DEFAULT_PSP} matches best price for {route.method}",
                )

    log.info(
        "routing.payment_routed",
        psp=route.psp,
        method=route.method,
        amount=str(amount),
        estimated_fee=str(route.estimated_fee),
    )

    return route
