"""Spending limits and threshold enforcement.

Pure-function threshold checks for spending caps, discount limits,
and outcome caps.  The ``check_threshold`` function compares a current
value against a ``ThresholdRule`` and returns a ``ThresholdResult``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_FOUR_PLACES = Decimal("0.0001")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThresholdRule:
    """A spending/metric threshold definition."""

    entity_id: uuid.UUID
    metric: str
    limit: Decimal
    period: Literal["monthly", "quarterly", "yearly"]
    currency: str = "EUR"


@dataclass(frozen=True)
class ThresholdResult:
    """Result of checking a value against a threshold."""

    within_limit: bool
    current_value: Decimal
    limit: Decimal
    remaining: Decimal
    pct_used: Decimal


# ---------------------------------------------------------------------------
# Threshold check
# ---------------------------------------------------------------------------


def check_threshold(
    session: Any,
    entity_id: uuid.UUID,
    metric: str,
    current_value: Decimal,
    threshold: ThresholdRule,
) -> ThresholdResult:
    """Check whether *current_value* is within the threshold *limit*.

    Args:
        session: Database session (reserved for future use — the current
            implementation is a pure comparison).
        entity_id: The entity being checked.
        metric: The metric name being checked.
        current_value: The current accumulated value for the metric.
        threshold: The threshold rule to check against.

    Returns:
        A ``ThresholdResult`` with limit status and remaining capacity.
    """
    limit = threshold.limit
    remaining = max(limit - current_value, Decimal("0"))
    within_limit = current_value < limit

    pct_used = Decimal("0")
    if limit > Decimal("0"):
        pct_used = (current_value / limit * Decimal("100")).quantize(
            _FOUR_PLACES, rounding=ROUND_HALF_UP,
        )

    result = ThresholdResult(
        within_limit=within_limit,
        current_value=current_value,
        limit=limit,
        remaining=remaining,
        pct_used=pct_used,
    )

    log.debug(
        "policy.threshold.checked",
        entity_id=str(entity_id),
        metric=metric,
        current_value=str(current_value),
        limit=str(limit),
        within_limit=within_limit,
        pct_used=str(pct_used),
    )

    return result
