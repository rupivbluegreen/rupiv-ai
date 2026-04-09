"""Audit log model — append-only record of every state-changing action."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class AuditLog(Base):
    """Immutable audit trail entry.

    Every write operation (create, update, delete) against a tracked resource
    produces exactly one ``AuditLog`` row.  Rows are **append-only** — they
    must never be updated or deleted.
    """

    __tablename__ = "audit_logs"

    # Who performed the action
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="ID of the user, API key, or system actor",
    )
    actor_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g. user, api_key, system, agent",
    )

    # What happened
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g. create, update, delete, export, anonymize",
    )

    # Which resource was affected
    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g. customer, invoice, subscription",
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Primary key of the affected resource",
    )

    # Change details
    changes: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="JSON diff of changed fields {field: {old, new}}",
    )

    # Request context
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP (IPv4 or IPv6)",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    # Explicit timestamp (distinct from Base.created_at for query clarity)
    timestamp: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
        comment="When the action occurred (UTC)",
    )

    # Arbitrary extra context
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
    )

    __table_args__ = (
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
        Index("ix_audit_logs_action", "action"),
    )
