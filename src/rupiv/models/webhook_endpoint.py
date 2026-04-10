"""WebhookEndpoint and WebhookDelivery models for outbound event notifications."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class WebhookEndpoint(Base):
    """A customer-registered URL for receiving billing event webhooks."""

    __tablename__ = "webhook_endpoints"

    customer_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="HMAC-SHA256 signing secret",
    )
    events: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        comment="List of subscribed event types, e.g. ['invoice.paid']",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_webhook_endpoints_customer_id", "customer_id"),
        Index("ix_webhook_endpoints_is_active", "is_active"),
    )


class WebhookDelivery(Base):
    """Log of a webhook delivery attempt."""

    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_webhook_deliveries_endpoint_id", "endpoint_id"),
        Index("ix_webhook_deliveries_event_type", "event_type"),
    )
