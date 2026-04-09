"""Tests for the declarative policy engine.

Covers rule evaluation, priority ordering, dot-path field access,
threshold checks, YAML/JSON parsing, and the approval lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from rupiv.policy.approvals import (
    ApprovalRequest,
    ApprovalState,
    check_escalation,
    create_approval_request,
    resolve_approval,
)
from rupiv.policy.engine import Condition, PolicyEngine, PolicyResult, PolicyRuleData
from rupiv.policy.rules import evaluate_condition, evaluate_conditions, parse_rules_json, parse_rules_yaml
from rupiv.policy.thresholds import ThresholdResult, ThresholdRule, check_threshold


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> PolicyEngine:
    return PolicyEngine()


@pytest.fixture()
def small_invoice_context() -> dict:
    return {"invoice": {"total": Decimal("2500"), "currency": "EUR"}}


@pytest.fixture()
def large_invoice_context() -> dict:
    return {"invoice": {"total": Decimal("75000"), "currency": "EUR"}}


@pytest.fixture()
def low_csat_context() -> dict:
    return {
        "outcome": {
            "properties": {"csat_score": 1.5, "escalated": False},
        },
    }


@pytest.fixture()
def auto_approve_rule() -> PolicyRuleData:
    return PolicyRuleData(
        name="Auto-approve small invoices",
        trigger="invoice.generated",
        conditions=[
            Condition(field="invoice.total", operator="lt", value=5000),
        ],
        action="auto_approve",
        priority=10,
    )


@pytest.fixture()
def require_approval_rule() -> PolicyRuleData:
    return PolicyRuleData(
        name="CFO approval for large invoices",
        trigger="invoice.generated",
        conditions=[
            Condition(field="invoice.total", operator="gte", value=50000),
        ],
        action="require_approval",
        approver="cfo",
        escalation_after_hours=24,
        priority=20,
    )


@pytest.fixture()
def reject_low_csat_rule() -> PolicyRuleData:
    return PolicyRuleData(
        name="Reject low CSAT outcomes",
        trigger="outcome.validated",
        conditions=[
            Condition(field="outcome.properties.csat_score", operator="lt", value=2.0),
        ],
        action="reject",
        priority=5,
    )


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------


class TestPolicyEngine:
    def test_auto_approve_small_invoice(
        self,
        engine: PolicyEngine,
        small_invoice_context: dict,
        auto_approve_rule: PolicyRuleData,
    ) -> None:
        result = engine.evaluate(small_invoice_context, [auto_approve_rule])
        assert result.matched is True
        assert result.action == "auto_approve"
        assert result.rule_name == "Auto-approve small invoices"

    def test_require_approval_large_invoice(
        self,
        engine: PolicyEngine,
        large_invoice_context: dict,
        require_approval_rule: PolicyRuleData,
    ) -> None:
        result = engine.evaluate(large_invoice_context, [require_approval_rule])
        assert result.matched is True
        assert result.action == "require_approval"
        assert result.approver == "cfo"

    def test_reject_low_csat(
        self,
        engine: PolicyEngine,
        low_csat_context: dict,
        reject_low_csat_rule: PolicyRuleData,
    ) -> None:
        result = engine.evaluate(low_csat_context, [reject_low_csat_rule])
        assert result.matched is True
        assert result.action == "reject"

    def test_no_matching_rules(
        self,
        engine: PolicyEngine,
        large_invoice_context: dict,
        auto_approve_rule: PolicyRuleData,
    ) -> None:
        """When no rules match, the engine returns 'allow' (default pass-through)."""
        result = engine.evaluate(large_invoice_context, [auto_approve_rule])
        assert result.matched is False
        assert result.action == "allow"

    def test_reject_wins_over_approve(
        self,
        engine: PolicyEngine,
    ) -> None:
        """If both reject and approve rules match, reject takes precedence."""
        context = {"invoice": {"total": Decimal("100")}}

        approve_rule = PolicyRuleData(
            name="Approve all",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="gt", value=0),
            ],
            action="auto_approve",
            priority=10,
        )
        reject_rule = PolicyRuleData(
            name="Reject all",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="gt", value=0),
            ],
            action="reject",
            priority=20,  # Lower priority (evaluated later) but reject still wins
        )

        result = engine.evaluate(context, [approve_rule, reject_rule])
        assert result.action == "reject"
        assert result.rule_name == "Reject all"

    def test_priority_ordering(
        self,
        engine: PolicyEngine,
    ) -> None:
        """Lower priority number is evaluated first and wins (for non-reject)."""
        context = {"invoice": {"total": Decimal("100")}}

        low_priority = PolicyRuleData(
            name="Low priority allow",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="gt", value=0),
            ],
            action="allow",
            priority=100,
        )
        high_priority = PolicyRuleData(
            name="High priority approve",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="gt", value=0),
            ],
            action="auto_approve",
            priority=1,
        )

        result = engine.evaluate(context, [low_priority, high_priority])
        assert result.rule_name == "High priority approve"
        assert result.action == "auto_approve"

    def test_evaluate_all(
        self,
        engine: PolicyEngine,
    ) -> None:
        """evaluate_all returns ALL matching results."""
        context = {"invoice": {"total": Decimal("100")}}

        rules = [
            PolicyRuleData(
                name="Rule A",
                trigger="invoice.generated",
                conditions=[Condition(field="invoice.total", operator="gt", value=0)],
                action="auto_approve",
                priority=10,
            ),
            PolicyRuleData(
                name="Rule B",
                trigger="invoice.generated",
                conditions=[Condition(field="invoice.total", operator="lt", value=500)],
                action="allow",
                priority=20,
            ),
            PolicyRuleData(
                name="Rule C (no match)",
                trigger="invoice.generated",
                conditions=[Condition(field="invoice.total", operator="gt", value=9999)],
                action="reject",
                priority=5,
            ),
        ]

        results = engine.evaluate_all(context, rules)
        assert len(results) == 2
        assert results[0].rule_name == "Rule A"
        assert results[1].rule_name == "Rule B"


# ---------------------------------------------------------------------------
# Condition evaluation tests
# ---------------------------------------------------------------------------


class TestConditionEvaluation:
    def test_dot_path_field_access(self) -> None:
        """Dot-path 'invoice.customer.country_code' resolves correctly."""
        context = {
            "invoice": {
                "customer": {
                    "country_code": "NL",
                },
                "total": Decimal("1000"),
            },
        }
        condition = Condition(field="invoice.customer.country_code", operator="eq", value="NL")
        assert evaluate_condition(condition, context) is True

    def test_missing_field_returns_false(self) -> None:
        context = {"invoice": {"total": Decimal("100")}}
        condition = Condition(field="invoice.nonexistent", operator="eq", value="x")
        assert evaluate_condition(condition, context) is False

    def test_in_operator(self) -> None:
        context = {"invoice": {"currency": "EUR"}}
        condition = Condition(field="invoice.currency", operator="in", value=["EUR", "USD"])
        assert evaluate_condition(condition, context) is True

    def test_not_in_operator(self) -> None:
        context = {"invoice": {"currency": "GBP"}}
        condition = Condition(field="invoice.currency", operator="not_in", value=["EUR", "USD"])
        assert evaluate_condition(condition, context) is True

    def test_contains_operator(self) -> None:
        context = {"invoice": {"description": "monthly subscription fee"}}
        condition = Condition(field="invoice.description", operator="contains", value="subscription")
        assert evaluate_condition(condition, context) is True

    def test_decimal_coercion(self) -> None:
        """Integer rule values are coerced to Decimal for comparison."""
        context = {"invoice": {"total": Decimal("4999.99")}}
        condition = Condition(field="invoice.total", operator="lt", value=5000)
        assert evaluate_condition(condition, context) is True

    def test_evaluate_conditions_and_logic(self) -> None:
        """All conditions must be true (AND logic)."""
        context = {"invoice": {"total": Decimal("3000"), "currency": "EUR"}}
        conditions = [
            Condition(field="invoice.total", operator="lt", value=5000),
            Condition(field="invoice.currency", operator="eq", value="EUR"),
        ]
        assert evaluate_conditions(conditions, context) is True

    def test_evaluate_conditions_empty_list(self) -> None:
        """Empty condition list is vacuously true."""
        assert evaluate_conditions([], {"anything": "here"}) is True


# ---------------------------------------------------------------------------
# Threshold tests
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_threshold_within_limit(self) -> None:
        entity_id = uuid.uuid4()
        threshold = ThresholdRule(
            entity_id=entity_id,
            metric="monthly_spend",
            limit=Decimal("10000"),
            period="monthly",
            currency="EUR",
        )

        result = check_threshold(
            session=None,
            entity_id=entity_id,
            metric="monthly_spend",
            current_value=Decimal("5000"),
            threshold=threshold,
        )

        assert result.within_limit is True
        assert result.current_value == Decimal("5000")
        assert result.limit == Decimal("10000")
        assert result.remaining == Decimal("5000")
        assert result.pct_used == Decimal("50.0000")

    def test_threshold_exceeded(self) -> None:
        entity_id = uuid.uuid4()
        threshold = ThresholdRule(
            entity_id=entity_id,
            metric="monthly_spend",
            limit=Decimal("10000"),
            period="monthly",
            currency="EUR",
        )

        result = check_threshold(
            session=None,
            entity_id=entity_id,
            metric="monthly_spend",
            current_value=Decimal("10000"),
            threshold=threshold,
        )

        assert result.within_limit is False
        assert result.remaining == Decimal("0")
        assert result.pct_used == Decimal("100.0000")

    def test_threshold_over_limit(self) -> None:
        entity_id = uuid.uuid4()
        threshold = ThresholdRule(
            entity_id=entity_id,
            metric="monthly_spend",
            limit=Decimal("10000"),
            period="monthly",
        )

        result = check_threshold(
            session=None,
            entity_id=entity_id,
            metric="monthly_spend",
            current_value=Decimal("15000"),
            threshold=threshold,
        )

        assert result.within_limit is False
        assert result.remaining == Decimal("0")


# ---------------------------------------------------------------------------
# Rule parsing tests
# ---------------------------------------------------------------------------


class TestRuleParsing:
    def test_parse_yaml_rules(self) -> None:
        yaml_str = """\
rules:
  - name: "Auto-approve small invoices"
    trigger: "invoice.generated"
    conditions:
      - field: "invoice.total"
        operator: "lt"
        value: 5000
    action: "auto_approve"
    priority: 10
  - name: "CFO approval for large invoices"
    trigger: "invoice.generated"
    conditions:
      - field: "invoice.total"
        operator: "gte"
        value: 50000
    action: "require_approval"
    approver: "cfo"
    escalation_after_hours: 24
    priority: 20
"""
        rules = parse_rules_yaml(yaml_str)
        assert len(rules) == 2
        assert rules[0].name == "Auto-approve small invoices"
        assert rules[0].action == "auto_approve"
        assert rules[0].priority == 10
        assert len(rules[0].conditions) == 1
        assert rules[0].conditions[0].field == "invoice.total"
        assert rules[0].conditions[0].operator == "lt"
        assert rules[1].approver == "cfo"
        assert rules[1].escalation_after_hours == 24

    def test_parse_json_rules(self) -> None:
        import json

        data = {
            "rules": [
                {
                    "name": "Reject high risk",
                    "trigger": "payment.initiated",
                    "conditions": [
                        {"field": "payment.risk_score", "operator": "gt", "value": 90},
                    ],
                    "action": "reject",
                    "priority": 1,
                },
            ],
        }
        rules = parse_rules_json(json.dumps(data))
        assert len(rules) == 1
        assert rules[0].name == "Reject high risk"
        assert rules[0].action == "reject"


# ---------------------------------------------------------------------------
# Approval lifecycle tests
# ---------------------------------------------------------------------------


class TestApprovalLifecycle:
    def test_approval_lifecycle(self) -> None:
        """Create an approval request, then resolve it, and verify state changes."""
        rule_result = PolicyResult(
            rule_name="CFO approval for large invoices",
            action="require_approval",
            approver="cfo",
            reason="Rule 'CFO approval for large invoices' matched",
            matched=True,
        )
        context = {"invoice": {"total": Decimal("75000"), "currency": "EUR"}}

        # Create
        request = create_approval_request(
            rule_result,
            context,
            escalation_after_hours=24,
        )
        assert request.state == ApprovalState.PENDING
        assert request.approver == "cfo"
        assert request.escalation_deadline is not None
        assert request.resolved_at is None

        # Should not be escalated yet
        assert check_escalation(request) is False

        # Resolve
        resolved = resolve_approval(request, "approved", resolved_by="cfo@example.com")
        assert resolved.state == ApprovalState.APPROVED
        assert resolved.resolved_at is not None
        assert resolved.id == request.id

    def test_resolve_already_resolved_raises(self) -> None:
        """Cannot resolve an already-resolved request."""
        rule_result = PolicyResult(
            rule_name="test",
            action="require_approval",
            approver="admin",
            matched=True,
        )
        request = create_approval_request(rule_result, {})
        resolved = resolve_approval(request, "approved", resolved_by="admin")

        with pytest.raises(ValueError, match="Cannot resolve"):
            resolve_approval(resolved, "rejected", resolved_by="someone")

    def test_invalid_decision_raises(self) -> None:
        rule_result = PolicyResult(
            rule_name="test",
            action="require_approval",
            approver="admin",
            matched=True,
        )
        request = create_approval_request(rule_result, {})

        with pytest.raises(ValueError, match="Invalid decision"):
            resolve_approval(request, "maybe", resolved_by="admin")

    def test_escalation_past_deadline(self) -> None:
        """check_escalation returns True when past the deadline."""
        request = ApprovalRequest(
            id=uuid.uuid4(),
            rule_name="test",
            trigger="test.trigger",
            context_summary={},
            approver="admin",
            state=ApprovalState.PENDING,
            created_at=datetime.now(timezone.utc) - timedelta(hours=48),
            escalation_deadline=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert check_escalation(request) is True

    def test_escalation_no_deadline(self) -> None:
        """check_escalation returns False when there is no deadline."""
        request = ApprovalRequest(
            id=uuid.uuid4(),
            rule_name="test",
            trigger="test.trigger",
            context_summary={},
            approver="admin",
            state=ApprovalState.PENDING,
            created_at=datetime.now(timezone.utc),
            escalation_deadline=None,
        )
        assert check_escalation(request) is False
