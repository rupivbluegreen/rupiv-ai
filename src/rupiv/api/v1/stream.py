"""Real-time WebSocket event stream — ws://localhost:8000/v1/stream/events."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from rupiv.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

STREAM_CHANNEL = "rupiv:events:stream"

router = APIRouter(tags=["stream"])


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


def _authenticate_api_key(api_key: str | None) -> bool:
    """Stub authentication for MVP.

    In production this would validate against the database or Clerk.
    For now, accept any non-empty key or allow ``None`` (open access).
    """
    # TODO: Implement real API key validation against the database.
    if api_key is not None and len(api_key) == 0:
        return False
    return True


def _matches_filters(
    event: dict[str, Any],
    event_type: str | None,
    metric: str | None,
) -> bool:
    """Check whether an event matches the optional query-param filters."""
    if event_type is not None and event.get("event_type") != event_type:
        return False
    if metric is not None and event.get("metric") != metric:
        return False
    return True


@router.websocket("/stream/events")
async def stream_events(
    websocket: WebSocket,
    api_key: str | None = Query(default=None),
    type: str | None = Query(default=None, alias="type"),
    metric: str | None = Query(default=None),
) -> None:
    """Stream real-time events over a WebSocket connection.

    Query parameters:
        api_key: Optional API key for authentication (stub for MVP).
        type: Optional event type filter (e.g. ``"usage"``, ``"outcome"``).
        metric: Optional metric filter (e.g. ``"ticket_resolved"``).
    """
    # --- Authentication (stub) ---
    if not _authenticate_api_key(api_key):
        await websocket.close(code=4001, reason="Invalid API key")
        return

    await manager.connect(websocket)
    log = logger.bind(
        client=str(websocket.client),
        filter_type=type,
        filter_metric=metric,
    )
    log.info("websocket.connected")

    # --- Subscribe to Redis pub/sub ---
    pubsub = None
    listen_task: asyncio.Task[None] | None = None

    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.REDIS_URL,
            decode_responses=True,
        )
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(STREAM_CHANNEL)

        async def _listen_redis() -> None:
            """Read messages from Redis pub/sub and forward to the WebSocket."""
            assert pubsub is not None  # noqa: S101
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data: str = message["data"]
                try:
                    event = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue

                if _matches_filters(event, event_type=type, metric=metric):
                    try:
                        await websocket.send_text(data)
                    except Exception:
                        break

        listen_task = asyncio.create_task(_listen_redis())

        # Keep the connection alive — wait for client messages or disconnect.
        while True:
            # Receiving data keeps the connection open; we discard payloads.
            await websocket.receive_text()

    except WebSocketDisconnect:
        log.info("websocket.disconnected")
    except Exception:
        log.warning("websocket.error", exc_info=True)
    finally:
        if listen_task is not None:
            listen_task.cancel()
            try:
                await listen_task
            except (asyncio.CancelledError, Exception):
                pass
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(STREAM_CHANNEL)
                await pubsub.aclose()
                await redis_client.aclose()  # type: ignore[possibly-undefined]
            except Exception:
                pass
        manager.disconnect(websocket)
        log.info("websocket.cleanup_complete")
