"""Invoice generation with EU VAT support for Rupiv.ai."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

import structlog

from rupiv.billing.pricing import LineItem

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# EU VAT standard rates (2026 approximations — keep up-to-date)
# ---------------------------------------------------------------------------

EU_VAT_RATES: dict[str, Decimal] = {
    "AT": Decimal("20"),
    "BE": Decimal("21"),
    "BG": Decimal("20"),
    "HR": Decimal("25"),
    "CY": Decimal("19"),
    "CZ": Decimal("21"),
    "DK": Decimal("25"),
    "EE": Decimal("22"),
    "FI": Decimal("25.5"),
    "FR": Decimal("20"),
    "DE": Decimal("19"),
    "GR": Decimal("24"),
    "HU": Decimal("27"),
    "IE": Decimal("23"),
    "IT": Decimal("22"),
    "LV": Decimal("21"),
    "LT": Decimal("21"),
    "LU": Decimal("17"),
    "MT": Decimal("18"),
    "NL": Decimal("21"),
    "PL": Decimal("23"),
    "PT": Decimal("23"),
    "RO": Decimal("19"),
    "SK": Decimal("23"),
    "SI": Decimal("22"),
    "ES": Decimal("21"),
    "SE": Decimal("25"),
}

_TWO_PLACES = Decimal("0.01")
_HUNDRED = Decimal("100")

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaxInfo:
    """Tax context for invoice generation."""

    country_code: str
    is_business: bool
    vat_number: str | None = None
    seller_country: str = "NL"  # Rupiv is based in the Netherlands


@dataclass
class Invoice:
    """Generated invoice."""

    invoice_id: str
    customer_id: str
    subscription_id: str
    line_items: list[LineItem]
    subtotal: Decimal
    tax_amount: Decimal
    tax_type: str  # "standard" | "reverse_charge" | "none"
    total: Decimal
    currency: str
    issued_at: datetime
    status: str = "draft"
    metadata: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# VAT calculation
# ---------------------------------------------------------------------------


def calculate_vat(
    country_code: str,
    is_business: bool,
    subtotal: Decimal,
    seller_country: str = "NL",
) -> tuple[Decimal, str]:
    """Compute VAT for a transaction.

    Rules implemented:
    1. Non-EU buyer              -> no VAT              (``"none"``)
    2. EU B2B cross-border       -> reverse charge       (``"reverse_charge"``)
    3. EU B2C or domestic B2B    -> standard rate of
       *buyer* country (B2C) or *seller* country (domestic)

    Returns:
        ``(tax_amount, tax_type)`` where *tax_type* is one of
        ``"standard"``, ``"reverse_charge"``, ``"none"``.
    """
    buyer_in_eu = country_code in EU_VAT_RATES

    if not buyer_in_eu:
        # Outside EU — no VAT
        return Decimal("0"), "none"

    cross_border = country_code != seller_country

    if is_business and cross_border:
        # EU B2B cross-border: reverse charge, zero-rated
        return Decimal("0"), "reverse_charge"

    # EU B2C, or domestic (same-country) sale
    if cross_border:
        # B2C cross-border: apply buyer country rate (OSS)
        rate = EU_VAT_RATES[country_code]
    else:
        # Domestic: apply seller country rate
        rate = EU_VAT_RATES[seller_country]

    tax = (subtotal * rate / _HUNDRED).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return tax, "standard"


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------


async def generate_invoice(
    subscription: object,
    line_items: list[LineItem],
    tax_info: TaxInfo,
    currency: str = "EUR",
) -> Invoice:
    """Create an invoice from computed line items and tax info.

    The *subscription* object must expose ``subscription_id`` and
    ``customer_id`` attributes.

    Returns:
        A fully populated ``Invoice`` in ``"draft"`` status.
    """
    subtotal = sum(
        (item.amount for item in line_items),
        Decimal("0"),
    ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    tax_amount, tax_type = calculate_vat(
        country_code=tax_info.country_code,
        is_business=tax_info.is_business,
        subtotal=subtotal,
        seller_country=tax_info.seller_country,
    )

    total = (subtotal + tax_amount).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    invoice = Invoice(
        invoice_id=str(uuid4()),
        customer_id=getattr(subscription, "customer_id", ""),
        subscription_id=getattr(subscription, "subscription_id", ""),
        line_items=line_items,
        subtotal=subtotal,
        tax_amount=tax_amount,
        tax_type=tax_type,
        total=total,
        currency=currency,
        issued_at=datetime.now(timezone.utc),
    )

    log.info(
        "invoice.generated",
        invoice_id=invoice.invoice_id,
        subtotal=str(subtotal),
        tax_amount=str(tax_amount),
        tax_type=tax_type,
        total=str(total),
    )
    return invoice
