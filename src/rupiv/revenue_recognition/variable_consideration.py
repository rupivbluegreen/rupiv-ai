"""Variable consideration estimation (IFRS 15 Step 3 — outcome billing).

Outcome-based billing produces *variable consideration*: revenue that depends
on uncertain future events.  IFRS 15 requires estimating the amount and
applying a constraint so that recognised revenue is "highly probable" of not
being reversed.

Two estimation methods:
- **Expected value**: probability-weighted average of possible outcomes.
- **Most likely amount**: single most probable outcome amount.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
from dataclasses import dataclass


@dataclass(frozen=True)
class VariableEstimate:
    """Result of estimating variable consideration for an obligation."""

    method: str  # "expected_value" | "most_likely_amount"
    estimated_amount: Decimal
    constraint_applied: bool
    constrained_amount: Decimal
    confidence_level: Decimal


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_FOUR_PLACES = Decimal("0.0001")


def constrain_estimate(
    estimate: Decimal,
    confidence: Decimal,
    threshold: Decimal = Decimal("0.80"),
) -> tuple[Decimal, bool]:
    """Apply the IFRS 15 variable consideration constraint.

    Revenue is only included to the extent that it is *highly probable* of
    not reversing.  We use a configurable confidence threshold (default 80%).

    Parameters
    ----------
    estimate:
        The unconstrained estimated amount.
    confidence:
        The probability that this amount will actually be realised (0-1).
    threshold:
        Minimum confidence required.  Defaults to ``0.80`` (80%).

    Returns
    -------
    tuple[Decimal, bool]
        ``(constrained_amount, was_constraint_applied)``
    """
    if confidence >= threshold:
        return estimate, False
    # Scale down proportionally to the confidence level.
    constrained = (estimate * confidence).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)
    return constrained, True


def estimate_variable_consideration(
    historical_outcomes: list[dict],
    price_per_outcome: Decimal,
    method: str = "expected_value",
) -> VariableEstimate:
    """Estimate variable consideration from historical outcome data.

    Parameters
    ----------
    historical_outcomes:
        Each dict must contain:
        - ``volume`` (int): number of outcomes in a period.
        - ``probability`` (float|str): likelihood of this volume occurring (0-1).
    price_per_outcome:
        The per-outcome fee.
    method:
        ``"expected_value"`` (default) or ``"most_likely_amount"``.

    Returns
    -------
    VariableEstimate
    """
    if not historical_outcomes:
        return VariableEstimate(
            method=method,
            estimated_amount=Decimal("0"),
            constraint_applied=False,
            constrained_amount=Decimal("0"),
            confidence_level=Decimal("0"),
        )

    if method == "most_likely_amount":
        # Pick the outcome with the highest probability.
        best = max(historical_outcomes, key=lambda o: Decimal(str(o["probability"])))
        volume = Decimal(str(best["volume"]))
        confidence = Decimal(str(best["probability"]))
        estimated = (volume * price_per_outcome).quantize(
            _FOUR_PLACES, rounding=ROUND_HALF_UP
        )
    else:
        # Expected value: sum of (volume * probability) across all scenarios.
        weighted_volume = sum(
            Decimal(str(o["volume"])) * Decimal(str(o["probability"]))
            for o in historical_outcomes
        )
        estimated = (weighted_volume * price_per_outcome).quantize(
            _FOUR_PLACES, rounding=ROUND_HALF_UP
        )
        # Confidence = sum of probabilities of scenarios that actually occur
        # We use the total probability mass as a proxy.
        confidence = sum(
            Decimal(str(o["probability"])) for o in historical_outcomes
        )
        # Clamp to [0, 1].
        confidence = min(confidence, Decimal("1"))

    constrained_amount, was_constrained = constrain_estimate(estimated, confidence)

    result = VariableEstimate(
        method=method,
        estimated_amount=estimated,
        constraint_applied=was_constrained,
        constrained_amount=constrained_amount,
        confidence_level=confidence,
    )

    log.debug(
        "variable_consideration_estimated",
        method=method,
        estimated=str(estimated),
        constrained=str(constrained_amount),
        confidence=str(confidence),
    )

    return result
