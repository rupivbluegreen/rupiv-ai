"""Invoice generation worker — runs at the end of each billing period."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from rupiv.billing.invoicing import TaxInfo, generate_invoice
from rupiv.billing.pricing import PricingEngine

log = structlog.get_logger(__name__)


async def generate_period_invoices(period_end: datetime) -> list[str]:
    """Find all active subscriptions and generate invoices for the
    completed billing period ending at *period_end*.

    Returns:
        List of generated invoice IDs.

    High-level flow:
    1. Query PostgreSQL for active subscriptions whose current period
       ended at or before *period_end*.
    2. For each subscription, aggregate events from ClickHouse.
    3. Run the pricing engine to produce line items.
    4. Generate an invoice (with VAT) and persist it.
    """
    log.info("worker.invoice.start", period_end=period_end.isoformat())

    # TODO: Replace with actual DB query
    # async with get_db_session() as session:
    #     subscriptions = await session.execute(
    #         select(Subscription)
    #         .where(Subscription.status == "active")
    #         .where(Subscription.current_period_end <= period_end)
    #     )

    subscriptions: list[Any] = []  # stub
    engine = PricingEngine()
    invoice_ids: list[str] = []

    for subscription in subscriptions:
        try:
            # TODO: Aggregate events from ClickHouse for this subscription
            events: dict[str, Any] = {}

            line_items = engine.calculate_line_items(subscription, events)

            if not line_items:
                log.info(
                    "worker.invoice.skip_empty",
                    subscription_id=subscription.subscription_id,
                )
                continue

            # TODO: Fetch real tax info from customer record
            tax_info = TaxInfo(
                country_code=getattr(subscription, "country_code", "NL"),
                is_business=getattr(subscription, "is_business", False),
            )

            invoice = await generate_invoice(subscription, line_items, tax_info)
            invoice_ids.append(invoice.invoice_id)

            log.info(
                "worker.invoice.generated",
                subscription_id=subscription.subscription_id,
                invoice_id=invoice.invoice_id,
            )
        except Exception:
            log.exception(
                "worker.invoice.failed",
                subscription_id=getattr(subscription, "subscription_id", "unknown"),
            )

    log.info(
        "worker.invoice.done",
        period_end=period_end.isoformat(),
        invoice_count=len(invoice_ids),
    )
    return invoice_ids
