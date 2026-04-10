"""PaymentMethod model — stored customer payment instruments."""

from __future__ import annotations

import uuid as _uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class PaymentMethod(Base):
    """A stored payment instrument (card, iDEAL, SEPA mandate) for a customer."""

    __tablename__ = "payment_methods"

    customer_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="mollie | stripe | adyen",
    )
    type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="card | ideal | sepa_direct_debit | bancontact",
    )
    provider_method_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="External ID at the PSP (e.g. Mollie mandate ID, Stripe PM ID)",
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
    )

    __table_args__ = (
        Index("ix_payment_methods_customer_id", "customer_id"),
        Index("ix_payment_methods_customer_default", "customer_id", "is_default"),
    )
