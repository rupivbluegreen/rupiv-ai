"""TransformationRule model — rules for transforming raw events into billing format."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class TransformationRule(Base):
    """A rule that transforms raw event data before billing ingestion."""

    __tablename__ = "transformation_rules"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_metric: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Input event metric to match",
    )
    target_metric: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Output metric name after transformation",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Ordered array of transformation step objects",
    )

    __table_args__ = (
        Index("ix_transformation_rules_source_metric", "source_metric"),
        Index("ix_transformation_rules_is_active", "is_active"),
    )
