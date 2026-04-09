"""LegalEntity model — companies within a corporate group structure."""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rupiv.db import Base


class EntityType(str, enum.Enum):
    """European legal entity types."""

    BV = "bv"  # Netherlands
    GMBH = "gmbh"  # Germany, Austria, Switzerland
    SAS = "sas"  # France
    LTD = "ltd"  # UK, Ireland
    SRL = "srl"  # Italy, Romania
    AB = "ab"  # Sweden
    OY = "oy"  # Finland
    OTHER = "other"


class LegalEntity(Base):
    """A legal entity within a corporate group (BV, GmbH, SAS, Ltd, etc.)."""

    __tablename__ = "legal_entities"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(nullable=False)
    country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        comment="ISO 3166-1 alpha-2",
    )
    vat_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Chamber of commerce / company registration number",
    )
    default_currency: Mapped[str] = mapped_column(
        String(3),
        default="EUR",
        nullable=False,
        comment="ISO 4217 currency code",
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("legal_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
    )

    # ----- Relationships -----
    parent: Mapped[LegalEntity | None] = relationship(
        back_populates="children",
        remote_side="LegalEntity.id",
        lazy="selectin",
    )
    children: Mapped[list[LegalEntity]] = relationship(
        back_populates="parent",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("name", "country_code", name="uq_legal_entities_name_country"),
        Index("ix_legal_entities_parent_id", "parent_id"),
        Index("ix_legal_entities_country_code", "country_code"),
        Index("ix_legal_entities_entity_type", "entity_type"),
    )
