"""EU27 VAT rate table for all member states.

Standard and reduced rates for digital services, updated for 2026.
"""

from __future__ import annotations

from decimal import Decimal


# Rupiv B.V. is based in the Netherlands.
SELLER_COUNTRY: str = "NL"

# ---------------------------------------------------------------------------
# EU VAT standard rates (all 27 member states, 2026 rates)
# ---------------------------------------------------------------------------

EU_VAT_RATES: dict[str, Decimal] = {
    "AT": Decimal("20"),      # Austria
    "BE": Decimal("21"),      # Belgium
    "BG": Decimal("20"),      # Bulgaria
    "HR": Decimal("25"),      # Croatia
    "CY": Decimal("19"),      # Cyprus
    "CZ": Decimal("21"),      # Czech Republic
    "DK": Decimal("25"),      # Denmark
    "EE": Decimal("22"),      # Estonia
    "FI": Decimal("25.5"),    # Finland
    "FR": Decimal("20"),      # France
    "DE": Decimal("19"),      # Germany
    "GR": Decimal("24"),      # Greece
    "HU": Decimal("27"),      # Hungary
    "IE": Decimal("23"),      # Ireland
    "IT": Decimal("22"),      # Italy
    "LV": Decimal("21"),      # Latvia
    "LT": Decimal("21"),      # Lithuania
    "LU": Decimal("17"),      # Luxembourg
    "MT": Decimal("18"),      # Malta
    "NL": Decimal("21"),      # Netherlands
    "PL": Decimal("23"),      # Poland
    "PT": Decimal("23"),      # Portugal
    "RO": Decimal("19"),      # Romania
    "SK": Decimal("23"),      # Slovakia
    "SI": Decimal("22"),      # Slovenia
    "ES": Decimal("21"),      # Spain
    "SE": Decimal("25"),      # Sweden
}

# ---------------------------------------------------------------------------
# EU VAT reduced rates for digital services (where applicable)
# ---------------------------------------------------------------------------

EU_VAT_REDUCED_RATES: dict[str, Decimal] = {
    "AT": Decimal("10"),      # Austria — reduced
    "BE": Decimal("6"),       # Belgium — reduced
    "BG": Decimal("9"),       # Bulgaria — reduced
    "HR": Decimal("13"),      # Croatia — reduced
    "CY": Decimal("5"),       # Cyprus — reduced
    "CZ": Decimal("12"),      # Czech Republic — reduced
    "DK": Decimal("0"),       # Denmark — no reduced rate for digital
    "EE": Decimal("9"),       # Estonia — reduced
    "FI": Decimal("10"),      # Finland — reduced
    "FR": Decimal("5.5"),     # France — reduced
    "DE": Decimal("7"),       # Germany — reduced
    "GR": Decimal("6"),       # Greece — reduced
    "HU": Decimal("5"),       # Hungary — reduced
    "IE": Decimal("9"),       # Ireland — reduced
    "IT": Decimal("10"),      # Italy — reduced
    "LV": Decimal("12"),      # Latvia — reduced
    "LT": Decimal("9"),       # Lithuania — reduced
    "LU": Decimal("8"),       # Luxembourg — reduced
    "MT": Decimal("5"),       # Malta — reduced
    "NL": Decimal("9"),       # Netherlands — reduced
    "PL": Decimal("8"),       # Poland — reduced
    "PT": Decimal("6"),       # Portugal — reduced
    "RO": Decimal("9"),       # Romania — reduced
    "SK": Decimal("10"),      # Slovakia — reduced
    "SI": Decimal("9.5"),     # Slovenia — reduced
    "ES": Decimal("10"),      # Spain — reduced
    "SE": Decimal("6"),       # Sweden — reduced
}


def get_rate(country_code: str, category: str = "standard") -> Decimal:
    """Look up the VAT rate for a given EU country and rate category.

    Args:
        country_code: ISO 3166-1 alpha-2 code.
        category: ``"standard"`` or ``"reduced"``.

    Returns:
        The VAT rate as a percentage (e.g. ``Decimal("21")`` for 21%).

    Raises:
        KeyError: If the country code is not an EU member state.
        ValueError: If the category is not ``"standard"`` or ``"reduced"``.
    """
    if category == "standard":
        return EU_VAT_RATES[country_code]
    elif category == "reduced":
        return EU_VAT_REDUCED_RATES[country_code]
    else:
        raise ValueError(f"Unknown rate category: {category!r}. Use 'standard' or 'reduced'.")


def is_eu_country(country_code: str) -> bool:
    """Check whether a country code belongs to an EU27 member state."""
    return country_code in EU_VAT_RATES
