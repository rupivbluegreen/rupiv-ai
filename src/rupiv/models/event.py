"""Event model — PostgreSQL mirror for tracking; main data lives in ClickHouse."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class EventType(str, enum.Enum):
    """The kind of billable event."""

    USAGE = "usage"
    OUTCOME = "outcome"


class OutcomeStatus(str, enum.Enum):
    """Validation state for outcome events."""

    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class Event(Base):
    """A billable event recorded against a customer.

    The authoritative event store is ClickHouse. This PostgreSQL table serves
    as a durable write-ahead record and is referenced by foreign keys from
    invoices and ledger entries.

    Note: ``updated_at`` is inherited from Base but is not meaningful for
    events (append-only by design).
    """

    __tablename__ = "events"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[EventType] = mapped_column(nullable=False)
    metric: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Metric name, e.g. api_call, ticket_resolved",
    )
    properties: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Caller-supplied dedup key",
    )
    outcome_status: Mapped[OutcomeStatus | None] = mapped_column(
        nullable=True,
        comment="Set only for outcome events",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the event actually occurred",
    )

    __table_args__ = (
        Index("ix_events_customer_id", "customer_id"),
        Index("ix_events_subscription_id", "subscription_id"),
        Index("ix_events_metric", "metric"),
        Index("ix_events_timestamp", "timestamp"),
        Index("ix_events_event_type", "event_type"),
    )
