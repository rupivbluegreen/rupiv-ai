"""Tests for transformation engine and API."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from rupiv.transformations.engine import apply_rules, apply_step, transform_event


# ---------------------------------------------------------------------------
# Engine unit tests
# ---------------------------------------------------------------------------


class TestFilterStep:
    """Tests for the filter transformation step."""

    def test_passes_matching_event(self) -> None:
        event = {"properties": {"status": "completed"}}
        step = {"type": "filter", "field": "properties.status", "operator": "eq", "value": "completed"}
        result = apply_step(event, step)
        assert result is not None

    def test_drops_non_matching_event(self) -> None:
        event = {"properties": {"status": "pending"}}
        step = {"type": "filter", "field": "properties.status", "operator": "eq", "value": "completed"}
        result = apply_step(event, step)
        assert result is None

    def test_filter_with_gte_operator(self) -> None:
        event = {"properties": {"score": 4.5}}
        step = {"type": "filter", "field": "properties.score", "operator": "gte", "value": 3.0}
        result = apply_step(event, step)
        assert result is not None

    def test_filter_with_lt_drops(self) -> None:
        event = {"properties": {"score": 2.0}}
        step = {"type": "filter", "field": "properties.score", "operator": "gte", "value": 3.0}
        result = apply_step(event, step)
        assert result is None


class TestRenameStep:
    """Tests for the rename transformation step."""

    def test_renames_nested_field(self) -> None:
        event = {"properties": {"user_count": 42}}
        step = {"type": "rename", "source": "properties.user_count", "target": "properties.users"}
        result = apply_step(event, step)
        assert result is not None
        assert result["properties"]["users"] == 42
        assert "user_count" not in result["properties"]

    def test_renames_top_level_field(self) -> None:
        event = {"old_name": "value"}
        step = {"type": "rename", "source": "old_name", "target": "new_name"}
        result = apply_step(event, step)
        assert result is not None
        assert result["new_name"] == "value"
        assert "old_name" not in result


class TestMapStep:
    """Tests for the map transformation step."""

    def test_map_with_expression(self) -> None:
        event = {"properties": {"duration_ms": 5000}}
        step = {
            "type": "map",
            "source": "properties.duration_ms",
            "target": "properties.duration_seconds",
            "expression": "value / 1000",
        }
        result = apply_step(event, step)
        assert result is not None
        assert result["properties"]["duration_seconds"] == 5.0

    def test_map_without_expression_copies(self) -> None:
        event = {"properties": {"x": 42}}
        step = {"type": "map", "source": "properties.x", "target": "properties.y"}
        result = apply_step(event, step)
        assert result is not None
        assert result["properties"]["y"] == 42


class TestSetStep:
    """Tests for the set transformation step."""

    def test_sets_field(self) -> None:
        event = {"properties": {}}
        step = {"type": "set", "field": "properties.source", "value": "rupiv"}
        result = apply_step(event, step)
        assert result is not None
        assert result["properties"]["source"] == "rupiv"


class TestTransformEvent:
    """Tests for the full pipeline."""

    def test_pipeline_with_multiple_steps(self) -> None:
        event = {
            "metric": "raw_event",
            "properties": {"status": "completed", "duration_ms": 3000},
        }
        steps = [
            {"type": "filter", "field": "properties.status", "operator": "eq", "value": "completed"},
            {"type": "map", "source": "properties.duration_ms", "target": "properties.duration_s", "expression": "value / 1000"},
            {"type": "set", "field": "properties.processed", "value": True},
        ]
        result = transform_event(event, steps)
        assert result is not None
        assert result["properties"]["duration_s"] == 3.0
        assert result["properties"]["processed"] is True

    def test_pipeline_drops_on_filter(self) -> None:
        event = {"properties": {"status": "pending"}}
        steps = [
            {"type": "filter", "field": "properties.status", "operator": "eq", "value": "completed"},
            {"type": "set", "field": "properties.processed", "value": True},
        ]
        result = transform_event(event, steps)
        assert result is None

    def test_original_event_not_mutated(self) -> None:
        event = {"properties": {"x": 1}}
        steps = [{"type": "set", "field": "properties.y", "value": 2}]
        transform_event(event, steps)
        assert "y" not in event["properties"]


class TestApplyRules:
    """Tests for rule matching and application."""

    def test_matches_by_source_metric(self) -> None:
        event = {"metric": "raw_call", "properties": {"x": 1}}
        rules = [
            {
                "source_metric": "raw_call",
                "target_metric": "api_call",
                "is_active": True,
                "steps": [{"type": "set", "field": "properties.transformed", "value": True}],
            },
        ]
        result = apply_rules(event, rules)
        assert result is not None
        assert result["metric"] == "api_call"
        assert result["properties"]["transformed"] is True

    def test_no_matching_rule_returns_unchanged(self) -> None:
        event = {"metric": "other_metric", "properties": {}}
        rules = [{"source_metric": "raw_call", "target_metric": "api_call", "is_active": True, "steps": []}]
        result = apply_rules(event, rules)
        assert result is not None
        assert result["metric"] == "other_metric"

    def test_inactive_rule_skipped(self) -> None:
        event = {"metric": "raw_call", "properties": {}}
        rules = [{"source_metric": "raw_call", "target_metric": "api_call", "is_active": False, "steps": []}]
        result = apply_rules(event, rules)
        assert result is not None
        assert result["metric"] == "raw_call"


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


class TestTransformationAPI:
    """Tests for transformation rule CRUD and test endpoints."""

    async def test_create_rule(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/v1/transformations",
            json={
                "name": "Normalize API calls",
                "source_metric": "raw_api_call",
                "target_metric": "api_call",
                "steps": [
                    {"type": "filter", "field": "properties.status", "operator": "eq", "value": "success"},
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Normalize API calls"
        assert data["source_metric"] == "raw_api_call"
        assert data["is_active"] is True

    async def test_list_rules(self, client: AsyncClient) -> None:
        # Create one first
        await client.post(
            "/v1/transformations",
            json={
                "name": "Test rule",
                "source_metric": "x",
                "target_metric": "y",
                "steps": [{"type": "set", "field": "properties.a", "value": 1}],
            },
        )
        resp = await client.get("/v1/transformations")
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) >= 1

    async def test_test_endpoint(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/v1/transformations/test",
            json={
                "event": {"metric": "raw", "properties": {"status": "completed", "value": 100}},
                "steps": [
                    {"type": "filter", "field": "properties.status", "operator": "eq", "value": "completed"},
                    {"type": "map", "source": "properties.value", "target": "properties.doubled", "expression": "value * 2"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dropped"] is False
        assert data["output"]["properties"]["doubled"] == 200

    async def test_test_endpoint_dropped(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/v1/transformations/test",
            json={
                "event": {"metric": "raw", "properties": {"status": "pending"}},
                "steps": [
                    {"type": "filter", "field": "properties.status", "operator": "eq", "value": "completed"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dropped"] is True
        assert data["output"] is None
