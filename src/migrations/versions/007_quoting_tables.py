"""Add quotes, quote_line_items, and contracts tables.

Revision ID: 007_quoting_tables
Revises: 006
Create Date: 2026-04-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_quoting_tables"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create quotes, quote_line_items, and contracts tables."""

    # ------------------------------------------------------------------
    # 1. quotes
    # ------------------------------------------------------------------
    op.create_table(
        "quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'draft'"),
            comment="draft | sent | accepted | rejected | expired",
        ),
        sa.Column(
            "discount_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
            comment="Discount percentage (0-100)",
        ),
        sa.Column(
            "estimated_monthly",
            sa.Numeric(19, 4),
            nullable=False,
            server_default=sa.text("0"),
            comment="Estimated monthly charge",
        ),
        sa.Column(
            "estimated_total",
            sa.Numeric(19, 4),
            nullable=False,
            server_default=sa.text("0"),
            comment="Estimated total over contract term",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default=sa.text("'EUR'"),
            comment="ISO 4217 currency code",
        ),
        sa.Column(
            "term_months",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("12"),
            comment="Contract term in months",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_quotes"),
    )
    op.create_index("ix_quotes_customer_id", "quotes", ["customer_id"])
    op.create_index("ix_quotes_status", "quotes", ["status"])

    # ------------------------------------------------------------------
    # 2. quote_line_items
    # ------------------------------------------------------------------
    op.create_table(
        "quote_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "quote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quotes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column(
            "pricing_model",
            sa.String(50),
            nullable=False,
            comment="flat | usage | outcome | tiered | credit | hybrid",
        ),
        sa.Column("metric", sa.String(255), nullable=True),
        sa.Column(
            "unit_amount",
            sa.Numeric(19, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "estimated_quantity",
            sa.Numeric(19, 4),
            nullable=False,
            server_default=sa.text("0"),
            comment="Estimated units per month",
        ),
        sa.Column(
            "estimated_amount",
            sa.Numeric(19, 4),
            nullable=False,
            server_default=sa.text("0"),
            comment="unit_amount * estimated_quantity (monthly)",
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
        sa.PrimaryKeyConstraint("id", name="pk_quote_line_items"),
    )
    op.create_index(
        "ix_quote_line_items_quote_id", "quote_line_items", ["quote_id"]
    )

    # ------------------------------------------------------------------
    # 3. contracts
    # ------------------------------------------------------------------
    op.create_table(
        "contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "quote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quotes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "term_months",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("12"),
        ),
        sa.Column(
            "renewal_type",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'auto'"),
            comment="auto | manual | none",
        ),
        sa.Column(
            "early_termination_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("50"),
            comment="Early termination fee as % of remaining value",
        ),
        sa.Column(
            "auto_renewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'active'"),
            comment="active | completed | terminated",
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
        sa.PrimaryKeyConstraint("id", name="pk_contracts"),
    )
    op.create_index(
        "ix_contracts_subscription_id", "contracts", ["subscription_id"]
    )
    op.create_index("ix_contracts_status", "contracts", ["status"])
    op.create_index(
        "ix_contracts_subscription_status",
        "contracts",
        ["subscription_id", "status"],
    )


def downgrade() -> None:
    """Drop quoting tables in reverse dependency order."""
    op.drop_table("contracts")
    op.drop_table("quote_line_items")
    op.drop_table("quotes")
