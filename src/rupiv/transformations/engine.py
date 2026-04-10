"""Stateless transformation engine.

Applies an ordered list of transformation steps to an event dict.
Mirrors the policy engine pattern — stateless, no I/O, pure functions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _resolve_field(event: dict[str, Any], field: str) -> Any:
    """Resolve a dot-path field (e.g. 'properties.status') from the event."""
    parts = field.split(".")
    current: Any = event
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _set_field(event: dict[str, Any], field: str, value: Any) -> None:
    """Set a dot-path field on the event dict, creating nested dicts as needed."""
    parts = field.split(".")
    current = event
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _evaluate_condition(
    actual: Any,
    operator: str,
    expected: Any,
) -> bool:
    """Evaluate a single condition (reuses operators from policy engine)."""
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "lt":
        return actual is not None and actual < expected
    if operator == "lte":
        return actual is not None and actual <= expected
    if operator == "gt":
        return actual is not None and actual > expected
    if operator == "gte":
        return actual is not None and actual >= expected
    if operator == "in":
        return actual in expected
    if operator == "not_in":
        return actual not in expected
    if operator == "contains":
        return isinstance(actual, str) and expected in actual
    return False


def apply_step(event: dict[str, Any], step: dict[str, Any]) -> dict[str, Any] | None:
    """Apply a single transformation step to an event.

    Returns the (possibly modified) event, or ``None`` if the event
    should be dropped (filtered out).
    """
    step_type = step.get("type", "")

    if step_type == "filter":
        field_val = _resolve_field(event, step["field"])
        if not _evaluate_condition(field_val, step["operator"], step["value"]):
            return None  # Drop event
        return event

    if step_type == "rename":
        source_val = _resolve_field(event, step["source"])
        if source_val is not None:
            _set_field(event, step["target"], source_val)
            # Remove old field (only top-level for simplicity)
            parts = step["source"].split(".")
            if len(parts) == 1 and parts[0] in event:
                del event[parts[0]]
            elif len(parts) == 2 and parts[0] in event:  # noqa: PLR2004
                parent = event[parts[0]]
                if isinstance(parent, dict) and parts[1] in parent:
                    del parent[parts[1]]
        return event

    if step_type == "map":
        source_val = _resolve_field(event, step["source"])
        if source_val is not None:
            expression = step.get("expression", "value")
            try:
                result = eval(expression, {"__builtins__": {}}, {"value": source_val})  # noqa: S307
            except Exception:
                result = source_val
            _set_field(event, step["target"], result)
        return event

    if step_type == "set":
        _set_field(event, step["field"], step["value"])
        return event

    # Unknown step type — pass through unchanged
    log.warning("unknown_transformation_step", step_type=step_type)
    return event


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transform_event(
    event: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Apply an ordered list of steps to an event.

    Returns the transformed event, or ``None`` if a filter step dropped it.
    """
    result = deepcopy(event)
    for step in steps:
        transformed = apply_step(result, step)
        if transformed is None:
            return None
        result = transformed
    return result


def apply_rules(
    event: dict[str, Any],
    rules: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Apply matching transformation rules to an event.

    Rules are expected to be sorted by priority (lower = higher priority).
    Only the first matching rule (by ``source_metric``) is applied.

    Each rule dict must have: ``source_metric``, ``target_metric``, ``steps``.
    """
    metric = event.get("metric", "")

    for rule in rules:
        if rule.get("source_metric") == metric and rule.get("is_active", True):
            result = transform_event(event, rule.get("steps", []))
            if result is not None:
                result["metric"] = rule.get("target_metric", metric)
            return result

    # No matching rule — return event unchanged
    return event
