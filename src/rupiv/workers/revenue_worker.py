"""Revenue schedule generation worker — listens for invoice creation events.

When an invoice is created, triggers IFRS 15 revenue schedule generation
for the associated subscription via the revenue recognition agent.

Run as a standalone process::

    python -m rupiv.workers.revenue_worker
"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import Any

import structlog

from rupiv.agents.revenue_agent import generate_revenue_schedule
from rupiv.config import get_settings

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

REVENUE_QUEUE = "rupiv:revenue:generate"
POLL_TIMEOUT_SECONDS: int = 5


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class RevenueWorker:
    """Async worker that listens on a Redis queue for revenue schedule requests.

    Messages are expected as JSON with at least a ``subscription_id`` field.
    Typical trigger: invoice creation pushes a message to the queue.
    """

    def __init__(self) -> None:
        self._shutdown: bool = False

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        sig_name = signal.Signals(sig).name
        log.info("revenue_worker.signal_received", signal=sig_name)
        self._shutdown = True

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    async def _process_message(self, raw_message: str) -> None:
        """Parse and process a single queue message."""
        try:
            payload = json.loads(raw_message)
        except (json.JSONDecodeError, TypeError) as exc:
            log.error(
                "revenue_worker.invalid_message",
                raw=raw_message,
                error=str(exc),
            )
            return

        subscription_id: str | None = payload.get("subscription_id")
        if not subscription_id:
            log.error(
                "revenue_worker.missing_subscription_id",
                payload=payload,
            )
            return

        log.info(
            "revenue_worker.processing",
            subscription_id=subscription_id,
        )

        try:
            result = await generate_revenue_schedule(subscription_id)

            if result.get("error"):
                log.error(
                    "revenue_worker.generation_failed",
                    subscription_id=subscription_id,
                    error=result["error"],
                )
            else:
                log.info(
                    "revenue_worker.generation_complete",
                    subscription_id=subscription_id,
                    schedule_id=result.get("schedule_id"),
                )
        except Exception:
            log.error(
                "revenue_worker.unexpected_error",
                subscription_id=subscription_id,
                exc_info=True,
            )

    async def run(self) -> None:
        """Run the revenue worker loop.

        Listens on Redis list ``rupiv:revenue:generate`` using BLPOP for
        efficient blocking consumption.
        """
        import redis.asyncio as aioredis

        self._install_signal_handlers()
        settings = get_settings()

        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.REDIS_URL,
            decode_responses=True,
        )

        log.info(
            "revenue_worker.started",
            queue=REVENUE_QUEUE,
            poll_timeout=POLL_TIMEOUT_SECONDS,
        )

        try:
            while not self._shutdown:
                try:
                    # BLPOP blocks until a message arrives or timeout elapses
                    result = await redis_client.blpop(
                        REVENUE_QUEUE,
                        timeout=POLL_TIMEOUT_SECONDS,
                    )
                except asyncio.CancelledError:
                    break
                except Exception:
                    log.error("revenue_worker.redis_error", exc_info=True)
                    await asyncio.sleep(1)
                    continue

                if result is None:
                    # Timeout — no message, loop back to check shutdown flag
                    continue

                # BLPOP returns (key, value)
                _key, raw_message = result
                await self._process_message(raw_message)

        finally:
            await redis_client.aclose()
            log.info("revenue_worker.shutdown_complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``python -m rupiv.workers.revenue_worker``."""
    log.info("revenue_worker.starting")
    worker = RevenueWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        log.info("revenue_worker.interrupted")


if __name__ == "__main__":
    main()
