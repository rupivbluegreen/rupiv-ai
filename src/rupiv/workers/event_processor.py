"""Event processor worker — pops events from Redis queue and writes to ClickHouse.

Run as a standalone process::

    python -m rupiv.workers.event_processor
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
import time
from typing import Any

import structlog

from rupiv.billing.metering import EVENTS_QUEUE_KEY, write_to_clickhouse
from rupiv.config import get_settings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BATCH_SIZE: int = 100
BATCH_TIMEOUT_SECONDS: float = 1.0
BLPOP_TIMEOUT_SECONDS: int = 1


class EventProcessorWorker:
    """Async worker that drains the Redis event queue into ClickHouse.

    Batches up to ``BATCH_SIZE`` events or flushes after
    ``BATCH_TIMEOUT_SECONDS``, whichever comes first.
    """

    def __init__(self) -> None:
        self._shutdown: bool = False
        self._batch: list[dict[str, Any]] = []
        self._batch_start: float = time.monotonic()

    # -- Signal handling -------------------------------------------------------

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        sig_name = signal.Signals(sig).name
        log.info("worker.signal_received", signal=sig_name)
        self._shutdown = True

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    # -- Batch management ------------------------------------------------------

    def _should_flush(self) -> bool:
        if not self._batch:
            return False
        if len(self._batch) >= BATCH_SIZE:
            return True
        elapsed = time.monotonic() - self._batch_start
        if elapsed >= BATCH_TIMEOUT_SECONDS:
            return True
        return False

    async def _flush_batch(self) -> None:
        if not self._batch:
            return

        batch = self._batch
        self._batch = []
        self._batch_start = time.monotonic()

        try:
            written = await write_to_clickhouse(batch)
            log.info("worker.batch_flushed", count=written)
        except Exception:
            log.error(
                "worker.batch_flush_failed",
                count=len(batch),
                exc_info=True,
            )
            # Events are still in PostgreSQL — they are not lost.

    # -- Main loop -------------------------------------------------------------

    async def run(self) -> None:
        """Start the infinite event processing loop."""
        import redis.asyncio as aioredis

        self._install_signal_handlers()

        settings = get_settings()
        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.REDIS_URL,
            decode_responses=True,
        )

        log.info(
            "worker.started",
            queue=EVENTS_QUEUE_KEY,
            batch_size=BATCH_SIZE,
            batch_timeout=BATCH_TIMEOUT_SECONDS,
        )

        try:
            while not self._shutdown:
                try:
                    # blpop returns (key, value) or None on timeout
                    result = await redis_client.blpop(
                        EVENTS_QUEUE_KEY,
                        timeout=BLPOP_TIMEOUT_SECONDS,
                    )
                except Exception:
                    log.error("worker.redis_blpop_failed", exc_info=True)
                    await asyncio.sleep(1)
                    continue

                if result is not None:
                    _key, raw_payload = result
                    try:
                        event_data: dict[str, Any] = json.loads(raw_payload)
                        self._batch.append(event_data)
                        log.debug(
                            "worker.event_dequeued",
                            event_id=event_data.get("event_id"),
                        )
                    except (json.JSONDecodeError, TypeError):
                        log.error(
                            "worker.event_deserialize_failed",
                            raw=str(raw_payload)[:200],
                        )

                if self._should_flush():
                    await self._flush_batch()

            # Drain remaining events on shutdown
            await self._flush_batch()
            log.info("worker.shutdown_complete")
        finally:
            await redis_client.aclose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for ``python -m rupiv.workers.event_processor``."""
    log.info("worker.event_processor.starting")
    worker = EventProcessorWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        log.info("worker.event_processor.interrupted")


if __name__ == "__main__":
    main()
