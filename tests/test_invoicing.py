"""Tests for invoice generation and EU VAT logic in rupiv.billing.invoicing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from rupiv.billing.invoicing import (
    _generate_invoice_number,
    calculate_vat,
)
from rupiv.models.invoice import TaxType


# ---------------------------------------------------------------------------
# VAT calculation
# ---------------------------------------------------------------------------


class TestCalculateVat:
    """Tests for the calculate_vat function covering EU VAT scenarios."""

    def test_calculate_vat_domestic(self) -> None:
        """NL business buying from NL seller -> NL standard rate (21%)."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="NL",
            is_business=True,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )

        assert tax_type == TaxType.STANDARD
        assert tax_rate == Decimal("21")
        assert tax_amount == Decimal("21.00")

    def test_calculate_vat_eu_b2b_reverse_charge(self) -> None:
        """DE business buying from NL seller -> reverse charge, 0 tax."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="DE",
            is_business=True,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )

        assert tax_type == TaxType.REVERSE_CHARGE
        assert tax_amount == Decimal("0")
        assert tax_rate == Decimal("0")

    def test_calculate_vat_eu_b2c(self) -> None:
        """FR consumer buying from NL seller -> FR standard rate (20%)."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="FR",
            is_business=False,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )

        assert tax_type == TaxType.STANDARD
        assert tax_rate == Decimal("20")
        assert tax_amount == Decimal("20.00")

    def test_calculate_vat_non_eu(self) -> None:
        """US customer -> no VAT (0 tax, None tax_type)."""
        tax_amount, tax_rate, tax_type = calculate_vat(
            country_code="US",
            is_business=False,
            subtotal=Decimal("100.00"),
            seller_country="NL",
        )

        assert tax_type is None
        assert tax_amount == Decimal("0")
        assert tax_rate == Decimal("0")


# ---------------------------------------------------------------------------
# Invoice number generation
# ---------------------------------------------------------------------------


class TestInvoiceNumberFormat:
    """Tests for the _generate_invoice_number helper."""

    def test_generate_invoice_number_format(self) -> None:
        """Verify INV-YYYYMM-XXXXX format."""
        period_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        number = _generate_invoice_number(period_start)

        # Pattern: INV-YYYYMM-XXXXX (5 uppercase hex chars)
        pattern = re.compile(r"^INV-\d{6}-[0-9A-F]{5}$")
        assert pattern.match(number), f"Invoice number {number!r} does not match INV-YYYYMM-XXXXX"

        # Year-month portion should be 202604
        assert number.startswith("INV-202604-")

    def test_generate_invoice_number_uniqueness(self) -> None:
        """Two consecutive calls should produce different numbers."""
        period_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        n1 = _generate_invoice_number(period_start)
        n2 = _generate_invoice_number(period_start)

        # Extremely unlikely to collide (5 hex chars = 1M combinations)
        assert n1 != n2
