"""LedgerEntry model — double-entry bookkeeping for A2A payments."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class EntryType(str, enum.Enum):
    """Debit or credit side of a ledger entry."""

    DEBIT = "debit"
    CREDIT = "credit"


class LedgerStatus(str, enum.Enum):
    """Settlement state of a ledger entry."""

    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"


class LedgerEntry(Base):
    """A single side of a double-entry ledger transaction.

    Every A2A payment creates exactly two entries that share the same
    ``transaction_id``: one debit (buyer) and one credit (seller).

    Note: ``updated_at`` is inherited from Base but is kept for status
    transitions (pending -> settled / failed).
    """

    __tablename__ = "ledger_entries"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
        comment="Groups the debit + credit pair",
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Agent or customer account UUID",
    )
    entry_type: Mapped[EntryType] = mapped_column(nullable=False)
    amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
    )
    status: Mapped[LedgerStatus] = mapped_column(
        nullable=False,
        default=LedgerStatus.PENDING,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="e.g. invoice, a2a_intent, refund",
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Override created_at to drop updated_at requirement from the query perspective
    created_at: Mapped[datetime] = mapped_column(  # type: ignore[assignment]
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_ledger_entries_transaction_id", "transaction_id"),
        Index("ix_ledger_entries_account_id", "account_id"),
        Index("ix_ledger_entries_status", "status"),
        Index("ix_ledger_entries_reference", "reference_type", "reference_id"),
    )
