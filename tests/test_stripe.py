"""Tests for Stripe payment integration."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from rupiv.billing.stripe_client import (
    StripeClient,
    StripePaymentIntent,
    _from_cents,
    _to_cents,
    verify_webhook_signature,
)


def _mock_response(status_code: int, json_data: dict) -> httpx.Response:
    """Create an httpx.Response with a fake request so raise_for_status works."""
    request = httpx.Request("POST", "https://api.stripe.com/v1/test")
    return httpx.Response(status_code=status_code, json=json_data, request=request)


# ---------------------------------------------------------------------------
# Cents conversion
# ---------------------------------------------------------------------------


class TestCentsConversion:
    def test_to_cents_integer_amount(self) -> None:
        assert _to_cents(Decimal("10.00")) == 1000

    def test_to_cents_fractional_amount(self) -> None:
        assert _to_cents(Decimal("49.99")) == 4999

    def test_to_cents_large_amount(self) -> None:
        assert _to_cents(Decimal("1234.56")) == 123456

    def test_from_cents_basic(self) -> None:
        assert _from_cents(1000, "usd") == Decimal("10.00")

    def test_from_cents_fractional(self) -> None:
        assert _from_cents(4999, "eur") == Decimal("49.99")


# ---------------------------------------------------------------------------
# StripeClient — create_payment_intent
# ---------------------------------------------------------------------------


class TestCreatePaymentIntent:
    @pytest.mark.asyncio
    async def test_create_payment_intent_converts_to_cents(self) -> None:
        """Verify that the amount is converted from Decimal to int cents."""
        mock_response = _mock_response(
            200,
            {
                "id": "pi_test123",
                "status": "requires_payment_method",
                "amount": 4999,
                "currency": "usd",
                "client_secret": "pi_test123_secret_abc",
                "metadata": {"invoice_id": "inv-001"},
            },
        )

        client = StripeClient(api_key="sk_test_fake")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.post = AsyncMock(return_value=mock_response)

        result = await client.create_payment_intent(
            amount=Decimal("49.99"),
            currency="usd",
            description="Test payment",
            metadata={"invoice_id": "inv-001"},
            idempotency_key="idem-key-001",
        )

        # Verify the POST call used cents
        call_kwargs = client._client.post.call_args
        assert call_kwargs[1]["data"]["amount"] == 4999
        assert call_kwargs[1]["data"]["currency"] == "usd"
        assert call_kwargs[1]["headers"]["Idempotency-Key"] == "idem-key-001"

        # Verify the result converts back from cents
        assert isinstance(result, StripePaymentIntent)
        assert result.id == "pi_test123"
        assert result.amount == Decimal("49.99")
        assert result.status == "requires_payment_method"
        assert result.client_secret == "pi_test123_secret_abc"

    @pytest.mark.asyncio
    async def test_create_payment_intent_with_customer(self) -> None:
        mock_response = _mock_response(
            200,
            {
                "id": "pi_cust123",
                "status": "requires_confirmation",
                "amount": 10000,
                "currency": "eur",
                "client_secret": "secret",
                "metadata": {},
            },
        )

        client = StripeClient(api_key="sk_test_fake")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.post = AsyncMock(return_value=mock_response)

        await client.create_payment_intent(
            amount=Decimal("100.00"),
            currency="eur",
            customer_id="cus_abc123",
            description="Invoice INV-002",
        )

        call_kwargs = client._client.post.call_args
        assert call_kwargs[1]["data"]["customer"] == "cus_abc123"


# ---------------------------------------------------------------------------
# StripeClient — get_payment_intent
# ---------------------------------------------------------------------------


class TestGetPaymentIntent:
    @pytest.mark.asyncio
    async def test_get_payment_intent_parses_response(self) -> None:
        mock_response = _mock_response(
            200,
            {
                "id": "pi_existing456",
                "status": "succeeded",
                "amount": 25050,
                "currency": "usd",
                "client_secret": "pi_existing456_secret",
                "metadata": {"order": "42"},
            },
        )

        client = StripeClient(api_key="sk_test_fake")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.get = AsyncMock(return_value=mock_response)

        result = await client.get_payment_intent("pi_existing456")

        assert result.id == "pi_existing456"
        assert result.status == "succeeded"
        assert result.amount == Decimal("250.50")
        assert result.currency == "usd"
        assert result.metadata == {"order": "42"}

        client._client.get.assert_called_once_with(
            "/v1/payment_intents/pi_existing456"
        )


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


class TestWebhookSignature:
    def _make_signature(self, payload: bytes, secret: str, timestamp: int) -> str:
        """Helper to create a valid Stripe-Signature header."""
        signed_payload = f"{timestamp}.".encode() + payload
        sig = hmac.new(
            secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={sig}"

    def test_valid_signature(self) -> None:
        secret = "whsec_test_secret"
        payload = b'{"type":"payment_intent.succeeded"}'
        ts = int(time.time())
        header = self._make_signature(payload, secret, ts)

        assert verify_webhook_signature(payload, header, secret) is True

    def test_invalid_signature(self) -> None:
        secret = "whsec_test_secret"
        payload = b'{"type":"payment_intent.succeeded"}'
        header = f"t={int(time.time())},v1=invalidsignature"

        assert verify_webhook_signature(payload, header, secret) is False

    def test_expired_timestamp(self) -> None:
        secret = "whsec_test_secret"
        payload = b'{"type":"payment_intent.succeeded"}'
        old_ts = int(time.time()) - 600  # 10 minutes ago
        header = self._make_signature(payload, secret, old_ts)

        assert verify_webhook_signature(payload, header, secret, tolerance=300) is False

    def test_missing_elements(self) -> None:
        assert verify_webhook_signature(b"body", "garbage", "secret") is False

    def test_tampered_payload(self) -> None:
        secret = "whsec_test_secret"
        original = b'{"amount":1000}'
        ts = int(time.time())
        header = self._make_signature(original, secret, ts)

        tampered = b'{"amount":9999}'
        assert verify_webhook_signature(tampered, header, secret) is False


# ---------------------------------------------------------------------------
# Payment routing — US vs EU
# ---------------------------------------------------------------------------


class TestPaymentRouting:
    def test_route_us_customer_to_stripe(self) -> None:
        """US customers should be routed to Stripe."""
        from rupiv.analytics.routing_optimizer import find_cheapest_route

        route = find_cheapest_route(
            amount=Decimal("100.00"),
            currency="USD",
            country_code="US",
            payment_method="card",
        )

        assert route.psp == "stripe"
        assert route.method == "card"

    def test_route_eu_customer_to_mollie(self) -> None:
        """EU customers should be routed to Mollie (or Adyen), not Stripe."""
        from rupiv.analytics.routing_optimizer import find_cheapest_route

        route = find_cheapest_route(
            amount=Decimal("100.00"),
            currency="EUR",
            country_code="NL",
            payment_method="ideal",
        )

        # iDEAL is only available on Mollie and Adyen, not Stripe
        assert route.psp in ("mollie", "adyen")
        assert route.method == "ideal"

    def test_route_eu_card_not_stripe(self) -> None:
        """EU card payments should prefer Mollie/Adyen over Stripe."""
        from rupiv.billing.payment_routing import route_payment

        route = route_payment(
            amount=Decimal("50.00"),
            currency="EUR",
            country_code="DE",
            preferred_method="card",
        )

        # DE is not a Stripe-preferred country, so should go to Mollie/Adyen
        assert route.psp in ("mollie", "adyen")

    def test_stripe_ach_fee_cap(self) -> None:
        """ACH fee should be capped at $5.00 for large amounts."""
        from rupiv.analytics.routing_optimizer import PSP_FEE_SCHEDULES, _estimate_fee

        ach_schedule = PSP_FEE_SCHEDULES["stripe"]["ach"]

        # $1000 * 0.8% = $8.00 -> should be capped at $5.00
        fee = _estimate_fee(Decimal("1000.00"), ach_schedule)
        assert fee == Decimal("5.0000")

        # $100 * 0.8% = $0.80 -> no cap
        fee_small = _estimate_fee(Decimal("100.00"), ach_schedule)
        assert fee_small == Decimal("0.8000")

    def test_stripe_in_fee_schedules(self) -> None:
        """Stripe should be present in PSP_FEE_SCHEDULES."""
        from rupiv.analytics.routing_optimizer import PSP_FEE_SCHEDULES

        assert "stripe" in PSP_FEE_SCHEDULES
        assert "card" in PSP_FEE_SCHEDULES["stripe"]
        assert "ach" in PSP_FEE_SCHEDULES["stripe"]
        assert "sepa_dd" in PSP_FEE_SCHEDULES["stripe"]
