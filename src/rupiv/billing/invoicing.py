"""Invoice generation with EU VAT support for Rupiv.ai.

Creates SQLAlchemy ORM ``Invoice`` and ``InvoiceLineItem`` objects,
calculates EU VAT (all 27 member states), and handles B2B reverse charge.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.pricing import LineItem
from rupiv.models.invoice import (
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    TaxType,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# EU VAT standard rates (all 27 member states, 2026 rates)
# ---------------------------------------------------------------------------

EU_VAT_RATES: dict[str, Decimal] = {
    "AT": Decimal("20"),     # Austria
    "BE": Decimal("21"),     # Belgium
    "BG": Decimal("20"),     # Bulgaria
    "HR": Decimal("25"),     # Croatia
    "CY": Decimal("19"),     # Cyprus
    "CZ": Decimal("21"),     # Czech Republic
    "DK": Decimal("25"),     # Denmark
    "EE": Decimal("22"),     # Estonia
    "FI": Decimal("25.5"),   # Finland
    "FR": Decimal("20"),     # France
    "DE": Decimal("19"),     # Germany
    "GR": Decimal("24"),     # Greece
    "HU": Decimal("27"),     # Hungary
    "IE": Decimal("23"),     # Ireland
    "IT": Decimal("22"),     # Italy
    "LV": Decimal("21"),     # Latvia
    "LT": Decimal("21"),     # Lithuania
    "LU": Decimal("17"),     # Luxembourg
    "MT": Decimal("18"),     # Malta
    "NL": Decimal("21"),     # Netherlands
    "PL": Decimal("23"),     # Poland
    "PT": Decimal("23"),     # Portugal
    "RO": Decimal("19"),     # Romania
    "SK": Decimal("23"),     # Slovakia
    "SI": Decimal("22"),     # Slovenia
    "ES": Decimal("21"),     # Spain
    "SE": Decimal("25"),     # Sweden
}

_TWO_PLACES = Decimal("0.01")
_HUNDRED = Decimal("100")

# Rupiv B.V. is based in the Netherlands.
SELLER_COUNTRY = "NL"


# ---------------------------------------------------------------------------
# VAT calculation
# ---------------------------------------------------------------------------


def calculate_vat(
    country_code: str,
    is_business: bool,
    subtotal: Decimal,
    seller_country: str = SELLER_COUNTRY,
) -> tuple[Decimal, Decimal, TaxType | None]:
    """Compute VAT for a transaction.

    Rules implemented:
    1. Non-EU buyer              -> no VAT             (``None``)
    2. EU B2B cross-border       -> reverse charge      (``TaxType.REVERSE_CHARGE``)
    3. EU B2C or domestic B2B/B2C -> standard rate of
       *buyer* country (B2C cross-border / OSS) or
       *seller* country (domestic)

    Args:
        country_code: ISO 3166-1 alpha-2 code of the buyer.
        is_business: Whether the buyer is a VAT-registered business.
        subtotal: Invoice subtotal before tax.
        seller_country: ISO 3166-1 alpha-2 code of the seller.

    Returns:
        ``(tax_amount, tax_rate, tax_type)`` where *tax_rate* is as a
        percentage (e.g. ``Decimal("21")`` for 21 %) and *tax_type* is
        ``None`` when outside the EU.
    """
    buyer_in_eu = country_code in EU_VAT_RATES

    if not buyer_in_eu:
        return Decimal("0"), Decimal("0"), None

    cross_border = country_code != seller_country

    if is_business and cross_border:
        # EU B2B cross-border: reverse charge — zero-rated
        return Decimal("0"), Decimal("0"), TaxType.REVERSE_CHARGE

    # EU B2C cross-border (OSS) or domestic sale
    if cross_border:
        rate = EU_VAT_RATES[country_code]
    else:
        rate = EU_VAT_RATES[seller_country]

    tax = (subtotal * rate / _HUNDRED).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return tax, rate, TaxType.STANDARD


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
