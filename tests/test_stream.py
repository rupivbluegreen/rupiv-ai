"""Tests for the WebSocket event stream at /v1/stream/events.

Uses Starlette's ``TestClient`` which provides synchronous WebSocket testing
via ``client.websocket_connect()``.  Redis pub/sub is mocked so no live
Redis is required.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from rupiv.api.v1.stream import ConnectionManager, _matches_filters


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ws_client(app: Any) -> TestClient:
    """Starlette TestClient for synchronous WebSocket testing."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Unit tests for _matches_filters
# ---------------------------------------------------------------------------


class TestMatchesFilters:
    """Tests for the ``_matches_filters`` helper."""

    def test_no_filters_matches_everything(self) -> None:
        event: dict[str, Any] = {"event_type": "usage", "metric": "api_call"}
        assert _matches_filters(event, event_type=None, metric=None) is True

    def test_type_filter_matches(self) -> None:
        event: dict[str, Any] = {"event_type": "outcome", "metric": "ticket_resolved"}
        assert _matches_filters(event, event_type="outcome", metric=None) is True

    def test_type_filter_rejects(self) -> None:
        event: dict[str, Any] = {"event_type": "usage", "metric": "api_call"}
        assert _matches_filters(event, event_type="outcome", metric=None) is False

    def test_metric_filter_matches(self) -> None:
        event: dict[str, Any] = {"event_type": "usage", "metric": "api_call"}
        assert _matches_filters(event, event_type=None, metric="api_call") is True

    def test_metric_filter_rejects(self) -> None:
        event: dict[str, Any] = {"event_type": "usage", "metric": "api_call"}
        assert _matches_filters(event, event_type=None, metric="tokens") is False

    def test_both_filters_match(self) -> None:
        event: dict[str, Any] = {"event_type": "outcome", "metric": "ticket_resolved"}
        assert _matches_filters(event, event_type="outcome", metric="ticket_resolved") is True

    def test_both_filters_partial_mismatch(self) -> None:
        event: dict[str, Any] = {"event_type": "outcome", "metric": "ticket_resolved"}
        assert _matches_filters(event, event_type="outcome", metric="api_call") is False


# ---------------------------------------------------------------------------
# ConnectionManager unit tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    """Tests for the ``ConnectionManager`` class."""

    @pytest.fixture()
    def mgr(self) -> ConnectionManager:
        return ConnectionManager()

    async def test_connect_adds_websocket(self, mgr: ConnectionManager) -> None:
        ws: AsyncMock = AsyncMock()
        await mgr.connect(ws)
        assert ws in mgr.active_connections
        ws.accept.assert_awaited_once()

    async def test_disconnect_removes_websocket(self, mgr: ConnectionManager) -> None:
        ws: AsyncMock = AsyncMock()
        await mgr.connect(ws)
        mgr.disconnect(ws)
        assert ws not in mgr.active_connections

    async def test_disconnect_ignores_unknown_websocket(
        self, mgr: ConnectionManager,
    ) -> None:
        ws: AsyncMock = AsyncMock()
        # Should not raise
        mgr.disconnect(ws)
        assert mgr.active_connections == []

    async def test_broadcast_sends_to_all(self, mgr: ConnectionManager) -> None:
        ws1: AsyncMock = AsyncMock()
        ws2: AsyncMock = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        await mgr.broadcast("hello")

        ws1.send_text.assert_awaited_once_with("hello")
        ws2.send_text.assert_awaited_once_with("hello")

    async def test_broadcast_removes_failed_connections(
        self, mgr: ConnectionManager,
    ) -> None:
        ws_good: AsyncMock = AsyncMock()
        ws_bad: AsyncMock = AsyncMock()
        ws_bad.send_text.side_effect = RuntimeError("connection lost")

        await mgr.connect(ws_good)
        await mgr.connect(ws_bad)

        await mgr.broadcast("test")

        assert ws_good in mgr.active_connections
        assert ws_bad not in mgr.active_connections


# ---------------------------------------------------------------------------
# WebSocket integration tests
# ---------------------------------------------------------------------------


def _make_mock_redis() -> tuple[MagicMock, MagicMock]:
    """Build a mock Redis client and pubsub that the stream handler expects."""
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_redis.aclose = AsyncMock()

    return mock_redis, mock_pubsub


async def _empty_async_gen() -> Any:  # noqa: ANN401
    """Async generator that yields nothing -- stubs Redis pubsub.listen()."""
    return
    yield  # noqa: unreachable -- makes this a generator


class TestWebSocketConnect:
    """Integration tests for the /v1/stream/events WebSocket endpoint."""

    def test_websocket_connect_accepted(self, ws_client: TestClient) -> None:
        """Connecting to the WebSocket endpoint should succeed."""
        mock_redis, mock_pubsub = _make_mock_redis()
        mock_pubsub.listen = MagicMock(return_value=_empty_async_gen())

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with ws_client.websocket_connect("/v1/stream/events") as ws:
                # Connection was accepted -- close gracefully
                ws.close()

    def test_websocket_rejects_empty_api_key(self, ws_client: TestClient) -> None:
        """An empty api_key query parameter should close the connection."""
        with pytest.raises(Exception):
            with ws_client.websocket_connect("/v1/stream/events?api_key=") as ws:
                ws.receive_text()

    def test_websocket_receives_broadcast_event(self, ws_client: TestClient) -> None:
        """The WebSocket should receive events forwarded from Redis pub/sub."""
        sample_event: str = json.dumps({
            "event_type": "outcome",
            "metric": "ticket_resolved",
            "customer_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        })

        async def _one_message_gen() -> Any:  # noqa: ANN401
            """Async generator that yields one Redis pub/sub message then blocks."""
            yield {
                "type": "message",
                "data": sample_event,
            }
            # Block until the test client closes the socket
            await asyncio.sleep(999)

        mock_redis, mock_pubsub = _make_mock_redis()
        mock_pubsub.listen = MagicMock(return_value=_one_message_gen())

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            with ws_client.websocket_connect("/v1/stream/events") as ws:
                data: str = ws.receive_text()
                parsed: dict[str, Any] = json.loads(data)
                assert parsed["event_type"] == "outcome"
                assert parsed["metric"] == "ticket_resolved"
                ws.close()
