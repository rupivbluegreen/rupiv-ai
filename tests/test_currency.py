"""Tests for rupiv.entities.currency — multi-currency conversion and rounding."""

from __future__ import annotations

from decimal import Decimal

import pytest

from unittest.mock import AsyncMock, patch

from rupiv.entities.currency import ECBRateProvider, _MVP_RATES, round_currency


class TestRoundCurrency:
    """Tests for the round_currency helper."""

    def test_round_currency_standard(self) -> None:
        """Standard currencies should round to 2 decimal places."""
        result: Decimal = round_currency(Decimal("99.9950"), "EUR")
        assert result == Decimal("100.00")

        result = round_currency(Decimal("49.994"), "USD")
        assert result == Decimal("49.99")

    def test_round_currency_jpy(self) -> None:
        """JPY (zero-decimal currency) should round to 0 decimal places."""
        result: Decimal = round_currency(Decimal("163.5"), "JPY")
        assert result == Decimal("164")

        result = round_currency(Decimal("163.4"), "JPY")
        assert result == Decimal("163")


class TestECBRateProvider:
    """Tests for ECBRateProvider currency conversion."""

    @pytest.fixture
    def provider(self) -> ECBRateProvider:
        """Return a provider that uses hardcoded MVP rates for deterministic tests."""
        p = ECBRateProvider()
        p._cache = dict(_MVP_RATES)
        p._cache_timestamp = __import__("time").monotonic()
        return p

    async def test_convert_eur_to_usd(self, provider: ECBRateProvider) -> None:
        """Converting EUR to USD should use the MVP rate (1.0850)."""
        result: Decimal = await provider.convert(Decimal("100.00"), "EUR", "USD")
        assert result == Decimal("108.50")

    async def test_convert_usd_to_gbp(self, provider: ECBRateProvider) -> None:
        """Cross-rate USD->GBP goes through EUR as pivot currency."""
        result: Decimal = await provider.convert(Decimal("100.00"), "USD", "GBP")
        # rate = GBP/EUR / USD/EUR = 0.8560 / 1.0850 ≈ 0.788940
        # 100 * 0.788940 = 78.89 (rounded to 2dp)
        expected: Decimal = round_currency(
            Decimal("100") * (Decimal("0.8560") / Decimal("1.0850")),
            "GBP",
        )
        assert result == expected

    async def test_convert_same_currency(self, provider: ECBRateProvider) -> None:
        """Converting same currency should return the exact same amount."""
        result: Decimal = await provider.convert(Decimal("123.45"), "EUR", "EUR")
        assert result == Decimal("123.45")

    async def test_get_rate_same_currency(self, provider: ECBRateProvider) -> None:
        """get_rate for same currency should return exactly 1."""
        rate: Decimal = await provider.get_rate("USD", "USD")
        assert rate == Decimal("1.0000")
