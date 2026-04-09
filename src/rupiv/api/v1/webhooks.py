"""Payment provider webhook endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.payment import MollieClient, process_stripe_webhook, process_webhook
from rupiv.billing.stripe_client import StripeClient
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


def _get_stripe_client() -> StripeClient:
    """Build a StripeClient from application settings."""
    settings = get_settings()
    api_key = settings.STRIPE_API_KEY
    if not api_key:
        raise RuntimeError("STRIPE_API_KEY is not configured")
    return StripeClient(api_key=api_key)


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    summary="Handle Stripe payment webhook",
)
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Process incoming Stripe webhook event.

    Stripe sends ``POST`` requests with a JSON body.  The
    ``Stripe-Signature`` header is used to verify authenticity via
    HMAC SHA-256.  We must always return **200 OK** to acknowledge
    receipt; any other status causes Stripe to retry.
    """
    settings = get_settings()
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    if not webhook_secret:
        logger.error("stripe_webhook_secret_not_configured")
        return Response(status_code=status.HTTP_200_OK)

    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    if not signature:
        logger.warning("stripe_webhook_missing_signature")
        return Response(status_code=status.HTTP_200_OK)

    logger.info("stripe_webhook_received")

    stripe = _get_stripe_client()
    try:
        invoice = await process_stripe_webhook(
            stripe, session, payload, signature, webhook_secret
        )

        if invoice is not None:
            logger.info(
                "stripe_webhook_processed",
                invoice_id=str(invoice.id),
                invoice_status=invoice.status.value
                if hasattr(invoice.status, "value")
                else str(invoice.status),
            )
        else:
            logger.info("stripe_webhook_no_invoice")
    except ValueError:
        logger.warning("stripe_webhook_invalid_signature")
    except Exception:
        logger.exception("stripe_webhook_error")
    finally:
        await stripe.close()

    return Response(status_code=status.HTTP_200_OK)
