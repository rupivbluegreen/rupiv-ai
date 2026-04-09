"""Initial schema — all core tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-04-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables."""

    # ------------------------------------------------------------------
    # 1. customers
    # ------------------------------------------------------------------
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_id", sa.String(255), unique=True, nullable=False, comment="Caller-supplied unique identifier"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("billing_email", sa.String(255), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=False, comment="ISO 3166-1 alpha-2"),
        sa.Column("vat_number", sa.String(50), nullable=True),
        sa.Column("is_business", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
        sa.UniqueConstraint("external_id", name="uq_customers_external_id"),
    )
    op.create_index("ix_customers_email", "customers", ["email"])
    op.create_index("ix_customers_country_code", "customers", ["country_code"])

    # ------------------------------------------------------------------
    # 2. plans
    # ------------------------------------------------------------------
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_plans"),
    )

    # ------------------------------------------------------------------
    # 3. pricing_rules
    # ------------------------------------------------------------------
    op.create_table(
        "pricing_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pricing_model", sa.String(50), nullable=False, comment="flat | usage | outcome | tiered | credit | hybrid"),
        sa.Column("metric", sa.String(255), nullable=True, comment="Event metric name, e.g. ticket_resolved"),
        sa.Column("unit_amount", sa.Numeric(19, 4), nullable=True, comment="Per-unit price (usage/outcome models)"),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("tiers", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Tiered pricing brackets"),
        sa.Column("outcome_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="billable_when conditions, cap_per_period"),
        sa.Column("flat_amount", sa.Numeric(19, 4), nullable=True, comment="Fixed recurring charge (flat/hybrid models)"),
        sa.Column("billing_interval", sa.String(50), nullable=True, comment="monthly | yearly"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_pricing_rules"),
    )
    op.create_index("ix_pricing_rules_plan_id", "pricing_rules", ["plan_id"])
    op.create_index("ix_pricing_rules_metric", "pricing_rules", ["metric"])

    # ------------------------------------------------------------------
    # 4. subscriptions
    # ------------------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
    )
    op.create_index("ix_subscriptions_customer_id", "subscriptions", ["customer_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    # ------------------------------------------------------------------
    # 5. events
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("metric", sa.String(255), nullable=False, comment="Metric name, e.g. api_call, ticket_resolved"),
        sa.Column("properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=False, comment="Caller-supplied dedup key"),
        sa.Column("outcome_status", sa.String(50), nullable=True, comment="Set only for outcome events"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="When the event actually occurred"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.UniqueConstraint("idempotency_key", name="uq_events_idempotency_key"),
    )
    op.create_index("ix_events_customer_id", "events", ["customer_id"])
    op.create_index("ix_events_subscription_id", "events", ["subscription_id"])
    op.create_index("ix_events_metric", "events", ["metric"])
    op.create_index("ix_events_timestamp", "events", ["timestamp"])
    op.create_index("ix_events_event_type", "events", ["event_type"])

    # ------------------------------------------------------------------
    # 6. invoices
    # ------------------------------------------------------------------
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invoice_number", sa.String(50), unique=True, nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("subtotal", sa.Numeric(19, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(19, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("total", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("tax_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("tax_type", sa.String(50), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mollie_payment_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
    )
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_due_date", "invoices", ["due_date"])

    # ------------------------------------------------------------------
    # 7. invoice_line_items
    # ------------------------------------------------------------------
    op.create_table(
        "invoice_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(19, 4), nullable=False),
        sa.Column("unit_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("metric", sa.String(255), nullable=True),
        sa.Column("pricing_model", sa.String(50), nullable=True, comment="flat | usage | outcome | tiered | credit | hybrid"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_line_items"),
    )
    op.create_index("ix_invoice_line_items_invoice_id", "invoice_line_items", ["invoice_id"])

    # ------------------------------------------------------------------
    # 8. ledger_entries
    # ------------------------------------------------------------------
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False, comment="Groups the debit + credit pair"),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False, comment="Agent or customer account UUID"),
        sa.Column("entry_type", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default=sa.text("'EUR'")),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reference_type", sa.String(50), nullable=True, comment="e.g. invoice, a2a_intent, refund"),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_ledger_entries"),
    )
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])
    op.create_index("ix_ledger_entries_status", "ledger_entries", ["status"])
    op.create_index("ix_ledger_entries_reference", "ledger_entries", ["reference_type", "reference_id"])


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("ledger_entries")
    op.drop_table("invoice_line_items")
    op.drop_table("invoices")
    op.drop_table("events")
    op.drop_table("subscriptions")
    op.drop_table("pricing_rules")
    op.drop_table("plans")
    op.drop_table("customers")
