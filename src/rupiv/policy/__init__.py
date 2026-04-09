"""Declarative policy engine for Rupiv.ai.

Evaluates business rules against events, invoices, quotes, and outcomes.
Supports auto-approval, manual approval workflows, and rejection.
"""

from rupiv.policy.approvals import (
    ApprovalRequest,
    ApprovalState,
    check_escalation,
    create_approval_request,
    resolve_approval,
)
from rupiv.policy.engine import Condition, PolicyEngine, PolicyResult, PolicyRuleData
from rupiv.policy.rules import (
    evaluate_condition,
    evaluate_conditions,
    parse_rules_json,
    parse_rules_yaml,
)
from rupiv.policy.thresholds import ThresholdResult, ThresholdRule, check_threshold

__all__ = [
    # Engine
    "Condition",
    "PolicyEngine",
    "PolicyResult",
    "PolicyRuleData",
    # Rules
    "evaluate_condition",
    "evaluate_conditions",
    "parse_rules_json",
    "parse_rules_yaml",
    # Approvals
    "ApprovalRequest",
    "ApprovalState",
    "check_escalation",
    "create_approval_request",
    "resolve_approval",
    # Thresholds
    "ThresholdResult",
    "ThresholdRule",
    "check_threshold",
]
