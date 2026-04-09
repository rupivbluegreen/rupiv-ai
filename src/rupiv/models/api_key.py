"""ApiKey model — hashed API keys for customer authentication."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base

if TYPE_CHECKING:
    from rupiv.models.customer import Customer


class ApiKey(Base):
    """An API key bound to a customer account.

    Only the SHA-256 hash of the key is stored.  The full key is returned
    exactly once at creation time and can never be retrieved again.
    """

    __tablename__ = "api_keys"

    customer_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    key_prefix: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="e.g. rp_live_ or rp_test_",
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="SHA-256 hex digest of the full API key",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable label for the key",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    scopes: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="Allowed scopes; null means all scopes",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # ----- Relationships -----
    customer: Mapped[Customer] = relationship(
        back_populates="api_keys",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_api_keys_key_hash", "key_hash", unique=True),
        Index("ix_api_keys_customer_id", "customer_id"),
    )
