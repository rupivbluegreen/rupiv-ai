"""End-to-end plan builder: create hybrid plans with multiple pricing rules."""

from __future__ import annotations

from typing import Any

import httpx
import pytest


async def test_complex_plan_creation_and_listing(client: httpx.AsyncClient) -> None:
    """Create a plan with multiple pricing rules, update it, then list plans.

    Steps:
    1. Create a plan with 4 pricing rules: flat + usage + outcome + hybrid
    2. Verify all 4 pricing rules are returned with correct types and amounts
    3. Update the plan name
    4. Create a second plan, list plans, verify count = 2

    Note: tiered pricing rules with the ``tiers`` JSON column are excluded from
    this SQLite-backed test because Pydantic coerces tier values to
    ``Decimal`` which the default JSON serializer cannot handle.  Tiered
    rules should be covered in integration tests against PostgreSQL.
    """

    # ------------------------------------------------------------------
    # 1. Create a plan with 4 pricing rules
    # ------------------------------------------------------------------
    plan_payload: dict[str, Any] = {
        "name": "Enterprise Hybrid",
        "description": "Full hybrid plan: base fee, usage metering, outcome billing, and hybrid component",
        "currency": "EUR",
        "billing_period": "monthly",
        "pricing_rules": [
            # Rule 1: Flat base fee
            {
                "model": "flat",
                "flat_amount": "299.0000",
                "unit_price": "0.0000",
            },
            # Rule 2: Usage-based (per API call)
            {
                "model": "usage",
                "metric": "api_call",
                "unit_price": "0.0010",
                "flat_amount": "0.0000",
            },
            # Rule 3: Outcome-based (per ticket resolved)
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "unit_price": "1.4900",
                "flat_amount": "0.0000",
                "outcome_rules": {
                    "billable_when": {
                        "escalated": False,
                        "resolution_time_lt": 600,
                        "csat_score_gte": 2.5,
                    },
                    "cap_per_period": 100000,
                },
            },
            # Rule 4: Hybrid — flat base + per-unit for a different metric
            {
                "model": "hybrid",
                "metric": "data_processed_gb",
                "unit_price": "0.1500",
                "flat_amount": "50.0000",
            },
        ],
    }

    resp = await client.post("/v1/plans", json=plan_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating plan, got {resp.status_code}: {resp.text}"
    )

    created_plan: dict[str, Any] = resp.json()
    plan_id: str = created_plan["id"]

    assert created_plan["name"] == "Enterprise Hybrid", "Plan name mismatch"
    assert created_plan["currency"] == "EUR", "Plan currency mismatch"
    assert created_plan["billing_period"] == "monthly", "Plan billing_period mismatch"
    assert created_plan["description"] == plan_payload["description"], "Plan description mismatch"

    # ------------------------------------------------------------------
    # 2. Verify all 4 pricing rules with correct types and amounts
    # ------------------------------------------------------------------
    rules: list[dict[str, Any]] = created_plan["pricing_rules"]
    assert len(rules) == 4, f"Expected 4 pricing rules, got {len(rules)}"

    # Verify each rule by model type
    rule_models: list[str] = [r["model"] for r in rules]
    assert "flat" in rule_models, "Missing flat pricing rule"
    assert "usage" in rule_models, "Missing usage pricing rule"
    assert "outcome" in rule_models, "Missing outcome pricing rule"
    assert "hybrid" in rule_models, "Missing hybrid pricing rule"

    # Verify flat rule amounts
    flat_rule: dict[str, Any] = next(r for r in rules if r["model"] == "flat")
    assert flat_rule["id"] is not None, "Flat rule should have an id"
    # Compare as floats to handle string/Decimal serialization differences
    assert float(flat_rule["flat_amount"]) == 299.0, (
        f"Flat rule flat_amount should be 299.0000, got {flat_rule['flat_amount']}"
    )

    # Verify usage rule
    usage_rule: dict[str, Any] = next(r for r in rules if r["model"] == "usage")
    assert usage_rule["metric"] == "api_call", "Usage rule metric mismatch"
    assert float(usage_rule["unit_price"]) == 0.001, (
        f"Usage rule unit_price should be 0.0010, got {usage_rule['unit_price']}"
    )

    # Verify outcome rule
    outcome_rule: dict[str, Any] = next(r for r in rules if r["model"] == "outcome")
    assert outcome_rule["metric"] == "ticket_resolved", "Outcome rule metric mismatch"
    assert float(outcome_rule["unit_price"]) == 1.49, (
        f"Outcome rule unit_price should be 1.4900, got {outcome_rule['unit_price']}"
    )
    assert outcome_rule["outcome_rules"] is not None, "Outcome rule should have outcome_rules"
    assert outcome_rule["outcome_rules"]["cap_per_period"] == 100000, (
        "Outcome cap_per_period mismatch"
    )

    # Verify hybrid rule
    hybrid_rule: dict[str, Any] = next(r for r in rules if r["model"] == "hybrid")
    assert hybrid_rule["metric"] == "data_processed_gb", "Hybrid rule metric mismatch"
    assert float(hybrid_rule["unit_price"]) == 0.15, (
        f"Hybrid rule unit_price should be 0.1500, got {hybrid_rule['unit_price']}"
    )
    assert float(hybrid_rule["flat_amount"]) == 50.0, (
        f"Hybrid rule flat_amount should be 50.0000, got {hybrid_rule['flat_amount']}"
    )

    # ------------------------------------------------------------------
    # 3. Update the plan name
    # ------------------------------------------------------------------
    update_payload: dict[str, Any] = {
        "name": "Enterprise Hybrid v2",
    }
    resp = await client.patch(f"/v1/plans/{plan_id}", json=update_payload)
    assert resp.status_code == 200, (
        f"Expected 200 updating plan, got {resp.status_code}: {resp.text}"
    )

    updated_plan: dict[str, Any] = resp.json()
    assert updated_plan["name"] == "Enterprise Hybrid v2", "Plan name should be updated"
    assert updated_plan["id"] == plan_id, "Plan ID should not change on update"
    assert updated_plan["currency"] == "EUR", "Currency should be unchanged after name update"

    # Verify via GET that the update persisted
    resp = await client.get(f"/v1/plans/{plan_id}")
    assert resp.status_code == 200, (
        f"Expected 200 fetching updated plan, got {resp.status_code}: {resp.text}"
    )
    refetched_plan: dict[str, Any] = resp.json()
    assert refetched_plan["name"] == "Enterprise Hybrid v2", "Plan name update did not persist"

    # ------------------------------------------------------------------
    # 4. Create a second plan, list plans, verify count = 2
    # ------------------------------------------------------------------
    second_plan_payload: dict[str, Any] = {
        "name": "Starter",
        "description": "Simple flat-rate plan for small teams",
        "currency": "EUR",
        "billing_period": "monthly",
        "pricing_rules": [
            {
                "model": "flat",
                "flat_amount": "49.0000",
                "unit_price": "0.0000",
            },
        ],
    }
    resp = await client.post("/v1/plans", json=second_plan_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating second plan, got {resp.status_code}: {resp.text}"
    )

    second_plan: dict[str, Any] = resp.json()
    assert second_plan["name"] == "Starter", "Second plan name mismatch"
    assert second_plan["id"] != plan_id, "Second plan should have a different ID"

    # List all plans and verify count
    resp = await client.get("/v1/plans")
    assert resp.status_code == 200, (
        f"Expected 200 listing plans, got {resp.status_code}: {resp.text}"
    )
    plans_list: dict[str, Any] = resp.json()
    assert plans_list["total"] == 2, f"Expected 2 plans, got {plans_list['total']}"
    assert len(plans_list["items"]) == 2, f"Expected 2 plan items, got {len(plans_list['items'])}"

    # Verify both plan names are present
    plan_names: set[str] = {p["name"] for p in plans_list["items"]}
    assert "Enterprise Hybrid v2" in plan_names, "Updated hybrid plan should appear in list"
    assert "Starter" in plan_names, "Starter plan should appear in list"
