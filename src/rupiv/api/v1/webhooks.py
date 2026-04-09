"""Payment provider webhook endpoints."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request, status
from pydantic import BaseModel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookAck(BaseModel):
    """Acknowledgement response for webhook processing."""

    received: bool = True


@router.post(
    "/mollie",
    response_model=WebhookAck,
    status_code=status.HTTP_200_OK,
    summary="Handle Mollie payment webhook",
)
async def mollie_webhook(request: Request) -> WebhookAck:
    """Process incoming Mollie payment status webhook.

    Mollie sends POST requests with payment/refund status updates.
    Signature verification via X-Mollie-Signature HMAC is required in production.
    """
    body: dict[str, Any] = await request.json()
    logger.info("mollie_webhook_received", payload_keys=list(body.keys()))
    # TODO: Verify X-Mollie-Signature HMAC
    # TODO: Look up payment, update invoice status, trigger dunning if needed
    return WebhookAck()
