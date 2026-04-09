"""Quote generation — build quotes from plan templates with pricing rules."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.customer import Customer
from rupiv.models.plan import Plan, PricingModel
from rupiv.models.quote import Quote, QuoteLineItem, QuoteStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


async def build_quote(
    session: AsyncSession,
    customer_id: uuid.UUID,
    plan_id: uuid.UUID,
    overrides: dict[str, Decimal] | None = None,
    discount_pct: Decimal = Decimal("0"),
    term_months: int = 12,
    expires_in_days: int = 30,
) -> Quote:
    """Build a quote from a plan's pricing rules.

    Args:
        session: Async database session.
        customer_id: Customer to quote for.
        plan_id: Plan to base the quote on.
        overrides: Estimated quantities keyed by metric name
                   (e.g. ``{"ticket_resolved": Decimal("5000")}``).
        discount_pct: Discount as a percentage (0-100).
        term_months: Contract term length in months.
        expires_in_days: Days until the quote expires.

    Returns:
        The flushed Quote with line items attached.

    Raises:
        ValueError: If customer or plan is not found.
    """
    overrides = overrides or {}

    # Load customer
    result = await session.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise ValueError(f"Customer {customer_id} not found")

    # Load plan (pricing_rules come via selectin)
    result = await session.execute(
        select(Plan).where(Plan.id == plan_id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found")

    now = datetime.now(tz=timezone.utc)

    quote = Quote(
        customer_id=customer_id,
        plan_id=plan_id,
        status=QuoteStatus.DRAFT,
        discount_pct=discount_pct,
        currency=plan.currency,
        term_months=term_months,
        expires_at=now + timedelta(days=expires_in_days),
    )
    session.add(quote)
    await session.flush()

    # Build line items from pricing rules
    monthly_total = Decimal("0")
    for rule in plan.pricing_rules:
        unit_amount = Decimal("0")
        estimated_qty = Decimal("0")
        estimated_amount = Decimal("0")
        description = f"{rule.pricing_model.value} charge"

        if rule.pricing_model == PricingModel.FLAT:
            unit_amount = Decimal(str(rule.flat_amount or 0))
            estimated_qty = Decimal("1")
            estimated_amount = unit_amount
            description = f"Flat fee — {plan.name}"
        elif rule.pricing_model in (PricingModel.USAGE, PricingModel.OUTCOME):
            unit_amount = Decimal(str(rule.unit_amount or 0))
            metric_key = rule.metric or ""
            estimated_qty = overrides.get(metric_key, Decimal("0"))
            estimated_amount = unit_amount * estimated_qty
            description = f"{rule.pricing_model.value.title()} — {metric_key}"
        elif rule.pricing_model == PricingModel.HYBRID:
            # Hybrid: flat base + per-unit component
            flat = Decimal(str(rule.flat_amount or 0))
            per_unit = Decimal(str(rule.unit_amount or 0))
            metric_key = rule.metric or ""
            estimated_qty = overrides.get(metric_key, Decimal("0"))
            unit_amount = per_unit
            estimated_amount = flat + (per_unit * estimated_qty)
            description = f"Hybrid — {metric_key} (base {flat})"
        elif rule.pricing_model == PricingModel.TIERED:
            unit_amount = Decimal(str(rule.unit_amount or 0))
            metric_key = rule.metric or ""
            estimated_qty = overrides.get(metric_key, Decimal("0"))
            estimated_amount = unit_amount * estimated_qty
            description = f"Tiered — {metric_key}"
        elif rule.pricing_model == PricingModel.CREDIT:
            unit_amount = Decimal(str(rule.unit_amount or 0))
            metric_key = rule.metric or ""
            estimated_qty = overrides.get(metric_key, Decimal("0"))
            estimated_amount = unit_amount * estimated_qty
            description = f"Credit — {metric_key}"

        line_item = QuoteLineItem(
            quote_id=quote.id,
            description=description,
            pricing_model=rule.pricing_model.value,
            metric=rule.metric,
            unit_amount=unit_amount,
            estimated_quantity=estimated_qty,
            estimated_amount=estimated_amount,
        )
        session.add(line_item)
        monthly_total += estimated_amount

    # Apply discount
    discount_factor = Decimal("1") - (discount_pct / Decimal("100"))
    estimated_monthly = monthly_total * discount_factor
    estimated_total = estimated_monthly * Decimal(str(term_months))

    quote.estimated_monthly = estimated_monthly
    quote.estimated_total = estimated_total

    await session.flush()
    await session.refresh(quote)

    logger.info(
        "quote_built",
        quote_id=str(quote.id),
        customer_id=str(customer_id),
        plan_id=str(plan_id),
        estimated_monthly=str(estimated_monthly),
        estimated_total=str(estimated_total),
    )

    return quote


async def recalculate_quote(
    session: AsyncSession,
    quote_id: uuid.UUID,
    new_overrides: dict[str, Decimal],
) -> Quote:
    """Recalculate a quote's estimates with new override quantities.

    Args:
        session: Async database session.
        quote_id: Quote to recalculate.
        new_overrides: Updated estimated quantities keyed by metric name.

    Returns:
        The updated Quote.

    Raises:
        ValueError: If quote is not found or not in a recalculable state.
    """
    result = await session.execute(
        select(Quote).where(Quote.id == quote_id)
    )
    quote = result.scalar_one_or_none()
    if quote is None:
        raise ValueError(f"Quote {quote_id} not found")

    if quote.status not in (QuoteStatus.DRAFT, QuoteStatus.SENT):
        raise ValueError(f"Cannot recalculate quote in status {quote.status.value}")

    monthly_total = Decimal("0")
    for item in quote.line_items:
        if item.metric and item.metric in new_overrides:
            new_qty = new_overrides[item.metric]
            item.estimated_quantity = new_qty
            item.estimated_amount = item.unit_amount * new_qty
        monthly_total += Decimal(str(item.estimated_amount))

    discount_factor = Decimal("1") - (Decimal(str(quote.discount_pct)) / Decimal("100"))
    quote.estimated_monthly = monthly_total * discount_factor
    quote.estimated_total = quote.estimated_monthly * Decimal(str(quote.term_months))

    await session.flush()
    await session.refresh(quote)

    logger.info(
        "quote_recalculated",
        quote_id=str(quote.id),
        estimated_monthly=str(quote.estimated_monthly),
        estimated_total=str(quote.estimated_total),
    )

    return quote
