"""Async VIES VAT ID validation worker.

Picks up VAT validation jobs from the Redis queue ``rupiv:vat:validate``,
calls the VIES API via :func:`rupiv.tax.vat_id_validation.validate_vat_id`,
and updates the customer record with the validation result.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Redis queue name
VAT_VALIDATE_QUEUE = "rupiv:vat:validate"

# Retry configuration
_MAX_RETRIES: int = 3
_RETRY_DELAY_SECONDS: float = 5.0


async def _process_job(job_data: dict[str, Any]) -> None:
    """Process a single VAT validation job.

    Args:
        job_data: Dict with keys ``customer_id``, ``country_code``,
            ``vat_number``.
    """
    from rupiv.tax.vat_id_validation import validate_vat_id

    customer_id: str = job_data["customer_id"]
    country_code: str = job_data["country_code"]
    vat_number: str = job_data["vat_number"]

    log.info(
        "vat_worker.processing",
        customer_id=customer_id,
        country_code=country_code,
        vat_number=vat_number,
    )

    result = await validate_vat_id(country_code, vat_number)

    if result.valid is None:
        # VIES was unreachable -- the result is unknown
        log.warning(
            "vat_worker.vies_unavailable",
            customer_id=customer_id,
            country_code=country_code,
        )
        return

    # Persist validation result to the customer record
    from datetime import UTC, datetime

    from sqlalchemy import update

    from rupiv.db import _get_session_factory
    from rupiv.models.customer import Customer

    session_factory = _get_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Customer)
            .where(Customer.id == customer_id)
            .values(
                vat_valid=result.valid,
                vat_validated_at=datetime.now(UTC),
            ),
        )
        await session.commit()

    log.info(
        "vat_worker.validated",
        customer_id=customer_id,
        country_code=country_code,
        vat_number=vat_number,
        valid=result.valid,
        name=result.name,
    )


async def _process_with_retries(job_data: dict[str, Any]) -> None:
    """Process a job with retry logic for VIES downtime."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            await _process_job(job_data)
            return
        except Exception:
            log.exception(
                "vat_worker.attempt_failed",
                attempt=attempt,
                max_retries=_MAX_RETRIES,
                customer_id=job_data.get("customer_id"),
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_DELAY_SECONDS * attempt)

    log.error(
        "vat_worker.exhausted_retries",
        customer_id=job_data.get("customer_id"),
        max_retries=_MAX_RETRIES,
    )


async def run_worker(redis_url: str = "redis://localhost:6379/0") -> None:
    """Run the VAT validation worker loop.

    Blocks forever, polling Redis for jobs on the
    ``rupiv:vat:validate`` queue.

    Args:
        redis_url: Redis connection URL.
    """
    import redis.asyncio as aioredis

    pool = aioredis.from_url(redis_url, decode_responses=True)

    log.info("vat_worker.started", queue=VAT_VALIDATE_QUEUE)

    try:
        while True:
            # BLPOP blocks until a message is available (timeout 5s)
            result = await pool.blpop(VAT_VALIDATE_QUEUE, timeout=5)
            if result is None:
                continue

            _queue_name, raw_payload = result
            try:
                job_data: dict[str, Any] = json.loads(raw_payload)
            except (json.JSONDecodeError, TypeError) as exc:
                log.error(
                    "vat_worker.invalid_payload",
                    payload=raw_payload,
                    error=str(exc),
                )
                continue

            await _process_with_retries(job_data)
    finally:
        await pool.aclose()
        log.info("vat_worker.stopped")
