"""Add payment_cost_records table.

Revision ID: 008_payment_cost_table
Revises: 007_quoting_tables
Create Date: 2026-04-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "008_payment_cost_table"
down_revision: str | None = "007_quoting_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_cost_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("psp", sa.String(50), nullable=False),
        sa.Column("payment_id", sa.String(255), nullable=False),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("gross_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("fee_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("net_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("payment_method", sa.String(50), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_payment_cost_records_psp", "payment_cost_records", ["psp"])
    op.create_index("ix_payment_cost_records_created_at", "payment_cost_records", ["created_at"])
    op.create_index("ix_payment_cost_records_invoice_id", "payment_cost_records", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_cost_records_invoice_id", table_name="payment_cost_records")
    op.drop_index("ix_payment_cost_records_created_at", table_name="payment_cost_records")
    op.drop_index("ix_payment_cost_records_psp", table_name="payment_cost_records")
    op.drop_table("payment_cost_records")
