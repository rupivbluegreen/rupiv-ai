"""Tests for PaymentMethod model and charge routing."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.payment import (
    PaymentMethod,
    PaymentResult,
    charge_invoice_routed,
)
from rupiv.models.customer import Customer
from rupiv.models.invoice import Invoice
from rupiv.models.payment_method import PaymentMethod as PaymentMethodModel
from rupiv.models.subscription import Subscription, SubscriptionStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CUSTOMER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
async def customer_with_payment_method(
    db_session: AsyncSession,
) -> dict[str, Any]:
    """Seed a customer with a default payment method."""
    customer = Customer(
        id=CUSTOMER_ID,
        name="PM Test Corp",
        email="pm@test.example.com",
        external_id="ext-pm-001",
        country_code="NL",
        is_business=True,
        currency="EUR",
    )
    db_session.add(customer)

    pm = PaymentMethodModel(
        id=uuid.uuid4(),
        customer_id=CUSTOMER_ID,
        provider="mollie",
        type="ideal",
        provider_method_id="mnd_test_123",
        is_default=True,
        last_four=None,
    )
    db_session.add(pm)

    pm_secondary = PaymentMethodModel(
        id=uuid.uuid4(),
        customer_id=CUSTOMER_ID,
        provider="stripe",
        type="card",
        provider_method_id="pm_stripe_456",
        is_default=False,
        last_four="4242",
    )
    db_session.add(pm_secondary)

    await db_session.commit()

    return {
        "customer_id": CUSTOMER_ID,
        "default_pm_id": pm.id,
        "secondary_pm_id": pm_secondary.id,
    }


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestPaymentMethodModel:
    """Tests for the PaymentMethod ORM model."""

    async def test_create_payment_method(self, db_session: AsyncSession) -> None:
        customer = Customer(
            id=uuid.uuid4(),
            name="Test",
            email="test@example.com",
            external_id="ext-test-pm",
            country_code="NL",
            is_business=False,
            currency="EUR",
        )
        db_session.add(customer)
        await db_session.flush()

        pm = PaymentMethodModel(
            customer_id=customer.id,
            provider="stripe",
            type="card",
            provider_method_id="pm_test_789",
            is_default=True,
            last_four="1234",
        )
        db_session.add(pm)
        await db_session.flush()

        assert pm.id is not None
        assert pm.provider == "stripe"
        assert pm.is_default is True
        assert pm.last_four == "1234"

    async def test_query_default_method(
        self,
        db_session: AsyncSession,
        customer_with_payment_method: dict[str, Any],
    ) -> None:
        from sqlalchemy import select

        stmt = select(PaymentMethodModel).where(
            PaymentMethodModel.customer_id == CUSTOMER_ID,
            PaymentMethodModel.is_default.is_(True),
        )
        result = await db_session.execute(stmt)
        pm = result.scalar_one_or_none()

        assert pm is not None
        assert pm.provider == "mollie"
        assert pm.provider_method_id == "mnd_test_123"


# ---------------------------------------------------------------------------
# Charge routing tests
# ---------------------------------------------------------------------------


class TestChargeInvoiceRouted:
    """Tests for PSP dispatch logic."""

    def _make_invoice(self) -> Invoice:
        """Create a minimal Invoice for testing."""
        return Invoice(
            id=uuid.uuid4(),
            customer_id=CUSTOMER_ID,
            subscription_id=uuid.uuid4(),
            invoice_number="INV-TEST-001",
            status="open",
            currency="EUR",
            subtotal="100.0000",
            tax_amount="21.0000",
            total="121.0000",
            period_start="2026-03-01T00:00:00Z",
            period_end="2026-03-31T23:59:59Z",
            due_date="2026-04-14",
        )

    async def test_mollie_routing(self) -> None:
        invoice = self._make_invoice()
        pm = PaymentMethod(method_id="mnd_123", provider="mollie", type="ideal")

        mock_settings = type("Settings", (), {
            "MOLLIE_API_KEY": "test_mollie_key",
            "STRIPE_API_KEY": "",
        })()

        with patch("rupiv.billing.payment.MollieClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.create_payment = AsyncMock(
                return_value=type("P", (), {
                    "id": "tr_test_123",
                    "status": "open",
                    "amount": Decimal("121.00"),
                    "currency": "EUR",
                })(),
            )
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            # Patch charge_invoice to return success
            with patch("rupiv.billing.payment.charge_invoice") as mock_charge:
                mock_charge.return_value = PaymentResult(
                    success=True, payment_id="tr_test_123",
                )
                result = await charge_invoice_routed(invoice, pm, mock_settings)

            assert result.success is True
            assert result.payment_id == "tr_test_123"
            mock_cls.assert_called_once_with("test_mollie_key")

    async def test_stripe_routing(self) -> None:
        invoice = self._make_invoice()
        pm = PaymentMethod(method_id="pm_456", provider="stripe", type="card")

        mock_settings = type("Settings", (), {
            "MOLLIE_API_KEY": "",
            "STRIPE_API_KEY": "test_stripe_key",
        })()

        with patch("rupiv.billing.payment.StripeClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.close = AsyncMock()
            mock_cls.return_value = mock_client

            with patch("rupiv.billing.payment.charge_invoice_stripe") as mock_charge:
                mock_charge.return_value = PaymentResult(
                    success=True, payment_id="pi_test_789",
                )
                result = await charge_invoice_routed(invoice, pm, mock_settings)

            assert result.success is True
            assert result.payment_id == "pi_test_789"
            mock_cls.assert_called_once_with("test_stripe_key")

    async def test_unsupported_provider(self) -> None:
        invoice = self._make_invoice()
        pm = PaymentMethod(method_id="x", provider="unknown", type="card")
        mock_settings = type("Settings", (), {})()

        result = await charge_invoice_routed(invoice, pm, mock_settings)
        assert result.success is False
        assert "Unsupported" in (result.error or "")

    async def test_missing_api_key(self) -> None:
        invoice = self._make_invoice()
        pm = PaymentMethod(method_id="x", provider="mollie", type="ideal")
        mock_settings = type("Settings", (), {"MOLLIE_API_KEY": ""})()

        result = await charge_invoice_routed(invoice, pm, mock_settings)
        assert result.success is False
        assert "not configured" in (result.error or "")
