"""Tests for plan CRUD endpoints — /v1/plans."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat_plan_payload(name: str = "Basic Flat") -> dict[str, Any]:
    """Return a plan payload with a single flat pricing rule."""
    return {
        "name": name,
        "description": "Monthly flat fee plan",
        "currency": "EUR",
        "billing_period": "monthly",
        "pricing_rules": [
            {
                "model": "flat",
                "flat_amount": "49.0000",
            },
        ],
    }


def _outcome_plan_payload() -> dict[str, Any]:
    """Return a plan payload with outcome pricing and validation rules."""
    return {
        "name": "Outcome Growth",
        "description": "Pay per resolved ticket",
        "currency": "EUR",
        "billing_period": "monthly",
        "pricing_rules": [
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "unit_price": "0.9900",
                "outcome_rules": {
                    "billable_when": {
                        "escalated": False,
                        "resolution_time_lt": 300,
                        "csat_score_gte": 3.0,
                    },
                    "cap_per_period": 50000,
                },
            },
        ],
    }


def _hybrid_plan_payload() -> dict[str, Any]:
    """Return a plan payload with flat + usage + outcome rules."""
    return {
        "name": "Hybrid Pro",
        "description": "Base fee plus usage and outcome charges",
        "currency": "EUR",
        "billing_period": "monthly",
        "pricing_rules": [
            {
                "model": "flat",
                "flat_amount": "99.0000",
            },
            {
                "model": "usage",
                "metric": "api_call",
                "unit_price": "0.0010",
            },
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "unit_price": "0.9900",
                "outcome_rules": {
                    "billable_when": {"escalated": False},
                    "cap_per_period": 10000,
                },
            },
        ],
    }


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_plan_flat(client: AsyncClient) -> None:
    """POST /v1/plans with a flat pricing rule returns 201."""
    payload = _flat_plan_payload()
    response = await client.post("/v1/plans", json=payload)

    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    assert body["name"] == "Basic Flat"
    assert body["currency"] == "EUR"
    assert body["billing_period"] == "monthly"
    assert len(body["pricing_rules"]) == 1
    assert body["pricing_rules"][0]["model"] == "flat"


async def test_create_plan_with_outcome_rules(client: AsyncClient) -> None:
    """POST /v1/plans with outcome pricing and validation rules returns 201."""
    payload = _outcome_plan_payload()
    response = await client.post("/v1/plans", json=payload)

    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    assert body["name"] == "Outcome Growth"
    assert len(body["pricing_rules"]) == 1

    rule: dict[str, Any] = body["pricing_rules"][0]
    assert rule["model"] == "outcome"
    assert rule["metric"] == "ticket_resolved"
    assert rule["outcome_rules"] is not None
    assert rule["outcome_rules"]["cap_per_period"] == 50000
    assert rule["outcome_rules"]["billable_when"]["escalated"] is False


async def test_create_plan_hybrid(client: AsyncClient) -> None:
    """POST /v1/plans with flat + usage + outcome rules returns 201."""
    payload = _hybrid_plan_payload()
    response = await client.post("/v1/plans", json=payload)

    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    assert body["name"] == "Hybrid Pro"
    assert len(body["pricing_rules"]) == 3

    models = [r["model"] for r in body["pricing_rules"]]
    assert "flat" in models
    assert "usage" in models
    assert "outcome" in models


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_plans(client: AsyncClient) -> None:
    """Create multiple plans, then list them."""
    for i in range(3):
        payload = _flat_plan_payload(name=f"Plan {i}")
        resp = await client.post("/v1/plans", json=payload)
        assert resp.status_code == 201

    response = await client.get("/v1/plans")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


async def test_get_plan_with_pricing_rules(client: AsyncClient) -> None:
    """Create a plan with rules, then GET by ID includes pricing_rules."""
    create_resp = await client.post("/v1/plans", json=_outcome_plan_payload())
    assert create_resp.status_code == 201
    plan_id: str = create_resp.json()["id"]

    response = await client.get(f"/v1/plans/{plan_id}")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["id"] == plan_id
    assert len(body["pricing_rules"]) == 1
    assert body["pricing_rules"][0]["metric"] == "ticket_resolved"


async def test_get_plan_not_found(client: AsyncClient) -> None:
    """GET /v1/plans/<random-uuid> returns 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/v1/plans/{random_id}")

    assert response.status_code == 404
