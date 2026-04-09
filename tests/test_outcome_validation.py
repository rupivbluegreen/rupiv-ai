"""Tests for rupiv.agents.outcome_agent — outcome validation logic."""

from __future__ import annotations

from typing import Any

import pytest

langgraph = pytest.importorskip("langgraph", reason="langgraph not installed")

from rupiv.agents.outcome_agent import (
    OutcomeValidationState,
    check_rules,
    outcome_graph,
)


def _make_state(
    *,
    properties: dict[str, Any],
    billable_when: dict[str, Any],
    validation_result: str | None = None,
) -> OutcomeValidationState:
    """Helper to build an OutcomeValidationState for check_rules tests."""
    return {
        "event_id": "test-event",
        "customer_id": "cust-001",
        "metric": "ticket_resolved",
        "properties": properties,
        "pricing_rule": {"billable_when": billable_when},
        "validation_result": validation_result,
        "rejection_reason": None,
        "messages": [],
    }


class TestOutcomeValidation:
    """Tests for outcome validation graph and check_rules node."""

    def test_outcome_graph_compiles(self) -> None:
        """The outcome graph should be compiled and non-None."""
        assert outcome_graph is not None

    async def test_check_rules_all_pass(self) -> None:
        """When all billable_when conditions are met, result should be validated."""
        state = _make_state(
            properties={
                "escalated": False,
                "resolution_time": 45,
                "csat_score": 4.8,
            },
            billable_when={
                "escalated": False,
                "resolution_time_lt": 300,
                "csat_score_gte": 3.0,
            },
        )

        result: dict[str, Any] = await check_rules(state)
        assert result["validation_result"] == "validated"
        assert result["rejection_reason"] is None

    async def test_check_rules_escalated_rejected(self) -> None:
        """When escalated=True violates escalated=False rule, result is rejected."""
        state = _make_state(
            properties={
                "escalated": True,
                "resolution_time": 45,
                "csat_score": 4.8,
            },
            billable_when={
                "escalated": False,
            },
        )

        result: dict[str, Any] = await check_rules(state)
        assert result["validation_result"] == "rejected"
        assert result["rejection_reason"] is not None
        assert "escalated" in result["rejection_reason"]

    async def test_check_rules_gte_operator(self) -> None:
        """csat_score_gte check should pass when score meets threshold."""
        state_pass = _make_state(
            properties={"csat_score": 3.0},
            billable_when={"csat_score_gte": 3.0},
        )
        result = await check_rules(state_pass)
        assert result["validation_result"] == "validated"

        # Failing case: score below threshold
        state_fail = _make_state(
            properties={"csat_score": 2.9},
            billable_when={"csat_score_gte": 3.0},
        )
        result = await check_rules(state_fail)
        assert result["validation_result"] == "rejected"
        assert "csat_score" in result["rejection_reason"]

    async def test_check_rules_lt_operator(self) -> None:
        """resolution_time_lt check should pass when time is below limit."""
        state_pass = _make_state(
            properties={"resolution_time": 299},
            billable_when={"resolution_time_lt": 300},
        )
        result = await check_rules(state_pass)
        assert result["validation_result"] == "validated"

        # Failing case: at the boundary
        state_fail = _make_state(
            properties={"resolution_time": 300},
            billable_when={"resolution_time_lt": 300},
        )
        result = await check_rules(state_fail)
        assert result["validation_result"] == "rejected"
        assert "resolution_time" in result["rejection_reason"]
