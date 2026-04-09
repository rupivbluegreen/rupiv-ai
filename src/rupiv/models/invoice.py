"""Invoice and InvoiceLineItem models."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base
from rupiv.models.customer import Customer


class InvoiceStatus(str, enum.Enum):
    """Invoice lifecycle states."""

    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class TaxType(str, enum.Enum):
    """EU VAT treatment."""

    STANDARD = "standard"
    REVERSE_CHARGE = "reverse_charge"


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------
class Invoice(Base):
    """An invoice generated for a billing period."""

    __tablename__ = "invoices"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invoice_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        nullable=False,
        default=InvoiceStatus.DRAFT,
    )

    # ----- Money columns (NUMERIC(19,4), never Float) -----
    subtotal: Mapped[Any] = mapped_column(Numeric(19, 4), nullable=False)
    tax_amount: Mapped[Any] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    total: Mapped[Any] = mapped_column(Numeric(19, 4), nullable=False)

    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    tax_rate: Mapped[Any | None] = mapped_column(Numeric(5, 4), nullable=True)
    tax_type: Mapped[TaxType | None] = mapped_column(nullable=True)

    # ----- Period & dates -----
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ----- Payment provider -----
    mollie_payment_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ----- Relationships -----
    customer: Mapped[Customer] = relationship(back_populates="invoices")
    line_items: Mapped[list[InvoiceLineItem]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_invoices_customer_id", "customer_id"),
        Index("ix_invoices_subscription_id", "subscription_id"),
        Index("ix_invoices_status", "status"),
        Index("ix_invoices_due_date", "due_date"),
    )


# ---------------------------------------------------------------------------
# InvoiceLineItem
# ---------------------------------------------------------------------------
class InvoiceLineItem(Base):
    """A single charge line on an invoice."""

    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Any] = mapped_column(Numeric(19, 4), nullable=False)
    unit_amount: Mapped[Any] = mapped_column(Numeric(19, 4), nullable=False)
    amount: Mapped[Any] = mapped_column(Numeric(19, 4), nullable=False)
    metric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pricing_model: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="flat | usage | outcome | tiered | credit | hybrid",
    )

    # ----- Relationships -----
    invoice: Mapped[Invoice] = relationship(back_populates="line_items")

    __table_args__ = (Index("ix_invoice_line_items_invoice_id", "invoice_id"),)
