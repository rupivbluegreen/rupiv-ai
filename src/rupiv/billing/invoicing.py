"""Invoice generation with EU VAT support for Rupiv.ai.

Creates SQLAlchemy ORM ``Invoice`` and ``InvoiceLineItem`` objects,
calculates EU VAT (all 27 member states), and handles B2B reverse charge.

VAT logic lives in :mod:`rupiv.tax` — this module imports
:func:`~rupiv.tax.vat_engine.calculate_vat` from there.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.pricing import LineItem
from rupiv.models.invoice import (
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
)
from rupiv.tax.vat_engine import calculate_vat  # noqa: F401 — re-exported for back-compat

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_TWO_PLACES = Decimal("0.01")
_HUNDRED = Decimal("100")


# ---------------------------------------------------------------------------
# Invoice number generation
# ---------------------------------------------------------------------------


def _generate_invoice_number(period_start: datetime) -> str:
    """Generate a unique invoice number in format ``INV-YYYYMM-XXXXX``.

    The random suffix uses 5 uppercase hex characters for uniqueness.
    """
    ym = period_start.strftime("%Y%m")
    suffix = secrets.token_hex(3)[:5].upper()
    return f"INV-{ym}-{suffix}"


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------


async def generate_invoice(
    session: AsyncSession,
    subscription: Any,
    line_items: list[LineItem],
    currency: str = "EUR",
) -> Invoice:
    """Create an Invoice ORM object with its line items.

    Args:
        session: An active SQLAlchemy async session.
        subscription: An ORM ``Subscription`` with eagerly loaded
            ``customer`` and ``plan`` relationships.
        line_items: Calculated ``LineItem`` dataclasses from the pricing
            engine.
        currency: ISO 4217 currency code (default ``"EUR"``).

    Returns:
        A persisted (flushed) ``Invoice`` ORM object in ``draft`` status.
    """
    customer = subscription.customer
    period_start: datetime = subscription.current_period_start
    period_end: datetime = subscription.current_period_end
    due_date = (period_end + timedelta(days=30)).date()

    # -- Subtotal --
    subtotal = sum(
        (item.amount for item in line_items),
        Decimal("0"),
    ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    # -- VAT --
    tax_amount, tax_rate, tax_type = calculate_vat(
        country_code=customer.country_code,
        is_business=customer.is_business,
        subtotal=subtotal,
    )

    total = (subtotal + tax_amount).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    # -- Invoice ORM --
    invoice = Invoice(
        customer_id=subscription.customer_id,
        subscription_id=subscription.id,
        invoice_number=_generate_invoice_number(period_start),
        status=InvoiceStatus.DRAFT,
        subtotal=subtotal,
        tax_amount=tax_amount,
        tax_rate=tax_rate / _HUNDRED if tax_rate else None,
        tax_type=tax_type,
        total=total,
        currency=currency,
        period_start=period_start,
        period_end=period_end,
        due_date=due_date,
    )
    session.add(invoice)
    # Flush to get the id assigned before creating line items.
    await session.flush()

    # -- Line item ORMs --
    for item in line_items:
        orm_item = InvoiceLineItem(
            invoice_id=invoice.id,
            description=item.description,
            quantity=item.quantity,
            unit_amount=item.unit_amount,
            amount=item.amount,
            metric=item.metric,
            pricing_model=item.pricing_model.value,
        )
        session.add(orm_item)

    await session.flush()

    log.info(
        "invoice.generated",
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        customer_id=str(subscription.customer_id),
        subtotal=str(subtotal),
        tax_amount=str(tax_amount),
        tax_type=tax_type.value if tax_type else "none",
        total=str(total),
    )
    return invoice
