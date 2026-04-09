"""Revenue schedule ORM models (IFRS 15).

``RevenueSchedule`` tracks the overall recognition plan for a subscription's
performance obligation.  ``RevenueEntry`` stores the per-period recognised /
deferred amounts and the corresponding GL accounts.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ScheduleStatus(str, enum.Enum):
    """Lifecycle states of a revenue schedule."""

    ACTIVE = "active"
    COMPLETED = "completed"
    VOIDED = "voided"


class EntryType(str, enum.Enum):
    """Types of revenue entries."""

    RECOGNIZED = "recognized"
    DEFERRED = "deferred"
    ADJUSTMENT = "adjustment"


# ---------------------------------------------------------------------------
# RevenueSchedule
# ---------------------------------------------------------------------------


class RevenueSchedule(Base):
    """Aggregate revenue recognition plan for one obligation on a subscription."""

    __tablename__ = "revenue_schedules"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    obligation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="platform_access | outcome_delivery | usage_consumption | support",
    )
    recognition_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="over_time | point_in_time",
    )
    total_amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        comment="Total allocated transaction price",
    )
    recognized_amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        default=0,
        comment="Cumulative recognised revenue",
    )
    deferred_amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        default=0,
        comment="Remaining deferred revenue",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
        comment="ISO 4217 currency code",
    )
    status: Mapped[ScheduleStatus] = mapped_column(
        nullable=False,
        default=ScheduleStatus.ACTIVE,
    )

    # ----- Relationships -----
    entries: Mapped[list[RevenueEntry]] = relationship(
        back_populates="schedule",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_revenue_schedules_subscription_id", "subscription_id"),
    )


# ---------------------------------------------------------------------------
# RevenueEntry
# ---------------------------------------------------------------------------


class RevenueEntry(Base):
    """A single period's revenue recognition entry within a schedule."""

    __tablename__ = "revenue_entries"

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("revenue_schedules.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        comment="YYYY-MM period",
    )
    amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
    )
    entry_type: Mapped[EntryType] = mapped_column(
        nullable=False,
        default=EntryType.RECOGNIZED,
    )
    gl_debit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="GL debit account code",
    )
    gl_credit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="GL credit account code",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    # ----- Relationships -----
    schedule: Mapped[RevenueSchedule] = relationship(back_populates="entries")

    __table_args__ = (
        Index("ix_revenue_entries_schedule_id", "schedule_id"),
        Index("ix_revenue_entries_period", "period"),
    )
