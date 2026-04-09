"""Credit balance and transaction models for credit-based billing."""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class TransactionType(str, enum.Enum):
    """Types of credit transactions."""

    PURCHASE = "purchase"
    CONSUMPTION = "consumption"
    REFUND = "refund"
    EXPIRY = "expiry"
    ADJUSTMENT = "adjustment"


# ---------------------------------------------------------------------------
# CreditBalance
# ---------------------------------------------------------------------------
class CreditBalance(Base):
    """Tracks the current credit balance for a customer.

    Each customer has at most one balance record (unique on customer_id).
    """

    __tablename__ = "credit_balances"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    balance: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        default=0,
        comment="Current credit balance",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
        comment="ISO 4217 currency code",
    )

    # ----- Relationships -----
    transactions: Mapped[list[CreditTransaction]] = relationship(
        back_populates="credit_balance",
        lazy="selectin",
    )

    __table_args__ = (UniqueConstraint("customer_id", name="uq_credit_balances_customer_id"),)


# ---------------------------------------------------------------------------
# CreditTransaction
# ---------------------------------------------------------------------------
class CreditTransaction(Base):
    """An individual credit ledger entry (purchase, consumption, refund, etc.).

    Positive ``amount`` adds credits; negative ``amount`` deducts credits.
    """

    __tablename__ = "credit_transactions"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    credit_balance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_balances.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        nullable=False,
        comment="purchase | consumption | refund | expiry | adjustment",
    )
    amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        comment="Positive for additions, negative for deductions",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment='e.g. "invoice", "event"',
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # ----- Relationships -----
    credit_balance: Mapped[CreditBalance] = relationship(
        back_populates="transactions",
    )

    __table_args__ = (
        Index("ix_credit_transactions_customer_id", "customer_id"),
        Index("ix_credit_transactions_credit_balance_id", "credit_balance_id"),
    )
