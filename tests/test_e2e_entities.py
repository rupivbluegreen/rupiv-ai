"""End-to-end entity hierarchy tests via the API."""

from __future__ import annotations

from typing import Any

import httpx
import pytest


async def test_entity_hierarchy(client: httpx.AsyncClient) -> None:
    """Create parent + child entities and verify hierarchy endpoints.

    1. Create parent entity (BV, NL)
    2. Create child entity (GmbH, DE) with parent_id
    3. GET /v1/entities/{parent_id}/children -> verify child present
    4. GET /v1/entities/{child_id}/ancestors -> verify parent present
    5. List entities -> verify both present
    """

    # ------------------------------------------------------------------
    # 1. Create parent entity (BV, NL)
    # ------------------------------------------------------------------
    parent_payload: dict[str, Any] = {
        "name": "HoldCo BV",
        "entity_type": "bv",
        "country_code": "NL",
        "currency": "EUR",
        "vat_number": "NL001234567B01",
    }
    resp = await client.post("/v1/entities", json=parent_payload)
    assert resp.status_code == 201, f"Expected 201 creating parent entity, got {resp.status_code}: {resp.text}"

    parent_data: dict[str, Any] = resp.json()
    parent_id: str = parent_data["id"]

    assert parent_data["name"] == "HoldCo BV", "Parent entity name mismatch"
    assert parent_data["entity_type"] == "bv", "Parent entity type mismatch"
    assert parent_data["country_code"] == "NL", "Parent country_code mismatch"
    assert parent_data["default_currency"] == "EUR", "Parent currency mismatch"
    assert parent_data["vat_number"] == "NL001234567B01", "Parent vat_number mismatch"
    assert parent_data["is_active"] is True, "Parent entity should be active"
    assert parent_data["parent_id"] is None, "Root entity should have no parent"
    assert parent_data["created_at"] is not None, "created_at should be set"
    assert parent_data["updated_at"] is not None, "updated_at should be set"

    # ------------------------------------------------------------------
    # 2. Create child entity (GmbH, DE) with parent_id
    # ------------------------------------------------------------------
    child_payload: dict[str, Any] = {
        "name": "OpsCo GmbH",
        "entity_type": "gmbh",
        "country_code": "DE",
        "currency": "EUR",
        "parent_id": parent_id,
        "vat_number": "DE987654321",
    }
    resp = await client.post("/v1/entities", json=child_payload)
    assert resp.status_code == 201, f"Expected 201 creating child entity, got {resp.status_code}: {resp.text}"

    child_data: dict[str, Any] = resp.json()
    child_id: str = child_data["id"]

    assert child_data["name"] == "OpsCo GmbH", "Child entity name mismatch"
    assert child_data["entity_type"] == "gmbh", "Child entity type mismatch"
    assert child_data["country_code"] == "DE", "Child country_code mismatch"
    assert child_data["default_currency"] == "EUR", "Child currency mismatch"
    assert child_data["parent_id"] == parent_id, "Child parent_id should point to parent"
    assert child_data["vat_number"] == "DE987654321", "Child vat_number mismatch"
    assert child_data["is_active"] is True, "Child entity should be active"

    # ------------------------------------------------------------------
    # 3. GET /v1/entities/{parent_id}/children -> verify child present
    # ------------------------------------------------------------------
    resp = await client.get(f"/v1/entities/{parent_id}/children")
    assert resp.status_code == 200, (
        f"Expected 200 fetching children, got {resp.status_code}: {resp.text}"
    )

    children_data: dict[str, Any] = resp.json()
    assert children_data["total"] >= 1, "Parent should have at least 1 child"

    child_ids: list[str] = [item["id"] for item in children_data["items"]]
    assert child_id in child_ids, "Child entity should appear in parent's children list"

    # Verify the child data in the list
    child_in_list: dict[str, Any] = next(
        item for item in children_data["items"] if item["id"] == child_id
    )
    assert child_in_list["name"] == "OpsCo GmbH", "Child name in list mismatch"
    assert child_in_list["entity_type"] == "gmbh", "Child type in list mismatch"
    assert child_in_list["country_code"] == "DE", "Child country in list mismatch"

    # ------------------------------------------------------------------
    # 4. GET /v1/entities/{child_id}/ancestors -> verify parent present
    # ------------------------------------------------------------------
    resp = await client.get(f"/v1/entities/{child_id}/ancestors")
    assert resp.status_code == 200, (
        f"Expected 200 fetching ancestors, got {resp.status_code}: {resp.text}"
    )

    ancestors_data: dict[str, Any] = resp.json()
    assert ancestors_data["total"] >= 1, "Child should have at least 1 ancestor"

    ancestor_ids: list[str] = [item["id"] for item in ancestors_data["items"]]
    assert parent_id in ancestor_ids, "Parent entity should appear in child's ancestors"

    # Verify the parent data in the ancestors list
    parent_in_list: dict[str, Any] = next(
        item for item in ancestors_data["items"] if item["id"] == parent_id
    )
    assert parent_in_list["name"] == "HoldCo BV", "Parent name in ancestors mismatch"
    assert parent_in_list["entity_type"] == "bv", "Parent type in ancestors mismatch"
    assert parent_in_list["country_code"] == "NL", "Parent country in ancestors mismatch"

    # ------------------------------------------------------------------
    # 5. List entities -> verify both present
    # ------------------------------------------------------------------
    resp = await client.get("/v1/entities")
    assert resp.status_code == 200, f"Expected 200 listing entities, got {resp.status_code}: {resp.text}"

    list_data: dict[str, Any] = resp.json()
    assert list_data["total"] >= 2, "Should have at least 2 entities"

    all_ids: list[str] = [item["id"] for item in list_data["items"]]
    assert parent_id in all_ids, "Parent entity should appear in entity list"
    assert child_id in all_ids, "Child entity should appear in entity list"


async def test_entity_get_by_id(client: httpx.AsyncClient) -> None:
    """Create an entity and verify it can be retrieved by ID."""
    payload: dict[str, Any] = {
        "name": "Fetch Test SAS",
        "entity_type": "sas",
        "country_code": "FR",
        "currency": "EUR",
        "vat_number": "FR12345678901",
    }
    resp = await client.post("/v1/entities", json=payload)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    entity_id: str = resp.json()["id"]

    resp = await client.get(f"/v1/entities/{entity_id}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    data: dict[str, Any] = resp.json()
    assert data["id"] == entity_id, "Entity ID mismatch"
    assert data["name"] == "Fetch Test SAS", "Entity name mismatch"
    assert data["entity_type"] == "sas", "Entity type mismatch"
    assert data["country_code"] == "FR", "Entity country_code mismatch"


async def test_entity_not_found(client: httpx.AsyncClient) -> None:
    """GET for a non-existent entity returns 404."""
    resp = await client.get("/v1/entities/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404, f"Expected 404 for non-existent entity, got {resp.status_code}"
