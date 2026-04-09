"""Customer model — companies or individuals being billed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base

if TYPE_CHECKING:
    from rupiv.models.invoice import Invoice
    from rupiv.models.subscription import Subscription


class Customer(Base):
    """A billable entity — either a company (B2B) or individual (B2C)."""

    __tablename__ = "customers"

    external_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Caller-supplied unique identifier",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        comment="ISO 3166-1 alpha-2",
    )
    vat_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_business: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
        comment="ISO 4217 currency code",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
    )

    # ----- Relationships -----
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="customer",
        lazy="selectin",
    )
    invoices: Mapped[list[Invoice]] = relationship(
        back_populates="customer",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_customers_email", "email"),
        Index("ix_customers_country_code", "country_code"),
    )
