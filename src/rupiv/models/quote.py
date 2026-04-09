"""Quote and QuoteLineItem models — pricing proposals sent to customers."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class QuoteStatus(str, enum.Enum):
    """Lifecycle states of a quote."""

    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Quote
# ---------------------------------------------------------------------------
class Quote(Base):
    """A pricing proposal for a customer based on a plan."""

    __tablename__ = "quotes"

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
    status: Mapped[QuoteStatus] = mapped_column(
        nullable=False,
        default=QuoteStatus.DRAFT,
    )
    discount_pct: Mapped[Any] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=0,
        comment="Discount percentage (0-100)",
    )
    estimated_monthly: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        default=0,
        comment="Estimated monthly charge",
    )
    estimated_total: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        default=0,
        comment="Estimated total over contract term",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
        comment="ISO 4217 currency code",
    )
    term_months: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=12,
        comment="Contract term in months",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ----- Relationships -----
    line_items: Mapped[list[QuoteLineItem]] = relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    customer: Mapped[Any] = relationship("Customer", lazy="selectin")
    plan: Mapped[Any] = relationship("Plan", lazy="selectin")

    __table_args__ = (
        Index("ix_quotes_customer_id", "customer_id"),
        Index("ix_quotes_status", "status"),
    )


# ---------------------------------------------------------------------------
# QuoteLineItem
# ---------------------------------------------------------------------------
class QuoteLineItem(Base):
    """A single line item on a quote, derived from a pricing rule."""

    __tablename__ = "quote_line_items"

    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    pricing_model: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="flat | usage | outcome | tiered | credit | hybrid",
    )
    metric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit_amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        default=0,
    )
    estimated_quantity: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        default=0,
        comment="Estimated units per month",
    )
    estimated_amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        default=0,
        comment="unit_amount * estimated_quantity (monthly)",
    )

    # ----- Relationships -----
    quote: Mapped[Quote] = relationship(back_populates="line_items")

    __table_args__ = (
        Index("ix_quote_line_items_quote_id", "quote_id"),
    )
