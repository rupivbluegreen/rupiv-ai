"""Tests for rupiv.tax.oss — One-Stop Shop EU cross-border B2C rules."""

from __future__ import annotations

from decimal import Decimal

from rupiv.tax.oss import check_oss_applicable


class TestOSSApplicability:
    """Tests for check_oss_applicable."""

    def test_oss_below_threshold(self) -> None:
        """Under EUR 10K cross-border sales, OSS should not apply."""
        result: bool = check_oss_applicable(
            seller_country="NL",
            buyer_country="DE",
            annual_b2c_sales=Decimal("9999.99"),
        )
        assert result is False

    def test_oss_above_threshold(self) -> None:
        """Over EUR 10K cross-border sales, OSS should apply."""
        result: bool = check_oss_applicable(
            seller_country="NL",
            buyer_country="DE",
            annual_b2c_sales=Decimal("10000.01"),
        )
        assert result is True

    def test_oss_domestic(self) -> None:
        """Same country sale should never trigger OSS, regardless of amount."""
        result: bool = check_oss_applicable(
            seller_country="NL",
            buyer_country="NL",
            annual_b2c_sales=Decimal("999999.99"),
        )
        assert result is False

    def test_oss_exact_threshold(self) -> None:
        """Exactly EUR 10K should NOT trigger OSS (threshold is strictly >)."""
        result: bool = check_oss_applicable(
            seller_country="NL",
            buyer_country="DE",
            annual_b2c_sales=Decimal("10000.00"),
        )
        assert result is False
