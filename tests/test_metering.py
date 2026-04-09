"""Tests for rupiv.billing.metering — event ingestion and Redis enqueue."""

from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from rupiv.billing.metering import (
    EVENTS_QUEUE_KEY,
    EVENTS_STREAM_CHANNEL,
    ingest_event,
)


def _make_mock_redis() -> MagicMock:
    """Create a mock redis client with async methods."""
    mock_redis = MagicMock()
    mock_redis.rpush = AsyncMock()
    mock_redis.publish = AsyncMock()
    mock_redis.aclose = AsyncMock()
    return mock_redis


def _make_mock_aioredis_module(mock_redis: MagicMock) -> MagicMock:
    """Create a mock redis.asyncio module whose from_url returns mock_redis."""
    mock_module = MagicMock()
    mock_module.from_url.return_value = mock_redis
    return mock_module


class TestIngestEvent:
    """Tests for the ingest_event function."""

    async def test_ingest_event_pushes_to_redis(self) -> None:
        """ingest_event should rpush the event JSON to the Redis queue."""
        mock_redis = _make_mock_redis()
        mock_aioredis = _make_mock_aioredis_module(mock_redis)

        # Save originals
        orig_redis = sys.modules.get("redis")
        orig_redis_asyncio = sys.modules.get("redis.asyncio")

        # Create a mock redis parent that has .asyncio pointing to our mock
        mock_redis_parent = MagicMock()
        mock_redis_parent.asyncio = mock_aioredis

        try:
            sys.modules["redis"] = mock_redis_parent
            sys.modules["redis.asyncio"] = mock_aioredis

            result: dict[str, Any] = await ingest_event(
                customer_id="cust-001",
                metric="api_call",
                value=1.0,
                properties={"region": "eu-west"},
                idempotency_key="idem-001",
            )
        finally:
            # Restore originals
            if orig_redis is not None:
                sys.modules["redis"] = orig_redis
            else:
                sys.modules.pop("redis", None)
            if orig_redis_asyncio is not None:
                sys.modules["redis.asyncio"] = orig_redis_asyncio
            else:
                sys.modules.pop("redis.asyncio", None)

        mock_redis.rpush.assert_awaited_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == EVENTS_QUEUE_KEY

        # Verify the pushed JSON is valid and contains expected fields
        pushed_json = call_args[0][1]
        payload = json.loads(pushed_json)
        assert payload["customer_id"] == "cust-001"
        assert payload["metric"] == "api_call"
        assert payload["value"] == 1.0
        assert payload["idempotency_key"] == "idem-001"
        assert result["event_id"] == payload["event_id"]

    async def test_ingest_event_redis_unavailable(self) -> None:
        """When Redis is unavailable, ingest_event should not crash."""
        mock_aioredis = MagicMock()
        mock_aioredis.from_url.side_effect = ConnectionError("Redis down")

        mock_redis_parent = MagicMock()
        mock_redis_parent.asyncio = mock_aioredis

        orig_redis = sys.modules.get("redis")
        orig_redis_asyncio = sys.modules.get("redis.asyncio")
        try:
            sys.modules["redis"] = mock_redis_parent
            sys.modules["redis.asyncio"] = mock_aioredis

            result: dict[str, Any] = await ingest_event(
                customer_id="cust-002",
                metric="api_call",
                value=1.0,
            )
        finally:
            if orig_redis is not None:
                sys.modules["redis"] = orig_redis
            else:
                sys.modules.pop("redis", None)
            if orig_redis_asyncio is not None:
                sys.modules["redis.asyncio"] = orig_redis_asyncio
            else:
                sys.modules.pop("redis.asyncio", None)

        # Should still return a valid payload dict
        assert "event_id" in result
        assert result["customer_id"] == "cust-002"
        assert result["metric"] == "api_call"

    async def test_ingest_event_publishes_to_stream(self) -> None:
        """ingest_event should PUBLISH the event to the stream channel."""
        mock_redis = _make_mock_redis()
        mock_aioredis = _make_mock_aioredis_module(mock_redis)

        mock_redis_parent = MagicMock()
        mock_redis_parent.asyncio = mock_aioredis

        orig_redis = sys.modules.get("redis")
        orig_redis_asyncio = sys.modules.get("redis.asyncio")
        try:
            sys.modules["redis"] = mock_redis_parent
            sys.modules["redis.asyncio"] = mock_aioredis

            await ingest_event(
                customer_id="cust-003",
                metric="ticket_resolved",
                value=1.0,
                event_type="outcome",
            )
        finally:
            if orig_redis is not None:
                sys.modules["redis"] = orig_redis
            else:
                sys.modules.pop("redis", None)
            if orig_redis_asyncio is not None:
                sys.modules["redis.asyncio"] = orig_redis_asyncio
            else:
                sys.modules.pop("redis.asyncio", None)

        mock_redis.publish.assert_awaited_once()
        publish_args = mock_redis.publish.call_args
        assert publish_args[0][0] == EVENTS_STREAM_CHANNEL

        published_payload = json.loads(publish_args[0][1])
        assert published_payload["customer_id"] == "cust-003"
        assert published_payload["event_type"] == "outcome"
