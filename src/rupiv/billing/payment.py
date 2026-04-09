"""Mollie payment integration for Rupiv.ai.

Handles payment creation, status retrieval, refunds, invoice charging,
and webhook processing via the Mollie v2 API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.invoice import Invoice, InvoiceStatus

log = structlog.get_logger(__name__)

MOLLIE_BASE_URL = "https://api.mollie.com/v2"

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MolliePayment:
    """Parsed representation of a Mollie payment resource."""

    id: str
    status: str
    amount: Decimal
    currency: str
    description: str
    redirect_url: str | None
    webhook_url: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class MollieRefund:
    """Parsed representation of a Mollie refund resource."""

    id: str
    payment_id: str
    amount: Decimal
    currency: str
    status: str
    description: str


@dataclass(frozen=True)
class PaymentResult:
    """Outcome of a charge attempt."""

    success: bool
    payment_id: str
    checkout_url: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Mollie API client
# ---------------------------------------------------------------------------


class MollieClient:
    """Async wrapper around the Mollie v2 REST API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=MOLLIE_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    # -- Payments ----------------------------------------------------------

    async def create_payment(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        redirect_url: str,
        webhook_url: str,
        metadata: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> MolliePayment:
        """Create a new payment via ``POST /v2/payments``."""
        body: dict[str, Any] = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": currency,
            },
            "description": description,
            "redirectUrl": redirect_url,
            "webhookUrl": webhook_url,
            "metadata": metadata,
        }

        headers: dict[str, str] = {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        response = await self._client.post(
            "/v2/payments",
            json=body,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        log.info(
            "mollie.payment_created",
            payment_id=data["id"],
            status=data["status"],
            amount=data["amount"]["value"],
            currency=data["amount"]["currency"],
        )

        return _parse_payment(data)

    async def get_payment(self, payment_id: str) -> MolliePayment:
        """Retrieve a payment via ``GET /v2/payments/{id}``."""
        response = await self._client.get(f"/v2/payments/{payment_id}")
        response.raise_for_status()
        data = response.json()
        return _parse_payment(data)

    # -- Refunds -----------------------------------------------------------

    async def create_refund(
        self,
        payment_id: str,
        amount: Decimal,
        currency: str,
        description: str,
    ) -> MollieRefund:
        """Create a refund via ``POST /v2/payments/{id}/refunds``."""
        body: dict[str, Any] = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": currency,
            },
            "description": description,
        }

        response = await self._client.post(
            f"/v2/payments/{payment_id}/refunds",
            json=body,
        )
        response.raise_for_status()
        data = response.json()

        log.info(
            "mollie.refund_created",
            refund_id=data["id"],
            payment_id=payment_id,
            amount=data["amount"]["value"],
        )

        return MollieRefund(
            id=data["id"],
            payment_id=payment_id,
            amount=Decimal(data["amount"]["value"]),
            currency=data["amount"]["currency"],
            status=data["status"],
            description=data.get("description", ""),
        )

    # -- Lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_payment(data: dict[str, Any]) -> MolliePayment:
    """Parse a Mollie payment JSON response into a ``MolliePayment``."""
    return MolliePayment(
        id=data["id"],
        status=data["status"],
        amount=Decimal(data["amount"]["value"]),
        currency=data["amount"]["currency"],
        description=data.get("description", ""),
        redirect_url=data.get("redirectUrl"),
        webhook_url=data.get("webhookUrl"),
        metadata=data.get("metadata") or {},
        created_at=datetime.fromisoformat(data["createdAt"]),
    )


def _format_amount(value: Decimal) -> str:
    """Format a Decimal as a two-decimal-place string for Mollie."""
    return f"{value:.2f}"


# ---------------------------------------------------------------------------
# Invoice charging
# ---------------------------------------------------------------------------


async def charge_invoice(
    mollie: MollieClient,
    invoice: Invoice,
    webhook_base_url: str,
    redirect_url: str = "https://app.rupiv.ai/payments/complete",
) -> PaymentResult:
    """Create a Mollie payment for *invoice* and update its payment ID.

    Uses ``invoice.id`` (stringified) as the idempotency key so retries
    are safe.
    """
    idempotency_key = str(invoice.id)

    try:
        payment = await mollie.create_payment(
            amount=Decimal(str(invoice.total)),
            currency=invoice.currency,
            description=f"Invoice {invoice.invoice_number}",
            redirect_url=redirect_url,
            webhook_url=f"{webhook_base_url}/v1/webhooks/mollie",
            metadata={"invoice_id": idempotency_key},
            idempotency_key=idempotency_key,
        )
    except httpx.HTTPStatusError as exc:
        log.error(
            "mollie.charge_failed",
            invoice_id=idempotency_key,
            status_code=exc.response.status_code,
            detail=exc.response.text,
        )
        return PaymentResult(
            success=False,
            payment_id="",
            error=f"Mollie API error: {exc.response.status_code}",
        )

    invoice.mollie_payment_id = payment.id

    log.info(
        "payment.charge_initiated",
        invoice_id=idempotency_key,
        payment_id=payment.id,
        amount=_format_amount(payment.amount),
        currency=payment.currency,
    )

    return PaymentResult(
        success=True,
        payment_id=payment.id,
        checkout_url=None,
    )


# ---------------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------------

# Mollie status -> Invoice status mapping
_MOLLIE_STATUS_TO_INVOICE: dict[str, InvoiceStatus] = {
    "paid": InvoiceStatus.PAID,
    "failed": InvoiceStatus.UNCOLLECTIBLE,
    "expired": InvoiceStatus.UNCOLLECTIBLE,
    "canceled": InvoiceStatus.UNCOLLECTIBLE,
}


async def process_webhook(
    mollie: MollieClient,
    session: AsyncSession,
    payment_id: str,
) -> Invoice | None:
    """Fetch a payment from Mollie and update the matching invoice.

    Returns the updated :class:`Invoice`, or ``None`` if no invoice was
    found for the given *payment_id*.
    """
    payment = await mollie.get_payment(payment_id)

    log.info(
        "payment.webhook_processing",
        payment_id=payment_id,
        mollie_status=payment.status,
    )

    result = await session.execute(
        select(Invoice).where(Invoice.mollie_payment_id == payment_id)
    )
    invoice: Invoice | None = result.scalar_one_or_none()

    if invoice is None:
        log.warning(
            "payment.webhook_invoice_not_found",
            payment_id=payment_id,
        )
        return None

    new_status = _MOLLIE_STATUS_TO_INVOICE.get(payment.status)
    if new_status is None:
        log.info(
            "payment.webhook_no_status_change",
            payment_id=payment_id,
            mollie_status=payment.status,
            invoice_id=str(invoice.id),
        )
        return invoice

    invoice.status = new_status

    if new_status == InvoiceStatus.PAID:
        invoice.paid_at = datetime.now(timezone.utc)

    log.info(
        "payment.webhook_invoice_updated",
        payment_id=payment_id,
        invoice_id=str(invoice.id),
        old_status=invoice.status,
        new_status=new_status.value,
    )

    return invoice
