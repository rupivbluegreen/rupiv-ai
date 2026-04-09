"""End-to-end customer lifecycle: create -> update -> subscribe -> cancel."""

from __future__ import annotations

from typing import Any

import httpx
import pytest


async def test_customer_lifecycle(client: httpx.AsyncClient) -> None:
    """Walk through the full customer lifecycle via the API.

    Steps:
    1. Create a customer
    2. Update customer email and name
    3. Verify update persisted (GET)
    4. Create a plan and subscription for customer
    5. Cancel subscription
    6. Verify subscription status = canceled
    """

    # ------------------------------------------------------------------
    # 1. Create a customer
    # ------------------------------------------------------------------
    customer_payload: dict[str, Any] = {
        "name": "AutoBot B.V.",
        "email": "admin@autobot.nl",
        "external_id": "ext-autobot-001",
        "country_code": "NL",
        "currency": "EUR",
        "is_business": True,
        "vat_number": "NL123456789B01",
        "metadata": {"segment": "smb"},
    }
    resp = await client.post("/v1/customers", json=customer_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating customer, got {resp.status_code}: {resp.text}"
    )

    customer: dict[str, Any] = resp.json()
    customer_id: str = customer["id"]

    assert customer["name"] == "AutoBot B.V.", "Customer name mismatch"
    assert customer["email"] == "admin@autobot.nl", "Customer email mismatch"
    assert customer["country_code"] == "NL", "Customer country_code mismatch"
    assert customer["is_business"] is True, "Customer is_business mismatch"

    # ------------------------------------------------------------------
    # 2. Update customer email and name
    # ------------------------------------------------------------------
    update_payload: dict[str, Any] = {
        "name": "AutoBot International B.V.",
        "email": "billing@autobot-intl.eu",
    }
    resp = await client.patch(f"/v1/customers/{customer_id}", json=update_payload)
    assert resp.status_code == 200, (
        f"Expected 200 updating customer, got {resp.status_code}: {resp.text}"
    )

    updated_customer: dict[str, Any] = resp.json()
    assert updated_customer["name"] == "AutoBot International B.V.", (
        "Customer name should be updated"
    )
    assert updated_customer["email"] == "billing@autobot-intl.eu", (
        "Customer email should be updated"
    )
    # Fields not in the update payload should remain unchanged
    assert updated_customer["country_code"] == "NL", "country_code should be unchanged"
    assert updated_customer["external_id"] == "ext-autobot-001", "external_id should be unchanged"
    assert updated_customer["is_business"] is True, "is_business should be unchanged"
    assert updated_customer["vat_number"] == "NL123456789B01", "vat_number should be unchanged"

    # ------------------------------------------------------------------
    # 3. Verify update persisted via GET
    # ------------------------------------------------------------------
    resp = await client.get(f"/v1/customers/{customer_id}")
    assert resp.status_code == 200, (
        f"Expected 200 fetching customer, got {resp.status_code}: {resp.text}"
    )

    fetched_customer: dict[str, Any] = resp.json()
    assert fetched_customer["id"] == customer_id, "Fetched customer ID mismatch"
    assert fetched_customer["name"] == "AutoBot International B.V.", (
        "Persisted name mismatch after update"
    )
    assert fetched_customer["email"] == "billing@autobot-intl.eu", (
        "Persisted email mismatch after update"
    )
    assert fetched_customer["country_code"] == "NL", "Persisted country_code should be unchanged"
    assert fetched_customer["currency"] == "EUR", "Persisted currency should be unchanged"

    # ------------------------------------------------------------------
    # 4. Create a plan and subscription for the customer
    # ------------------------------------------------------------------
    plan_payload: dict[str, Any] = {
        "name": "Basic",
        "description": "Basic monthly plan for SMB customers",
        "currency": "EUR",
        "billing_period": "monthly",
        "pricing_rules": [
            {
                "model": "flat",
                "flat_amount": "79.0000",
                "unit_price": "0.0000",
            },
        ],
    }
    resp = await client.post("/v1/plans", json=plan_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating plan, got {resp.status_code}: {resp.text}"
    )
    plan: dict[str, Any] = resp.json()
    plan_id: str = plan["id"]

    subscription_payload: dict[str, Any] = {
        "customer_id": customer_id,
        "plan_id": plan_id,
    }
    resp = await client.post("/v1/subscriptions", json=subscription_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating subscription, got {resp.status_code}: {resp.text}"
    )

    subscription: dict[str, Any] = resp.json()
    subscription_id: str = subscription["id"]

    assert subscription["customer_id"] == customer_id, "Subscription customer_id mismatch"
    assert subscription["plan_id"] == plan_id, "Subscription plan_id mismatch"
    assert subscription["status"] == "active", "New subscription should be active"
    assert subscription["current_period_start"] is not None, "Period start should be set"
    assert subscription["current_period_end"] is not None, "Period end should be set"
    assert subscription["canceled_at"] is None, "New subscription should not have canceled_at"

    # ------------------------------------------------------------------
    # 5. Cancel subscription
    # ------------------------------------------------------------------
    resp = await client.post(f"/v1/subscriptions/{subscription_id}/cancel")
    assert resp.status_code == 200, (
        f"Expected 200 canceling subscription, got {resp.status_code}: {resp.text}"
    )

    canceled_sub: dict[str, Any] = resp.json()
    assert canceled_sub["status"] == "canceled", "Subscription should be canceled after cancel"
    assert canceled_sub["canceled_at"] is not None, "canceled_at should be set after cancel"

    # ------------------------------------------------------------------
    # 6. Verify subscription status persisted via GET
    # ------------------------------------------------------------------
    resp = await client.get(f"/v1/subscriptions/{subscription_id}")
    assert resp.status_code == 200, (
        f"Expected 200 fetching canceled subscription, got {resp.status_code}: {resp.text}"
    )

    fetched_sub: dict[str, Any] = resp.json()
    assert fetched_sub["id"] == subscription_id, "Fetched subscription ID mismatch"
    assert fetched_sub["status"] == "canceled", "Fetched subscription should be canceled"
    assert fetched_sub["canceled_at"] is not None, "Fetched canceled_at should be set"
    assert fetched_sub["customer_id"] == customer_id, "Fetched customer_id should match"
    assert fetched_sub["plan_id"] == plan_id, "Fetched plan_id should match"

    # Verify via list endpoint filtered by customer
    resp = await client.get("/v1/subscriptions", params={"customer_id": customer_id})
    assert resp.status_code == 200, (
        f"Expected 200 listing subscriptions, got {resp.status_code}: {resp.text}"
    )
    subs_list: dict[str, Any] = resp.json()
    assert subs_list["total"] == 1, f"Expected 1 subscription for customer, got {subs_list['total']}"
    assert subs_list["items"][0]["status"] == "canceled", (
        "Listed subscription should show canceled status"
    )
