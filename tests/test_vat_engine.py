"""Comprehensive tests for the EU VAT tax engine (rupiv.tax)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rupiv.models.invoice import TaxType
from rupiv.tax.rates import (
    EU_VAT_RATES,
    EU_VAT_REDUCED_RATES,
    get_rate,
    is_eu_country,
)
from rupiv.tax.vat_engine import TaxResult, calculate_vat, calculate_vat_detailed
from rupiv.tax.oss import OSS_THRESHOLD, check_oss_applicable
from rupiv.tax.vat_id_validation import VatIdResult, validate_vat_id, clear_cache


# ---------------------------------------------------------------------------
# Rate table tests
# ---------------------------------------------------------------------------


class TestEU27Rates:
    """Verify the EU27 VAT rate table is complete and correct."""

    _EU27_CODES = {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
        "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
        "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    }

    def test_all_27_eu_rates(self) -> None:
        """Every EU27 member state must have a standard rate."""
        assert set(EU_VAT_RATES.keys()) == self._EU27_CODES
        assert len(EU_VAT_RATES) == 27

    def test_all_27_reduced_rates(self) -> None:
        """Every EU27 member state must have a reduced rate."""
        assert set(EU_VAT_REDUCED_RATES.keys()) == self._EU27_CODES
        assert len(EU_VAT_REDUCED_RATES) == 27

    def test_rates_are_decimal(self) -> None:
        """All rates must be Decimal, never float."""
        for code, rate in EU_VAT_RATES.items():
            assert isinstance(rate, Decimal), f"{code} standard rate is not Decimal"
        for code, rate in EU_VAT_REDUCED_RATES.items():
            assert isinstance(rate, Decimal), f"{code} reduced rate is not Decimal"

    def test_rates_are_positive(self) -> None:
        """Standard rates must be > 0."""
        for code, rate in EU_VAT_RATES.items():
            assert rate > Decimal("0"), f"{code} standard rate is not positive"

    def test_reduced_rates_not_above_standard(self) -> None:
        """Reduced rates must not exceed standard rates."""
        for code in self._EU27_CODES:
            assert EU_VAT_REDUCED_RATES[code] <= EU_VAT_RATES[code], (
                f"{code} reduced rate exceeds standard rate"
            )


class TestGetRate:
    """Tests for the get_rate() lookup function."""

    def test_get_rate_standard(self) -> None:
        """Standard rate for NL should be 21%."""
        assert get_rate("NL", "standard") == Decimal("21")

    def test_get_rate_standard_default(self) -> None:
        """Default category is standard."""
        assert get_rate("DE") == Decimal("19")

    def test_get_rate_reduced(self) -> None:
        """Reduced rate for DE should be 7%."""
        assert get_rate("DE", "reduced") == Decimal("7")

    def test_get_rate_unknown_country(self) -> None:
        """Non-EU country should raise KeyError."""
        with pytest.raises(KeyError):
            get_rate("US")

    def test_get_rate_invalid_category(self) -> None:
        """Invalid category should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown rate category"):
            get_rate("NL", "super_reduced")


class TestIsEuCountry:
    """Tests for is_eu_country()."""

    def test_is_eu_country_true(self) -> None:
        """EU member states should return True."""
        assert is_eu_country("NL") is True
        assert is_eu_country("DE") is True
        assert is_eu_country("FR") is True

    def test_is_eu_country_false_us(self) -> None:
        """US should return False."""
        assert is_eu_country("US") is False

    def test_is_eu_country_false_uk(self) -> None:
        """UK (post-Brexit) should return False."""
        assert is_eu_country("GB") is False

    def test_is_eu_country_false_empty(self) -> None:
        """Empty string should return False."""
        assert is_eu_country("") is False


# ---------------------------------------------------------------------------
# Core VAT calculation tests (tuple API)
# ---------------------------------------------------------------------------


class TestCalculateVat:
    """Tests for calculate_vat() — the original tuple-returning API."""

    def test_b2b_reverse_charge(self) -> None:
        """DE business buying from NL seller -> 0% reverse charge."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="DE",
            is_business=True,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )
        assert tax_type == TaxType.REVERSE_CHARGE
        assert tax_amount == Decimal("0")
        assert tax_rate == Decimal("0")

    def test_b2c_domestic(self) -> None:
        """NL consumer buying from NL seller -> 21% standard."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="NL",
            is_business=False,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )
        assert tax_type == TaxType.STANDARD
        assert tax_rate == Decimal("21")
        assert tax_amount == Decimal("21.00")

    def test_b2c_cross_border(self) -> None:
        """FR consumer buying from NL seller -> 20% (FR rate, OSS)."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="FR",
            is_business=False,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )
        assert tax_type == TaxType.STANDARD
        assert tax_rate == Decimal("20")
        assert tax_amount == Decimal("20.00")

    def test_non_eu(self) -> None:
        """US buyer -> 0%, no tax type."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="US",
            is_business=False,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )
        assert tax_type is None
        assert tax_amount == Decimal("0")
        assert tax_rate == Decimal("0")

    def test_domestic_business(self) -> None:
        """NL business buying from NL seller -> 21% (domestic, no reverse charge)."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="NL",
            is_business=True,
            subtotal=Decimal("250.00"),
            seller_country="NL",
        )
        assert tax_type == TaxType.STANDARD
        assert tax_rate == Decimal("21")
        assert tax_amount == Decimal("52.50")

    def test_rounding(self) -> None:
        """Tax should be rounded to 2 decimal places (ROUND_HALF_UP)."""
        # HU at 27%: 33.33 * 0.27 = 8.9991 -> 9.00
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="HU",
            is_business=False,
            subtotal=Decimal("33.33"),
            seller_country="HU",
        )
        assert tax_amount == Decimal("9.00")

    def test_default_seller_country(self) -> None:
        """Default seller country should be NL."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="DE",
            is_business=True,
            subtotal=Decimal("100.00"),
        )
        assert tax_type == TaxType.REVERSE_CHARGE


# ---------------------------------------------------------------------------
# Detailed VAT calculation tests (TaxResult API)
# ---------------------------------------------------------------------------


class TestCalculateVatDetailed:
    """Tests for calculate_vat_detailed() — the richer TaxResult API."""

    def test_returns_tax_result(self) -> None:
        """Should return a TaxResult dataclass."""
        result = calculate_vat_detailed(
            country_code="NL",
            is_business=False,
            subtotal=Decimal("100.00"),
        )
        assert isinstance(result, TaxResult)

    def test_reverse_charge_flags(self) -> None:
        """B2B cross-border should set reverse_charge=True."""
        result = calculate_vat_detailed(
            country_code="DE",
            is_business=True,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )
        assert result.reverse_charge is True
        assert result.oss_applicable is False
        assert result.tax_type == TaxType.REVERSE_CHARGE

    def test_oss_applicable_flag(self) -> None:
        """B2C cross-border above threshold should set oss_applicable=True."""
        result = calculate_vat_detailed(
            country_code="FR",
            is_business=False,
            subtotal=Decimal("100.00"),
            seller_country="NL",
            annual_b2c_sales=Decimal("15000"),
        )
        assert result.oss_applicable is True
        assert result.tax_rate == Decimal("20")  # FR rate

    def test_non_eu_flags(self) -> None:
        """Non-EU should have all flags False/None."""
        result = calculate_vat_detailed(
            country_code="US",
            is_business=False,
            subtotal=Decimal("100.00"),
        )
        assert result.tax_type is None
        assert result.reverse_charge is False
        assert result.oss_applicable is False


# ---------------------------------------------------------------------------
# OSS threshold tests
# ---------------------------------------------------------------------------


class TestOSSThreshold:
    """Tests for OSS threshold logic."""

    def test_oss_threshold_value(self) -> None:
        """OSS threshold should be EUR 10,000."""
        assert OSS_THRESHOLD == Decimal("10000")

    def test_oss_threshold_below(self) -> None:
        """Below 10K uses seller rate (OSS not applicable)."""
        assert check_oss_applicable("NL", "FR", Decimal("5000")) is False

    def test_oss_threshold_above(self) -> None:
        """Above 10K uses buyer rate (OSS applicable)."""
        assert check_oss_applicable("NL", "FR", Decimal("15000")) is True

    def test_oss_threshold_exact(self) -> None:
        """Exactly 10K is not above threshold."""
        assert check_oss_applicable("NL", "FR", Decimal("10000")) is False

    def test_oss_domestic_not_applicable(self) -> None:
        """Domestic sale never triggers OSS regardless of amount."""
        assert check_oss_applicable("NL", "NL", Decimal("999999")) is False

    def test_oss_below_threshold_uses_seller_rate(self) -> None:
        """Below threshold, detailed calculation uses seller country rate."""
        result = calculate_vat_detailed(
            country_code="FR",
            is_business=False,
            subtotal=Decimal("100.00"),
            seller_country="NL",
            annual_b2c_sales=Decimal("5000"),
        )
        assert result.oss_applicable is False
        # Below threshold -> seller country rate (NL 21%)
        assert result.tax_rate == Decimal("21")

    def test_oss_above_threshold_uses_buyer_rate(self) -> None:
        """Above threshold, detailed calculation uses buyer country rate."""
        result = calculate_vat_detailed(
            country_code="FR",
            is_business=False,
            subtotal=Decimal("100.00"),
            seller_country="NL",
            annual_b2c_sales=Decimal("15000"),
        )
        assert result.oss_applicable is True
        # Above threshold -> buyer country rate (FR 20%)
        assert result.tax_rate == Decimal("20")


# ---------------------------------------------------------------------------
# VAT ID validation format tests
# ---------------------------------------------------------------------------


class TestVatIdValidationFormat:
    """Tests for VAT ID validation (mocked HTTP)."""

    @pytest.fixture(autouse=True)
    def _clear_vies_cache(self) -> None:
        """Clear the VIES cache before each test."""
        clear_cache()

    @pytest.mark.asyncio
    async def test_valid_vat_id(self) -> None:
        """A valid VAT ID should return valid=True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {
            "valid": True,
            "name": "Acme GmbH",
            "address": "Berlin, Germany",
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("rupiv.tax.vat_id_validation.httpx.AsyncClient", return_value=mock_client):
            result = await validate_vat_id("DE", "123456789")

        assert result.valid is True
        assert result.name == "Acme GmbH"
        assert result.cached is False

    @pytest.mark.asyncio
    async def test_invalid_vat_id(self) -> None:
        """An invalid VAT ID should return valid=False."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {
            "valid": False,
            "name": None,
            "address": None,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("rupiv.tax.vat_id_validation.httpx.AsyncClient", return_value=mock_client):
            result = await validate_vat_id("DE", "000000000")

        assert result.valid is False

    @pytest.mark.asyncio
    async def test_vies_timeout_returns_unknown(self) -> None:
        """When VIES times out, valid should be None (unknown)."""
        import httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("rupiv.tax.vat_id_validation.httpx.AsyncClient", return_value=mock_client):
            result = await validate_vat_id("DE", "123456789")

        assert result.valid is None
        assert result.cached is False

    @pytest.mark.asyncio
    async def test_caching(self) -> None:
        """Second call for same VAT ID should be served from cache."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {
            "valid": True,
            "name": "Test BV",
            "address": "Amsterdam",
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("rupiv.tax.vat_id_validation.httpx.AsyncClient", return_value=mock_client):
            result1 = await validate_vat_id("NL", "123456789")
            result2 = await validate_vat_id("NL", "123456789")

        assert result1.cached is False
        assert result2.cached is True
        assert result2.valid is True
        # HTTP should only have been called once
        assert mock_client.post.call_count == 1
