"""Alert and AlertRule models for revenue leakage detection."""

from __future__ import annotations

import enum
import uuid as _uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class AlertType(enum.StrEnum):
    """Categories of anomaly alerts."""

    MRR_DROP = "mrr_drop"
    USAGE_SPIKE = "usage_spike"
    MISSED_INVOICE = "missed_invoice"
    VALIDATION_RATE_DROP = "validation_rate_drop"


class AlertSeverity(enum.StrEnum):
    """Alert severity levels."""

    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(enum.StrEnum):
    """Alert lifecycle states."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertRule(Base):
    """A configurable rule that triggers alerts when thresholds are breached."""

    __tablename__ = "alert_rules"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold_pct: Mapped[Any] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Trigger alert if deviation exceeds this percentage",
    )
    lookback_periods: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
        comment="Number of past periods to compare against",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_alert_rules_alert_type", "alert_type"),)


class Alert(Base):
    """A detected anomaly in billing metrics."""

    __tablename__ = "alerts"

    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[_uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        comment="NULL for global alerts (e.g. overall MRR drop)",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(Numeric(19, 4), nullable=True)
    actual_value: Mapped[str | None] = mapped_column(Numeric(19, 4), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default=AlertStatus.OPEN.value,
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_alert_type", "alert_type"),
        Index("ix_alerts_customer_id", "customer_id"),
    )
