"""EU VAT tax engine for Rupiv.ai.

Provides VAT calculation, rate lookup, VIES validation, OSS threshold
checks, and ViDA reporting stubs for all 27 EU member states.
"""

from rupiv.tax.oss import OSS_THRESHOLD, check_oss_applicable
from rupiv.tax.rates import (
    EU_VAT_RATES,
    EU_VAT_REDUCED_RATES,
    SELLER_COUNTRY,
    get_rate,
    is_eu_country,
)
from rupiv.tax.vat_engine import TaxResult, calculate_vat, calculate_vat_detailed
from rupiv.tax.vat_id_validation import VatIdResult, validate_vat_id
from rupiv.tax.vida import ViDAReport, ViDAReporter

__all__ = [
    "EU_VAT_RATES",
    "EU_VAT_REDUCED_RATES",
    "OSS_THRESHOLD",
    "SELLER_COUNTRY",
    "TaxResult",
    "VatIdResult",
    "ViDAReport",
    "ViDAReporter",
    "calculate_vat",
    "calculate_vat_detailed",
    "check_oss_applicable",
    "get_rate",
    "is_eu_country",
    "validate_vat_id",
]
