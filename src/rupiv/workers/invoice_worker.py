"""Invoice generation worker — finds due subscriptions and generates invoices.

Run as a standalone process::

    python -m rupiv.workers.invoice_worker
"""

from __future__ import annotations

import asyncio
import signal
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.billing.aggregation import aggregate_outcomes, aggregate_usage
from rupiv.billing.invoicing import Invoice as InvoiceDomain
from rupiv.billing.invoicing import TaxInfo, generate_invoice
from rupiv.billing.pricing import (
    PricingEngine,
    PricingModel,
    TierBracket,
)
from rupiv.billing.pricing import (
    PricingRule as PricingRuleDomain,
)
from rupiv.billing.pricing import (
    Subscription as SubscriptionDomain,
)
from rupiv.config import get_settings
from rupiv.db import _get_session_factory
from rupiv.models.customer import Customer
from rupiv.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus
from rupiv.models.plan import PricingModel as PlanPricingModel
from rupiv.models.plan import PricingRule
from rupiv.models.subscription import Subscription, SubscriptionStatus

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

INVOICE_CHANNEL = "rupiv:invoices:trigger"
POLL_INTERVAL_SECONDS: int = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_pricing_rule_domain(rule: PricingRule) -> PricingRuleDomain:
    """Convert a SQLAlchemy PricingRule to the pricing engine domain object."""
    tiers: list[TierBracket] | None = None
    if rule.tiers:
        raw_tiers = rule.tiers if isinstance(rule.tiers, list) else rule.tiers.get("brackets", [])
        tiers = [
            TierBracket(
                up_to=Decimal(str(t["up_to"])) if t.get("up_to") is not None else None,
                unit_amount=Decimal(str(t["unit_amount"])),
            )
            for t in raw_tiers
        ]

    outcome_rules = rule.outcome_rules or {}

    return PricingRuleDomain(
        model=PricingModel(rule.pricing_model.value),
        description=f"{rule.pricing_model.value} charge for {rule.metric or 'base'}",
        metric=rule.metric,
        amount=Decimal(str(rule.flat_amount)) if rule.flat_amount is not None else None,
        unit_amount=Decimal(str(rule.unit_amount)) if rule.unit_amount is not None else None,
        price_per_outcome=Decimal(str(rule.unit_amount))
        if (rule.pricing_model == PlanPricingModel.OUTCOME and rule.unit_amount is not None)
        else None,
        billable_when=outcome_rules.get("billable_when"),
        cap_per_period=Decimal(str(outcome_rules["cap_per_period"]))
        if outcome_rules.get("cap_per_period")
        else None,
        tiers=tiers,
    )


async def _aggregate_for_subscription(
    subscription: Subscription,
    pricing_rules: list[PricingRuleDomain],
) -> dict[str, Any]:
    """Build the events dict expected by PricingEngine.calculate_line_items.

    Queries ClickHouse for usage/outcome data per metric in the subscription
    period.
    """
    period_start = subscription.current_period_start
    period_end = subscription.current_period_end
    customer_id = str(subscription.customer_id)
    period_label = period_start.strftime("%Y-%m")

    events: dict[str, Any] = {"period": period_label}

    for rule in pricing_rules:
        if rule.metric is None:
            continue

        try:
            if rule.model in (PricingModel.USAGE, PricingModel.TIERED):
                qty = await aggregate_usage(
                    customer_id=customer_id,
                    metric=rule.metric,
                    period_start=period_start,
                    period_end=period_end,
                )
                events[rule.metric] = {"quantity": qty}

            elif rule.model == PricingModel.OUTCOME:
                outcomes = await aggregate_outcomes(
                    customer_id=customer_id,
                    metric=rule.metric,
                    period_start=period_start,
                    period_end=period_end,
                )
                events[rule.metric] = {"outcomes": outcomes}
        except Exception:
            log.error(
                "invoice_worker.aggregation_failed",
                customer_id=customer_id,
                metric=rule.metric,
                exc_info=True,
            )
            events[rule.metric] = {"quantity": Decimal("0"), "outcomes": []}

    return events


def _next_period_end(current_end: datetime, interval_months: int = 1) -> datetime:
    """Advance period end by the billing interval (default 1 month)."""
    year = current_end.year
    month = current_end.month + interval_months
    while month > 12:
        month -= 12
        year += 1
    # Preserve the day-of-month, clamping to last day
    import calendar

    max_day = calendar.monthrange(year, month)[1]
    day = min(current_end.day, max_day)
    return current_end.replace(year=year, month=month, day=day)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


async def generate_period_invoices(session: AsyncSession) -> list[str]:
    """Find all active subscriptions past their period end and invoice them.

    Returns:
        List of generated invoice IDs (as strings).
    """
    now = datetime.now(UTC)
    log.info("invoice_worker.scan_start", as_of=now.isoformat())

    stmt = (
        select(Subscription)
        .where(Subscription.status == SubscriptionStatus.ACTIVE)
        .where(Subscription.current_period_end <= now)
        .options(
            selectinload(Subscription.customer),
            selectinload(Subscription.plan),
        )
    )
    result = await session.execute(stmt)
    subscriptions: list[Subscription] = list(result.scalars().all())

    if not subscriptions:
        log.info("invoice_worker.no_due_subscriptions")
        return []

    log.info("invoice_worker.due_subscriptions_found", count=len(subscriptions))

    engine = PricingEngine()
    invoice_ids: list[str] = []

    for sub in subscriptions:
        try:
            # Load pricing rules from the plan
            plan = sub.plan
            if not plan or not plan.pricing_rules:
                log.warning(
                    "invoice_worker.no_pricing_rules",
                    subscription_id=str(sub.id),
                    plan_id=str(sub.plan_id),
                )
                continue

            domain_rules = [_build_pricing_rule_domain(r) for r in plan.pricing_rules]

            sub_domain = SubscriptionDomain(
                subscription_id=str(sub.id),
                customer_id=str(sub.customer_id),
                pricing_rules=domain_rules,
            )

            # Aggregate events from ClickHouse
            events = await _aggregate_for_subscription(sub, domain_rules)

            # Calculate line items
            line_items = engine.calculate_line_items(sub_domain, events)
            if not line_items:
                log.info(
                    "invoice_worker.skip_empty",
                    subscription_id=str(sub.id),
                )
                # Still advance the period so we don't re-check next time
                await _advance_subscription_period(session, sub)
                continue

            # Determine tax info from customer
            customer: Customer = sub.customer
            tax_info = TaxInfo(
                country_code=customer.country_code,
                is_business=customer.is_business,
                vat_number=customer.vat_number,
            )

            # Generate the domain invoice
            domain_invoice: InvoiceDomain = await generate_invoice(
                sub_domain, line_items, tax_info,
            )

            # Persist the invoice to PostgreSQL
            invoice_number = f"INV-{domain_invoice.invoice_id[:8].upper()}"
            db_invoice = Invoice(
                customer_id=sub.customer_id,
                subscription_id=sub.id,
                invoice_number=invoice_number,
                status=InvoiceStatus.OPEN,
                subtotal=domain_invoice.subtotal,
                tax_amount=domain_invoice.tax_amount,
                total=domain_invoice.total,
                currency=domain_invoice.currency,
                tax_type=domain_invoice.tax_type if domain_invoice.tax_type != "none" else None,
                period_start=sub.current_period_start,
                period_end=sub.current_period_end,
                due_date=(now + timedelta(days=30)).date(),
            )
            session.add(db_invoice)
            await session.flush()

            # Persist line items
            for li in line_items:
                db_line = InvoiceLineItem(
                    invoice_id=db_invoice.id,
                    description=li.description,
                    quantity=li.quantity,
                    unit_amount=li.unit_amount,
                    amount=li.amount,
                    metric=li.metric,
                    pricing_model=li.pricing_model.value,
                )
                session.add(db_line)

            # Advance the subscription period
            await _advance_subscription_period(session, sub)

            invoice_ids.append(str(db_invoice.id))

            log.info(
                "invoice_worker.invoice_generated",
                subscription_id=str(sub.id),
                invoice_id=str(db_invoice.id),
                total=str(domain_invoice.total),
            )

        except Exception:
            log.error(
                "invoice_worker.subscription_failed",
                subscription_id=str(sub.id),
                exc_info=True,
            )

    log.info("invoice_worker.scan_complete", invoice_count=len(invoice_ids))
    return invoice_ids


async def _advance_subscription_period(
    session: AsyncSession,
    sub: Subscription,
) -> None:
    """Move the subscription's billing window forward by one interval."""
    new_start = sub.current_period_end
    new_end = _next_period_end(new_start)

    await session.execute(
        update(Subscription)
        .where(Subscription.id == sub.id)
        .values(
            current_period_start=new_start,
            current_period_end=new_end,
        ),
    )
    log.info(
        "invoice_worker.period_advanced",
        subscription_id=str(sub.id),
        new_start=new_start.isoformat(),
        new_end=new_end.isoformat(),
    )


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


class InvoiceWorker:
    """Async worker that periodically generates invoices for due subscriptions.

    Can also be triggered immediately via Redis pub/sub on the
    ``rupiv:invoices:trigger`` channel.
    """

    def __init__(self) -> None:
        self._shutdown: bool = False

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        sig_name = signal.Signals(sig).name
        log.info("invoice_worker.signal_received", signal=sig_name)
        self._shutdown = True

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    async def run(self) -> None:
        """Run the invoice worker loop.

        Listens for pub/sub triggers and also polls on a fixed interval.
        """
        import redis.asyncio as aioredis

        self._install_signal_handlers()
        settings = get_settings()

        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.REDIS_URL,
            decode_responses=True,
        )
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(INVOICE_CHANNEL)

        session_factory = _get_session_factory()

        log.info(
            "invoice_worker.started",
            channel=INVOICE_CHANNEL,
            poll_interval=POLL_INTERVAL_SECONDS,
        )

        try:
            last_poll = 0.0
            while not self._shutdown:
                # Check for pub/sub trigger (non-blocking with short timeout)
                try:
                    message = await asyncio.wait_for(
                        pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0,
                    )
                except TimeoutError:
                    message = None

                triggered = message is not None and message.get("type") == "message"
                elapsed = asyncio.get_event_loop().time() - last_poll

                if triggered or elapsed >= POLL_INTERVAL_SECONDS:
                    if triggered:
                        log.info("invoice_worker.triggered_by_pubsub")

                    async with session_factory() as session:
                        try:
                            ids = await generate_period_invoices(session)
                            await session.commit()
                            if ids:
                                log.info("invoice_worker.cycle_complete", invoice_count=len(ids))
                        except Exception:
                            await session.rollback()
                            log.error("invoice_worker.cycle_failed", exc_info=True)

                    last_poll = asyncio.get_event_loop().time()

        finally:
            await pubsub.unsubscribe(INVOICE_CHANNEL)
            await pubsub.aclose()
            await redis_client.aclose()
            log.info("invoice_worker.shutdown_complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``python -m rupiv.workers.invoice_worker``."""
    log.info("invoice_worker.starting")
    worker = InvoiceWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        log.info("invoice_worker.interrupted")


if __name__ == "__main__":
    main()
