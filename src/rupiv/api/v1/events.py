"""Event ingestion endpoint — POST /v1/events."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.billing.metering import ingest_event
from rupiv.db import get_db
from rupiv.models.event import Event

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(tags=["events"])


class EventType(str, Enum):
    """Supported event types."""

    USAGE = "usage"
    OUTCOME = "outcome"


class EventCreate(BaseModel):
    """Request body for creating a new event."""

    type: EventType = Field(..., example="outcome")
    metric: str = Field(
        ...,
        description="Metric identifier, e.g. 'ticket_resolved'",
        example="ticket_resolved",
    )
    customer_id: uuid.UUID = Field(
        ..., example="e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        example={
            "resolution_time": 42,
            "escalated": False,
            "csat_score": 4.8,
            "agent_id": "support-agent-nl-003",
        },
    )
    idempotency_key: str = Field(
        ...,
        description="Client-provided idempotency key for deduplication",
        example="evt-20260409-nl-003-a7c9e2",
    )


class EventResponse(BaseModel):
    """Response returned after event ingestion."""

    model_config = ConfigDict(from_attributes=True)

    event_id: uuid.UUID
    status: str = "accepted"


@router.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a usage or outcome event",
)
async def create_event(
    payload: EventCreate,
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    """Ingest a usage or outcome event for later processing.

    Idempotent: if the idempotency_key already exists, the existing event_id
    is returned without creating a duplicate.
    """
    # Check for existing event with the same idempotency key
    stmt = select(Event).where(Event.idempotency_key == payload.idempotency_key)
    result = await db.execute(stmt)
    existing: Event | None = result.scalar_one_or_none()

    if existing is not None:
        logger.info(
            "event_idempotent_hit",
            event_id=str(existing.id),
            idempotency_key=payload.idempotency_key,
        )
        return EventResponse(event_id=existing.id, status="accepted")

    # Create new event in PostgreSQL
    event = Event(
        customer_id=payload.customer_id,
        event_type=payload.type.value,
        metric=payload.metric,
        properties=payload.properties,
        idempotency_key=payload.idempotency_key,
    )
    db.add(event)
    await db.flush()  # Flush to get the generated id before commit

    logger.info(
        "event_ingested",
        event_id=str(event.id),
        event_type=payload.type.value,
        metric=payload.metric,
        customer_id=str(payload.customer_id),
        idempotency_key=payload.idempotency_key,
    )

    # Queue the event for async processing into ClickHouse
    await ingest_event(
        customer_id=str(payload.customer_id),
        metric=payload.metric,
        value=payload.properties.get("value", 1.0),
        properties=payload.properties,
        idempotency_key=payload.idempotency_key,
        event_type=payload.type.value,
    )

    return EventResponse(event_id=event.id, status="accepted")
