"""Contract model — binds a subscription to contractual terms."""

from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ContractRenewalType(str, enum.Enum):
    """How a contract renews at end of term."""

    AUTO = "auto"
    MANUAL = "manual"
    NONE = "none"


class ContractStatus(str, enum.Enum):
    """Lifecycle states of a contract."""

    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------
class Contract(Base):
    """Contractual terms governing a subscription."""

    __tablename__ = "contracts"

    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=12,
    )
    renewal_type: Mapped[ContractRenewalType] = mapped_column(
        nullable=False,
        default=ContractRenewalType.AUTO,
    )
    early_termination_pct: Mapped[Any] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=50,
        comment="Early termination fee as % of remaining value",
    )
    auto_renewed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    status: Mapped[ContractStatus] = mapped_column(
        nullable=False,
        default=ContractStatus.ACTIVE,
    )

    # ----- Relationships -----
    quote: Mapped[Any] = relationship("Quote", lazy="selectin")
    subscription: Mapped[Any] = relationship("Subscription", lazy="selectin")

    __table_args__ = (
        Index("ix_contracts_subscription_id", "subscription_id"),
        Index("ix_contracts_status", "status"),
        Index("ix_contracts_subscription_status", "subscription_id", "status"),
    )
