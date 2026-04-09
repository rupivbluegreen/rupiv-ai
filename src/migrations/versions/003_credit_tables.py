"""Add credit_balances and credit_transactions tables.

Revision ID: 003_credit_tables
Revises: 002_api_keys
Create Date: 2026-04-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_credit_tables"
down_revision: str | None = "002_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create credit_balances and credit_transactions tables."""

    # ------------------------------------------------------------------
    # 1. credit_balances
    # ------------------------------------------------------------------
    op.create_table(
        "credit_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "balance",
            sa.Numeric(19, 4),
            nullable=False,
            server_default=sa.text("0"),
            comment="Current credit balance",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'EUR'"),
            comment="ISO 4217 currency code",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_credit_balances"),
        sa.UniqueConstraint("customer_id", name="uq_credit_balances_customer_id"),
    )

    # ------------------------------------------------------------------
    # 2. credit_transactions
    # ------------------------------------------------------------------
    op.create_table(
        "credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "credit_balance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_balances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transaction_type",
            sa.String(50),
            nullable=False,
            comment="purchase | consumption | refund | expiry | adjustment",
        ),
        sa.Column(
            "amount",
            sa.Numeric(19, 4),
            nullable=False,
            comment="Positive for additions, negative for deductions",
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "reference_type",
            sa.String(50),
            nullable=True,
            comment='e.g. "invoice", "event"',
        ),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_credit_transactions"),
    )
    op.create_index(
        "ix_credit_transactions_customer_id",
        "credit_transactions",
        ["customer_id"],
    )
    op.create_index(
        "ix_credit_transactions_credit_balance_id",
        "credit_transactions",
        ["credit_balance_id"],
    )


def downgrade() -> None:
    """Drop credit tables in reverse dependency order."""
    op.drop_table("credit_transactions")
    op.drop_table("credit_balances")
