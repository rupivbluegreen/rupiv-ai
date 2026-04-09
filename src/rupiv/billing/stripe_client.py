"""Stripe payment integration for Rupiv.ai.

Handles PaymentIntent creation, retrieval, refunds, customer management,
and webhook signature verification via the Stripe v1 API.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

STRIPE_BASE_URL = "https://api.stripe.com/v1"


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StripePaymentIntent:
    """Parsed representation of a Stripe PaymentIntent resource."""

    id: str
    status: str  # requires_payment_method | requires_confirmation | succeeded | canceled
    amount: Decimal
    currency: str
    client_secret: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class StripeRefund:
    """Parsed representation of a Stripe Refund resource."""

    id: str
    payment_intent_id: str
    amount: Decimal
    status: str
    reason: str


@dataclass(frozen=True)
class StripeCustomer:
    """Parsed representation of a Stripe Customer resource."""

    id: str
    email: str
    name: str


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _to_cents(amount: Decimal) -> int:
    """Convert a Decimal amount to Stripe's integer cents representation."""
    return int((amount * Decimal("100")).to_integral_value())


def _from_cents(cents: int, currency: str) -> Decimal:
    """Convert Stripe's integer cents to a Decimal amount."""
    return (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------


def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    webhook_secret: str,
    tolerance: int = 300,
) -> bool:
    """Verify a Stripe webhook signature using HMAC SHA-256.

    The ``Stripe-Signature`` header contains ``t=<timestamp>,v1=<signature>``.
    We recompute the expected signature from ``<timestamp>.<payload>`` and
    compare using constant-time comparison.

    Args:
        payload: Raw request body bytes.
        signature_header: Value of the ``Stripe-Signature`` header.
        webhook_secret: The endpoint's signing secret (``whsec_...``).
        tolerance: Maximum age in seconds for the timestamp (default 300).

    Returns:
        ``True`` if the signature is valid, ``False`` otherwise.
    """
    elements: dict[str, str] = {}
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        elements[key] = value

    timestamp = elements.get("t", "")
    expected_sig = elements.get("v1", "")

    if not timestamp or not expected_sig:
        log.warning("stripe.webhook_signature_missing_elements")
        return False

    # Check timestamp tolerance
    try:
        ts = int(timestamp)
    except ValueError:
        log.warning("stripe.webhook_signature_invalid_timestamp", timestamp=timestamp)
        return False

    if abs(time.time() - ts) > tolerance:
        log.warning(
            "stripe.webhook_signature_expired",
            timestamp=ts,
            tolerance=tolerance,
        )
        return False

    # Compute expected signature
    signed_payload = f"{timestamp}.".encode() + payload
    computed = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, expected_sig):
        log.warning("stripe.webhook_signature_mismatch")
        return False

    return True


# ---------------------------------------------------------------------------
# Stripe API client
# ---------------------------------------------------------------------------


class StripeClient:
    """Async wrapper around the Stripe v1 REST API.

    Uses ``httpx.AsyncClient`` with Bearer authentication and
    form-encoded bodies (as required by the Stripe API).
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=STRIPE_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=30.0,
        )

    # -- PaymentIntents ----------------------------------------------------

    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> StripePaymentIntent:
        """Create a PaymentIntent via ``POST /v1/payment_intents``."""
        data: dict[str, Any] = {
            "amount": _to_cents(amount),
            "currency": currency.lower(),
            "description": description,
        }

        if customer_id is not None:
            data["customer"] = customer_id

        metadata = metadata or {}
        for key, value in metadata.items():
            data[f"metadata[{key}]"] = str(value)

        headers: dict[str, str] = {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        response = await self._client.post(
            "/v1/payment_intents",
            data=data,
            headers=headers,
        )
        response.raise_for_status()
        resp_data = response.json()

        log.info(
            "stripe.payment_intent_created",
            payment_intent_id=resp_data["id"],
            status=resp_data["status"],
            amount=resp_data["amount"],
            currency=resp_data["currency"],
        )

        return _parse_payment_intent(resp_data)

    async def get_payment_intent(
        self, payment_intent_id: str
    ) -> StripePaymentIntent:
        """Retrieve a PaymentIntent via ``GET /v1/payment_intents/{id}``."""
        response = await self._client.get(
            f"/v1/payment_intents/{payment_intent_id}"
        )
        response.raise_for_status()
        return _parse_payment_intent(response.json())

    # -- Refunds -----------------------------------------------------------

    async def create_refund(
        self,
        payment_intent_id: str,
        amount: Decimal | None = None,
        reason: str = "",
    ) -> StripeRefund:
        """Create a refund via ``POST /v1/refunds``."""
        data: dict[str, Any] = {
            "payment_intent": payment_intent_id,
        }

        if amount is not None:
            data["amount"] = _to_cents(amount)

        if reason:
            data["reason"] = reason

        response = await self._client.post("/v1/refunds", data=data)
        response.raise_for_status()
        resp_data = response.json()

        log.info(
            "stripe.refund_created",
            refund_id=resp_data["id"],
            payment_intent_id=payment_intent_id,
            amount=resp_data["amount"],
        )

        return StripeRefund(
            id=resp_data["id"],
            payment_intent_id=resp_data.get("payment_intent", payment_intent_id),
            amount=_from_cents(resp_data["amount"], resp_data["currency"]),
            status=resp_data["status"],
            reason=resp_data.get("reason") or reason,
        )

    # -- Customers ---------------------------------------------------------

    async def create_customer(
        self,
        email: str,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> StripeCustomer:
        """Create a customer via ``POST /v1/customers``."""
        data: dict[str, Any] = {
            "email": email,
            "name": name,
        }

        metadata = metadata or {}
        for key, value in metadata.items():
            data[f"metadata[{key}]"] = str(value)

        response = await self._client.post("/v1/customers", data=data)
        response.raise_for_status()
        resp_data = response.json()

        log.info(
            "stripe.customer_created",
            customer_id=resp_data["id"],
            email=email,
        )

        return StripeCustomer(
            id=resp_data["id"],
            email=resp_data.get("email", email),
            name=resp_data.get("name", name),
        )

    # -- Lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_payment_intent(data: dict[str, Any]) -> StripePaymentIntent:
    """Parse a Stripe PaymentIntent JSON response."""
    return StripePaymentIntent(
        id=data["id"],
        status=data["status"],
        amount=_from_cents(data["amount"], data["currency"]),
        currency=data["currency"],
        client_secret=data.get("client_secret"),
        metadata=data.get("metadata") or {},
    )
