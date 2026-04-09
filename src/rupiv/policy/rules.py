"""Rule parsing, data types, and condition evaluation.

Pure functions — no I/O, no side effects.  Supports YAML and JSON rule
definitions and dot-path field access into nested context dicts.

The Pydantic models (``Condition``, ``PolicyRuleData``) and the
``PolicyResult`` dataclass live here to avoid circular imports with the
engine module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

try:
    import yaml

    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

ActionType = Literal["auto_approve", "require_approval", "reject", "allow"]


class Condition(BaseModel):
    """A single condition to evaluate against a context dict.

    ``field`` uses dot-path notation, e.g. ``"invoice.total"``.
    """

    field: str
    operator: str = Field(
        ...,
        pattern=r"^(eq|ne|lt|lte|gt|gte|in|not_in|contains)$",
    )
    value: Any


class PolicyRuleData(BaseModel):
    """A declarative policy rule definition (parsed from YAML/JSON)."""

    name: str
    trigger: str
    conditions: list[Condition]
    action: ActionType
    approver: str | None = None
    escalation_after_hours: int | None = None
    priority: int = Field(default=100, description="Lower number = higher priority")


@dataclass(frozen=True)
class PolicyResult:
    """Result of evaluating a single policy rule against a context."""

    rule_name: str
    action: ActionType
    approver: str | None = None
    reason: str | None = None
    matched: bool = False


# ---------------------------------------------------------------------------
# Dot-path field resolution
# ---------------------------------------------------------------------------


def _resolve_field(context: dict[str, Any], field: str) -> Any:
    """Resolve a dot-path field (e.g. ``"invoice.total"``) against *context*.

    Traverses nested dicts; raises ``KeyError`` if the path is invalid.
    """
    parts = field.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict):
            current = current[part]
        else:
            current = getattr(current, part)
    return current


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


def _to_decimal_safe(value: Any) -> Decimal | None:
    """Try to coerce *value* to ``Decimal``.  Return ``None`` on failure."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _coerce_for_comparison(field_val: Any, rule_val: Any) -> tuple[Any, Any]:
    """Coerce values for comparison, preferring Decimal for numeric types."""
    # If either side is already a Decimal, coerce the other
    if isinstance(field_val, Decimal) or isinstance(rule_val, Decimal):
        fd = _to_decimal_safe(field_val)
        rd = _to_decimal_safe(rule_val)
        if fd is not None and rd is not None:
            return fd, rd

    # If both are numeric (int/float), coerce to Decimal for precision
    if isinstance(field_val, (int, float)) and isinstance(rule_val, (int, float)):
        fd = _to_decimal_safe(field_val)
        rd = _to_decimal_safe(rule_val)
        if fd is not None and rd is not None:
            return fd, rd

    return field_val, rule_val


# ---------------------------------------------------------------------------
# Single condition evaluation
# ---------------------------------------------------------------------------


def evaluate_condition(condition: Condition, context: dict[str, Any]) -> bool:
    """Evaluate a single ``Condition`` against *context*.

    Supports dot-path field access and all comparison operators:
    ``eq``, ``ne``, ``lt``, ``lte``, ``gt``, ``gte``, ``in``,
    ``not_in``, ``contains``.

    Returns ``False`` (rather than raising) if the field is missing.
    """
    try:
        field_val = _resolve_field(context, condition.field)
    except (KeyError, AttributeError, TypeError):
        log.debug(
            "policy.condition.field_missing",
            field=condition.field,
        )
        return False

    op = condition.operator
    rule_val = condition.value

    # Coerce for numeric comparisons
    if op in ("lt", "lte", "gt", "gte", "eq", "ne"):
        field_val, rule_val = _coerce_for_comparison(field_val, rule_val)

    if op == "eq":
        return field_val == rule_val  # type: ignore[no-any-return]
    if op == "ne":
        return field_val != rule_val  # type: ignore[no-any-return]
    if op == "lt":
        return field_val < rule_val  # type: ignore[no-any-return]
    if op == "lte":
        return field_val <= rule_val  # type: ignore[no-any-return]
    if op == "gt":
        return field_val > rule_val  # type: ignore[no-any-return]
    if op == "gte":
        return field_val >= rule_val  # type: ignore[no-any-return]
    if op == "in":
        return field_val in rule_val  # type: ignore[no-any-return]
    if op == "not_in":
        return field_val not in rule_val  # type: ignore[no-any-return]
    if op == "contains":
        return rule_val in field_val  # type: ignore[no-any-return]
    log.warning("policy.condition.unknown_operator", operator=op)
    return False


# ---------------------------------------------------------------------------
# Multiple conditions (AND logic)
# ---------------------------------------------------------------------------


def evaluate_conditions(
    conditions: list[Condition],
    context: dict[str, Any],
) -> bool:
    """Evaluate a list of conditions — all must be true (AND logic).

    An empty condition list is considered a match (vacuously true).
    """
    return all(evaluate_condition(c, context) for c in conditions)


# ---------------------------------------------------------------------------
# Rule parsing
# ---------------------------------------------------------------------------


def parse_rules_yaml(yaml_str: str) -> list[PolicyRuleData]:
    """Parse a YAML string into a list of ``PolicyRuleData`` rules.

    Expected format::

        rules:
          - name: "Auto-approve small invoices"
            trigger: "invoice.generated"
            conditions:
              - field: "invoice.total"
                operator: "lt"
                value: 5000
            action: "auto_approve"
    """
    if not _HAS_YAML:
        raise ImportError(
            "PyYAML is required for YAML rule parsing. Install it with: pip install pyyaml",
        )

    data = yaml.safe_load(yaml_str)
    return _parse_rules_data(data)


def parse_rules_json(json_str: str) -> list[PolicyRuleData]:
    """Parse a JSON string into a list of ``PolicyRuleData`` rules.

    Expected format::

        {
          "rules": [
            {
              "name": "Auto-approve small invoices",
              "trigger": "invoice.generated",
              "conditions": [{"field": "invoice.total", "operator": "lt", "value": 5000}],
              "action": "auto_approve"
            }
          ]
        }
    """
    data = json.loads(json_str)
    return _parse_rules_data(data)


def _parse_rules_data(data: dict[str, Any]) -> list[PolicyRuleData]:
    """Validate and convert raw parsed data into ``PolicyRuleData`` objects."""
    raw_rules = data.get("rules", [])
    rules: list[PolicyRuleData] = []
    for raw in raw_rules:
        rules.append(PolicyRuleData(**raw))
    return rules
