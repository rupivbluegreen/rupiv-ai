"""End-to-end billing flow: customer -> plan -> subscription -> events -> invoice."""

from __future__ import annotations

from typing import Any

import httpx

from tests.conftest import make_event_payload


async def test_full_billing_flow(client: httpx.AsyncClient) -> None:
    """Walk through the complete happy-path billing flow via the API.

    Steps:
    1. Create a customer (ResolvAI)
    2. Create a plan (Growth: flat 149 EUR + outcome 0.99 EUR/ticket_resolved)
    3. Create a subscription linking customer to plan
    4. Send 5 usage events (api_call metric)
    5. Send 3 outcome events (ticket_resolved), mix of billable/non-billable
    6. Verify idempotency by resending one event
    7. Verify customer exists via GET
    8. Verify subscription is active via GET
    9. List invoices (expect empty — no billing cycle has run)
    """

    # ------------------------------------------------------------------
    # 1. Create a customer
    # ------------------------------------------------------------------
    customer_payload: dict[str, Any] = {
        "name": "ResolvAI GmbH",
        "email": "billing@resolvai.eu",
        "external_id": "ext-resolvai-001",
        "country_code": "DE",
        "currency": "EUR",
        "is_business": True,
        "billing_email": "invoices@resolvai.eu",
        "vat_number": "DE123456789",
        "metadata": {"tier": "growth", "source": "api"},
    }
    resp = await client.post("/v1/customers", json=customer_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating customer, got {resp.status_code}: {resp.text}"
    )

    customer_data: dict[str, Any] = resp.json()
    customer_id: str = customer_data["id"]

    assert customer_data["name"] == "ResolvAI GmbH", "Customer name mismatch"
    assert customer_data["email"] == "billing@resolvai.eu", "Customer email mismatch"
    assert customer_data["external_id"] == "ext-resolvai-001", "Customer external_id mismatch"
    assert customer_data["country_code"] == "DE", "Customer country_code mismatch"
    assert customer_data["currency"] == "EUR", "Customer currency mismatch"
    assert customer_data["is_business"] is True, "Customer is_business mismatch"
    assert customer_data["billing_email"] == "invoices@resolvai.eu", (
        "Customer billing_email mismatch"
    )
    assert customer_data["vat_number"] == "DE123456789", "Customer vat_number mismatch"

    # ------------------------------------------------------------------
    # 2. Create a plan — Growth plan (flat + outcome)
    # ------------------------------------------------------------------
    plan_payload: dict[str, Any] = {
        "name": "Growth",
        "description": "Flat base fee plus outcome-based pricing for resolved tickets",
        "currency": "EUR",
        "billing_period": "monthly",
        "pricing_rules": [
            {
                "model": "flat",
                "flat_amount": "149.0000",
                "unit_price": "0.0000",
            },
            {
                "model": "outcome",
                "metric": "ticket_resolved",
                "unit_price": "0.9900",
                "flat_amount": "0.0000",
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
    resp = await client.post("/v1/plans", json=plan_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating plan, got {resp.status_code}: {resp.text}"
    )

    plan_data: dict[str, Any] = resp.json()
    plan_id: str = plan_data["id"]

    assert plan_data["name"] == "Growth", "Plan name mismatch"
    assert plan_data["currency"] == "EUR", "Plan currency mismatch"
    assert plan_data["billing_period"] == "monthly", "Plan billing_period mismatch"
    assert len(plan_data["pricing_rules"]) == 2, "Expected 2 pricing rules on Growth plan"

    flat_rule: dict[str, Any] = plan_data["pricing_rules"][0]
    outcome_rule: dict[str, Any] = plan_data["pricing_rules"][1]
    assert flat_rule["model"] == "flat", "First pricing rule should be flat"
    assert outcome_rule["model"] == "outcome", "Second pricing rule should be outcome"
    assert outcome_rule["metric"] == "ticket_resolved", "Outcome metric mismatch"

    # ------------------------------------------------------------------
    # 3. Create a subscription
    # ------------------------------------------------------------------
    subscription_payload: dict[str, Any] = {
        "customer_id": customer_id,
        "plan_id": plan_id,
    }
    resp = await client.post("/v1/subscriptions", json=subscription_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating subscription, got {resp.status_code}: {resp.text}"
    )

    subscription_data: dict[str, Any] = resp.json()
    subscription_id: str = subscription_data["id"]

    assert subscription_data["customer_id"] == customer_id, "Subscription customer_id mismatch"
    assert subscription_data["plan_id"] == plan_id, "Subscription plan_id mismatch"
    assert subscription_data["status"] == "active", "New subscription should be active"
    assert subscription_data["current_period_start"] is not None, "Period start should be set"
    assert subscription_data["current_period_end"] is not None, "Period end should be set"

    # ------------------------------------------------------------------
    # 4. Send 5 usage events (api_call)
    # ------------------------------------------------------------------
    usage_event_ids: list[str] = []
    for i in range(5):
        event_payload: dict[str, Any] = make_event_payload(
            event_type="usage",
            metric="api_call",
            customer_id=customer_id,
            properties={"endpoint": f"/v1/resolve/{i}", "tokens": 150 + i * 10},
            idempotency_key=f"idem-usage-{i}",
        )
        resp = await client.post("/v1/events", json=event_payload)
        assert resp.status_code == 202, (
            f"Expected 202 for usage event {i}, got {resp.status_code}: {resp.text}"
        )
        event_data: dict[str, Any] = resp.json()
        assert "event_id" in event_data, f"Response for usage event {i} missing event_id"
        assert event_data["status"] == "accepted", f"Usage event {i} status should be 'accepted'"
        usage_event_ids.append(event_data["event_id"])

    assert len(usage_event_ids) == 5, "Should have ingested 5 usage events"

    # ------------------------------------------------------------------
    # 5. Send 3 outcome events (ticket_resolved) — mix of billable/non-billable
    # ------------------------------------------------------------------
    outcome_payloads: list[dict[str, Any]] = [
        # Billable: fast resolution, not escalated, good CSAT
        make_event_payload(
            event_type="outcome",
            metric="ticket_resolved",
            customer_id=customer_id,
            properties={
                "resolution_time": 45,
                "escalated": False,
                "csat_score": 4.8,
                "ticket_id": "TK-1001",
            },
            idempotency_key="idem-outcome-001",
        ),
        # Non-billable: escalated to human
        make_event_payload(
            event_type="outcome",
            metric="ticket_resolved",
            customer_id=customer_id,
            properties={
                "resolution_time": 120,
                "escalated": True,
                "csat_score": 3.5,
                "ticket_id": "TK-1002",
            },
            idempotency_key="idem-outcome-002",
        ),
        # Billable: within all thresholds
        make_event_payload(
            event_type="outcome",
            metric="ticket_resolved",
            customer_id=customer_id,
            properties={
                "resolution_time": 200,
                "escalated": False,
                "csat_score": 3.2,
                "ticket_id": "TK-1003",
            },
            idempotency_key="idem-outcome-003",
        ),
    ]

    outcome_event_ids: list[str] = []
    for idx, payload in enumerate(outcome_payloads):
        resp = await client.post("/v1/events", json=payload)
        assert resp.status_code == 202, (
            f"Expected 202 for outcome event {idx}, got {resp.status_code}: {resp.text}"
        )
        event_data = resp.json()
        assert "event_id" in event_data, f"Response for outcome event {idx} missing event_id"
        outcome_event_ids.append(event_data["event_id"])

    assert len(outcome_event_ids) == 3, "Should have ingested 3 outcome events"

    # ------------------------------------------------------------------
    # 6. Verify idempotency — resend the first outcome event
    # ------------------------------------------------------------------
    resp = await client.post("/v1/events", json=outcome_payloads[0])
    assert resp.status_code == 202, (
        f"Idempotent resend should return 202, got {resp.status_code}: {resp.text}"
    )
    idempotent_data: dict[str, Any] = resp.json()
    assert idempotent_data["event_id"] == outcome_event_ids[0], (
        "Idempotent resend should return the same event_id"
    )

    # ------------------------------------------------------------------
    # 7. Verify customer exists — GET /v1/customers/{id}
    # ------------------------------------------------------------------
    resp = await client.get(f"/v1/customers/{customer_id}")
    assert resp.status_code == 200, (
        f"Expected 200 fetching customer, got {resp.status_code}: {resp.text}"
    )
    fetched_customer: dict[str, Any] = resp.json()
    assert fetched_customer["id"] == customer_id, "Fetched customer ID mismatch"
    assert fetched_customer["name"] == "ResolvAI GmbH", "Fetched customer name mismatch"
    assert fetched_customer["email"] == "billing@resolvai.eu", "Fetched customer email mismatch"
    assert fetched_customer["external_id"] == "ext-resolvai-001", (
        "Fetched customer external_id mismatch"
    )
    assert fetched_customer["country_code"] == "DE", "Fetched customer country_code mismatch"
    assert fetched_customer["currency"] == "EUR", "Fetched customer currency mismatch"
    assert fetched_customer["is_business"] is True, "Fetched customer is_business mismatch"
    assert fetched_customer["billing_email"] == "invoices@resolvai.eu", (
        "Fetched customer billing_email mismatch"
    )
    assert fetched_customer["vat_number"] == "DE123456789", "Fetched customer vat_number mismatch"
    assert fetched_customer["created_at"] is not None, "Customer created_at should be set"
    assert fetched_customer["updated_at"] is not None, "Customer updated_at should be set"

    # ------------------------------------------------------------------
    # 8. Verify subscription is active — GET /v1/subscriptions/{id}
    # ------------------------------------------------------------------
    resp = await client.get(f"/v1/subscriptions/{subscription_id}")
    assert resp.status_code == 200, (
        f"Expected 200 fetching subscription, got {resp.status_code}: {resp.text}"
    )
    fetched_sub: dict[str, Any] = resp.json()
    assert fetched_sub["id"] == subscription_id, "Fetched subscription ID mismatch"
    assert fetched_sub["status"] == "active", "Subscription should still be active"
    assert fetched_sub["current_period_start"] is not None, "Period start should be set"
    assert fetched_sub["current_period_end"] is not None, "Period end should be set"
    assert fetched_sub["canceled_at"] is None, "Subscription should not be canceled"

    # ------------------------------------------------------------------
    # 9. List invoices — expect empty (no billing cycle run yet)
    # ------------------------------------------------------------------
    resp = await client.get("/v1/invoices", params={"customer_id": customer_id})
    assert resp.status_code == 200, (
        f"Expected 200 listing invoices, got {resp.status_code}: {resp.text}"
    )
    invoices_data: dict[str, Any] = resp.json()
    assert invoices_data["total"] == 0, "No invoices expected before billing cycle runs"
    assert invoices_data["items"] == [], "Invoice items list should be empty"
