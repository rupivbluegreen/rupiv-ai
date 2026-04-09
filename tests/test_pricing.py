"""Tests for the PricingEngine in ``rupiv.billing.pricing``.

All monetary values use ``Decimal`` — never ``float``.
"""

from __future__ import annotations

from decimal import Decimal

from rupiv.billing.pricing import (
    PricingEngine,
    PricingModel,
    PricingRule,
    TierBracket,
)

engine = PricingEngine()


# ---------------------------------------------------------------------------
# Flat pricing
# ---------------------------------------------------------------------------


class TestFlatPricing:
    """PricingEngine.calculate_flat returns a fixed amount."""

    def test_flat_returns_exact_amount(self) -> None:
        rule = PricingRule(
            model=PricingModel.FLAT,
            description="Monthly base fee",
            amount=Decimal("49.00"),
        )
        result = engine.calculate_flat(rule, period="2026-04")
        assert result == Decimal("49.00")

    def test_flat_rounds_to_two_decimal_places(self) -> None:
        rule = PricingRule(
            model=PricingModel.FLAT,
            description="Fractional fee",
            amount=Decimal("49.999"),
        )
        result = engine.calculate_flat(rule, period="2026-04")
        assert result == Decimal("50.00")

    def test_flat_raises_when_amount_missing(self) -> None:
        rule = PricingRule(
            model=PricingModel.FLAT,
            description="Bad rule",
            amount=None,
        )
        import pytest

        with pytest.raises(ValueError, match="amount"):
            engine.calculate_flat(rule, period="2026-04")


# ---------------------------------------------------------------------------
# Usage pricing
# ---------------------------------------------------------------------------


class TestUsagePricing:
    """PricingEngine.calculate_usage multiplies unit_amount by quantity."""

    def test_basic_usage_calculation(self) -> None:
        rule = PricingRule(
            model=PricingModel.USAGE,
            description="API calls",
            metric="api_call",
            unit_amount=Decimal("0.001"),
        )
        result = engine.calculate_usage(rule, quantity=Decimal("15000"))
        assert result == Decimal("15.00")

    def test_usage_rounds_to_two_places(self) -> None:
        rule = PricingRule(
            model=PricingModel.USAGE,
            description="Token usage",
            metric="tokens",
            unit_amount=Decimal("0.003"),
        )
        result = engine.calculate_usage(rule, quantity=Decimal("333"))
        # 0.003 * 333 = 0.999 -> rounds to 1.00
        assert result == Decimal("1.00")

    def test_usage_zero_quantity(self) -> None:
        rule = PricingRule(
            model=PricingModel.USAGE,
            description="API calls",
            metric="api_call",
            unit_amount=Decimal("0.01"),
        )
        result = engine.calculate_usage(rule, quantity=Decimal("0"))
        assert result == Decimal("0.00")

    def test_usage_raises_when_unit_amount_missing(self) -> None:
        rule = PricingRule(
            model=PricingModel.USAGE,
            description="Bad rule",
            metric="api_call",
            unit_amount=None,
        )
        import pytest

        with pytest.raises(ValueError, match="unit_amount"):
            engine.calculate_usage(rule, quantity=Decimal("100"))


# ---------------------------------------------------------------------------
# Outcome pricing
# ---------------------------------------------------------------------------


class TestOutcomePricing:
    """PricingEngine.calculate_outcome filters by billable_when and caps."""

    def test_all_outcomes_billable(self) -> None:
        rule = PricingRule(
            model=PricingModel.OUTCOME,
            description="Resolved tickets",
            metric="ticket_resolved",
            price_per_outcome=Decimal("0.99"),
            billable_when={"escalated": False},
        )
        outcomes = [
            {"escalated": False, "csat_score": 4.5},
            {"escalated": False, "csat_score": 3.2},
            {"escalated": False, "csat_score": 5.0},
        ]
        result = engine.calculate_outcome(rule, outcomes)
        # 3 * 0.99 = 2.97
        assert result == Decimal("2.97")

    def test_some_outcomes_filtered_out(self) -> None:
        rule = PricingRule(
            model=PricingModel.OUTCOME,
            description="Resolved tickets",
            metric="ticket_resolved",
            price_per_outcome=Decimal("0.99"),
            billable_when={"escalated": False},
        )
        outcomes = [
            {"escalated": False},
            {"escalated": True},   # not billable
            {"escalated": False},
            {"escalated": True},   # not billable
        ]
        result = engine.calculate_outcome(rule, outcomes)
        # 2 billable * 0.99 = 1.98
        assert result == Decimal("1.98")

    def test_cap_per_period_respected(self) -> None:
        rule = PricingRule(
            model=PricingModel.OUTCOME,
            description="Capped outcomes",
            metric="ticket_resolved",
            price_per_outcome=Decimal("1.00"),
            billable_when={},
            cap_per_period=Decimal("2"),
        )
        outcomes = [
            {"resolved": True},
            {"resolved": True},
            {"resolved": True},
            {"resolved": True},
            {"resolved": True},
        ]
        result = engine.calculate_outcome(rule, outcomes)
        # 5 billable but capped at 2 -> 2 * 1.00 = 2.00
        assert result == Decimal("2.00")

    def test_no_billable_when_means_all_billable(self) -> None:
        rule = PricingRule(
            model=PricingModel.OUTCOME,
            description="All outcomes count",
            metric="any",
            price_per_outcome=Decimal("2.50"),
            billable_when=None,
        )
        outcomes = [{"a": 1}, {"b": 2}]
        result = engine.calculate_outcome(rule, outcomes)
        assert result == Decimal("5.00")

    def test_empty_outcomes_list(self) -> None:
        rule = PricingRule(
            model=PricingModel.OUTCOME,
            description="No outcomes",
            metric="ticket_resolved",
            price_per_outcome=Decimal("0.99"),
        )
        result = engine.calculate_outcome(rule, outcomes=[])
        assert result == Decimal("0.00")

    def test_raises_when_price_per_outcome_missing(self) -> None:
        rule = PricingRule(
            model=PricingModel.OUTCOME,
            description="Bad rule",
            metric="ticket_resolved",
            price_per_outcome=None,
        )
        import pytest

        with pytest.raises(ValueError, match="price_per_outcome"):
            engine.calculate_outcome(rule, outcomes=[{"a": 1}])


# ---------------------------------------------------------------------------
# Tiered pricing
# ---------------------------------------------------------------------------


class TestTieredPricing:
    """PricingEngine.calculate_tiered applies graduated brackets."""

    def test_single_tier(self) -> None:
        rule = PricingRule(
            model=PricingModel.TIERED,
            description="Flat-rate tier",
            metric="events",
            tiers=[
                TierBracket(up_to=None, unit_amount=Decimal("0.01")),
            ],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("5000"))
        assert result == Decimal("50.00")

    def test_multi_tier_within_first_bracket(self) -> None:
        rule = PricingRule(
            model=PricingModel.TIERED,
            description="Multi-tier",
            metric="events",
            tiers=[
                TierBracket(up_to=Decimal("1000"), unit_amount=Decimal("0.01")),
                TierBracket(up_to=Decimal("10000"), unit_amount=Decimal("0.008")),
                TierBracket(up_to=None, unit_amount=Decimal("0.005")),
            ],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("500"))
        # All 500 in first tier: 500 * 0.01 = 5.00
        assert result == Decimal("5.00")

    def test_multi_tier_spans_two_brackets(self) -> None:
        rule = PricingRule(
            model=PricingModel.TIERED,
            description="Multi-tier",
            metric="events",
            tiers=[
                TierBracket(up_to=Decimal("1000"), unit_amount=Decimal("0.01")),
                TierBracket(up_to=Decimal("10000"), unit_amount=Decimal("0.008")),
                TierBracket(up_to=None, unit_amount=Decimal("0.005")),
            ],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("5000"))
        # 1000 * 0.01 + 4000 * 0.008 = 10 + 32 = 42.00
        assert result == Decimal("42.00")

    def test_multi_tier_spans_all_brackets(self) -> None:
        rule = PricingRule(
            model=PricingModel.TIERED,
            description="Multi-tier",
            metric="events",
            tiers=[
                TierBracket(up_to=Decimal("1000"), unit_amount=Decimal("0.01")),
                TierBracket(up_to=Decimal("10000"), unit_amount=Decimal("0.008")),
                TierBracket(up_to=None, unit_amount=Decimal("0.005")),
            ],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("15000"))
        # 1000 * 0.01 + 9000 * 0.008 + 5000 * 0.005
        # = 10 + 72 + 25 = 107.00
        assert result == Decimal("107.00")

    def test_zero_quantity(self) -> None:
        rule = PricingRule(
            model=PricingModel.TIERED,
            description="Zero usage",
            metric="events",
            tiers=[
                TierBracket(up_to=Decimal("1000"), unit_amount=Decimal("0.01")),
            ],
        )
        result = engine.calculate_tiered(rule, quantity=Decimal("0"))
        assert result == Decimal("0.00")

    def test_raises_when_no_tiers(self) -> None:
        rule = PricingRule(
            model=PricingModel.TIERED,
            description="Bad rule",
            metric="events",
            tiers=None,
        )
        import pytest

        with pytest.raises(ValueError, match="tier"):
            engine.calculate_tiered(rule, quantity=Decimal("100"))


# ---------------------------------------------------------------------------
# Hybrid pricing (calculate_line_items)
# ---------------------------------------------------------------------------


class TestHybridPricing:
    """PricingEngine.calculate_line_items combines multiple pricing models."""

    def test_base_plus_usage_plus_outcome(self) -> None:
        from rupiv.billing.pricing import Subscription

        sub = Subscription(
            subscription_id="sub-001",
            customer_id="cust-001",
            pricing_rules=[
                PricingRule(
                    model=PricingModel.FLAT,
                    description="Base fee",
                    amount=Decimal("99.00"),
                ),
                PricingRule(
                    model=PricingModel.USAGE,
                    description="API calls",
                    metric="api_call",
                    unit_amount=Decimal("0.001"),
                ),
                PricingRule(
                    model=PricingModel.OUTCOME,
                    description="Tickets resolved",
                    metric="ticket_resolved",
                    price_per_outcome=Decimal("0.99"),
                    billable_when={"escalated": False},
                ),
            ],
        )

        events = {
            "period": "2026-04",
            "api_call": {"quantity": 15000},
            "ticket_resolved": {
                "outcomes": [
                    {"escalated": False},
                    {"escalated": False},
                    {"escalated": True},
                ],
            },
        }

        line_items = engine.calculate_line_items(sub, events)
        assert len(line_items) == 3

        amounts = [li.amount for li in line_items]
        # Base: 99.00, Usage: 15.00, Outcome: 2 * 0.99 = 1.98
        assert amounts[0] == Decimal("99.00")
        assert amounts[1] == Decimal("15.00")
        assert amounts[2] == Decimal("1.98")

        total = sum(amounts)
        assert total == Decimal("115.98")
