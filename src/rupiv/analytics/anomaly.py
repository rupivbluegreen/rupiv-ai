"""Anomaly detection for revenue leakage alerting.

Simple threshold-based detection: compares current values against rolling
averages from previous periods.  No ML — ships fast, covers 80% of cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AnomalyResult:
    """Result of an anomaly check."""

    is_anomaly: bool
    metric_name: str
    current_value: Decimal
    expected_value: Decimal
    deviation_pct: Decimal
    threshold_pct: Decimal
    direction: str  # "drop" or "spike"


def check_deviation(
    metric_name: str,
    current_value: Decimal,
    historical_values: list[Decimal],
    threshold_pct: Decimal,
    direction: str = "drop",
) -> AnomalyResult:
    """Check if *current_value* deviates from the historical average by > *threshold_pct*.

    Args:
        metric_name: Human-readable name for logging.
        current_value: The current period's value.
        historical_values: Values from previous periods (most recent first).
        threshold_pct: Percentage deviation threshold (e.g. Decimal("20") = 20%).
        direction: ``"drop"`` triggers when current < expected,
                   ``"spike"`` triggers when current > expected,
                   ``"both"`` triggers on either.

    Returns:
        An ``AnomalyResult`` with ``is_anomaly=True`` if the threshold is breached.
    """
    if not historical_values:
        return AnomalyResult(
            is_anomaly=False,
            metric_name=metric_name,
            current_value=current_value,
            expected_value=Decimal("0"),
            deviation_pct=Decimal("0"),
            threshold_pct=threshold_pct,
            direction=direction,
        )

    avg = sum(historical_values) / len(historical_values)

    if avg == 0:
        deviation_pct = Decimal("0") if current_value == 0 else Decimal("100")
    else:
        deviation_pct = abs(((current_value - avg) / avg) * 100)

    deviation_pct = deviation_pct.quantize(Decimal("0.01"))

    is_anomaly = False
    if deviation_pct > threshold_pct:
        if direction == "drop" and current_value < avg:
            is_anomaly = True
        elif direction == "spike" and current_value > avg:
            is_anomaly = True
        elif direction == "both":
            is_anomaly = True

    result = AnomalyResult(
        is_anomaly=is_anomaly,
        metric_name=metric_name,
        current_value=current_value,
        expected_value=avg.quantize(Decimal("0.0001")),
        deviation_pct=deviation_pct,
        threshold_pct=threshold_pct,
        direction=direction,
    )

    if is_anomaly:
        log.warning(
            "anomaly_detected",
            metric=metric_name,
            current=str(current_value),
            expected=str(avg),
            deviation_pct=str(deviation_pct),
            threshold_pct=str(threshold_pct),
            direction=direction,
        )

    return result
