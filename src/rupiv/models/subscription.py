"""Subscription model — links a customer to a plan for a billing period."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base
from rupiv.models.customer import Customer
from rupiv.models.plan import Plan


class SubscriptionStatus(str, enum.Enum):
    """Lifecycle states of a subscription."""

    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"


class Subscription(Base):
    """A customer's active relationship with a plan."""

    __tablename__ = "subscriptions"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    canceled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ----- Relationships -----
    customer: Mapped[Customer] = relationship(back_populates="subscriptions")
    plan: Mapped[Plan] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_subscriptions_customer_id", "customer_id"),
        Index("ix_subscriptions_plan_id", "plan_id"),
        Index("ix_subscriptions_status", "status"),
    )
