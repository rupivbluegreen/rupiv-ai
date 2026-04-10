"""Add customer_users table for portal JWT auth.

Revision ID: 010_customer_users
Revises: 009_audit_logs
Create Date: 2026-04-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010_customer_users"
down_revision: str | None = "009_audit_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the customer_users table."""
    op.create_table(
        "customer_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "clerk_user_id",
            sa.String(255),
            unique=True,
            nullable=False,
            comment="Clerk user ID (JWT sub claim)",
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.String(50),
            nullable=False,
            server_default="viewer",
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_customer_users"),
        sa.UniqueConstraint("clerk_user_id", name="uq_customer_users_clerk_user_id"),
    )
    op.create_index(
        "ix_customer_users_clerk_user_id",
        "customer_users",
        ["clerk_user_id"],
        unique=True,
    )
    op.create_index("ix_customer_users_customer_id", "customer_users", ["customer_id"])


def downgrade() -> None:
    """Drop the customer_users table."""
    op.drop_table("customer_users")
