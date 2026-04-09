"""Tests for the event ingestion endpoint POST /v1/events.

These tests hit the real SQLite-backed database through the test session,
with the BullMQ metering call mocked out.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from tests.conftest import make_event_payload


# ---------------------------------------------------------------------------
# Helper: patch ingest_event so BullMQ/Redis are never called
# ---------------------------------------------------------------------------

def _patch_ingest() -> Any:
    """Return a context-manager that stubs out ``ingest_event``."""
    return patch(
        "rupiv.api.v1.events.ingest_event",
        new_callable=AsyncMock,
    )


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


async def test_create_usage_event_returns_202(
    client: AsyncClient,
    sample_customer: dict[str, Any],
) -> None:
    """POST /v1/events with a valid usage event should return 202 Accepted."""
    payload = make_event_payload(
        event_type="usage",
        metric="api_call",
        customer_id=sample_customer["id"],
    )

    with _patch_ingest():
        response = await client.post("/v1/events", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    # Verify the response contains a valid UUID for event_id
    uuid.UUID(body["event_id"])


async def test_create_outcome_event_returns_202(
    client: AsyncClient,
    sample_customer: dict[str, Any],
    sample_event: dict[str, Any],
) -> None:
    """POST /v1/events with a valid outcome event should return 202 Accepted."""
    with _patch_ingest():
        response = await client.post("/v1/events", json=sample_event)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    uuid.UUID(body["event_id"])


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


async def test_create_event_missing_fields_returns_422(
    client: AsyncClient,
) -> None:
    """POST /v1/events with missing required fields should return 422."""
    with _patch_ingest():
        response = await client.post("/v1/events", json={})

    assert response.status_code == 422


async def test_create_event_invalid_type_returns_422(
    client: AsyncClient,
    sample_customer: dict[str, Any],
    sample_event: dict[str, Any],
) -> None:
    """POST /v1/events with an invalid event type should return 422."""
    payload = {**sample_event, "type": "unknown_type"}

    with _patch_ingest():
        response = await client.post("/v1/events", json=payload)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


async def test_idempotency_key_deduplication(
    client: AsyncClient,
    sample_customer: dict[str, Any],
    sample_event: dict[str, Any],
) -> None:
    """Sending the same idempotency_key twice should return the same event_id."""
    with _patch_ingest():
        first = await client.post("/v1/events", json=sample_event)
        second = await client.post("/v1/events", json=sample_event)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["event_id"] == second.json()["event_id"]
