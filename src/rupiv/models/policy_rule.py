"""ORM models for policy rules and approval records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rupiv.db import Base


class PolicyRule(Base):
    """A declarative policy rule stored in the database."""

    __tablename__ = "policy_rules"

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Human-readable rule name",
    )
    trigger: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Event trigger, e.g. 'invoice.generated'",
    )
    conditions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="List of condition objects [{field, operator, value}]",
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="auto_approve | require_approval | reject | allow",
    )
    approver: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Required approver identity (for require_approval action)",
    )
    escalation_after_hours: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Hours before escalation (null = no escalation)",
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
        comment="Lower number = higher priority",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether the rule is currently active",
    )

    __table_args__ = (
        Index("ix_policy_rules_trigger", "trigger"),
        Index("ix_policy_rules_is_active", "is_active"),
    )


class ApprovalRecord(Base):
    """A persisted approval request linked to a policy rule."""

    __tablename__ = "approval_records"

    policy_rule_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="FK to policy_rules.id",
    )
    trigger: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="The trigger that created this approval",
    )
    context_summary: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Summary of the evaluation context",
    )
    approver: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Assigned approver identity",
    )
    state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending | approved | rejected | escalated | auto_approved",
    )
    resolved_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Identity of the resolver",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="When the approval was resolved",
    )
    escalation_deadline: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Deadline before escalation triggers",
    )

    __table_args__ = (
        Index("ix_approval_records_state", "state"),
        Index("ix_approval_records_policy_rule_id", "policy_rule_id"),
    )
