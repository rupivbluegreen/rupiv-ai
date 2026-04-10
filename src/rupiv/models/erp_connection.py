"""ERP connection and export log models."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class ERPConnection(Base):
    """Configuration for an ERP/accounting system integration."""

    __tablename__ = "erp_connections"

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="quickbooks | xero | csv",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="OAuth tokens, tenant ID, etc.",
    )
    gl_account_mapping: Mapped[dict[str, str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Maps internal GL codes to customer chart of accounts",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (Index("ix_erp_connections_provider", "provider"),)


class ExportLog(Base):
    """Record of a journal entry export to an ERP system."""

    __tablename__ = "export_logs"

    erp_connection_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        comment="YYYY-MM format",
    )
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="success",
        nullable=False,
        comment="pending | success | failed",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_export_logs_erp_connection_id", "erp_connection_id"),
        Index("ix_export_logs_period", "period"),
    )
