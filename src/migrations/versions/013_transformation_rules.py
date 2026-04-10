"""Add transformation_rules table.

Revision ID: 013_transformation_rules
Revises: 012_erp_connections
Create Date: 2026-04-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013_transformation_rules"
down_revision: str | None = "012_erp_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the transformation_rules table."""
    op.create_table(
        "transformation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_metric", sa.String(255), nullable=False),
        sa.Column("target_metric", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_transformation_rules"),
    )
    op.create_index(
        "ix_transformation_rules_source_metric",
        "transformation_rules",
        ["source_metric"],
    )
    op.create_index(
        "ix_transformation_rules_is_active",
        "transformation_rules",
        ["is_active"],
    )


def downgrade() -> None:
    """Drop the transformation_rules table."""
    op.drop_table("transformation_rules")
