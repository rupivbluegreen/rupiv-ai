"""One-Stop Shop (OSS) for EU cross-border B2C digital services.

When a seller's annual cross-border B2C sales within the EU exceed
EUR 10,000, the seller must charge VAT at the buyer's country rate
and can file through the OSS mechanism in their home country.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# EUR 10K annual threshold for OSS applicability.
OSS_THRESHOLD: Decimal = Decimal("10000")


def check_oss_applicable(
    seller_country: str,
    buyer_country: str,
    annual_b2c_sales: Decimal,
) -> bool:
    """Determine whether OSS rules apply to a B2C cross-border sale.

    If the seller's cumulative annual cross-border B2C sales within the
    EU exceed :data:`OSS_THRESHOLD` (EUR 10,000), the seller **must**
    charge VAT at the buyer-country rate and can report through OSS.

    Below the threshold the seller *may* choose to use their home
    country rate instead.

    Args:
        seller_country: ISO 3166-1 alpha-2 code of the seller.
        buyer_country: ISO 3166-1 alpha-2 code of the buyer.
        annual_b2c_sales: Total cross-border B2C sales in EUR for the
            current calendar year (excluding the current transaction).

    Returns:
        ``True`` if OSS applies (buyer-country rate required),
        ``False`` if below threshold (seller may use home-country rate).
    """
    if seller_country == buyer_country:
        # Domestic sale -- OSS does not apply.
        return False

    applicable = annual_b2c_sales > OSS_THRESHOLD

    log.debug(
        "oss.threshold_check",
        seller_country=seller_country,
        buyer_country=buyer_country,
        annual_b2c_sales=str(annual_b2c_sales),
        threshold=str(OSS_THRESHOLD),
        applicable=applicable,
    )

    return applicable
