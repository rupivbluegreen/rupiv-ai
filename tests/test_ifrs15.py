"""Tests for the IFRS 15 revenue recognition module.

All calculation logic is pure (no I/O), so these are fast unit tests.
Money values use ``decimal.Decimal`` throughout.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from rupiv.models.plan import PricingModel
from rupiv.revenue_recognition.allocation import allocate_transaction_price
from rupiv.revenue_recognition.journal import JournalEntry, generate_journal_entries
from rupiv.revenue_recognition.obligations import (
    PerformanceObligation,
    identify_obligations,
)
from rupiv.revenue_recognition.schedules import (
    GL_AR,
    GL_OUTCOME_REVENUE,
    GL_SAAS_REVENUE,
    RevenueScheduleEntry,
    generate_schedule,
)
from rupiv.revenue_recognition.variable_consideration import (
    constrain_estimate,
    estimate_variable_consideration,
)

# ---------------------------------------------------------------------------
# Helpers — lightweight PricingRule stand-ins
# ---------------------------------------------------------------------------


def _make_rule(
    *,
    pricing_model: PricingModel,
    flat_amount: Decimal | None = None,
    unit_amount: Decimal | None = None,
    metric: str | None = None,
) -> MagicMock:
    """Create a minimal PricingRule-like object for testing."""
    rule = MagicMock()
    rule.pricing_model = pricing_model
    rule.flat_amount = flat_amount
    rule.unit_amount = unit_amount
    rule.metric = metric
    return rule


# ---------------------------------------------------------------------------
# 1. Obligation identification
# ---------------------------------------------------------------------------


class TestIdentifyObligations:
    """identify_obligations() maps pricing rules to performance obligations."""

    def test_identify_flat_obligation(self) -> None:
        """Flat pricing rule produces platform_access, over_time."""
        rule = _make_rule(
            pricing_model=PricingModel.FLAT,
            flat_amount=Decimal("99.0000"),
            metric="platform",
        )
        sub_id = uuid.uuid4()

        obligations = identify_obligations(
            subscription_id=sub_id,
            plan_name="Basic Plan",
            pricing_rules=[rule],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        assert len(obligations) == 1
        ob = obligations[0]
        assert ob.obligation_type == "platform_access"
        assert ob.recognition_method == "over_time"
        assert ob.standalone_selling_price == Decimal("99.0000")
        assert ob.subscription_id == sub_id
        assert ob.start_date == date(2026, 1, 1)
        assert ob.end_date == date(2026, 3, 31)

    def test_identify_outcome_obligation(self) -> None:
        """Outcome pricing rule produces outcome_delivery, point_in_time."""
        rule = _make_rule(
            pricing_model=PricingModel.OUTCOME,
            unit_amount=Decimal("0.9900"),
            metric="ticket_resolved",
        )

        obligations = identify_obligations(
            subscription_id=uuid.uuid4(),
            plan_name="Outcome Growth",
            pricing_rules=[rule],
            start_date=date(2026, 1, 1),
        )

        assert len(obligations) == 1
        ob = obligations[0]
        assert ob.obligation_type == "outcome_delivery"
        assert ob.recognition_method == "point_in_time"
        assert ob.standalone_selling_price == Decimal("0.9900")

    def test_identify_hybrid_obligations(self) -> None:
        """A hybrid plan with flat + outcome rules produces two obligations."""
        flat_rule = _make_rule(
            pricing_model=PricingModel.FLAT,
            flat_amount=Decimal("99.0000"),
            metric="platform",
        )
        outcome_rule = _make_rule(
            pricing_model=PricingModel.OUTCOME,
            unit_amount=Decimal("0.9900"),
            metric="ticket_resolved",
        )

        obligations = identify_obligations(
            subscription_id=uuid.uuid4(),
            plan_name="Hybrid Plan",
            pricing_rules=[flat_rule, outcome_rule],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )

        assert len(obligations) == 2
        types = {ob.obligation_type for ob in obligations}
        assert types == {"platform_access", "outcome_delivery"}
        methods = {ob.recognition_method for ob in obligations}
        assert methods == {"over_time", "point_in_time"}


# ---------------------------------------------------------------------------
# 2. Transaction price allocation
# ---------------------------------------------------------------------------


class TestAllocateTransactionPrice:
    """allocate_transaction_price() distributes the total by relative SSP."""

    def test_allocate_equal_prices(self) -> None:
        """Two obligations with equal SSP get 50/50 split."""
        ob1 = PerformanceObligation(
            id=uuid.uuid4(),
            standalone_selling_price=Decimal("100"),
        )
        ob2 = PerformanceObligation(
            id=uuid.uuid4(),
            standalone_selling_price=Decimal("100"),
        )

        results = allocate_transaction_price(Decimal("200"), [ob1, ob2])

        assert len(results) == 2
        assert results[0].allocated_amount == Decimal("100.0000")
        assert results[1].allocated_amount == Decimal("100.0000")
        assert results[0].allocation_pct == Decimal("0.500000")

    def test_allocate_proportional(self) -> None:
        """Different SSPs produce proportional allocation."""
        ob1 = PerformanceObligation(
            id=uuid.uuid4(),
            standalone_selling_price=Decimal("300"),
        )
        ob2 = PerformanceObligation(
            id=uuid.uuid4(),
            standalone_selling_price=Decimal("100"),
        )

        results = allocate_transaction_price(Decimal("200"), [ob1, ob2])

        assert len(results) == 2
        # ob1 has 75% of SSP, ob2 has 25%
        assert results[0].allocated_amount == Decimal("150.0000")
        assert results[1].allocated_amount == Decimal("50.0000")
        total = sum(r.allocated_amount for r in results)
        assert total == Decimal("200")


# ---------------------------------------------------------------------------
# 3. Revenue schedule generation
# ---------------------------------------------------------------------------


class TestGenerateSchedule:
    """generate_schedule() creates monthly entries."""

    def test_generate_schedule_over_time(self) -> None:
        """3-month contract produces 3 monthly entries with equal amounts."""
        ob = PerformanceObligation(
            id=uuid.uuid4(),
            obligation_type="platform_access",
            recognition_method="over_time",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )

        entries = generate_schedule(
            obligation=ob,
            total_allocated=Decimal("300"),
            start=date(2026, 1, 1),
            end=date(2026, 3, 31),
        )

        assert len(entries) == 3
        assert entries[0].period == "2026-01"
        assert entries[1].period == "2026-02"
        assert entries[2].period == "2026-03"

        # Each month recognises 100
        for entry in entries:
            assert entry.recognized == Decimal("100.0000")
            assert entry.method == "over_time"
            assert entry.gl_debit == GL_AR
            assert entry.gl_credit == GL_SAAS_REVENUE

        # Sum of recognised equals total
        total_recognized = sum(e.recognized for e in entries)
        assert total_recognized == Decimal("300")

        # Deferred decreases over time
        assert entries[0].deferred == Decimal("200.0000")
        assert entries[1].deferred == Decimal("100.0000")
        assert entries[2].deferred == Decimal("0")

    def test_generate_schedule_point_in_time(self) -> None:
        """Point-in-time produces a single entry at the event date."""
        ob = PerformanceObligation(
            id=uuid.uuid4(),
            obligation_type="outcome_delivery",
            recognition_method="point_in_time",
            start_date=date(2026, 2, 15),
        )

        entries = generate_schedule(
            obligation=ob,
            total_allocated=Decimal("49.50"),
            start=date(2026, 2, 15),
            end=date(2026, 2, 28),
        )

        assert len(entries) == 1
        entry = entries[0]
        assert entry.period == "2026-02"
        assert entry.recognized == Decimal("49.50")
        assert entry.deferred == Decimal("0")
        assert entry.method == "point_in_time"
        assert entry.gl_credit == GL_OUTCOME_REVENUE


# ---------------------------------------------------------------------------
# 4. Variable consideration
# ---------------------------------------------------------------------------


class TestVariableConsideration:
    """estimate_variable_consideration() and constrain_estimate()."""

    def test_variable_consideration_expected_value(self) -> None:
        """Historical data produces a probability-weighted estimate."""
        historical = [
            {"volume": 1000, "probability": "0.30"},
            {"volume": 800, "probability": "0.50"},
            {"volume": 500, "probability": "0.20"},
        ]
        price_per = Decimal("0.99")

        result = estimate_variable_consideration(
            historical_outcomes=historical,
            price_per_outcome=price_per,
            method="expected_value",
        )

        # weighted volume = 1000*0.30 + 800*0.50 + 500*0.20 = 300 + 400 + 100 = 800
        # estimated = 800 * 0.99 = 792.0000
        assert result.method == "expected_value"
        assert result.estimated_amount == Decimal("792.0000")
        assert isinstance(result.estimated_amount, Decimal)
        # confidence = 0.30 + 0.50 + 0.20 = 1.0 -> no constraint
        assert result.confidence_level == Decimal("1")
        assert result.constraint_applied is False
        assert result.constrained_amount == Decimal("792.0000")

    def test_variable_consideration_constraint(self) -> None:
        """If confidence < 80%, the constraint is applied."""
        historical = [
            {"volume": 1000, "probability": "0.40"},
            {"volume": 500, "probability": "0.30"},
        ]
        price_per = Decimal("1.00")

        result = estimate_variable_consideration(
            historical_outcomes=historical,
            price_per_outcome=price_per,
            method="expected_value",
        )

        # weighted volume = 1000*0.40 + 500*0.30 = 400 + 150 = 550
        # estimated = 550 * 1.00 = 550.0000
        assert result.estimated_amount == Decimal("550.0000")
        # confidence = 0.40 + 0.30 = 0.70 < 0.80 -> constrained
        assert result.confidence_level == Decimal("0.70")
        assert result.constraint_applied is True
        # constrained = 550 * 0.70 = 385.0000
        assert result.constrained_amount == Decimal("385.0000")

    def test_constrain_estimate_above_threshold(self) -> None:
        """No constraint when confidence >= threshold."""
        amount, applied = constrain_estimate(Decimal("1000"), Decimal("0.90"), Decimal("0.80"))
        assert amount == Decimal("1000")
        assert applied is False

    def test_constrain_estimate_below_threshold(self) -> None:
        """Constraint applied when confidence < threshold."""
        amount, applied = constrain_estimate(Decimal("1000"), Decimal("0.60"), Decimal("0.80"))
        assert amount == Decimal("600.0000")
        assert applied is True


# ---------------------------------------------------------------------------
# 5. Journal entries
# ---------------------------------------------------------------------------


class TestJournalEntries:
    """generate_journal_entries() converts schedule entries to GL entries."""

    def test_journal_entries(self) -> None:
        """Each schedule entry with recognised > 0 becomes a journal entry."""
        ob_id = uuid.uuid4()
        schedule_entries = [
            RevenueScheduleEntry(
                period="2026-01",
                obligation_id=ob_id,
                method="over_time",
                gross_amount=Decimal("300"),
                recognized=Decimal("100"),
                deferred=Decimal("200"),
                gl_debit=GL_AR,
                gl_credit=GL_SAAS_REVENUE,
            ),
            RevenueScheduleEntry(
                period="2026-02",
                obligation_id=ob_id,
                method="over_time",
                gross_amount=Decimal("300"),
                recognized=Decimal("100"),
                deferred=Decimal("100"),
                gl_debit=GL_AR,
                gl_credit=GL_SAAS_REVENUE,
            ),
            RevenueScheduleEntry(
                period="2026-03",
                obligation_id=ob_id,
                method="over_time",
                gross_amount=Decimal("300"),
                recognized=Decimal("100"),
                deferred=Decimal("0"),
                gl_debit=GL_AR,
                gl_credit=GL_SAAS_REVENUE,
            ),
        ]

        journal = generate_journal_entries(schedule_entries, currency="EUR")

        assert len(journal) == 3
        for je in journal:
            assert isinstance(je, JournalEntry)
            assert je.debit_account == GL_AR
            assert je.credit_account == GL_SAAS_REVENUE
            assert je.amount == Decimal("100")
            assert je.currency == "EUR"
            assert je.reference_type == "revenue_schedule_entry"
            assert je.reference_id == ob_id

        # Dates correspond to first of each period month
        assert journal[0].date == date(2026, 1, 1)
        assert journal[1].date == date(2026, 2, 1)
        assert journal[2].date == date(2026, 3, 1)
