"""Add revenue_schedules and revenue_entries tables (IFRS 15).

Revision ID: 006_revenue_tables
Revises: 005_entity_tables
Create Date: 2026-04-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_revenue_tables"
down_revision: str | None = "005_entity_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create revenue_schedules and revenue_entries tables."""

    # ------------------------------------------------------------------
    # 1. revenue_schedules
    # ------------------------------------------------------------------
    op.create_table(
        "revenue_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "obligation_type",
            sa.String(50),
            nullable=False,
            comment="platform_access | outcome_delivery | usage_consumption | support",
        ),
        sa.Column(
            "recognition_method",
            sa.String(50),
            nullable=False,
            comment="over_time | point_in_time",
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(19, 4),
            nullable=False,
            comment="Total allocated transaction price",
        ),
        sa.Column(
            "recognized_amount",
            sa.Numeric(19, 4),
            nullable=False,
            server_default=sa.text("0"),
            comment="Cumulative recognised revenue",
        ),
        sa.Column(
            "deferred_amount",
            sa.Numeric(19, 4),
            nullable=False,
            server_default=sa.text("0"),
            comment="Remaining deferred revenue",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'EUR'"),
            comment="ISO 4217 currency code",
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'active'"),
            comment="active | completed | voided",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_revenue_schedules"),
    )
    op.create_index(
        "ix_revenue_schedules_subscription_id",
        "revenue_schedules",
        ["subscription_id"],
    )

    # ------------------------------------------------------------------
    # 2. revenue_entries
    # ------------------------------------------------------------------
    op.create_table(
        "revenue_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("revenue_schedules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "period",
            sa.String(7),
            nullable=False,
            comment="YYYY-MM period",
        ),
        sa.Column(
            "amount",
            sa.Numeric(19, 4),
            nullable=False,
        ),
        sa.Column(
            "entry_type",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'recognized'"),
            comment="recognized | deferred | adjustment",
        ),
        sa.Column(
            "gl_debit",
            sa.String(50),
            nullable=False,
            comment="GL debit account code",
        ),
        sa.Column(
            "gl_credit",
            sa.String(50),
            nullable=False,
            comment="GL credit account code",
        ),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_revenue_entries"),
    )
    op.create_index(
        "ix_revenue_entries_schedule_id",
        "revenue_entries",
        ["schedule_id"],
    )
    op.create_index(
        "ix_revenue_entries_period",
        "revenue_entries",
        ["period"],
    )


def downgrade() -> None:
    """Drop revenue tables in reverse dependency order."""
    op.drop_table("revenue_entries")
    op.drop_table("revenue_schedules")
