"""Tests for the Rupiv Python SDK client."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# We import from the SDK package path directly so the tests work regardless
# of whether the package is installed.
# ---------------------------------------------------------------------------
import importlib
import sys
import os

# The SDK lives under src/rupiv/sdk/python/rupiv/ which clashes with the
# top-level rupiv package. We import the SDK modules by manipulating the
# path temporarily and using importlib.
_sdk_root = os.path.join(
    os.path.dirname(__file__), "..", "src", "rupiv", "sdk", "python",
)
sys.path.insert(0, _sdk_root)
# Save the main rupiv package then temporarily remove it so the SDK's
# rupiv sub-package can be found.
_main_rupiv = sys.modules.pop("rupiv", None)
_sdk_client_mod = importlib.import_module("rupiv.client")
_sdk_events_mod = importlib.import_module("rupiv.events")
_sdk_types_mod = importlib.import_module("rupiv.types")
# Restore
if _main_rupiv is not None:
    sys.modules["rupiv"] = _main_rupiv
sys.path.remove(_sdk_root)

Client = _sdk_client_mod.Client
AsyncClient = _sdk_client_mod.AsyncClient
EventBatcher = _sdk_events_mod.EventBatcher
RupivError = _sdk_types_mod.RupivError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=timezone.utc).isoformat()


def _make_response(
    status_code: int = 200,
    json_data: Any = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Build a fake httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        headers=headers or {},
        request=httpx.Request("GET", "https://api.rupiv.ai"),
    )
    return resp


# ---------------------------------------------------------------------------
# Sync Client tests
# ---------------------------------------------------------------------------


class TestClientTrackEvent:
    """test_client_track_event -- mock httpx, verify request shape."""

    def test_sends_usage_event(self) -> None:
        json_data = {
            "id": "evt_001",
            "type": "usage",
            "metric": "api_call",
            "customer_id": "cust_123",
            "properties": {"tokens": 150},
            "idempotency_key": "key-1",
            "created_at": _NOW,
        }
        mock_response = _make_response(json_data=json_data)

        with patch.object(httpx.Client, "post", return_value=mock_response) as mock_post:
            client = Client(api_key="rp_test_xxx")
            result = client.track_event(
                metric="api_call",
                customer_id="cust_123",
                properties={"tokens": 150},
                idempotency_key="key-1",
            )

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "/v1/events"
            payload = call_args[1]["json"]
            assert payload["metric"] == "api_call"
            assert payload["customer_id"] == "cust_123"
            assert payload["type"] == "usage"
            assert payload["properties"] == {"tokens": 150}
            assert payload["idempotency_key"] == "key-1"

            assert result.id == "evt_001"
            assert result.type == "usage"
            assert result.metric == "api_call"
            client.close()

    def test_auto_generates_idempotency_key(self) -> None:
        json_data = {
            "id": "evt_002",
            "type": "usage",
            "metric": "api_call",
            "customer_id": "cust_123",
            "properties": {},
            "idempotency_key": "auto-uuid",
            "created_at": _NOW,
        }
        mock_response = _make_response(json_data=json_data)

        with patch.object(httpx.Client, "post", return_value=mock_response) as mock_post:
            client = Client(api_key="rp_test_xxx")
            client.track_event(metric="api_call", customer_id="cust_123")

            payload = mock_post.call_args[1]["json"]
            # Should have auto-generated a UUID idempotency key
            assert payload["idempotency_key"] is not None
            assert len(payload["idempotency_key"]) > 0
            client.close()


class TestClientTrackOutcome:
    """test_client_track_outcome -- verify type='outcome'."""

    def test_sends_outcome_event(self) -> None:
        json_data = {
            "id": "evt_003",
            "type": "outcome",
            "metric": "ticket_resolved",
            "customer_id": "cust_456",
            "properties": {"resolution_time": 45},
            "idempotency_key": "key-2",
            "created_at": _NOW,
        }
        mock_response = _make_response(json_data=json_data)

        with patch.object(httpx.Client, "post", return_value=mock_response) as mock_post:
            client = Client(api_key="rp_test_xxx")
            result = client.track_outcome(
                metric="ticket_resolved",
                customer_id="cust_456",
                properties={"resolution_time": 45},
                idempotency_key="key-2",
            )

            payload = mock_post.call_args[1]["json"]
            assert payload["type"] == "outcome"
            assert result.type == "outcome"
            assert result.metric == "ticket_resolved"
            client.close()


class TestClientCreateQuote:
    """test_client_create_quote -- verify POST to /v1/quotes."""

    def test_creates_quote(self) -> None:
        json_data = {
            "id": "qt_001",
            "customer_id": "cust_123",
            "plan_id": "plan_abc",
            "status": "draft",
            "currency": "eur",
            "discount_pct": 10.0,
            "term_months": 12,
            "subtotal": 120000,
            "total": 108000,
            "line_items": [],
            "rejection_reason": None,
            "sent_at": None,
            "accepted_at": None,
            "rejected_at": None,
            "expires_at": None,
            "created_at": _NOW,
        }
        mock_response = _make_response(json_data=json_data)

        with patch.object(httpx.Client, "post", return_value=mock_response) as mock_post:
            client = Client(api_key="rp_test_xxx")
            result = client.create_quote(
                customer_id="cust_123",
                plan_id="plan_abc",
                discount_pct=10.0,
                term_months=12,
            )

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "/v1/quotes"
            payload = call_args[1]["json"]
            assert payload["customer_id"] == "cust_123"
            assert payload["plan_id"] == "plan_abc"
            assert payload["discount_pct"] == 10.0
            assert payload["term_months"] == 12
            assert "idempotency_key" in payload

            assert result.id == "qt_001"
            assert result.status == "draft"
            assert result.total == 108000
            client.close()


class TestClientGetCredits:
    """test_client_get_credits -- verify GET to /v1/credits/{id}/balance."""

    def test_fetches_credit_balance(self) -> None:
        json_data = {
            "customer_id": "cust_123",
            "balance": 5000,
            "currency": "eur",
            "updated_at": _NOW,
        }
        mock_response = _make_response(json_data=json_data)

        with patch.object(httpx.Client, "get", return_value=mock_response) as mock_get:
            client = Client(api_key="rp_test_xxx")
            result = client.get_credits("cust_123")

            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "/v1/credits/cust_123/balance"

            assert result.customer_id == "cust_123"
            assert result.balance == 5000
            assert result.currency == "eur"
            client.close()


# ---------------------------------------------------------------------------
# Async Client tests
# ---------------------------------------------------------------------------


class TestAsyncClientTrackEvent:
    """test_async_client_track_event -- same but async."""

    def test_sends_usage_event_async(self) -> None:
        json_data = {
            "id": "evt_010",
            "type": "usage",
            "metric": "api_call",
            "customer_id": "cust_789",
            "properties": {"tokens": 200},
            "idempotency_key": "key-async-1",
            "created_at": _NOW,
        }
        mock_response = _make_response(json_data=json_data)

        async def _run() -> None:
            with patch.object(
                httpx.AsyncClient, "post", return_value=mock_response
            ) as mock_post:
                client = AsyncClient(api_key="rp_test_xxx")
                result = await client.track_event(
                    metric="api_call",
                    customer_id="cust_789",
                    properties={"tokens": 200},
                    idempotency_key="key-async-1",
                )

                mock_post.assert_called_once()
                call_args = mock_post.call_args
                assert call_args[0][0] == "/v1/events"
                payload = call_args[1]["json"]
                assert payload["metric"] == "api_call"
                assert payload["type"] == "usage"

                assert result.id == "evt_010"
                assert result.type == "usage"
                await client.close()

        asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# EventBatcher tests
# ---------------------------------------------------------------------------


class TestEventBatcherFlush:
    """test_event_batcher_flush -- add events, flush, verify batch sent."""

    def test_flush_sends_batch(self) -> None:
        batch_response = _make_response(
            json_data={"accepted": 3, "errors": []},
        )

        with patch.object(
            httpx.Client, "post", return_value=batch_response
        ) as mock_post:
            batcher = EventBatcher(
                api_key="rp_test_xxx",
                max_batch_size=100,
                max_wait_seconds=60,
            )

            batcher.add("api_call", "cust_1", "usage", {"tokens": 10})
            batcher.add("api_call", "cust_2", "usage", {"tokens": 20})
            batcher.add("ticket_resolved", "cust_3", "outcome", {"csat": 4.5})

            batcher.flush()

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "/v1/events/batch"
            events = call_args[1]["json"]["events"]
            assert len(events) == 3
            assert events[0]["metric"] == "api_call"
            assert events[0]["customer_id"] == "cust_1"
            assert events[2]["type"] == "outcome"

            # Each event should have an auto-generated idempotency key
            for event in events:
                assert "idempotency_key" in event
                assert len(event["idempotency_key"]) > 0

            batcher.close()

    def test_flush_noop_when_empty(self) -> None:
        with patch.object(httpx.Client, "post") as mock_post:
            batcher = EventBatcher(
                api_key="rp_test_xxx",
                max_batch_size=100,
                max_wait_seconds=60,
            )
            batcher.flush()
            mock_post.assert_not_called()
            batcher.close()

    def test_auto_flush_on_max_batch_size(self) -> None:
        batch_response = _make_response(
            json_data={"accepted": 2, "errors": []},
        )

        with patch.object(
            httpx.Client, "post", return_value=batch_response
        ) as mock_post:
            batcher = EventBatcher(
                api_key="rp_test_xxx",
                max_batch_size=2,
                max_wait_seconds=60,
            )

            batcher.add("api_call", "cust_1", "usage")
            # Should not have flushed yet
            assert mock_post.call_count == 0

            batcher.add("api_call", "cust_2", "usage")
            # Should auto-flush after reaching batch size of 2
            assert mock_post.call_count == 1

            batcher.close()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Verify that non-2xx responses raise RupivError."""

    def test_raises_rupiv_error_on_4xx(self) -> None:
        error_response = _make_response(
            status_code=422,
            json_data={"error": {"message": "Invalid plan_id"}},
            headers={"x-request-id": "req_abc"},
        )

        with patch.object(httpx.Client, "post", return_value=error_response):
            client = Client(api_key="rp_test_xxx")
            with pytest.raises(RupivError) as exc_info:
                client.create_quote(
                    customer_id="cust_123",
                    plan_id="bad_plan",
                )
            assert exc_info.value.status_code == 422
            assert "Invalid plan_id" in exc_info.value.message
            assert exc_info.value.request_id == "req_abc"
            client.close()
