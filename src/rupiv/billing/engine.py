"""Billing engine orchestrator for Rupiv.ai.

``run_billing_cycle`` is the top-level function invoked by the
``invoice_worker`` at the end of each billing period.  It ties together
ClickHouse aggregation, the pricing engine, and invoice generation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog
from clickhouse_connect.driver.asyncclient import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.aggregation import aggregate_outcomes, aggregate_usage
from rupiv.billing.invoicing import generate_invoice
from rupiv.billing.pricing import PricingEngine, PricingModel
from rupiv.models.invoice import Invoice
from rupiv.models.plan import PricingModel as ORMPricingModel

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


async def _aggregate_for_rule(
    clickhouse_client: AsyncClient,
    customer_id: str,
    rule: Any,
    period_start: Any,
    period_end: Any,
) -> dict[str, Any]:
    """Run the appropriate ClickHouse aggregation for a single pricing rule.

    Returns a dict with ``"quantity"`` and/or ``"outcomes"`` keys depending
    on the pricing model.
    """
    model_val = getattr(rule, "pricing_model", None)
    if hasattr(model_val, "value"):
        model_val = model_val.value

    metric: str = getattr(rule, "metric", None) or ""
    customer_id_str = str(customer_id)

    result: dict[str, Any] = {}

    if model_val in (PricingModel.USAGE.value, PricingModel.TIERED.value):
        qty = await aggregate_usage(
            client=clickhouse_client,
            customer_id=customer_id_str,
            metric=metric,
            period_start=period_start,
            period_end=period_end,
        )
        result["quantity"] = qty

    elif model_val == PricingModel.OUTCOME.value:
        outcomes = await aggregate_outcomes(
            client=clickhouse_client,
            customer_id=customer_id_str,
            metric=metric,
            period_start=period_start,
            period_end=period_end,
        )
        result["outcomes"] = outcomes

    # Flat rules need no aggregation.
    return result


async def run_billing_cycle(
    session: AsyncSession,
    clickhouse_client: AsyncClient,
    subscription: Any,
) -> Invoice:
    """Execute a full billing cycle for a single subscription.

    Steps:
        1. Read the subscription's plan and pricing rules (assumed eagerly
           loaded via ``selectin``).
        2. For each pricing rule, aggregate usage/outcome data from
           ClickHouse.
        3. Pass the aggregated data to the pricing engine to compute line
           items.
        4. Generate an Invoice ORM object with line items and EU VAT.
        5. Return the persisted Invoice.

    Args:
        session: An active SQLAlchemy async session.
        clickhouse_client: An async ClickHouse client.
        subscription: An ORM ``Subscription`` with eagerly loaded
            ``plan.pricing_rules`` and ``customer``.

    Returns:
        The generated ``Invoice`` ORM object (flushed, status=draft).
    """
    plan = subscription.plan
    customer = subscription.customer
    period_start = subscription.current_period_start
    period_end = subscription.current_period_end
    period_label = period_start.strftime("%Y-%m")

    log.info(
        "billing.cycle_start",
        subscription_id=str(subscription.id),
        customer_id=str(customer.id),
        plan_id=str(plan.id),
        period=period_label,
    )

    # -- Step 2: aggregate ClickHouse data per metric -----------------------
    aggregated: dict[str, dict[str, Any]] = {}

    for rule in plan.pricing_rules:
        metric: str = getattr(rule, "metric", None) or ""
        if metric and metric not in aggregated:
            data = await _aggregate_for_rule(
                clickhouse_client=clickhouse_client,
                customer_id=str(customer.id),
                rule=rule,
                period_start=period_start,
                period_end=period_end,
            )
            aggregated[metric] = data
        elif not metric:
            # Flat rules don't need a metric key in aggregated
            aggregated.setdefault("", {})

    log.debug(
        "billing.aggregation_complete",
        subscription_id=str(subscription.id),
        metrics=list(aggregated.keys()),
    )

    # -- Step 3: pricing engine ---------------------------------------------
    engine = PricingEngine()
    line_items = engine.calculate_line_items(
        pricing_rules=list(plan.pricing_rules),
        aggregated=aggregated,
        period=period_label,
    )

    if not line_items:
        log.warning(
            "billing.no_line_items",
            subscription_id=str(subscription.id),
            period=period_label,
        )

    # -- Step 4: generate invoice -------------------------------------------
    currency = getattr(plan, "currency", "EUR") or "EUR"
    invoice = await generate_invoice(
        session=session,
        subscription=subscription,
        line_items=line_items,
        currency=currency,
    )

    log.info(
        "billing.cycle_complete",
        subscription_id=str(subscription.id),
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        total=str(invoice.total),
    )
    return invoice
