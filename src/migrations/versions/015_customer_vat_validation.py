"""Add vat_valid and vat_validated_at columns to customers.

Revision ID: 015_customer_vat_validation
Revises: 014_payment_methods
Create Date: 2026-04-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_customer_vat_validation"
down_revision: str | None = "014_payment_methods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add VAT validation columns to customers table."""
    op.add_column("customers", sa.Column("vat_valid", sa.Boolean(), nullable=True))
    op.add_column(
        "customers",
        sa.Column("vat_validated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove VAT validation columns from customers table."""
    op.drop_column("customers", "vat_validated_at")
    op.drop_column("customers", "vat_valid")
