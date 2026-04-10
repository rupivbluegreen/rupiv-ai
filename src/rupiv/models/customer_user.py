"""CustomerUser model — login users linked to a Customer account."""

from __future__ import annotations

import enum
import uuid as _uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base

if TYPE_CHECKING:
    from rupiv.models.customer import Customer


class CustomerUserRole(enum.StrEnum):
    """Roles for customer portal users."""

    ADMIN = "admin"
    VIEWER = "viewer"


class CustomerUser(Base):
    """A login user associated with a Customer — for portal access via JWT."""

    __tablename__ = "customer_users"

    customer_id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    clerk_user_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Clerk user ID (JWT sub claim)",
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50),
        default=CustomerUserRole.VIEWER.value,
        nullable=False,
    )

    # ----- Relationships -----
    customer: Mapped[Customer] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_customer_users_clerk_user_id", "clerk_user_id", unique=True),
        Index("ix_customer_users_customer_id", "customer_id"),
    )
