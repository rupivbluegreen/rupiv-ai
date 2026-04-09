"""Tests for subscription endpoints — /v1/subscriptions."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer(client: AsyncClient, suffix: str = "1") -> str:
    """Create a customer and return its ID."""
    resp = await client.post(
        "/v1/customers",
        json={
            "name": f"Sub Test Customer {suffix}",
            "email": f"sub-test-{suffix}@example.com",
            "external_id": f"ext-sub-{suffix}",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_plan(client: AsyncClient, suffix: str = "1") -> str:
    """Create a minimal flat plan and return its ID."""
    resp = await client.post(
        "/v1/plans",
        json={
            "name": f"Sub Test Plan {suffix}",
            "description": "Plan for subscription tests",
            "currency": "EUR",
            "billing_period": "monthly",
            "pricing_rules": [
                {"model": "flat", "flat_amount": "49.0000"},
            ],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_subscription(client: AsyncClient) -> None:
    """POST /v1/subscriptions creates an active subscription with period dates."""
    customer_id = await _create_customer(client, suffix="create")
    plan_id = await _create_plan(client, suffix="create")

    response = await client.post(
        "/v1/subscriptions",
        json={"customer_id": customer_id, "plan_id": plan_id},
    )

    assert response.status_code == 201
    body: dict[str, Any] = response.json()

    assert body["customer_id"] == customer_id
    assert body["plan_id"] == plan_id
    assert body["status"] == "active"
    assert body["current_period_start"] is not None
    assert body["current_period_end"] is not None
    assert body["canceled_at"] is None

    # Verify the UUID is valid
    uuid.UUID(body["id"])


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_subscriptions(client: AsyncClient) -> None:
    """Create subscriptions for two customers, filter by customer_id."""
    cust_a = await _create_customer(client, suffix="list-a")
    cust_b = await _create_customer(client, suffix="list-b")
    plan_id = await _create_plan(client, suffix="list")

    # 2 subs for cust_a, 1 for cust_b
    for _ in range(2):
        resp = await client.post(
            "/v1/subscriptions",
            json={"customer_id": cust_a, "plan_id": plan_id},
        )
        assert resp.status_code == 201

    resp = await client.post(
        "/v1/subscriptions",
        json={"customer_id": cust_b, "plan_id": plan_id},
    )
    assert resp.status_code == 201

    # Filter by customer A
    response = await client.get("/v1/subscriptions", params={"customer_id": cust_a})
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(item["customer_id"] == cust_a for item in body["items"])


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


async def test_cancel_subscription(client: AsyncClient) -> None:
    """Create then cancel a subscription; verify status and canceled_at."""
    customer_id = await _create_customer(client, suffix="cancel")
    plan_id = await _create_plan(client, suffix="cancel")

    create_resp = await client.post(
        "/v1/subscriptions",
        json={"customer_id": customer_id, "plan_id": plan_id},
    )
    assert create_resp.status_code == 201
    sub_id: str = create_resp.json()["id"]

    response = await client.post(f"/v1/subscriptions/{sub_id}/cancel")

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["status"] == "canceled"
    assert body["canceled_at"] is not None


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------


async def test_get_subscription_not_found(client: AsyncClient) -> None:
    """GET /v1/subscriptions/<random-uuid> returns 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/v1/subscriptions/{random_id}")

    assert response.status_code == 404
