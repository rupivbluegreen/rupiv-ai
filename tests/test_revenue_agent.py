"""Tests for rupiv.agents.revenue_agent — IFRS 15 revenue recognition graph."""

from __future__ import annotations

import pytest

langgraph = pytest.importorskip("langgraph", reason="langgraph not installed")

from rupiv.agents.revenue_agent import RevenueRecState, revenue_graph


class TestRevenueAgent:
    """Tests for the revenue recognition agent graph."""

    def test_revenue_graph_compiles(self) -> None:
        """The revenue graph should be compiled and non-None."""
        assert revenue_graph is not None

    def test_revenue_state_schema(self) -> None:
        """RevenueRecState should contain all expected keys."""
        annotations = RevenueRecState.__annotations__
        expected_keys: set[str] = {
            "subscription_id",
            "obligations",
            "allocations",
            "schedule_entries",
            "journal_entries",
            "schedule_id",
            "error",
            "messages",
        }
        found: set[str] = set(annotations.keys())
        missing: set[str] = expected_keys - found
        assert not missing, f"RevenueRecState is missing keys: {missing}"

    def test_revenue_nodes_registered(self) -> None:
        """All expected nodes should be present in the compiled graph."""
        node_names: set[str] = set(revenue_graph.nodes.keys())
        expected_nodes: set[str] = {
            "load_subscription",
            "identify_obligations",
            "allocate_prices",
            "generate_schedules",
            "generate_journals",
            "persist_schedule",
        }
        missing: set[str] = expected_nodes - node_names
        assert not missing, (
            f"Revenue graph is missing expected nodes: {missing}. "
            f"Found: {node_names}"
        )
