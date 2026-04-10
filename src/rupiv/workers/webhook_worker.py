"""Outbound webhook delivery worker.

Picks up events from the Redis queue, finds matching webhook endpoints,
delivers via HTTP POST with HMAC-SHA256 signature, and logs results.

Run as a standalone process::

    python -m rupiv.workers.webhook_worker
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import signal
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.config import get_settings
from rupiv.db import _get_session_factory
from rupiv.models.webhook_endpoint import WebhookDelivery, WebhookEndpoint
from rupiv.webhooks.dispatcher import WEBHOOK_QUEUE_KEY

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

DELIVERY_TIMEOUT_SECONDS: float = 5.0
MAX_ATTEMPTS: int = 3
BACKOFF_SECONDS: list[float] = [0, 2.0, 4.0, 8.0]
CIRCUIT_BREAKER_THRESHOLD: int = 10


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature of the payload."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


async def _deliver_to_endpoint(
    http_client: httpx.AsyncClient,
    endpoint: WebhookEndpoint,
    event_type: str,
    payload: dict[str, Any],
    timestamp: str,
    session: AsyncSession,
) -> bool:
    """Deliver a webhook to a single endpoint with retries.

    Returns ``True`` if delivery succeeded.
    """
    body = {
        "event_type": event_type,
        "timestamp": timestamp,
        "data": payload,
    }
    body_bytes = json.dumps(body).encode()
    signature = _sign_payload(body_bytes, endpoint.secret)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            await asyncio.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])

        response_status: int | None = None
        response_body: str | None = None

        try:
            resp = await http_client.post(
                endpoint.url,
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Rupiv-Signature": signature,
                    "X-Rupiv-Event": event_type,
                },
            )
            response_status = resp.status_code
            response_body = resp.text[:1024]  # truncate

            if 200 <= resp.status_code < 300:  # noqa: PLR2004
                # Success — log delivery and reset failure count
                delivery = WebhookDelivery(
                    endpoint_id=endpoint.id,
                    event_type=event_type,
                    payload=body,
                    response_status=response_status,
                    response_body=response_body,
                    attempt=attempt,
                    delivered_at=datetime.now(UTC),
                )
                session.add(delivery)

                if endpoint.failure_count > 0:
                    await session.execute(
                        update(WebhookEndpoint)
                        .where(WebhookEndpoint.id == endpoint.id)
                        .values(failure_count=0),
                    )

                log.info(
                    "webhook_worker.delivered",
                    endpoint_id=str(endpoint.id),
                    event_type=event_type,
                    status=response_status,
                    attempt=attempt,
                )
                return True

        except httpx.HTTPError as exc:
            response_body = str(exc)[:1024]
            log.warning(
                "webhook_worker.delivery_error",
                endpoint_id=str(endpoint.id),
                attempt=attempt,
                error=str(exc),
            )

    # All attempts exhausted — log failure
    delivery = WebhookDelivery(
        endpoint_id=endpoint.id,
        event_type=event_type,
        payload=body,
        response_status=response_status,
        response_body=response_body,
        attempt=MAX_ATTEMPTS,
    )
    session.add(delivery)

    # Increment failure count
    new_count = endpoint.failure_count + 1
    values: dict[str, Any] = {"failure_count": new_count}
    if new_count >= CIRCUIT_BREAKER_THRESHOLD:
        values["is_active"] = False
        log.error(
            "webhook_worker.circuit_breaker_tripped",
            endpoint_id=str(endpoint.id),
            failure_count=new_count,
        )

    await session.execute(
        update(WebhookEndpoint)
        .where(WebhookEndpoint.id == endpoint.id)
        .values(**values),
    )

    log.error(
        "webhook_worker.delivery_failed",
        endpoint_id=str(endpoint.id),
        event_type=event_type,
        failure_count=new_count,
    )
    return False


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


class WebhookWorker:
    """Async worker that delivers outbound webhooks."""

    def __init__(self) -> None:
        self._shutdown: bool = False

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        sig_name = signal.Signals(sig).name
        log.info("webhook_worker.signal_received", signal=sig_name)
        self._shutdown = True

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    async def run(self) -> None:
        """Run the webhook delivery loop."""
        import redis.asyncio as aioredis

        self._install_signal_handlers()
        settings = get_settings()

        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.REDIS_URL,
            decode_responses=True,
        )
        session_factory = _get_session_factory()

        log.info("webhook_worker.started", queue=WEBHOOK_QUEUE_KEY)

        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as http_client:
                while not self._shutdown:
                    try:
                        result = await redis_client.blpop(WEBHOOK_QUEUE_KEY, timeout=1)
                    except Exception:
                        log.error("webhook_worker.redis_blpop_failed", exc_info=True)
                        await asyncio.sleep(1)
                        continue

                    if result is None:
                        continue

                    _key, raw_message = result
                    try:
                        message = json.loads(raw_message)
                    except (json.JSONDecodeError, TypeError):
                        log.error("webhook_worker.invalid_message", raw=raw_message)
                        continue

                    event_type = message.get("event_type", "")
                    payload = message.get("payload", {})
                    timestamp = message.get("timestamp", "")

                    async with session_factory() as session:
                        try:
                            # Find active endpoints subscribed to this event type
                            stmt = select(WebhookEndpoint).where(
                                WebhookEndpoint.is_active == True,  # noqa: E712
                            )
                            ep_result = await session.execute(stmt)
                            endpoints = list(ep_result.scalars().all())

                            for ep in endpoints:
                                # Check if this endpoint subscribes to this event type
                                if event_type not in (ep.events or []):
                                    continue

                                # Skip if circuit breaker tripped
                                if ep.failure_count >= CIRCUIT_BREAKER_THRESHOLD:
                                    continue

                                await _deliver_to_endpoint(
                                    http_client, ep, event_type, payload, timestamp, session,
                                )

                            await session.commit()

                        except Exception:
                            await session.rollback()
                            log.error(
                                "webhook_worker.processing_failed",
                                event_type=event_type,
                                exc_info=True,
                            )

        finally:
            await redis_client.aclose()
            log.info("webhook_worker.shutdown_complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``python -m rupiv.workers.webhook_worker``."""
    log.info("webhook_worker.starting")
    worker = WebhookWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        log.info("webhook_worker.interrupted")


if __name__ == "__main__":
    main()
