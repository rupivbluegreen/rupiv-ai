"""Core EU VAT calculation engine.

Handles standard VAT, B2B reverse charge, and B2C cross-border (OSS)
scenarios for all 27 EU member states.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import structlog

from rupiv.models.invoice import TaxType
from rupiv.tax.rates import EU_VAT_RATES, SELLER_COUNTRY

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_TWO_PLACES = Decimal("0.01")
_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class TaxResult:
    """Detailed result of a VAT calculation."""

    tax_amount: Decimal
    tax_rate: Decimal
    tax_type: TaxType | None
    reverse_charge: bool
    oss_applicable: bool


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
        # EU B2B cross-border: reverse charge -- zero-rated
        return Decimal("0"), Decimal("0"), TaxType.REVERSE_CHARGE

    # EU B2C cross-border (OSS) or domestic sale
    if cross_border:
        rate = EU_VAT_RATES[country_code]
    else:
        rate = EU_VAT_RATES[seller_country]

    tax = (subtotal * rate / _HUNDRED).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return tax, rate, TaxType.STANDARD


def calculate_vat_detailed(
    country_code: str,
    is_business: bool,
    subtotal: Decimal,
    seller_country: str = SELLER_COUNTRY,
    annual_b2c_sales: Decimal | None = None,
) -> TaxResult:
    """Compute VAT with full detail, including OSS and reverse charge flags.

    This is a richer alternative to :func:`calculate_vat` that returns a
    :class:`TaxResult` dataclass instead of a plain tuple.

    Args:
        country_code: ISO 3166-1 alpha-2 code of the buyer.
        is_business: Whether the buyer is a VAT-registered business.
        subtotal: Invoice subtotal before tax.
        seller_country: ISO 3166-1 alpha-2 code of the seller.
        annual_b2c_sales: Annual cross-border B2C sales in EUR for OSS
            threshold check. If ``None``, OSS is assumed applicable for
            cross-border B2C.

    Returns:
        A :class:`TaxResult` with tax amount, rate, type, and flags.
    """
    from rupiv.tax.oss import OSS_THRESHOLD

    buyer_in_eu = country_code in EU_VAT_RATES

    if not buyer_in_eu:
        return TaxResult(
            tax_amount=Decimal("0"),
            tax_rate=Decimal("0"),
            tax_type=None,
            reverse_charge=False,
            oss_applicable=False,
        )

    cross_border = country_code != seller_country

    if is_business and cross_border:
        log.info(
            "vat.reverse_charge",
            buyer_country=country_code,
            seller_country=seller_country,
        )
        return TaxResult(
            tax_amount=Decimal("0"),
            tax_rate=Decimal("0"),
            tax_type=TaxType.REVERSE_CHARGE,
            reverse_charge=True,
            oss_applicable=False,
        )

    # Determine OSS applicability for B2C cross-border
    oss_applicable = False
    if cross_border and not is_business:
        if annual_b2c_sales is None or annual_b2c_sales > OSS_THRESHOLD:
            oss_applicable = True

    # Rate selection: buyer country if OSS, seller country otherwise
    if oss_applicable:
        rate = EU_VAT_RATES[country_code]
    elif cross_border:
        # Below OSS threshold — seller can use home country rate
        rate = EU_VAT_RATES[seller_country]
    else:
        rate = EU_VAT_RATES[seller_country]

    tax = (subtotal * rate / _HUNDRED).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    log.info(
        "vat.calculated",
        buyer_country=country_code,
        seller_country=seller_country,
        rate=str(rate),
        tax_amount=str(tax),
        oss_applicable=oss_applicable,
    )

    return TaxResult(
        tax_amount=tax,
        tax_rate=rate,
        tax_type=TaxType.STANDARD,
        reverse_charge=False,
        oss_applicable=oss_applicable,
    )
