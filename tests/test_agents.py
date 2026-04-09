"""Tests for LangGraph agent graph structure and node logic.

Tests graph compilation, state schemas, node registration, and individual
node functions (called directly with mock state dicts, patching DB calls).
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Guard: skip the entire module if langgraph is not installed
# ---------------------------------------------------------------------------

langgraph = pytest.importorskip("langgraph", reason="langgraph not installed")


# =========================================================================
# Billing Agent
# =========================================================================


class TestBillingAgent:
    """Tests for rupiv.agents.billing_agent."""

    def test_billing_graph_compiles(self) -> None:
        """The billing agent graph should already be compiled without error."""
        from rupiv.agents.billing_agent import billing_graph

        # billing_graph is a compiled graph — verify it's not None
        assert billing_graph is not None

    def test_billing_state_schema(self) -> None:
        """BillingState should contain the expected keys."""
        from rupiv.agents.billing_agent import BillingState

        annotations = BillingState.__annotations__
        expected_keys = {
            "subscription_id",
            "customer_id",
            "period_start",
            "period_end",
            "pricing_rules",
            "aggregated_data",
            "line_items",
            "invoice_id",
            "invoice_total",
            "payment_status",
            "error",
            "messages",
        }
        found = set(annotations.keys())
        missing = expected_keys - found
        assert not missing, f"BillingState is missing keys: {missing}"

    def test_billing_nodes_registered(self) -> None:
        """All expected nodes should be present in the compiled graph."""
        from rupiv.agents.billing_agent import billing_graph

        # LangGraph compiled graphs expose a .nodes dict
        node_names: set[str] = set(billing_graph.nodes.keys())

        expected_nodes = {
            "load_subscription",
            "aggregate_usage",
            "calculate_pricing",
            "generate_invoice",
            "attempt_payment",
            "handle_payment_result",
            "run_dunning",
        }
        missing = expected_nodes - node_names
        assert not missing, (
            f"Billing graph is missing expected nodes: {missing}. Found: {node_names}"
        )


# =========================================================================
# Outcome Agent
# =========================================================================


class TestOutcomeAgent:
    """Tests for rupiv.agents.outcome_agent."""

    def test_outcome_graph_compiles(self) -> None:
        """The outcome agent graph should already be compiled without error."""
        from rupiv.agents.outcome_agent import outcome_graph

        assert outcome_graph is not None

    def test_outcome_nodes_registered(self) -> None:
        """All expected nodes should be present in the compiled graph."""
        from rupiv.agents.outcome_agent import outcome_graph

        node_names: set[str] = set(outcome_graph.nodes.keys())
        expected_nodes = {"load_event", "check_rules", "decide", "update_status"}
        missing = expected_nodes - node_names
        assert not missing, (
            f"Outcome graph is missing expected nodes: {missing}. Found: {node_names}"
        )

    async def test_outcome_validation_passes(self) -> None:
        """When all outcome rule conditions are met, check_rules should validate."""
        from rupiv.agents.outcome_agent import OutcomeValidationState, check_rules

        state: OutcomeValidationState = {
            "event_id": "test-event-001",
            "customer_id": "cust-001",
            "metric": "ticket_resolved",
            "properties": {
                "escalated": False,
                "resolution_time": 45,
                "csat_score": 4.8,
            },
            "pricing_rule": {
                "billable_when": {
                    "escalated": False,
                    "resolution_time_lt": 300,
                    "csat_score_gte": 3.0,
                },
            },
            "validation_result": None,
            "rejection_reason": None,
            "messages": [],
        }

        result = await check_rules(state)
        assert result["validation_result"] == "validated"
        assert result["rejection_reason"] is None

    async def test_outcome_validation_rejects_escalated(self) -> None:
        """When the event was escalated (violating the rule), check_rules should reject."""
        from rupiv.agents.outcome_agent import OutcomeValidationState, check_rules

        state: OutcomeValidationState = {
            "event_id": "test-event-002",
            "customer_id": "cust-001",
            "metric": "ticket_resolved",
            "properties": {
                "escalated": True,
                "resolution_time": 600,
                "csat_score": 1.5,
            },
            "pricing_rule": {
                "billable_when": {
                    "escalated": False,
                    "resolution_time_lt": 300,
                    "csat_score_gte": 3.0,
                },
            },
            "validation_result": None,
            "rejection_reason": None,
            "messages": [],
        }

        result = await check_rules(state)
        assert result["validation_result"] == "rejected"
        assert result["rejection_reason"] is not None
        assert "escalated" in result["rejection_reason"]

    async def test_outcome_validation_no_conditions_passes(self) -> None:
        """When billable_when is empty, all outcomes should be billable."""
        from rupiv.agents.outcome_agent import OutcomeValidationState, check_rules

        state: OutcomeValidationState = {
            "event_id": "test-event-003",
            "customer_id": "cust-001",
            "metric": "ticket_resolved",
            "properties": {"escalated": True},
            "pricing_rule": {"billable_when": {}},
            "validation_result": None,
            "rejection_reason": None,
            "messages": [],
        }

        result = await check_rules(state)
        assert result["validation_result"] == "validated"

    async def test_outcome_validation_skips_if_already_decided(self) -> None:
        """If validation_result is already set, check_rules should be a no-op."""
        from rupiv.agents.outcome_agent import OutcomeValidationState, check_rules

        state: OutcomeValidationState = {
            "event_id": "test-event-004",
            "customer_id": "cust-001",
            "metric": "ticket_resolved",
            "properties": {},
            "pricing_rule": {},
            "validation_result": "rejected",
            "rejection_reason": "Already rejected at load time",
            "messages": [],
        }

        result = await check_rules(state)
        assert result == {}

    async def test_outcome_state_schema(self) -> None:
        """OutcomeValidationState should contain the expected keys."""
        from rupiv.agents.outcome_agent import OutcomeValidationState

        annotations = OutcomeValidationState.__annotations__
        expected_keys = {
            "event_id",
            "customer_id",
            "metric",
            "properties",
            "pricing_rule",
            "validation_result",
            "rejection_reason",
            "messages",
        }
        found = set(annotations.keys())
        missing = expected_keys - found
        assert not missing, f"OutcomeValidationState is missing keys: {missing}"


# =========================================================================
# Dunning Agent
# =========================================================================


class TestDunningAgent:
    """Tests for rupiv.agents.dunning_agent."""

    def test_dunning_graph_compiles(self) -> None:
        """The dunning agent graph should already be compiled without error."""
        from rupiv.agents.dunning_agent import dunning_graph

        assert dunning_graph is not None

    def test_dunning_state_schema(self) -> None:
        """DunningState should contain the expected keys."""
        from rupiv.agents.dunning_agent import DunningState

        annotations = DunningState.__annotations__
        expected_keys = {
            "invoice_id",
            "attempt_number",
            "max_attempts",
            "retry_delays_hours",
            "last_payment_error",
            "final_status",
            "messages",
        }
        found = set(annotations.keys())
        missing = expected_keys - found
        assert not missing, f"DunningState is missing keys: {missing}"

    def test_dunning_nodes_registered(self) -> None:
        """All expected nodes should be present in the compiled graph."""
        from rupiv.agents.dunning_agent import dunning_graph

        node_names: set[str] = set(dunning_graph.nodes.keys())
        expected_nodes = {
            "load_invoice",
            "attempt_payment",
            "evaluate_result",
            "schedule_retry",
            "mark_uncollectible",
        }
        missing = expected_nodes - node_names
        assert not missing, (
            f"Dunning graph is missing expected nodes: {missing}. Found: {node_names}"
        )

    def test_dunning_route_ends_on_paid(self) -> None:
        """The routing function should end the graph when status is 'paid'."""
        from rupiv.agents.dunning_agent import DunningState, _route_after_evaluate

        state: DunningState = {
            "invoice_id": "inv-001",
            "attempt_number": 1,
            "max_attempts": 3,
            "retry_delays_hours": [24, 72, 168],
            "last_payment_error": None,
            "final_status": "paid",
            "messages": [],
        }
        assert _route_after_evaluate(state) == "__end__"

    def test_dunning_route_retries_on_failure(self) -> None:
        """The routing function should schedule a retry if attempts remain."""
        from rupiv.agents.dunning_agent import DunningState, _route_after_evaluate

        state: DunningState = {
            "invoice_id": "inv-001",
            "attempt_number": 1,
            "max_attempts": 3,
            "retry_delays_hours": [24, 72, 168],
            "last_payment_error": "card declined",
            "final_status": None,
            "messages": [],
        }
        assert _route_after_evaluate(state) == "schedule_retry"

    def test_dunning_route_uncollectible_when_exhausted(self) -> None:
        """The routing function should mark uncollectible when attempts are exhausted."""
        from rupiv.agents.dunning_agent import DunningState, _route_after_evaluate

        state: DunningState = {
            "invoice_id": "inv-001",
            "attempt_number": 3,
            "max_attempts": 3,
            "retry_delays_hours": [24, 72, 168],
            "last_payment_error": "card declined",
            "final_status": None,
            "messages": [],
        }
        assert _route_after_evaluate(state) == "mark_uncollectible"


# =========================================================================
# Quoting Agent
# =========================================================================


class TestQuotingAgent:
    """Tests for rupiv.agents.quoting_agent."""

    def test_quoting_graph_compiles(self) -> None:
        """The quoting agent graph should already be compiled without error."""
        from rupiv.agents.quoting_agent import quoting_graph

        assert quoting_graph is not None

    def test_quoting_state_schema(self) -> None:
        """QuotingState should contain the expected keys."""
        from rupiv.agents.quoting_agent import QuotingState

        annotations = QuotingState.__annotations__
        expected_keys = {
            "customer_id",
            "plan_id",
            "discount_pct",
            "term_months",
            "overrides",
            "quote_id",
            "policy_result",
            "requires_approval",
            "approval_status",
            "error",
            "messages",
        }
        found = set(annotations.keys())
        missing = expected_keys - found
        assert not missing, f"QuotingState is missing keys: {missing}"

    def test_quoting_nodes_registered(self) -> None:
        """All expected nodes should be present in the compiled graph."""
        from rupiv.agents.quoting_agent import quoting_graph

        node_names: set[str] = set(quoting_graph.nodes.keys())
        expected_nodes = {"load_context", "check_policies", "build_quote", "finalize"}
        missing = expected_nodes - node_names
        assert not missing, (
            f"Quoting graph is missing expected nodes: {missing}. Found: {node_names}"
        )


# =========================================================================
# Revenue Agent
# =========================================================================


class TestRevenueAgent:
    """Tests for rupiv.agents.revenue_agent."""

    def test_revenue_graph_compiles(self) -> None:
        """The revenue agent graph should already be compiled without error."""
        from rupiv.agents.revenue_agent import revenue_graph

        assert revenue_graph is not None

    def test_revenue_state_schema(self) -> None:
        """RevenueRecState should contain the expected keys."""
        from rupiv.agents.revenue_agent import RevenueRecState

        annotations = RevenueRecState.__annotations__
        expected_keys = {
            "subscription_id",
            "obligations",
            "allocations",
            "schedule_entries",
            "journal_entries",
            "schedule_id",
            "error",
            "messages",
        }
        found = set(annotations.keys())
        missing = expected_keys - found
        assert not missing, f"RevenueRecState is missing keys: {missing}"

    def test_revenue_nodes_registered(self) -> None:
        """All expected nodes should be present in the compiled graph."""
        from rupiv.agents.revenue_agent import revenue_graph

        node_names: set[str] = set(revenue_graph.nodes.keys())
        expected_nodes = {
            "load_subscription",
            "identify_obligations",
            "allocate_prices",
            "generate_schedules",
            "generate_journals",
            "persist_schedule",
        }
        missing = expected_nodes - node_names
        assert not missing, (
            f"Revenue graph is missing expected nodes: {missing}. Found: {node_names}"
        )


# =========================================================================
# A2A Agent
# =========================================================================


class TestA2AAgent:
    """Tests for rupiv.agents.a2a_agent."""

    def test_a2a_graph_compiles(self) -> None:
        """The A2A agent graph should compile without error."""
        from rupiv.agents.a2a_agent import a2a_graph

        assert a2a_graph is not None

    def test_a2a_state_schema(self) -> None:
        """A2AState should contain the expected keys."""
        from rupiv.agents.a2a_agent import A2AState

        annotations = A2AState.__annotations__
        expected_keys = {
            "intent_id",
            "buyer_agent_id",
            "seller_agent_id",
            "amount",
            "currency",
            "reason",
            "compliance_passed",
            "ledger_debit_id",
            "ledger_credit_id",
            "transfer_id",
            "settlement_status",
            "error",
            "messages",
        }
        found = set(annotations.keys())
        missing = expected_keys - found
        assert not missing, f"A2AState is missing keys: {missing}"

    def test_a2a_nodes_registered(self) -> None:
        """All expected nodes should be present in the compiled graph."""
        from rupiv.agents.a2a_agent import a2a_graph

        node_names: set[str] = set(a2a_graph.nodes.keys())
        expected_nodes = {
            "validate_intent",
            "compliance_check",
            "reserve_funds",
            "execute_transfer",
            "settle",
        }
        missing = expected_nodes - node_names
        assert not missing, f"A2A graph is missing expected nodes: {missing}. Found: {node_names}"
