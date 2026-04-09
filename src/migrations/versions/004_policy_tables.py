"""Add policy_rules and approval_records tables.

Revision ID: 004_policy_tables
Revises: 003_credit_tables
Create Date: 2026-04-09
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_policy_tables"
down_revision: str | None = "003_credit_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create policy_rules and approval_records tables."""

    # ------------------------------------------------------------------
    # 1. policy_rules
    # ------------------------------------------------------------------
    op.create_table(
        "policy_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
            unique=True,
            comment="Human-readable rule name",
        ),
        sa.Column(
            "trigger",
            sa.String(255),
            nullable=False,
            comment="Event trigger, e.g. 'invoice.generated'",
        ),
        sa.Column(
            "conditions",
            postgresql.JSONB(),
            nullable=False,
            comment="List of condition objects [{field, operator, value}]",
        ),
        sa.Column(
            "action",
            sa.String(50),
            nullable=False,
            comment="auto_approve | require_approval | reject | allow",
        ),
        sa.Column(
            "approver",
            sa.String(255),
            nullable=True,
            comment="Required approver identity",
        ),
        sa.Column(
            "escalation_after_hours",
            sa.Integer(),
            nullable=True,
            comment="Hours before escalation",
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
            comment="Lower number = higher priority",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Whether the rule is currently active",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_policy_rules"),
        sa.UniqueConstraint("name", name="uq_policy_rules_name"),
    )
    op.create_index("ix_policy_rules_trigger", "policy_rules", ["trigger"])
    op.create_index("ix_policy_rules_is_active", "policy_rules", ["is_active"])

    # ------------------------------------------------------------------
    # 2. approval_records
    # ------------------------------------------------------------------
    op.create_table(
        "approval_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "policy_rule_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="FK to policy_rules.id",
        ),
        sa.Column(
            "trigger",
            sa.String(255),
            nullable=False,
            comment="The trigger that created this approval",
        ),
        sa.Column(
            "context_summary",
            postgresql.JSONB(),
            nullable=False,
            comment="Summary of the evaluation context",
        ),
        sa.Column(
            "approver",
            sa.String(255),
            nullable=False,
            comment="Assigned approver identity",
        ),
        sa.Column(
            "state",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'pending'"),
            comment="pending | approved | rejected | escalated | auto_approved",
        ),
        sa.Column(
            "resolved_by",
            sa.String(255),
            nullable=True,
            comment="Identity of the resolver",
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(),
            nullable=True,
            comment="When the approval was resolved",
        ),
        sa.Column(
            "escalation_deadline",
            sa.DateTime(),
            nullable=True,
            comment="Deadline before escalation triggers",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_approval_records"),
    )
    op.create_index("ix_approval_records_state", "approval_records", ["state"])
    op.create_index(
        "ix_approval_records_policy_rule_id",
        "approval_records",
        ["policy_rule_id"],
    )


def downgrade() -> None:
    """Drop policy tables in reverse dependency order."""
    op.drop_table("approval_records")
    op.drop_table("policy_rules")
