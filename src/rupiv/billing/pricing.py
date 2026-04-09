"""Pricing engine for Rupiv.ai outcome-based billing.

ALL money arithmetic uses ``decimal.Decimal`` — never ``float``.

This module works with both the local ``PricingRule`` dataclass (for
standalone testing) and the SQLAlchemy ORM ``PricingRule`` model from
``rupiv.models.plan``.  The engine accesses attributes by name, so any
object that exposes the expected fields will work.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any, Protocol, runtime_checkable

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


class PricingModel(str, Enum):
    FLAT = "flat"
    USAGE = "usage"
    OUTCOME = "outcome"
    TIERED = "tiered"
    CREDIT = "credit"


@runtime_checkable
class PricingRuleLike(Protocol):
    """Structural interface satisfied by both the local dataclass and the
    SQLAlchemy ORM ``PricingRule`` model."""

    @property
    def pricing_model(self) -> str: ...  # "flat" | "usage" | "outcome" | "tiered"

    @property
    def metric(self) -> str | None: ...

    # Flat
    @property
    def flat_amount(self) -> Decimal | None: ...

    # Usage / outcome
    @property
    def unit_amount(self) -> Decimal | None: ...

    # Outcome specifics (stored in outcome_rules JSONB on the ORM model)
    @property
    def outcome_rules(self) -> dict[str, Any] | None: ...

    # Tiered specifics (stored in tiers JSONB on the ORM model)
    @property
    def tiers(self) -> list[dict[str, Any]] | None: ...


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
class TierBracket:
    """A single tier in tiered pricing."""

    up_to: Decimal | None  # None = unlimited (last tier)
    unit_amount: Decimal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TWO_PLACES = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _to_decimal(value: Any) -> Decimal:
    """Safely coerce a value to ``Decimal``."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value)) if value is not None else Decimal("0")


def _parse_tiers(raw: Any) -> list[TierBracket]:
    """Parse a JSONB tiers column into ``TierBracket`` objects.

    Accepts either a list of dicts (ORM JSONB) or a list of
    ``TierBracket`` instances.
    """
    if not raw:
        return []
    brackets: list[TierBracket] = []
    for item in raw:
        if isinstance(item, TierBracket):
            brackets.append(item)
        elif isinstance(item, dict):
            up_to_raw = item.get("up_to")
            up_to = Decimal(str(up_to_raw)) if up_to_raw is not None else None
            unit_amt = Decimal(str(item["unit_amount"]))
            brackets.append(TierBracket(up_to=up_to, unit_amount=unit_amt))
        else:
            raise TypeError(f"Unexpected tier type: {type(item)}")
    return brackets


def _rule_description(rule: Any) -> str:
    """Extract a human-readable description from a pricing rule."""
    # ORM PricingRule has no 'description' column — derive one.
    model_label = getattr(rule, "pricing_model", "unknown")
    if isinstance(model_label, Enum):
        model_label = model_label.value
    metric = getattr(rule, "metric", None) or ""
    return f"{model_label} — {metric}".strip(" —") if metric else str(model_label)


# ---------------------------------------------------------------------------
# Pricing engine
# ---------------------------------------------------------------------------


class PricingEngine:
    """Stateless pricing calculator.

    Every ``calculate_*`` method is a pure function — no I/O.
    """

    # -- Flat ---------------------------------------------------------------

    @staticmethod
    def calculate_flat(rule: Any, period: str) -> Decimal:
        """Return the fixed amount for *period*.

        Reads ``flat_amount`` (ORM) or ``amount`` (dataclass).
        """
        amount = getattr(rule, "flat_amount", None) or getattr(rule, "amount", None)
        if amount is None:
            raise ValueError("Flat rule must have a flat_amount or amount")

        amount = _to_decimal(amount)
        log.debug("pricing.flat", description=_rule_description(rule), period=period)
        return _round_money(amount)

    # -- Usage --------------------------------------------------------------

    @staticmethod
    def calculate_usage(rule: Any, quantity: Decimal) -> Decimal:
        """unit_amount * quantity."""
        unit_amount = _to_decimal(getattr(rule, "unit_amount", None))
        if unit_amount == Decimal("0"):
            raise ValueError("Usage rule must have a unit_amount")

        total = unit_amount * quantity
        log.debug(
            "pricing.usage",
            description=_rule_description(rule),
            quantity=str(quantity),
            unit_amount=str(unit_amount),
            total=str(total),
        )
        return _round_money(total)

    # -- Outcome ------------------------------------------------------------

    @staticmethod
    def calculate_outcome(
        rule: Any,
        outcomes: list[dict[str, Any]],
    ) -> Decimal:
        """Filter outcomes by ``billable_when`` rules, price valid ones,
        and respect ``cap_per_period``.

        The ORM model stores outcome config in the ``outcome_rules`` JSONB
        column with keys ``billable_when``, ``cap_per_period``.  The
        per-outcome price lives in ``unit_amount``.
        """
        # Extract outcome config from ORM JSONB or dataclass attrs.
        outcome_cfg: dict[str, Any] = getattr(rule, "outcome_rules", None) or {}
        billable_when: dict[str, Any] = outcome_cfg.get("billable_when", {})
        cap_raw = outcome_cfg.get("cap_per_period")
        cap_per_period: Decimal | None = Decimal(str(cap_raw)) if cap_raw is not None else None
        price_per_outcome = _to_decimal(
            outcome_cfg.get("price_per_outcome") or getattr(rule, "unit_amount", None),
        )

        if price_per_outcome == Decimal("0"):
            raise ValueError("Outcome rule must have a price_per_outcome or unit_amount")

        billable: list[dict[str, Any]] = []
        for outcome in outcomes:
            props = outcome.get("properties", outcome)
            if isinstance(props, str):
                import json

                try:
                    props = json.loads(props)
                except (json.JSONDecodeError, TypeError):
                    props = {}
            if all(props.get(k) == v for k, v in billable_when.items()):
                billable.append(outcome)

        billable_count = Decimal(len(billable))

        if cap_per_period is not None and billable_count > cap_per_period:
            billable_count = cap_per_period

        total = price_per_outcome * billable_count

        log.debug(
            "pricing.outcome",
            description=_rule_description(rule),
            raw_count=len(outcomes),
            billable_count=str(billable_count),
            total=str(total),
        )
        return _round_money(total)

    # -- Tiered -------------------------------------------------------------

    @staticmethod
    def calculate_tiered(rule: Any, quantity: Decimal) -> Decimal:
        """Apply graduated tiered pricing brackets."""
        brackets = _parse_tiers(getattr(rule, "tiers", None))
        if not brackets:
            raise ValueError("Tiered rule must have at least one tier")

        total = Decimal("0")
        remaining = quantity
        prev_limit = Decimal("0")

        for tier in brackets:
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
            description=_rule_description(rule),
            quantity=str(quantity),
            total=str(total),
        )
        return _round_money(total)

    # -- Credit -------------------------------------------------------------

    @staticmethod
    def calculate_credit(rule: Any, quantity: Decimal) -> Decimal:
        """Calculate the monetary value of consumed credits.

        Reads ``credits_per_unit`` and ``credit_rate`` from the rule's
        ``outcome_rules`` JSONB.  The formula is::

            total_credits = quantity * credits_per_unit
            amount = total_credits * credit_rate
        """
        outcome_cfg: dict[str, Any] = getattr(rule, "outcome_rules", None) or {}
        credits_per_unit = _to_decimal(outcome_cfg.get("credits_per_unit", 1))
        credit_rate = _to_decimal(outcome_cfg.get("credit_rate", 0))

        if credit_rate == Decimal("0"):
            raise ValueError("Credit rule must have a credit_rate in outcome_rules")

        total_credits = quantity * credits_per_unit
        total = total_credits * credit_rate

        log.debug(
            "pricing.credit",
            description=_rule_description(rule),
            quantity=str(quantity),
            credits_per_unit=str(credits_per_unit),
            credit_rate=str(credit_rate),
            total_credits=str(total_credits),
            total=str(total),
        )
        return _round_money(total)

    # -- Main entry point ---------------------------------------------------

    def calculate_line_items(
        self,
        pricing_rules: list[Any],
        aggregated: dict[str, dict[str, Any]],
        period: str,
    ) -> list[LineItem]:
        """Calculate all line items for a set of pricing rules.

        Args:
            pricing_rules: ORM ``PricingRule`` objects (or dataclass equivalents)
                with eagerly loaded plan data.
            aggregated: Dict keyed by metric name.  Each value is a dict that
                may contain ``"quantity"`` (``Decimal``) and/or ``"outcomes"``
                (``list[dict]``).
            period: ISO-8601 period label, e.g. ``"2026-04"``.

        Returns:
            Ordered list of ``LineItem`` instances.
        """
        line_items: list[LineItem] = []

        for rule in pricing_rules:
            model_val = getattr(rule, "pricing_model", None)
            if isinstance(model_val, Enum):
                model_val = model_val.value
            model = PricingModel(model_val)

            metric = getattr(rule, "metric", None) or ""
            metric_data: dict[str, Any] = aggregated.get(metric, {})
            desc = _rule_description(rule)

            if model == PricingModel.FLAT:
                amount = self.calculate_flat(rule, period)
                line_items.append(
                    LineItem(
                        description=desc,
                        quantity=Decimal("1"),
                        unit_amount=amount,
                        amount=amount,
                        metric=metric or None,
                        pricing_model=PricingModel.FLAT,
                    ),
                )

            elif model == PricingModel.USAGE:
                qty = _to_decimal(metric_data.get("quantity", 0))
                amount = self.calculate_usage(rule, qty)
                line_items.append(
                    LineItem(
                        description=desc,
                        quantity=qty,
                        unit_amount=_to_decimal(getattr(rule, "unit_amount", 0)),
                        amount=amount,
                        metric=metric or None,
                        pricing_model=PricingModel.USAGE,
                    ),
                )

            elif model == PricingModel.OUTCOME:
                outcomes_list: list[dict[str, Any]] = metric_data.get("outcomes", [])
                amount = self.calculate_outcome(rule, outcomes_list)
                outcome_cfg = getattr(rule, "outcome_rules", None) or {}
                ppo = _to_decimal(
                    outcome_cfg.get("price_per_outcome") or getattr(rule, "unit_amount", None),
                )
                billable_qty = amount / ppo if ppo else Decimal("0")
                line_items.append(
                    LineItem(
                        description=desc,
                        quantity=_round_money(billable_qty),
                        unit_amount=ppo,
                        amount=amount,
                        metric=metric or None,
                        pricing_model=PricingModel.OUTCOME,
                    ),
                )

            elif model == PricingModel.CREDIT:
                # Credit-based pricing: outcome_rules contains
                # {"credits_per_unit": 1, "credit_rate": 0.05}
                outcome_cfg = getattr(rule, "outcome_rules", None) or {}
                credits_per_unit = _to_decimal(outcome_cfg.get("credits_per_unit", 1))
                credit_rate = _to_decimal(outcome_cfg.get("credit_rate", 0))
                if credit_rate == Decimal("0"):
                    raise ValueError("Credit rule must have a credit_rate in outcome_rules")

                qty = _to_decimal(metric_data.get("quantity", 0))
                total_credits = qty * credits_per_unit
                amount = self.calculate_credit(rule, qty)
                line_items.append(
                    LineItem(
                        description=desc,
                        quantity=total_credits,
                        unit_amount=credit_rate,
                        amount=amount,
                        metric=metric or None,
                        pricing_model=PricingModel.CREDIT,
                    ),
                )

            elif model == PricingModel.TIERED:
                qty = _to_decimal(metric_data.get("quantity", 0))
                amount = self.calculate_tiered(rule, qty)
                line_items.append(
                    LineItem(
                        description=desc,
                        quantity=qty,
                        unit_amount=Decimal("0"),  # varies per tier
                        amount=amount,
                        metric=metric or None,
                        pricing_model=PricingModel.TIERED,
                    ),
                )

        log.info(
            "pricing.line_items_calculated",
            line_item_count=len(line_items),
        )
        return line_items
