"""Subscription CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.db import get_db
from rupiv.models.subscription import Subscription, SubscriptionStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class SubscriptionCreate(BaseModel):
    """Request body for creating a subscription."""

    customer_id: uuid.UUID
    plan_id: uuid.UUID


class SubscriptionResponse(BaseModel):
    """Subscription resource representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    canceled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SubscriptionListResponse(BaseModel):
    """Paginated list of subscriptions."""

    items: list[SubscriptionResponse]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=SubscriptionListResponse, summary="List subscriptions")
async def list_subscriptions(
    customer_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionListResponse:
    """Return a paginated list of subscriptions, optionally filtered by customer."""
    logger.info(
        "list_subscriptions",
        customer_id=str(customer_id) if customer_id else None,
        limit=limit,
        offset=offset,
    )

    stmt = select(Subscription)
    count_stmt = select(func.count()).select_from(Subscription)

    if customer_id is not None:
        stmt = stmt.where(Subscription.customer_id == customer_id)
        count_stmt = count_stmt.where(Subscription.customer_id == customer_id)

    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = stmt.order_by(Subscription.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    subscriptions = result.scalars().all()

    return SubscriptionListResponse(
        items=[SubscriptionResponse.model_validate(s) for s in subscriptions],
        total=total,
    )


@router.get(
    "/{subscription_id}", response_model=SubscriptionResponse, summary="Get a subscription",
)
async def get_subscription(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    """Return a single subscription by ID."""
    logger.info("get_subscription", subscription_id=str(subscription_id))

    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found",
        )

    return SubscriptionResponse.model_validate(subscription)


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subscription",
)
async def create_subscription(
    payload: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    """Create a new subscription with status=active and a 30-day billing period."""
    logger.info(
        "create_subscription",
        customer_id=str(payload.customer_id),
        plan_id=str(payload.plan_id),
    )

    now = datetime.now(tz=UTC)
    subscription = Subscription(
        customer_id=payload.customer_id,
        plan_id=payload.plan_id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db.add(subscription)
    await db.flush()
    await db.refresh(subscription)

    return SubscriptionResponse.model_validate(subscription)


@router.post(
    "/{subscription_id}/cancel",
    response_model=SubscriptionResponse,
    summary="Cancel a subscription",
)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    """Cancel an existing subscription."""
    logger.info("cancel_subscription", subscription_id=str(subscription_id))

    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found",
        )

    subscription.status = SubscriptionStatus.CANCELED
    subscription.canceled_at = datetime.now(tz=UTC)
    await db.flush()
    await db.refresh(subscription)

    return SubscriptionResponse.model_validate(subscription)
