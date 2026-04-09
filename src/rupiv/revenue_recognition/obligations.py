"""Performance obligation identification (IFRS 15 Step 2).

Maps pricing rules on a subscription's plan to distinct performance obligations,
each with a standalone selling price and a recognition method.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

import structlog

from rupiv.models.plan import PricingModel, PricingRule

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

ObligationType = Literal[
    "platform_access",
    "outcome_delivery",
    "usage_consumption",
    "support",
]

RecognitionMethod = Literal["over_time", "point_in_time"]


@dataclass(frozen=True)
class PerformanceObligation:
    """A single IFRS 15 performance obligation derived from a pricing rule."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    subscription_id: uuid.UUID = field(default_factory=uuid.uuid4)
    obligation_type: ObligationType = "platform_access"
    description: str = ""
    standalone_selling_price: Decimal = Decimal("0")
    recognition_method: RecognitionMethod = "over_time"
    start_date: date = field(default_factory=date.today)
    end_date: date | None = None


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

_MODEL_TO_OBLIGATION: dict[PricingModel, tuple[ObligationType, RecognitionMethod]] = {
    PricingModel.FLAT: ("platform_access", "over_time"),
    PricingModel.USAGE: ("usage_consumption", "point_in_time"),
    PricingModel.OUTCOME: ("outcome_delivery", "point_in_time"),
    PricingModel.TIERED: ("usage_consumption", "point_in_time"),
    PricingModel.CREDIT: ("usage_consumption", "point_in_time"),
}


def _standalone_price(rule: PricingRule) -> Decimal:
    """Derive the standalone selling price from a pricing rule."""
    if rule.flat_amount is not None and rule.flat_amount > 0:
        return Decimal(str(rule.flat_amount))
    if rule.unit_amount is not None and rule.unit_amount > 0:
        return Decimal(str(rule.unit_amount))
    return Decimal("0")


def _description_for(rule: PricingRule, ob_type: ObligationType) -> str:
    """Build a human-readable obligation description."""
    metric = rule.metric or "N/A"
    return f"{ob_type} — {rule.pricing_model.value} pricing on {metric}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def identify_obligations(
    subscription_id: uuid.UUID,
    plan_name: str,
    pricing_rules: list[PricingRule],
    start_date: date,
    end_date: date | None = None,
) -> list[PerformanceObligation]:
    """Identify performance obligations from a plan's pricing rules.

    Each pricing rule produces exactly one obligation.  Hybrid plans are
    expected to have multiple pricing rules (e.g. one flat + one outcome),
    so the caller should pass all rules from the plan.

    Parameters
    ----------
    subscription_id:
        UUID of the subscription that owns the obligations.
    plan_name:
        Human-readable plan name (used in descriptions).
    pricing_rules:
        The ``PricingRule`` instances attached to the plan.
    start_date / end_date:
        Contract period boundaries.

    Returns
    -------
    list[PerformanceObligation]
    """
    obligations: list[PerformanceObligation] = []

    for rule in pricing_rules:
        model = rule.pricing_model

        # Hybrid plans are decomposed into their constituent rules upstream,
        # so we should not see PricingModel.HYBRID here.  If we do, fall back
        # to platform_access / over_time.
        ob_type, method = _MODEL_TO_OBLIGATION.get(
            model, ("platform_access", "over_time")
        )

        obligation = PerformanceObligation(
            id=uuid.uuid4(),
            subscription_id=subscription_id,
            obligation_type=ob_type,
            description=_description_for(rule, ob_type),
            standalone_selling_price=_standalone_price(rule),
            recognition_method=method,
            start_date=start_date,
            end_date=end_date,
        )
        obligations.append(obligation)
        log.debug(
            "obligation_identified",
            obligation_id=str(obligation.id),
            type=ob_type,
            method=method,
            ssp=str(obligation.standalone_selling_price),
        )

    return obligations
