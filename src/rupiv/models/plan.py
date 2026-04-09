"""Plan and PricingRule models — defines how customers are charged."""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class PricingModel(str, enum.Enum):
    """Supported pricing models."""

    FLAT = "flat"
    USAGE = "usage"
    OUTCOME = "outcome"
    TIERED = "tiered"
    CREDIT = "credit"
    HYBRID = "hybrid"


class BillingInterval(str, enum.Enum):
    """Billing cadence."""

    MONTHLY = "monthly"
    YEARLY = "yearly"


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------
class Plan(Base):
    """A product plan that groups one or more pricing rules."""

    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
        comment="ISO 4217 currency code",
    )

    # ----- Relationships -----
    pricing_rules: Mapped[list[PricingRule]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# ---------------------------------------------------------------------------
# PricingRule
# ---------------------------------------------------------------------------
class PricingRule(Base):
    """A single pricing dimension attached to a plan."""

    __tablename__ = "pricing_rules"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    pricing_model: Mapped[PricingModel] = mapped_column(
        nullable=False,
        comment="flat | usage | outcome | tiered | credit | hybrid",
    )
    metric: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Event metric name, e.g. ticket_resolved",
    )
    unit_amount: Mapped[Any | None] = mapped_column(
        Numeric(19, 4),
        nullable=True,
        comment="Per-unit price (usage/outcome models)",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
    )
    tiers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Tiered pricing brackets",
    )
    outcome_rules: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="billable_when conditions, cap_per_period",
    )
    flat_amount: Mapped[Any | None] = mapped_column(
        Numeric(19, 4),
        nullable=True,
        comment="Fixed recurring charge (flat/hybrid models)",
    )
    billing_interval: Mapped[BillingInterval | None] = mapped_column(
        nullable=True,
        comment="monthly | yearly",
    )

    # ----- Relationships -----
    plan: Mapped[Plan] = relationship(back_populates="pricing_rules")

    __table_args__ = (
        Index("ix_pricing_rules_plan_id", "plan_id"),
        Index("ix_pricing_rules_metric", "metric"),
    )
