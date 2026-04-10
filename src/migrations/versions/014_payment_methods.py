"""Add payment_methods table.

Revision ID: 014_payment_methods
Revises: 013_transformation_rules
Create Date: 2026-04-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_payment_methods"
down_revision: str | None = "013_transformation_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the payment_methods table."""
    op.create_table(
        "payment_methods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("provider_method_id", sa.String(255), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_four", sa.String(4), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_payment_methods"),
    )
    op.create_index("ix_payment_methods_customer_id", "payment_methods", ["customer_id"])
    op.create_index(
        "ix_payment_methods_customer_default",
        "payment_methods",
        ["customer_id", "is_default"],
    )


def downgrade() -> None:
    """Drop the payment_methods table."""
    op.drop_table("payment_methods")
