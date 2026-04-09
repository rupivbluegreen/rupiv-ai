"""High-throughput event batcher for the Rupiv API."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

import httpx

from .types import RupivError

logger = logging.getLogger("rupiv.events")


class EventBatcher:
    """Buffers events in memory and flushes them in batches.

    Events are flushed automatically when the buffer reaches *max_batch_size*
    or every *max_wait_seconds*, whichever comes first.

    Usage::

        batcher = EventBatcher(api_key="rp_live_xxx")
        batcher.add("api_call", "cust_123", "usage", {"tokens": 150})
        batcher.close()  # flushes remaining events and stops the timer
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.rupiv.ai",
        max_batch_size: int = 100,
        max_wait_seconds: float = 5.0,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_batch_size = max_batch_size
        self._max_wait_seconds = max_wait_seconds

        self._http = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "rupiv-python/0.1.0",
            },
            timeout=timeout,
        )

        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._closed = False

        # Background flush timer
        self._timer: threading.Timer | None = None
        self._start_timer()

    # -- Public API ------------------------------------------------------------

    def add(
        self,
        metric: str,
        customer_id: str,
        event_type: str = "usage",
        properties: dict | None = None,
    ) -> None:
        """Add an event to the buffer. Flushes automatically when full."""
        if self._closed:
            raise RuntimeError("EventBatcher is closed")

        event = {
            "metric": metric,
            "customer_id": customer_id,
            "type": event_type,
            "properties": properties or {},
            "idempotency_key": str(uuid.uuid4()),
        }

        should_flush = False
        with self._lock:
            self._buffer.append(event)
            if len(self._buffer) >= self._max_batch_size:
                should_flush = True

        if should_flush:
            self.flush()

    def flush(self) -> None:
        """Send all buffered events to the API immediately."""
        with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()

        self._send_batch(batch)

    def close(self) -> None:
        """Flush remaining events and stop the background timer."""
        self._closed = True
        self._stop_timer()
        self.flush()
        self._http.close()

    # -- Internals -------------------------------------------------------------

    def _send_batch(self, batch: list[dict[str, Any]]) -> None:
        """POST a batch of events to /v1/events/batch."""
        try:
            response = self._http.post("/v1/events/batch", json={"events": batch})
            if not response.is_success:
                request_id = response.headers.get("x-request-id")
                try:
                    body = response.json()
                    message = body.get("error", {}).get("message", response.text)
                except Exception:
                    message = response.text
                raise RupivError(
                    status_code=response.status_code,
                    message=message,
                    request_id=request_id,
                )
        except RupivError:
            raise
        except Exception:
            logger.exception("Failed to flush %d events", len(batch))

    def _start_timer(self) -> None:
        if self._closed:
            return
        self._timer = threading.Timer(self._max_wait_seconds, self._on_timer)
        self._timer.daemon = True
        self._timer.start()

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timer(self) -> None:
        """Called by the background timer to periodically flush."""
        try:
            self.flush()
        finally:
            self._start_timer()
