"""End-to-end policy enforcement tests — direct PolicyEngine evaluation."""

from __future__ import annotations

from typing import Any

from rupiv.policy.engine import PolicyEngine
from rupiv.policy.rules import Condition, PolicyResult, PolicyRuleData


async def test_policy_auto_approve() -> None:
    """Small invoice amount triggers auto-approve; large triggers require_approval."""
    engine = PolicyEngine()

    rules: list[PolicyRuleData] = [
        PolicyRuleData(
            name="Auto-approve small invoices",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="lt", value=5000),
            ],
            action="auto_approve",
            priority=10,
        ),
        PolicyRuleData(
            name="CFO approval for large invoices",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="gte", value=50000),
            ],
            action="require_approval",
            approver="cfo",
            escalation_after_hours=24,
            priority=20,
        ),
    ]

    # --- Case 1: Small invoice (EUR 1 000) -> auto_approve ---
    small_ctx: dict[str, Any] = {"invoice": {"total": 1000}}
    result: PolicyResult = engine.evaluate(small_ctx, rules)

    assert result.matched is True, "Small invoice should match a rule"
    assert result.action == "auto_approve", f"Expected auto_approve, got {result.action}"
    assert result.rule_name == "Auto-approve small invoices", "Rule name mismatch"

    # --- Case 2: Large invoice (EUR 75 000) -> require_approval ---
    large_ctx: dict[str, Any] = {"invoice": {"total": 75000}}
    result = engine.evaluate(large_ctx, rules)

    assert result.matched is True, "Large invoice should match a rule"
    assert result.action == "require_approval", f"Expected require_approval, got {result.action}"
    assert result.rule_name == "CFO approval for large invoices", "Rule name mismatch"
    assert result.approver == "cfo", "Approver should be cfo"

    # --- Case 3: Mid-range invoice (EUR 25 000) -> no rule matches -> allow ---
    mid_ctx: dict[str, Any] = {"invoice": {"total": 25000}}
    result = engine.evaluate(mid_ctx, rules)

    assert result.matched is False, "Mid-range invoice should not match any rule"
    assert result.action == "allow", f"Expected allow (default), got {result.action}"


async def test_policy_reject_low_csat() -> None:
    """Low CSAT outcome triggers rejection; high CSAT passes through."""
    engine = PolicyEngine()

    rules: list[PolicyRuleData] = [
        PolicyRuleData(
            name="Reject low-CSAT outcomes",
            trigger="outcome.validated",
            conditions=[
                Condition(
                    field="outcome.properties.csat_score",
                    operator="lt",
                    value=2.0,
                ),
            ],
            action="reject",
            priority=10,
        ),
    ]

    # --- Case 1: Low CSAT (1.5) -> reject ---
    low_csat_ctx: dict[str, Any] = {
        "outcome": {
            "metric": "ticket_resolved",
            "properties": {
                "csat_score": 1.5,
                "resolution_time": 120,
                "escalated": False,
            },
        },
    }
    result: PolicyResult = engine.evaluate(low_csat_ctx, rules)

    assert result.matched is True, "Low CSAT should match reject rule"
    assert result.action == "reject", f"Expected reject, got {result.action}"
    assert result.rule_name == "Reject low-CSAT outcomes", "Rule name mismatch"

    # --- Case 2: High CSAT (4.0) -> no match -> allow ---
    high_csat_ctx: dict[str, Any] = {
        "outcome": {
            "metric": "ticket_resolved",
            "properties": {
                "csat_score": 4.0,
                "resolution_time": 60,
                "escalated": False,
            },
        },
    }
    result = engine.evaluate(high_csat_ctx, rules)

    assert result.matched is False, "High CSAT should not match any rule"
    assert result.action == "allow", f"Expected allow (default), got {result.action}"


async def test_policy_priority_ordering() -> None:
    """Higher priority (lower number) rules win over lower priority ones."""
    engine = PolicyEngine()

    rules: list[PolicyRuleData] = [
        PolicyRuleData(
            name="Low-priority auto-approve",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="lt", value=10000),
            ],
            action="auto_approve",
            priority=100,
        ),
        PolicyRuleData(
            name="High-priority reject flagged",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.flagged", operator="eq", value=True),
            ],
            action="reject",
            priority=1,
        ),
    ]

    # Flagged small invoice: reject wins because it is higher priority AND reject always wins
    ctx: dict[str, Any] = {"invoice": {"total": 500, "flagged": True}}
    result: PolicyResult = engine.evaluate(ctx, rules)

    assert result.action == "reject", f"Expected reject (highest priority), got {result.action}"
    assert result.rule_name == "High-priority reject flagged"


async def test_policy_evaluate_all() -> None:
    """evaluate_all returns ALL matching rules, not just the first."""
    engine = PolicyEngine()

    rules: list[PolicyRuleData] = [
        PolicyRuleData(
            name="Rule A",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="gt", value=0),
            ],
            action="auto_approve",
            priority=10,
        ),
        PolicyRuleData(
            name="Rule B",
            trigger="invoice.generated",
            conditions=[
                Condition(field="invoice.total", operator="lt", value=10000),
            ],
            action="auto_approve",
            priority=20,
        ),
    ]

    ctx: dict[str, Any] = {"invoice": {"total": 500}}
    results: list[PolicyResult] = engine.evaluate_all(ctx, rules)

    assert len(results) == 2, f"Expected 2 matching rules, got {len(results)}"
    assert results[0].rule_name == "Rule A", "First result should be Rule A (priority 10)"
    assert results[1].rule_name == "Rule B", "Second result should be Rule B (priority 20)"
