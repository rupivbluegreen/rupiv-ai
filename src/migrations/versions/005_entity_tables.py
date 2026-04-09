"""Add legal_entities table for multi-entity support.

Revision ID: 005_entity_tables
Revises: 004_policy_tables
Create Date: 2026-04-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_entity_tables"
down_revision: str | None = "004_policy_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create legal_entities table with self-referential hierarchy."""

    op.create_table(
        "legal_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "entity_type",
            sa.String(50),
            nullable=False,
            comment="bv | gmbh | sas | ltd | srl | ab | oy | other",
        ),
        sa.Column(
            "country_code",
            sa.String(2),
            nullable=False,
            comment="ISO 3166-1 alpha-2",
        ),
        sa.Column("vat_number", sa.String(50), nullable=True),
        sa.Column(
            "registration_number",
            sa.String(100),
            nullable=True,
            comment="Chamber of commerce / company registration number",
        ),
        sa.Column(
            "default_currency",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'EUR'"),
            comment="ISO 4217 currency code",
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_legal_entities"),
        sa.UniqueConstraint(
            "name", "country_code", name="uq_legal_entities_name_country"
        ),
    )

    op.create_index(
        "ix_legal_entities_parent_id",
        "legal_entities",
        ["parent_id"],
    )
    op.create_index(
        "ix_legal_entities_country_code",
        "legal_entities",
        ["country_code"],
    )
    op.create_index(
        "ix_legal_entities_entity_type",
        "legal_entities",
        ["entity_type"],
    )


def downgrade() -> None:
    """Drop legal_entities table."""
    op.drop_table("legal_entities")
