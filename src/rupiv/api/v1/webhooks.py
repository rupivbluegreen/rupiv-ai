"""Payment provider webhook endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.payment import MollieClient, process_webhook
from rupiv.config import get_settings
from rupiv.db import get_db

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _get_mollie_client() -> MollieClient:
    """Build a MollieClient from application settings."""
    settings = get_settings()
    api_key = settings.MOLLIE_API_KEY
    if api_key is None:
        raise RuntimeError("MOLLIE_API_KEY is not configured")
    return MollieClient(api_key=api_key)


@router.post(
    "/mollie",
    status_code=status.HTTP_200_OK,
    summary="Handle Mollie payment webhook",
)
async def mollie_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Process incoming Mollie payment status webhook.

    Mollie sends ``POST`` requests with form-encoded body containing an
    ``id`` field (e.g. ``id=tr_xxx``).  We must always return **200 OK**;
    any other status causes Mollie to retry the webhook.
    """
    form_data = await request.form()
    payment_id: str = str(form_data.get("id", ""))

    if not payment_id:
        logger.warning("mollie_webhook_missing_id")
        # Still return 200 to prevent Mollie retries on malformed requests
        return Response(status_code=status.HTTP_200_OK)

    logger.info("mollie_webhook_received", payment_id=payment_id)

    mollie = _get_mollie_client()
    try:
        invoice = await process_webhook(mollie, session, payment_id)

        if invoice is not None:
            logger.info(
                "mollie_webhook_processed",
                payment_id=payment_id,
                invoice_id=str(invoice.id),
                invoice_status=invoice.status.value
                if hasattr(invoice.status, "value")
                else str(invoice.status),
            )
        else:
            logger.warning(
                "mollie_webhook_no_invoice",
                payment_id=payment_id,
            )
    except Exception:
        logger.exception("mollie_webhook_error", payment_id=payment_id)
        # Return 200 anyway to avoid infinite Mollie retries.
        # The error is logged for investigation.
    finally:
        await mollie.close()

    return Response(status_code=status.HTTP_200_OK)
