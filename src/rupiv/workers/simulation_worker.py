"""Background simulation worker — picks up simulation jobs from Redis.

Run as a standalone process::

    python -m rupiv.workers.simulation_worker
"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import Any
from uuid import UUID

import structlog

from rupiv.config import get_settings
from rupiv.pricing_studio.simulator import SimulationScenario, run_simulation

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SIMULATIONS_QUEUE_KEY: str = "rupiv:simulations:queue"
SIMULATIONS_RESULTS_PREFIX: str = "rupiv:simulations:result:"
RESULT_TTL_SECONDS: int = 3600  # 1 hour
BLPOP_TIMEOUT_SECONDS: int = 2


class SimulationWorker:
    """Async worker that processes pricing simulation jobs from Redis.

    Jobs are JSON objects with ``job_id``, ``plan_id``, and ``scenario``.
    Results are stored back into Redis under a per-job key.
    """

    def __init__(self) -> None:
        self._shutdown: bool = False

    # -- Signal handling -------------------------------------------------------

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        sig_name = signal.Signals(sig).name
        log.info("simulation_worker.signal_received", signal=sig_name)
        self._shutdown = True

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    # -- Job processing --------------------------------------------------------

    async def _process_job(
        self,
        redis_client: Any,
        job_data: dict[str, Any],
    ) -> None:
        """Run a single simulation job and store the result."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        job_id = job_data.get("job_id", "unknown")
        plan_id_str = job_data.get("plan_id")
        scenario_raw = job_data.get("scenario")

        if not plan_id_str or not scenario_raw:
            log.error(
                "simulation_worker.invalid_job",
                job_id=job_id,
                has_plan_id=bool(plan_id_str),
                has_scenario=bool(scenario_raw),
            )
            return

        log.info("simulation_worker.processing", job_id=job_id, plan_id=plan_id_str)

        try:
            scenario = SimulationScenario(**scenario_raw)
            plan_id = UUID(plan_id_str)

            settings = get_settings()
            engine = create_async_engine(settings.DATABASE_URL)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)

            async with session_factory() as session:
                result = await run_simulation(session, scenario, plan_id)

            # Store result in Redis
            result_key = f"{SIMULATIONS_RESULTS_PREFIX}{job_id}"
            result_data = {
                "job_id": job_id,
                "status": "completed",
                "current_revenue": str(result.current_revenue),
                "simulated_revenue": str(result.simulated_revenue),
                "delta": str(result.delta),
                "delta_pct": str(result.delta_pct),
                "billable_outcomes_current": result.billable_outcomes_current,
                "billable_outcomes_simulated": result.billable_outcomes_simulated,
                "affected_customers": result.affected_customers,
                "line_item_breakdown": result.line_item_breakdown,
            }
            await redis_client.set(
                result_key,
                json.dumps(result_data),
                ex=RESULT_TTL_SECONDS,
            )

            log.info(
                "simulation_worker.completed",
                job_id=job_id,
                delta=str(result.delta),
            )

            await engine.dispose()

        except Exception:
            log.error(
                "simulation_worker.job_failed",
                job_id=job_id,
                exc_info=True,
            )
            # Store error result
            result_key = f"{SIMULATIONS_RESULTS_PREFIX}{job_id}"
            await redis_client.set(
                result_key,
                json.dumps({"job_id": job_id, "status": "failed"}),
                ex=RESULT_TTL_SECONDS,
            )

    # -- Main loop -------------------------------------------------------------

    async def run(self) -> None:
        """Start the simulation processing loop."""
        import redis.asyncio as aioredis

        self._install_signal_handlers()

        settings = get_settings()
        redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            settings.REDIS_URL,
            decode_responses=True,
        )

        log.info(
            "simulation_worker.started",
            queue=SIMULATIONS_QUEUE_KEY,
        )

        try:
            while not self._shutdown:
                try:
                    result = await redis_client.blpop(
                        SIMULATIONS_QUEUE_KEY,
                        timeout=BLPOP_TIMEOUT_SECONDS,
                    )
                except Exception:
                    log.error("simulation_worker.redis_blpop_failed", exc_info=True)
                    await asyncio.sleep(1)
                    continue

                if result is not None:
                    _key, raw_payload = result
                    try:
                        job_data: dict[str, Any] = json.loads(raw_payload)
                        await self._process_job(redis_client, job_data)
                    except (json.JSONDecodeError, TypeError):
                        log.error(
                            "simulation_worker.deserialize_failed",
                            raw=str(raw_payload)[:200],
                        )

            log.info("simulation_worker.shutdown_complete")
        finally:
            await redis_client.aclose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``python -m rupiv.workers.simulation_worker``."""
    log.info("simulation_worker.starting")
    worker = SimulationWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        log.info("simulation_worker.interrupted")


if __name__ == "__main__":
    main()
