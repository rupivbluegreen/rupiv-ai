"""Tests for the PricingEngine in ``rupiv.billing.pricing``.

All monetary values use ``Decimal`` — never ``float``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from rupiv.billing.pricing import (
    PricingEngine,
    TierBracket,
)

engine = PricingEngine()


# ---------------------------------------------------------------------------
# Test-only dataclass that satisfies PricingRuleLike protocol
# ---------------------------------------------------------------------------
@dataclass
class FakeRule:
    """Lightweight rule object for testing the pricing engine."""

    pricing_model: str = "flat"
    metric: str | None = None
    flat_amount: Decimal | None = None
    unit_amount: Decimal | None = None
    outcome_rules: dict[str, Any] | None = None
    tiers: list[TierBracket] | None = None


# ---------------------------------------------------------------------------
# Flat pricing
# ---------------------------------------------------------------------------


class TestFlatPricing:
    """PricingEngine.calculate_flat returns a fixed amount."""

    def test_flat_returns_exact_amount(self) -> None:
        rule = FakeRule(flat_amount=Decimal("49.00"))
        result = engine.calculate_flat(rule, period="2026-04")
        assert result == Decimal("49.00")

    def test_flat_rounds_to_two_decimal_places(self) -> None:
        rule = FakeRule(flat_amount=Decimal("49.999"))
        result = engine.calculate_flat(rule, period="2026-04")
        assert result == Decimal("50.00")

    def test_flat_raises_when_amount_missing(self) -> None:
        rule = FakeRule(flat_amount=None)
        with pytest.raises(ValueError, match="amount"):
            engine.calculate_flat(rule, period="2026-04")


# ---------------------------------------------------------------------------
# Usage pricing
# ---------------------------------------------------------------------------


class TestUsagePricing:
    """PricingEngine.calculate_usage multiplies unit_amount by quantity."""

    def test_basic_usage_calculation(self) -> None:
        rule = FakeRule(pricing_model="usage", metric="api_call", unit_amount=Decimal("0.001"))
        result = engine.calculate_usage(rule, quantity=Decimal("15000"))
        assert result == Decimal("15.00")

    def test_usage_rounds_to_two_places(self) -> None:
        rule = FakeRule(pricing_model="usage", metric="tokens", unit_amount=Decimal("0.003"))
        result = engine.calculate_usage(rule, quantity=Decimal("333"))
        assert result == Decimal("1.00")

    def test_usage_zero_quantity(self) -> None:
        rule = FakeRule(pricing_model="usage", metric="api_call", unit_amount=Decimal("0.01"))
        result = engine.calculate_usage(rule, quantity=Decimal("0"))
        assert result == Decimal("0.00")

    def test_usage_raises_when_unit_amount_missing(self) -> None:
        rule = FakeRule(pricing_model="usage", metric="api_call", unit_amount=None)
        with pytest.raises(ValueError, match="unit_amount"):
            engine.calculate_usage(rule, quantity=Decimal("100"))


# ---------------------------------------------------------------------------
# Outcome pricing
# ---------------------------------------------------------------------------


class TestOutcomePricing:
    """PricingEngine.calculate_outcome filters by billable_when and caps."""

    def test_all_outcomes_billable(self) -> None:
        rule = FakeRule(
            pricing_model="outcome",
            metric="ticket_resolved",
            outcome_rules={
                "price_per_outcome": "0.99",
                "billable_when": {"escalated": False},
            },
        )
        outcomes = [
            {"escalated": False, "csat_score": 4.5},
            {"escalated": False, "csat_score": 3.2},
            {"escalated": False, "csat_score": 5.0},
        ]
        result = engine.calculate_outcome(rule, outcomes)
        assert result == Decimal("2.97")

    def test_some_outcomes_filtered_out(self) -> None:
        rule = FakeRule(
            pricing_model="outcome",
            metric="ticket_resolved",
            outcome_rules={
                "price_per_outcome": "0.99",
                "billable_when": {"escalated": False},
            },
        )
        outcomes = [
            {"escalated": False},
            {"escalated": True},
            {"escalated": False},
            {"escalated": True},
        ]
        result = engine.calculate_outcome(rule, outcomes)
        assert result == Decimal("1.98")

    def test_cap_per_period_respected(self) -> None:
        rule = FakeRule(
            pricing_model="outcome",
            metric="ticket_resolved",
            outcome_rules={
                "price_per_outcome": "1.00",
                "billable_when": {},
                "cap_per_period": 2,
            },
        )
        outcomes = [{"r": True}] * 5
        result = engine.calculate_outcome(rule, outcomes)
        assert result == Decimal("2.00")

    def test_no_billable_when_means_all_billable(self) -> None:
        rule = FakeRule(
            pricing_model="outcome",
            metric="any",
            outcome_rules={"price_per_outcome": "2.50"},
        )
        outcomes = [{"a": 1}, {"b": 2}]
        result = engine.calculate_outcome(rule, outcomes)
        assert result == Decimal("5.00")

    def test_empty_outcomes_list(self) -> None:
        rule = FakeRule(
            pricing_model="outcome",
            metric="ticket_resolved",
            outcome_rules={"price_per_outcome": "0.99"},
        )
        result = engine.calculate_outcome(rule, outcomes=[])
        assert result == Decimal("0.00")

    def test_raises_when_price_per_outcome_missing(self) -> None:
        rule = FakeRule(
            pricing_model="outcome",
            metric="ticket_resolved",
            outcome_rules={},
        )
        with pytest.raises(ValueError, match="price_per_outcome"):
            engine.calculate_outcome(rule, outcomes=[{"a": 1}])


# ---------------------------------------------------------------------------
# Tiered pricing
# ---------------------------------------------------------------------------


class TestTieredPricing:
    """PricingEngine.calculate_tiered applies graduated brackets."""

    def test_single_tier(self) -> None:
        rule = FakeRule(
            pricing_model="tiered",
            metric="events",
            tiers=[TierBracket(up_to=None, unit_amount=Decimal("0.01"))],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("5000"))
        assert result == Decimal("50.00")

    def test_multi_tier_within_first_bracket(self) -> None:
        rule = FakeRule(
            pricing_model="tiered",
            metric="events",
            tiers=[
                TierBracket(up_to=Decimal("1000"), unit_amount=Decimal("0.01")),
                TierBracket(up_to=Decimal("10000"), unit_amount=Decimal("0.008")),
                TierBracket(up_to=None, unit_amount=Decimal("0.005")),
            ],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("500"))
        assert result == Decimal("5.00")

    def test_multi_tier_spans_two_brackets(self) -> None:
        rule = FakeRule(
            pricing_model="tiered",
            metric="events",
            tiers=[
                TierBracket(up_to=Decimal("1000"), unit_amount=Decimal("0.01")),
                TierBracket(up_to=Decimal("10000"), unit_amount=Decimal("0.008")),
                TierBracket(up_to=None, unit_amount=Decimal("0.005")),
            ],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("5000"))
        assert result == Decimal("42.00")

    def test_multi_tier_spans_all_brackets(self) -> None:
        rule = FakeRule(
            pricing_model="tiered",
            metric="events",
            tiers=[
                TierBracket(up_to=Decimal("1000"), unit_amount=Decimal("0.01")),
                TierBracket(up_to=Decimal("10000"), unit_amount=Decimal("0.008")),
                TierBracket(up_to=None, unit_amount=Decimal("0.005")),
            ],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("15000"))
        assert result == Decimal("107.00")

    def test_zero_quantity(self) -> None:
        rule = FakeRule(
            pricing_model="tiered",
            metric="events",
            tiers=[TierBracket(up_to=Decimal("1000"), unit_amount=Decimal("0.01"))],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("0"))
        assert result == Decimal("0.00")

    def test_raises_when_no_tiers(self) -> None:
        rule = FakeRule(pricing_model="tiered", metric="events", tiers=None)
        with pytest.raises(ValueError, match="tier"):
            engine.calculate_tiered(rule, quantity=Decimal("100"))


# ---------------------------------------------------------------------------
# Hybrid pricing (calculate_line_items)
# ---------------------------------------------------------------------------


class TestHybridPricing:
    """PricingEngine.calculate_line_items combines multiple pricing models."""

    def test_base_plus_usage_plus_outcome(self) -> None:
        rules = [
            FakeRule(
                pricing_model="flat",
                flat_amount=Decimal("99.00"),
            ),
            FakeRule(
                pricing_model="usage",
                metric="api_call",
                unit_amount=Decimal("0.001"),
            ),
            FakeRule(
                pricing_model="outcome",
                metric="ticket_resolved",
                outcome_rules={
                    "price_per_outcome": "0.99",
                    "billable_when": {"escalated": False},
                },
            ),
        ]

        aggregated = {
            "api_call": {"quantity": Decimal("15000")},
            "ticket_resolved": {
                "outcomes": [
                    {"escalated": False},
                    {"escalated": False},
                    {"escalated": True},
                ],
            },
        }

        line_items = engine.calculate_line_items(rules, aggregated, period="2026-04")
        assert len(line_items) == 3

        amounts = [li.amount for li in line_items]
        assert amounts[0] == Decimal("99.00")
        assert amounts[1] == Decimal("15.00")
        assert amounts[2] == Decimal("1.98")

        total = sum(amounts)
        assert total == Decimal("115.98")
