"""Core policy evaluation engine.

The ``PolicyEngine`` is stateless and performs no I/O — all data is passed
in via ``context`` dicts and ``PolicyRuleData`` rule definitions.

Rules are evaluated in priority order (lower number = higher priority).
The first ``reject`` action wins immediately; otherwise the first match wins.
If no rules match, the default action is ``allow`` (pass-through).
"""

from __future__ import annotations

from typing import Any

import structlog

from rupiv.policy.rules import (
    Condition,
    PolicyResult,
    PolicyRuleData,
    evaluate_conditions,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Re-export so consumers can import from engine
__all__ = [
    "Condition",
    "PolicyEngine",
    "PolicyResult",
    "PolicyRuleData",
]

# ---------------------------------------------------------------------------
# Default result when no rules match
# ---------------------------------------------------------------------------

_DEFAULT_RESULT = PolicyResult(
    rule_name="__default__",
    action="allow",
    reason="No matching rules — default pass-through",
    matched=False,
)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Stateless, pure-function policy evaluator.

    No I/O — all data is passed in.  Thread-safe by design.
    """

    def evaluate(
        self,
        context: dict[str, Any],
        rules: list[PolicyRuleData],
    ) -> PolicyResult:
        """Evaluate *rules* against *context* and return the winning result.

        Rules are sorted by priority (ascending).  The first ``reject``
        action wins immediately.  Otherwise the first matching rule wins.
        If nothing matches, an ``allow`` result is returned.
        """
        sorted_rules = sorted(rules, key=lambda r: r.priority)

        first_match: PolicyResult | None = None

        for rule in sorted_rules:
            matched = evaluate_conditions(rule.conditions, context)
            if not matched:
                continue

            result = PolicyResult(
                rule_name=rule.name,
                action=rule.action,
                approver=rule.approver,
                reason=f"Rule '{rule.name}' matched",
                matched=True,
            )

            log.debug(
                "policy.rule_matched",
                rule_name=rule.name,
                action=rule.action,
                priority=rule.priority,
            )

            # Reject wins immediately
            if rule.action == "reject":
                return result

            if first_match is None:
                first_match = result

        if first_match is not None:
            return first_match

        log.debug("policy.no_match", context_keys=list(context.keys()))
        return _DEFAULT_RESULT

    def evaluate_all(
        self,
        context: dict[str, Any],
        rules: list[PolicyRuleData],
    ) -> list[PolicyResult]:
        """Evaluate *rules* against *context* and return ALL matching results.

        Results are returned in priority order.
        """
        sorted_rules = sorted(rules, key=lambda r: r.priority)
        results: list[PolicyResult] = []

        for rule in sorted_rules:
            matched = evaluate_conditions(rule.conditions, context)
            if matched:
                results.append(
                    PolicyResult(
                        rule_name=rule.name,
                        action=rule.action,
                        approver=rule.approver,
                        reason=f"Rule '{rule.name}' matched",
                        matched=True,
                    ),
                )

        return results
