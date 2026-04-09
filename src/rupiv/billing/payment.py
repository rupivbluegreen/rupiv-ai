"""Payment execution stubs (Mollie integration) for Rupiv.ai."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentResult:
    """Outcome of a charge attempt."""

    success: bool
    payment_id: str
    error: str | None = None


@dataclass(frozen=True)
class WebhookResult:
    """Outcome of processing a Mollie webhook."""

    verified: bool
    payment_id: str
    new_status: str
    error: str | None = None


@dataclass(frozen=True)
class PaymentMethod:
    """Reference to a stored payment method."""

    method_id: str
    provider: str  # e.g. "mollie"
    type: str  # e.g. "ideal", "creditcard", "sepa_direct_debit"


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


async def charge_invoice(
    invoice: object,
    payment_method: PaymentMethod,
) -> PaymentResult:
    """Initiate a charge via Mollie for the given invoice.

    The *invoice* object must expose ``invoice_id``, ``total``, and
    ``currency`` attributes.

    This is a **stub** — in production it will call the Mollie Payments
    API (``POST /v2/payments``).

    Idempotency: the Mollie ``idempotencyKey`` is set to the
    ``invoice_id`` so retries are safe.
    """
    invoice_id: str = getattr(invoice, "invoice_id", "")
    total: Decimal = getattr(invoice, "total", Decimal("0"))
    currency: str = getattr(invoice, "currency", "EUR")

    log.info(
        "payment.charge_initiated",
        invoice_id=invoice_id,
        amount=str(total),
        currency=currency,
        method_id=payment_method.method_id,
    )

    # TODO: Replace with actual Mollie API call
    # mollie_client = MollieClient(api_key=settings.MOLLIE_API_KEY)
    # payment = mollie_client.payments.create({
    #     "amount": {"currency": currency, "value": str(total)},
    #     "description": f"Invoice {invoice_id}",
    #     "method": payment_method.type,
    #     "metadata": {"invoice_id": invoice_id},
    #     "idempotencyKey": invoice_id,
    # })

    return PaymentResult(
        success=True,
        payment_id=f"tr_stub_{invoice_id}",
        error=None,
    )


async def process_mollie_webhook(
    payload: dict[str, str],
    signature: str,
) -> WebhookResult:
    """Verify and process a Mollie webhook notification.

    In production this will:
    1. Verify the webhook signature against the Mollie profile key.
    2. Fetch the payment from Mollie to get the authoritative status.
    3. Update the internal invoice / payment records.

    This is a **stub**.
    """
    payment_id = payload.get("id", "")

    log.info(
        "payment.webhook_received",
        payment_id=payment_id,
        signature_present=bool(signature),
    )

    # TODO: Replace with actual Mollie webhook verification
    # 1. Verify signature
    # 2. GET /v2/payments/{payment_id} to get current status
    # 3. Map Mollie status -> internal status

    return WebhookResult(
        verified=True,
        payment_id=payment_id,
        new_status="paid",
        error=None,
    )
