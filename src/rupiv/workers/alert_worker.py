"""Alert worker — periodic anomaly detection on billing metrics.

Run as a standalone process::

    python -m rupiv.workers.alert_worker
"""

from __future__ import annotations

import asyncio
import signal
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.analytics.anomaly import check_deviation
from rupiv.config import get_settings
from rupiv.db import _get_session_factory
from rupiv.models.alert import Alert, AlertRule
from rupiv.models.invoice import Invoice, InvoiceStatus
from rupiv.models.subscription import Subscription, SubscriptionStatus

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

CHECK_INTERVAL_SECONDS: int = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Metric gathering
# ---------------------------------------------------------------------------


async def _gather_mrr(session: AsyncSession) -> Decimal:
    """Calculate current MRR from active subscriptions with recent paid invoices."""
    result = await session.execute(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.status == InvoiceStatus.PAID,
            Invoice.created_at >= datetime.now(UTC) - timedelta(days=31),
        ),
    )
    return Decimal(str(result.scalar_one()))


async def _gather_mrr_history(
    session: AsyncSession,
    lookback: int,
) -> list[Decimal]:
    """Get MRR-like totals for the previous N 30-day periods."""
    values: list[Decimal] = []
    now = datetime.now(UTC)
    for i in range(1, lookback + 1):
        period_end = now - timedelta(days=30 * i)
        period_start = period_end - timedelta(days=30)
        result = await session.execute(
            select(func.coalesce(func.sum(Invoice.total), 0)).where(
                Invoice.status == InvoiceStatus.PAID,
                Invoice.created_at >= period_start,
                Invoice.created_at < period_end,
            ),
        )
        values.append(Decimal(str(result.scalar_one())))
    return values


async def _gather_open_invoice_count(session: AsyncSession) -> Decimal:
    """Count invoices that are open and past due."""
    result = await session.execute(
        select(func.count(Invoice.id)).where(
            Invoice.status == InvoiceStatus.OPEN,
            Invoice.due_date < datetime.now(UTC).date(),
        ),
    )
    return Decimal(str(result.scalar_one()))


# ---------------------------------------------------------------------------
# Core check logic
# ---------------------------------------------------------------------------


async def run_checks(session: AsyncSession) -> int:
    """Load active alert rules, evaluate metrics, create alerts.

    Returns the number of alerts created.
    """
    result = await session.execute(
        select(AlertRule).where(AlertRule.is_active == True),  # noqa: E712
    )
    rules = list(result.scalars().all())

    if not rules:
        return 0

    alerts_created = 0

    for rule in rules:
        alert_type = rule.alert_type
        threshold = Decimal(str(rule.threshold_pct))
        lookback = rule.lookback_periods

        try:
            if alert_type == "mrr_drop":
                current = await _gather_mrr(session)
                historical = await _gather_mrr_history(session, lookback)
                anomaly = check_deviation(
                    "mrr", current, historical, threshold, direction="drop",
                )

            elif alert_type == "missed_invoice":
                current = await _gather_open_invoice_count(session)
                # For missed invoices, compare against 0 baseline — any > threshold is an alert
                anomaly = check_deviation(
                    "missed_invoices",
                    current,
                    [Decimal("0")] * lookback,
                    threshold,
                    direction="spike",
                )

            else:
                log.debug("alert_worker.unsupported_type", alert_type=alert_type)
                continue

            if not anomaly.is_anomaly:
                continue

            # Dedup: skip if open alert with same type + metric exists
            existing = await session.execute(
                select(func.count(Alert.id)).where(
                    Alert.alert_type == alert_type,
                    Alert.metric_name == anomaly.metric_name,
                    Alert.status == "open",
                ),
            )
            if existing.scalar_one() > 0:
                log.debug(
                    "alert_worker.dedup_skip",
                    alert_type=alert_type,
                    metric=anomaly.metric_name,
                )
                continue

            severity = "critical" if anomaly.deviation_pct > threshold * 2 else "warning"

            alert = Alert(
                alert_type=alert_type,
                severity=severity,
                title=f"{alert_type.replace('_', ' ').title()}: "
                f"{anomaly.metric_name} deviated {anomaly.deviation_pct}%",
                description=(
                    f"Expected ~{anomaly.expected_value}, "
                    f"got {anomaly.current_value} "
                    f"({anomaly.direction} of {anomaly.deviation_pct}%)"
                ),
                metric_name=anomaly.metric_name,
                expected_value=anomaly.expected_value,
                actual_value=anomaly.current_value,
                status="open",
            )
            session.add(alert)
            alerts_created += 1

            log.warning(
                "alert_worker.alert_created",
                alert_type=alert_type,
                severity=severity,
                metric=anomaly.metric_name,
                deviation_pct=str(anomaly.deviation_pct),
            )

        except Exception:
            log.exception(
                "alert_worker.check_failed",
                alert_type=alert_type,
                rule_id=str(rule.id),
            )

    return alerts_created


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


class AlertWorker:
    """Periodic worker that runs anomaly detection checks."""

    def __init__(self) -> None:
        self._shutdown: bool = False

    def _handle_signal(self, sig: int, _frame: Any) -> None:
        sig_name = signal.Signals(sig).name
        log.info("alert_worker.signal_received", signal=sig_name)
        self._shutdown = True

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

    async def run(self) -> None:
        """Run the alert worker loop."""
        self._install_signal_handlers()
        session_factory = _get_session_factory()

        log.info(
            "alert_worker.started",
            interval_seconds=CHECK_INTERVAL_SECONDS,
        )

        try:
            while not self._shutdown:
                async with session_factory() as session:
                    try:
                        created = await run_checks(session)
                        await session.commit()
                        if created:
                            log.info("alert_worker.cycle_complete", alerts_created=created)
                    except Exception:
                        await session.rollback()
                        log.exception("alert_worker.cycle_failed")

                # Sleep in small increments so we can respond to shutdown signals
                for _ in range(CHECK_INTERVAL_SECONDS):
                    if self._shutdown:
                        break
                    await asyncio.sleep(1)

        finally:
            log.info("alert_worker.shutdown_complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``python -m rupiv.workers.alert_worker``."""
    log.info("alert_worker.starting")
    worker = AlertWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        log.info("alert_worker.interrupted")


if __name__ == "__main__":
    main()
