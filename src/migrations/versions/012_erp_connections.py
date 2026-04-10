"""Add erp_connections and export_logs tables.

Revision ID: 012_erp_connections
Revises: 011_alerts
Create Date: 2026-04-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_erp_connections"
down_revision: str | None = "011_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create erp_connections and export_logs tables."""
    op.create_table(
        "erp_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.Column("gl_account_mapping", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_erp_connections"),
    )
    op.create_index("ix_erp_connections_provider", "erp_connections", ["provider"])

    op.create_table(
        "export_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "erp_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_export_logs"),
    )
    op.create_index("ix_export_logs_erp_connection_id", "export_logs", ["erp_connection_id"])
    op.create_index("ix_export_logs_period", "export_logs", ["period"])


def downgrade() -> None:
    """Drop export_logs and erp_connections tables."""
    op.drop_table("export_logs")
    op.drop_table("erp_connections")
