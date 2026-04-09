"""PaymentCostRecord model — tracks fees charged by each PSP per transaction."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class PaymentCostRecord(Base):
    """A record of the fee charged by a PSP for a single payment."""

    __tablename__ = "payment_cost_records"

    psp: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Payment service provider name, e.g. mollie, adyen",
    )
    payment_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="PSP-specific payment identifier",
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
    )
    gross_amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        comment="Total payment amount before fees",
    )
    fee_amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        comment="Fee charged by the PSP",
    )
    net_amount: Mapped[Any] = mapped_column(
        Numeric(19, 4),
        nullable=False,
        comment="Amount received after fees (gross - fee)",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
        comment="ISO 4217 currency code",
    )
    payment_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Payment method, e.g. ideal, card, sepa_dd, bancontact",
    )
    country_code: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
        comment="ISO 3166-1 alpha-2 country of the payer",
    )

    __table_args__ = (
        Index("ix_payment_cost_records_psp", "psp"),
        Index("ix_payment_cost_records_created_at", "created_at"),
        Index("ix_payment_cost_records_invoice_id", "invoice_id"),
    )
