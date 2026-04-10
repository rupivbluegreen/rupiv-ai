"""Webhook endpoint management — CRUD for outbound webhook subscriptions."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.api.middleware.auth import get_current_customer
from rupiv.db import get_db
from rupiv.models.customer import Customer
from rupiv.models.webhook_endpoint import WebhookDelivery, WebhookEndpoint

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/webhook-endpoints", tags=["webhook-endpoints"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class WebhookEndpointResponse(BaseModel):
    """Webhook endpoint resource."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    secret: str
    events: list[str]
    is_active: bool
    failure_count: int
    created_at: datetime


_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::]", "[::1]"}  # noqa: S104
_BLOCKED_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.3",
                     "192.168.", "169.254.", "fc00:", "fd", "fe80:")


def _validate_webhook_url(url: str) -> str:
    """Reject URLs targeting internal/private networks (SSRF protection)."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        msg = "Webhook URL must use http or https"
        raise ValueError(msg)

    hostname = (parsed.hostname or "").lower()
    if hostname in _BLOCKED_HOSTS:
        msg = "Webhook URL cannot target localhost or loopback"
        raise ValueError(msg)
    if any(hostname.startswith(p) for p in _BLOCKED_PREFIXES):
        msg = "Webhook URL cannot target private/internal networks"
        raise ValueError(msg)

    # Block cloud metadata endpoints
    if "169.254.169.254" in url or "metadata.google" in url:
        msg = "Webhook URL cannot target cloud metadata services"
        raise ValueError(msg)

    return url


class WebhookEndpointCreate(BaseModel):
    """Request body for creating a webhook endpoint."""

    url: str = Field(min_length=1, max_length=2048)
    events: list[str] = Field(
        min_length=1,
        description="Event types to subscribe to, e.g. ['invoice.paid', 'payment.failed']",
    )

    @classmethod
    def model_validate(cls, *args: Any, **kwargs: Any) -> "WebhookEndpointCreate":
        """Validate and check URL safety."""
        instance = super().model_validate(*args, **kwargs)
        _validate_webhook_url(instance.url)
        return instance


class WebhookDeliveryResponse(BaseModel):
    """Webhook delivery log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    response_status: int | None = None
    attempt: int
    delivered_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=WebhookEndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook_endpoint(
    payload: WebhookEndpointCreate,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointResponse:
    """Register a new webhook endpoint for the authenticated customer."""
    try:
        _validate_webhook_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    endpoint = WebhookEndpoint(
        customer_id=customer.id,
        url=payload.url,
        secret=secrets.token_hex(32),
        events=payload.events,
        is_active=True,
        failure_count=0,
    )
    db.add(endpoint)
    await db.flush()
    await db.refresh(endpoint)
    return WebhookEndpointResponse.model_validate(endpoint)


@router.get("", response_model=list[WebhookEndpointResponse])
async def list_webhook_endpoints(
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookEndpointResponse]:
    """List all webhook endpoints for the authenticated customer."""
    result = await db.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.customer_id == customer.id)
        .order_by(WebhookEndpoint.created_at.desc()),
    )
    endpoints = result.scalars().all()
    return [WebhookEndpointResponse.model_validate(ep) for ep in endpoints]


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook_endpoint(
    endpoint_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a webhook endpoint."""
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id,
            WebhookEndpoint.customer_id == customer.id,
        ),
    )
    endpoint: WebhookEndpoint | None = result.scalar_one_or_none()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    await db.delete(endpoint)


@router.get(
    "/{endpoint_id}/deliveries",
    response_model=list[WebhookDeliveryResponse],
)
async def list_deliveries(
    endpoint_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryResponse]:
    """List delivery history for a webhook endpoint."""
    # Verify ownership
    ep_result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == endpoint_id,
            WebhookEndpoint.customer_id == customer.id,
        ),
    )
    if ep_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == endpoint_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit),
    )
    deliveries = result.scalars().all()
    return [WebhookDeliveryResponse.model_validate(d) for d in deliveries]
