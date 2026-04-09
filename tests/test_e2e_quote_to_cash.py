"""End-to-end quote-to-cash lifecycle: entity -> customer -> plan -> quote -> accept -> subscription -> events."""

from __future__ import annotations

from typing import Any

import httpx

from tests.conftest import make_event_payload


async def test_quote_to_cash_lifecycle(client: httpx.AsyncClient) -> None:
    """entity -> customer -> plan -> quote -> accept -> subscription -> events -> invoice.

    Walks through the full happy-path quote-to-cash flow via the API,
    verifying status codes and response content at every step.
    """

    # ------------------------------------------------------------------
    # 1. Create a legal entity (BV, NL)
    # ------------------------------------------------------------------
    entity_payload: dict[str, Any] = {
        "name": "TestCo BV",
        "entity_type": "bv",
        "country_code": "NL",
        "currency": "EUR",
        "vat_number": "NL123456789B01",
    }
    resp = await client.post("/v1/entities", json=entity_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating entity, got {resp.status_code}: {resp.text}"
    )

    entity_data: dict[str, Any] = resp.json()
    entity_id: str = entity_data["id"]

    assert entity_data["name"] == "TestCo BV", "Entity name mismatch"
    assert entity_data["entity_type"] == "bv", "Entity type mismatch"
    assert entity_data["country_code"] == "NL", "Entity country_code mismatch"
    assert entity_data["default_currency"] == "EUR", "Entity currency mismatch"
    assert entity_data["vat_number"] == "NL123456789B01", "Entity vat_number mismatch"
    assert entity_data["is_active"] is True, "New entity should be active"

    # ------------------------------------------------------------------
    # 2. Create a customer linked to the entity context
    # ------------------------------------------------------------------
    customer_payload: dict[str, Any] = {
        "name": "Resolvo AI BV",
        "email": "finance@resolvo.nl",
        "external_id": "ext-resolvo-001",
        "country_code": "NL",
        "currency": "EUR",
        "is_business": True,
        "billing_email": "invoices@resolvo.nl",
        "vat_number": "NL987654321B01",
        "metadata": {"entity_id": entity_id, "segment": "enterprise"},
    }
    resp = await client.post("/v1/customers", json=customer_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating customer, got {resp.status_code}: {resp.text}"
    )

    customer_data: dict[str, Any] = resp.json()
    customer_id: str = customer_data["id"]

    assert customer_data["name"] == "Resolvo AI BV", "Customer name mismatch"
    assert customer_data["email"] == "finance@resolvo.nl", "Customer email mismatch"
    assert customer_data["country_code"] == "NL", "Customer country_code mismatch"
    assert customer_data["currency"] == "EUR", "Customer currency mismatch"
    assert customer_data["is_business"] is True, "Customer is_business mismatch"
    assert customer_data["vat_number"] == "NL987654321B01", "Customer vat_number mismatch"

    # ------------------------------------------------------------------
    # 3. Create a hybrid plan: flat EUR 149 + outcome EUR 0.99/ticket_resolved
    # ------------------------------------------------------------------
    plan_payload: dict[str, Any] = {
        "name": "Hybrid Growth NL",
        "description": "Flat base fee EUR 149 plus EUR 0.99 per resolved ticket",
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

    assert plan_data["name"] == "Hybrid Growth NL", "Plan name mismatch"
    assert plan_data["currency"] == "EUR", "Plan currency mismatch"
    assert plan_data["billing_period"] == "monthly", "Plan billing_period mismatch"
    assert len(plan_data["pricing_rules"]) == 2, "Expected 2 pricing rules"

    flat_rule: dict[str, Any] = plan_data["pricing_rules"][0]
    outcome_rule: dict[str, Any] = plan_data["pricing_rules"][1]
    assert flat_rule["model"] == "flat", "First rule should be flat"
    assert outcome_rule["model"] == "outcome", "Second rule should be outcome"
    assert outcome_rule["metric"] == "ticket_resolved", "Outcome metric mismatch"

    # ------------------------------------------------------------------
    # 4. Create a quote: customer_id, plan_id, 10% discount, 12 month term
    # ------------------------------------------------------------------
    quote_payload: dict[str, Any] = {
        "customer_id": customer_id,
        "plan_id": plan_id,
        "discount_pct": "10.00",
        "term_months": 12,
    }
    resp = await client.post("/v1/quotes", json=quote_payload)
    assert resp.status_code == 201, (
        f"Expected 201 creating quote, got {resp.status_code}: {resp.text}"
    )

    quote_data: dict[str, Any] = resp.json()
    quote_id: str = quote_data["id"]

    # ------------------------------------------------------------------
    # 5. Verify quote status is draft, line items present
    # ------------------------------------------------------------------
    assert quote_data["status"] == "draft", "New quote should be in draft status"
    assert quote_data["customer_id"] == customer_id, "Quote customer_id mismatch"
    assert quote_data["plan_id"] == plan_id, "Quote plan_id mismatch"
    assert quote_data["currency"] == "EUR", "Quote currency mismatch"
    assert quote_data["term_months"] == 12, "Quote term_months mismatch"
    assert float(quote_data["discount_pct"]) == 10.0, "Quote discount_pct mismatch"
    assert len(quote_data["line_items"]) >= 1, "Quote should have at least one line item"
    assert quote_data["expires_at"] is not None, "Quote expires_at should be set"
    assert quote_data["estimated_monthly"] is not None, "estimated_monthly should be set"
    assert quote_data["estimated_total"] is not None, "estimated_total should be set"

    # ------------------------------------------------------------------
    # 6. Send the quote, verify status = sent
    # ------------------------------------------------------------------
    resp = await client.post(f"/v1/quotes/{quote_id}/send")
    assert resp.status_code == 200, (
        f"Expected 200 sending quote, got {resp.status_code}: {resp.text}"
    )

    sent_data: dict[str, Any] = resp.json()
    assert sent_data["status"] == "sent", "Quote status should be 'sent' after sending"
    assert sent_data["id"] == quote_id, "Sent quote ID mismatch"

    # ------------------------------------------------------------------
    # 7. Accept the quote, verify subscription + contract created
    # ------------------------------------------------------------------
    resp = await client.post(f"/v1/quotes/{quote_id}/accept")
    assert resp.status_code == 200, (
        f"Expected 200 accepting quote, got {resp.status_code}: {resp.text}"
    )

    accept_data: dict[str, Any] = resp.json()
    assert accept_data["quote_id"] == quote_id, "Accept response quote_id mismatch"
    assert "subscription_id" in accept_data, "Accept response should contain subscription_id"
    assert "contract_id" in accept_data, "Accept response should contain contract_id"

    subscription_id: str = accept_data["subscription_id"]
    contract_id: str = accept_data["contract_id"]

    assert subscription_id is not None, "subscription_id should not be None"
    assert contract_id is not None, "contract_id should not be None"

    # Verify the quote itself is now in accepted status
    resp = await client.get(f"/v1/quotes/{quote_id}")
    assert resp.status_code == 200, (
        f"Expected 200 fetching accepted quote, got {resp.status_code}: {resp.text}"
    )

    accepted_quote: dict[str, Any] = resp.json()
    assert accepted_quote["status"] == "accepted", "Quote should be in accepted status"
    assert accepted_quote["accepted_at"] is not None, "accepted_at should be set"

    # ------------------------------------------------------------------
    # 8. Send 3 outcome events (ticket_resolved)
    # ------------------------------------------------------------------
    outcome_event_ids: list[str] = []
    ticket_payloads: list[dict[str, Any]] = [
        make_event_payload(
            event_type="outcome",
            metric="ticket_resolved",
            customer_id=customer_id,
            properties={
                "resolution_time": 60,
                "escalated": False,
                "csat_score": 4.5,
                "ticket_id": "TK-NL-001",
            },
            idempotency_key="idem-qtc-outcome-001",
        ),
        make_event_payload(
            event_type="outcome",
            metric="ticket_resolved",
            customer_id=customer_id,
            properties={
                "resolution_time": 90,
                "escalated": False,
                "csat_score": 3.8,
                "ticket_id": "TK-NL-002",
            },
            idempotency_key="idem-qtc-outcome-002",
        ),
        make_event_payload(
            event_type="outcome",
            metric="ticket_resolved",
            customer_id=customer_id,
            properties={
                "resolution_time": 150,
                "escalated": False,
                "csat_score": 4.2,
                "ticket_id": "TK-NL-003",
            },
            idempotency_key="idem-qtc-outcome-003",
        ),
    ]

    for idx, payload in enumerate(ticket_payloads):
        resp = await client.post("/v1/events", json=payload)
        assert resp.status_code == 202, (
            f"Expected 202 for outcome event {idx}, got {resp.status_code}: {resp.text}"
        )
        event_data: dict[str, Any] = resp.json()
        assert "event_id" in event_data, f"Response for outcome event {idx} missing event_id"
        assert event_data["status"] == "accepted", (
            f"Outcome event {idx} status should be 'accepted'"
        )
        outcome_event_ids.append(event_data["event_id"])

    assert len(outcome_event_ids) == 3, "Should have ingested 3 outcome events"

    # ------------------------------------------------------------------
    # 9. Verify subscription is active
    # ------------------------------------------------------------------
    resp = await client.get(f"/v1/subscriptions/{subscription_id}")
    assert resp.status_code == 200, (
        f"Expected 200 fetching subscription, got {resp.status_code}: {resp.text}"
    )

    sub_data: dict[str, Any] = resp.json()
    assert sub_data["id"] == subscription_id, "Subscription ID mismatch"
    assert sub_data["status"] == "active", "Subscription should be active"
    assert sub_data["customer_id"] == customer_id, "Subscription customer_id mismatch"
    assert sub_data["plan_id"] == plan_id, "Subscription plan_id mismatch"
    assert sub_data["current_period_start"] is not None, "Period start should be set"
    assert sub_data["current_period_end"] is not None, "Period end should be set"
    assert sub_data["canceled_at"] is None, "Subscription should not be canceled"

    # ------------------------------------------------------------------
    # 10. Verify entity still accessible
    # ------------------------------------------------------------------
    resp = await client.get(f"/v1/entities/{entity_id}")
    assert resp.status_code == 200, (
        f"Expected 200 fetching entity, got {resp.status_code}: {resp.text}"
    )

    fetched_entity: dict[str, Any] = resp.json()
    assert fetched_entity["id"] == entity_id, "Fetched entity ID mismatch"
    assert fetched_entity["name"] == "TestCo BV", "Fetched entity name mismatch"
    assert fetched_entity["is_active"] is True, "Entity should still be active"
