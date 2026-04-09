"""Pricing engine for Rupiv.ai outcome-based billing.

ALL money arithmetic uses ``decimal.Decimal`` — never ``float``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class PricingModel(str, Enum):
    FLAT = "flat"
    USAGE = "usage"
    OUTCOME = "outcome"
    TIERED = "tiered"


@dataclass(frozen=True)
class LineItem:
    """A single line on an invoice."""

    description: str
    quantity: Decimal
    unit_amount: Decimal
    amount: Decimal
    metric: str | None
    pricing_model: PricingModel


@dataclass(frozen=True)
class PricingRule:
    """A pricing rule attached to a subscription plan.

    Fields vary by *model*:
    - flat:    amount
    - usage:   unit_amount, metric
    - outcome: price_per_outcome, billable_when, cap_per_period, metric
    - tiered:  tiers (list[TierBracket]), metric
    """

    model: PricingModel
    description: str
    metric: str | None = None
    amount: Decimal | None = None
    unit_amount: Decimal | None = None
    price_per_outcome: Decimal | None = None
    billable_when: dict[str, Any] | None = None
    cap_per_period: Decimal | None = None
    tiers: list[TierBracket] | None = None


@dataclass(frozen=True)
class TierBracket:
    """A single tier in tiered pricing."""

    up_to: Decimal | None  # None = unlimited (last tier)
    unit_amount: Decimal


@dataclass
class Subscription:
    """Minimal subscription representation for the pricing engine."""

    subscription_id: str
    customer_id: str
    pricing_rules: list[PricingRule]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TWO_PLACES = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Pricing engine
# ---------------------------------------------------------------------------


class PricingEngine:
    """Stateless pricing calculator.

    Every ``calculate_*`` method is a pure function — no I/O.
    """

    # -- Flat ---------------------------------------------------------------

    @staticmethod
    def calculate_flat(rule: PricingRule, period: str) -> Decimal:
        """Return the fixed amount for *period* (ignored for now; reserved
        for future pro-ration logic).

        Args:
            rule: A PricingRule with model=FLAT and ``amount`` set.
            period: ISO-8601 period label, e.g. ``"2026-04"``.

        Returns:
            The flat fee as a Decimal rounded to 2 d.p.
        """
        if rule.amount is None:
            raise ValueError("Flat rule must have an amount")

        log.debug("pricing.flat", description=rule.description, period=period)
        return _round_money(rule.amount)

    # -- Usage --------------------------------------------------------------

    @staticmethod
    def calculate_usage(rule: PricingRule, quantity: Decimal) -> Decimal:
        """unit_amount * quantity.

        Args:
            rule: A PricingRule with model=USAGE and ``unit_amount`` set.
            quantity: Metered usage quantity for the period.

        Returns:
            Total usage charge rounded to 2 d.p.
        """
        if rule.unit_amount is None:
            raise ValueError("Usage rule must have a unit_amount")

        total = rule.unit_amount * quantity
        log.debug(
            "pricing.usage",
            description=rule.description,
            quantity=str(quantity),
            unit_amount=str(rule.unit_amount),
            total=str(total),
        )
        return _round_money(total)

    # -- Outcome ------------------------------------------------------------

    @staticmethod
    def calculate_outcome(
        rule: PricingRule,
        outcomes: list[dict[str, Any]],
    ) -> Decimal:
        """Filter outcomes by ``billable_when`` rules, price valid ones,
        and respect ``cap_per_period``.

        ``billable_when`` is a dict of ``{field: expected_value}`` — an
        outcome is billable only when **all** conditions match.

        Args:
            rule: A PricingRule with model=OUTCOME.
            outcomes: Raw outcome dicts from the aggregation layer.

        Returns:
            Total outcome charge rounded to 2 d.p.
        """
        if rule.price_per_outcome is None:
            raise ValueError("Outcome rule must have a price_per_outcome")

        billable_when = rule.billable_when or {}

        billable: list[dict[str, Any]] = []
        for outcome in outcomes:
            if all(outcome.get(k) == v for k, v in billable_when.items()):
                billable.append(outcome)

        billable_count = Decimal(len(billable))

        if rule.cap_per_period is not None and billable_count > rule.cap_per_period:
            billable_count = rule.cap_per_period

        total = rule.price_per_outcome * billable_count

        log.debug(
            "pricing.outcome",
            description=rule.description,
            raw_count=len(outcomes),
            billable_count=str(billable_count),
            total=str(total),
        )
        return _round_money(total)

    # -- Tiered -------------------------------------------------------------

    @staticmethod
    def calculate_tiered(rule: PricingRule, quantity: Decimal) -> Decimal:
        """Apply graduated tiered pricing brackets.

        Each bracket covers ``(previous_up_to, bracket.up_to]``.  The last
        bracket (``up_to=None``) covers everything above the penultimate
        bracket.

        Args:
            rule: A PricingRule with model=TIERED and ``tiers`` set.
            quantity: Aggregate usage quantity for the period.

        Returns:
            Total tiered charge rounded to 2 d.p.
        """
        if not rule.tiers:
            raise ValueError("Tiered rule must have at least one tier")

        total = Decimal("0")
        remaining = quantity
        prev_limit = Decimal("0")

        for tier in rule.tiers:
            if remaining <= 0:
                break

            if tier.up_to is not None:
                bracket_size = tier.up_to - prev_limit
                taxable = min(remaining, bracket_size)
                prev_limit = tier.up_to
            else:
                # Unlimited last tier
                taxable = remaining

            total += tier.unit_amount * taxable
            remaining -= taxable

        log.debug(
            "pricing.tiered",
            description=rule.description,
            quantity=str(quantity),
            total=str(total),
        )
        return _round_money(total)

    # -- Main entry point ---------------------------------------------------

    def calculate_line_items(
        self,
        subscription: Subscription,
        events: dict[str, Any],
    ) -> list[LineItem]:
        """Calculate all line items for a subscription in a billing period.

        ``events`` is a dict keyed by metric name containing:
        - ``"quantity"``  — ``Decimal`` aggregate (for usage / tiered)
        - ``"outcomes"``  — ``list[dict]`` (for outcome rules)
        - ``"period"``    — ISO-8601 period label (for flat rules)

        Returns:
            Ordered list of ``LineItem`` instances.
        """
        line_items: list[LineItem] = []
        period: str = events.get("period", "")

        for rule in subscription.pricing_rules:
            if rule.model == PricingModel.FLAT:
                amount = self.calculate_flat(rule, period)
                line_items.append(
                    LineItem(
                        description=rule.description,
                        quantity=Decimal("1"),
                        unit_amount=amount,
                        amount=amount,
                        metric=rule.metric,
                        pricing_model=PricingModel.FLAT,
                    )
                )

            elif rule.model == PricingModel.USAGE:
                metric_data = events.get(rule.metric or "", {})
                qty = Decimal(str(metric_data.get("quantity", 0)))
                amount = self.calculate_usage(rule, qty)
                line_items.append(
                    LineItem(
                        description=rule.description,
                        quantity=qty,
                        unit_amount=rule.unit_amount or Decimal("0"),
                        amount=amount,
                        metric=rule.metric,
                        pricing_model=PricingModel.USAGE,
                    )
                )

            elif rule.model == PricingModel.OUTCOME:
                metric_data = events.get(rule.metric or "", {})
                outcomes_list: list[dict[str, Any]] = metric_data.get("outcomes", [])
                amount = self.calculate_outcome(rule, outcomes_list)
                billable_qty = amount / (rule.price_per_outcome or Decimal("1"))
                line_items.append(
                    LineItem(
                        description=rule.description,
                        quantity=_round_money(billable_qty),
                        unit_amount=rule.price_per_outcome or Decimal("0"),
                        amount=amount,
                        metric=rule.metric,
                        pricing_model=PricingModel.OUTCOME,
                    )
                )

            elif rule.model == PricingModel.TIERED:
                metric_data = events.get(rule.metric or "", {})
                qty = Decimal(str(metric_data.get("quantity", 0)))
                amount = self.calculate_tiered(rule, qty)
                line_items.append(
                    LineItem(
                        description=rule.description,
                        quantity=qty,
                        unit_amount=Decimal("0"),  # varies per tier
                        amount=amount,
                        metric=rule.metric,
                        pricing_model=PricingModel.TIERED,
                    )
                )

        log.info(
            "pricing.line_items_calculated",
            subscription_id=subscription.subscription_id,
            line_item_count=len(line_items),
        )
        return line_items
