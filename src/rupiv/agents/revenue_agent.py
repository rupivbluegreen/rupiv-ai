"""LangGraph revenue recognition agent — IFRS 15 schedule generation.

Orchestrates the full revenue recognition flow:
obligation identification -> price allocation -> schedule generation
-> journal entry creation -> persistence.

Modelled as a LangGraph ``StateGraph`` with error handling.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.config import get_settings
from rupiv.db import get_db
from rupiv.models.revenue_schedule import (
    EntryType,
    RevenueEntry,
    RevenueSchedule,
    ScheduleStatus,
)
from rupiv.models.subscription import Subscription
from rupiv.revenue_recognition.allocation import allocate_transaction_price
from rupiv.revenue_recognition.journal import generate_journal_entries
from rupiv.revenue_recognition.obligations import identify_obligations
from rupiv.revenue_recognition.schedules import generate_schedule

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class RevenueRecState(TypedDict):
    """State that flows through the revenue recognition agent graph."""

    subscription_id: str
    obligations: list[dict]
    allocations: list[dict]
    schedule_entries: list[dict]
    journal_entries: list[dict]
    schedule_id: str | None
    error: str | None
    messages: list


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load_subscription(state: RevenueRecState) -> dict[str, Any]:
    """Load the subscription with plan and pricing rules from DB."""
    log.info(
        "revenue_agent.load_subscription",
        subscription_id=state["subscription_id"],
    )

    try:
        async for session in get_db():
            result = await session.execute(
                select(Subscription)
                .options(
                    selectinload(Subscription.plan),
                    selectinload(Subscription.customer),
                )
                .where(Subscription.id == state["subscription_id"])
            )
            subscription = result.scalar_one_or_none()

            if subscription is None:
                return {
                    "error": f"Subscription {state['subscription_id']} not found",
                }

            plan = subscription.plan
            if not plan or not plan.pricing_rules:
                return {
                    "error": f"Subscription {state['subscription_id']} has no pricing rules",
                }

            # Serialize pricing rules and subscription data into messages
            # for downstream nodes to consume
            rules_data: list[dict] = []
            for rule in plan.pricing_rules:
                rules_data.append({
                    "id": str(rule.id),
                    "pricing_model": rule.pricing_model.value
                    if hasattr(rule.pricing_model, "value")
                    else str(rule.pricing_model),
                    "metric": rule.metric,
                    "unit_amount": str(rule.unit_amount) if rule.unit_amount else None,
                    "flat_amount": str(rule.flat_amount) if rule.flat_amount else None,
                    "tiers": rule.tiers,
                    "outcome_rules": rule.outcome_rules,
                })

            return {
                "messages": [
                    {
                        "role": "system",
                        "content": f"Loaded subscription {state['subscription_id']} "
                        f"with plan '{plan.name}' and {len(rules_data)} pricing rules",
                        "data": {
                            "plan_name": plan.name,
                            "currency": getattr(plan, "currency", "EUR") or "EUR",
                            "pricing_rules": rules_data,
                            "start_date": subscription.current_period_start.date().isoformat(),
                            "end_date": subscription.current_period_end.date().isoformat(),
                        },
                    }
                ],
            }
    except Exception as exc:
        log.error("revenue_agent.load_subscription_error", error=str(exc))
        return {"error": f"Failed to load subscription: {exc}"}


async def identify_obligations_node(state: RevenueRecState) -> dict[str, Any]:
    """Identify performance obligations from the subscription's pricing rules."""
    if state.get("error"):
        return {}

    log.info(
        "revenue_agent.identify_obligations",
        subscription_id=state["subscription_id"],
    )

    try:
        # Extract data from the load_subscription message
        load_msg = _get_data_message(state)
        if load_msg is None:
            return {"error": "No subscription data available"}

        data = load_msg["data"]
        sub_id = uuid.UUID(state["subscription_id"])
        start_date = date.fromisoformat(data["start_date"])
        end_date = date.fromisoformat(data["end_date"])

        # Reconstruct PricingRule-like objects for identify_obligations
        from rupiv.models.plan import PricingModel, PricingRule

        rule_objects: list[PricingRule] = []
        for rd in data["pricing_rules"]:
            rule = PricingRule.__new__(PricingRule)
            object.__setattr__(rule, "id", uuid.UUID(rd["id"]))
            object.__setattr__(rule, "pricing_model", PricingModel(rd["pricing_model"]))
            object.__setattr__(rule, "metric", rd.get("metric"))
            object.__setattr__(
                rule,
                "unit_amount",
                Decimal(rd["unit_amount"]) if rd.get("unit_amount") else None,
            )
            object.__setattr__(
                rule,
                "flat_amount",
                Decimal(rd["flat_amount"]) if rd.get("flat_amount") else None,
            )
            object.__setattr__(rule, "tiers", rd.get("tiers"))
            object.__setattr__(rule, "outcome_rules", rd.get("outcome_rules"))
            rule_objects.append(rule)

        obligations = identify_obligations(
            subscription_id=sub_id,
            plan_name=data["plan_name"],
            pricing_rules=rule_objects,
            start_date=start_date,
            end_date=end_date,
        )

        serialized: list[dict] = [
            {
                "id": str(ob.id),
                "subscription_id": str(ob.subscription_id),
                "obligation_type": ob.obligation_type,
                "description": ob.description,
                "standalone_selling_price": str(ob.standalone_selling_price),
                "recognition_method": ob.recognition_method,
                "start_date": ob.start_date.isoformat(),
                "end_date": ob.end_date.isoformat() if ob.end_date else None,
            }
            for ob in obligations
        ]

        log.info(
            "revenue_agent.obligations_identified",
            count=len(serialized),
        )
        return {"obligations": serialized}

    except Exception as exc:
        log.error("revenue_agent.identify_obligations_error", error=str(exc))
        return {"error": f"Failed to identify obligations: {exc}"}


async def allocate_prices_node(state: RevenueRecState) -> dict[str, Any]:
    """Allocate transaction price to obligations by relative SSP."""
    if state.get("error"):
        return {}

    log.info(
        "revenue_agent.allocate_prices",
        subscription_id=state["subscription_id"],
        obligation_count=len(state.get("obligations", [])),
    )

    try:
        from rupiv.revenue_recognition.obligations import PerformanceObligation

        obligations_data = state.get("obligations", [])
        if not obligations_data:
            return {"error": "No obligations to allocate"}

        # Reconstruct PerformanceObligation dataclasses
        obligations = [
            PerformanceObligation(
                id=uuid.UUID(ob["id"]),
                subscription_id=uuid.UUID(ob["subscription_id"]),
                obligation_type=ob["obligation_type"],
                description=ob["description"],
                standalone_selling_price=Decimal(ob["standalone_selling_price"]),
                recognition_method=ob["recognition_method"],
                start_date=date.fromisoformat(ob["start_date"]),
                end_date=date.fromisoformat(ob["end_date"]) if ob.get("end_date") else None,
            )
            for ob in obligations_data
        ]

        total_price = sum(ob.standalone_selling_price for ob in obligations)
        allocations = allocate_transaction_price(
            total_price=total_price,
            obligations=obligations,
        )

        serialized: list[dict] = [
            {
                "obligation_id": str(a.obligation_id),
                "allocated_amount": str(a.allocated_amount),
                "allocation_pct": str(a.allocation_pct),
            }
            for a in allocations
        ]

        log.info(
            "revenue_agent.prices_allocated",
            count=len(serialized),
            total_price=str(total_price),
        )
        return {"allocations": serialized}

    except Exception as exc:
        log.error("revenue_agent.allocate_prices_error", error=str(exc))
        return {"error": f"Failed to allocate prices: {exc}"}


async def generate_schedules_node(state: RevenueRecState) -> dict[str, Any]:
    """Generate revenue schedule entries for each obligation."""
    if state.get("error"):
        return {}

    log.info(
        "revenue_agent.generate_schedules",
        subscription_id=state["subscription_id"],
    )

    try:
        from rupiv.revenue_recognition.obligations import PerformanceObligation

        obligations_data = state.get("obligations", [])
        allocations_data = state.get("allocations", [])

        # Build allocation lookup
        alloc_map: dict[str, Decimal] = {
            a["obligation_id"]: Decimal(a["allocated_amount"])
            for a in allocations_data
        }

        all_entries: list[dict] = []

        for ob_data in obligations_data:
            obligation = PerformanceObligation(
                id=uuid.UUID(ob_data["id"]),
                subscription_id=uuid.UUID(ob_data["subscription_id"]),
                obligation_type=ob_data["obligation_type"],
                description=ob_data["description"],
                standalone_selling_price=Decimal(ob_data["standalone_selling_price"]),
                recognition_method=ob_data["recognition_method"],
                start_date=date.fromisoformat(ob_data["start_date"]),
                end_date=date.fromisoformat(ob_data["end_date"])
                if ob_data.get("end_date")
                else None,
            )

            allocated = alloc_map.get(ob_data["id"], Decimal("0"))
            start = obligation.start_date
            end = obligation.end_date or start

            entries = generate_schedule(
                obligation=obligation,
                total_allocated=allocated,
                start=start,
                end=end,
            )

            for entry in entries:
                all_entries.append({
                    "obligation_id": str(entry.obligation_id),
                    "period": entry.period,
                    "method": entry.method,
                    "gross_amount": str(entry.gross_amount),
                    "recognized": str(entry.recognized),
                    "deferred": str(entry.deferred),
                    "gl_debit": entry.gl_debit,
                    "gl_credit": entry.gl_credit,
                })

        log.info(
            "revenue_agent.schedules_generated",
            entry_count=len(all_entries),
        )
        return {"schedule_entries": all_entries}

    except Exception as exc:
        log.error("revenue_agent.generate_schedules_error", error=str(exc))
        return {"error": f"Failed to generate schedules: {exc}"}


async def generate_journals_node(state: RevenueRecState) -> dict[str, Any]:
    """Generate GL journal entries from the schedule entries."""
    if state.get("error"):
        return {}

    log.info(
        "revenue_agent.generate_journals",
        subscription_id=state["subscription_id"],
    )

    try:
        from rupiv.revenue_recognition.schedules import RevenueScheduleEntry

        entries_data = state.get("schedule_entries", [])

        # Reconstruct RevenueScheduleEntry dataclasses
        schedule_entries = [
            RevenueScheduleEntry(
                period=e["period"],
                obligation_id=uuid.UUID(e["obligation_id"]),
                method=e["method"],
                gross_amount=Decimal(e["gross_amount"]),
                recognized=Decimal(e["recognized"]),
                deferred=Decimal(e["deferred"]),
                gl_debit=e["gl_debit"],
                gl_credit=e["gl_credit"],
            )
            for e in entries_data
        ]

        load_msg = _get_data_message(state)
        currency = "EUR"
        if load_msg and load_msg.get("data"):
            currency = load_msg["data"].get("currency", "EUR")

        journal_entries = generate_journal_entries(
            schedule_entries=schedule_entries,
            currency=currency,
        )

        serialized: list[dict] = [
            {
                "date": je.date.isoformat(),
                "debit_account": je.debit_account,
                "credit_account": je.credit_account,
                "amount": str(je.amount),
                "currency": je.currency,
                "description": je.description,
                "reference_type": je.reference_type,
                "reference_id": str(je.reference_id),
            }
            for je in journal_entries
        ]

        log.info(
            "revenue_agent.journals_generated",
            count=len(serialized),
        )
        return {"journal_entries": serialized}

    except Exception as exc:
        log.error("revenue_agent.generate_journals_error", error=str(exc))
        return {"error": f"Failed to generate journal entries: {exc}"}


async def persist_schedule(state: RevenueRecState) -> dict[str, Any]:
    """Save RevenueSchedule and RevenueEntry ORM objects to PostgreSQL."""
    if state.get("error"):
        return {}

    log.info(
        "revenue_agent.persist_schedule",
        subscription_id=state["subscription_id"],
    )

    try:
        load_msg = _get_data_message(state)
        currency = "EUR"
        if load_msg and load_msg.get("data"):
            currency = load_msg["data"].get("currency", "EUR")

        obligations_data = state.get("obligations", [])
        allocations_data = state.get("allocations", [])
        entries_data = state.get("schedule_entries", [])

        alloc_map: dict[str, Decimal] = {
            a["obligation_id"]: Decimal(a["allocated_amount"])
            for a in allocations_data
        }

        # Group entries by obligation_id
        entries_by_obligation: dict[str, list[dict]] = {}
        for entry in entries_data:
            ob_id = entry["obligation_id"]
            entries_by_obligation.setdefault(ob_id, []).append(entry)

        schedule_id: str | None = None

        async for session in get_db():
            for ob_data in obligations_data:
                ob_id = ob_data["id"]
                allocated = alloc_map.get(ob_id, Decimal("0"))
                ob_entries = entries_by_obligation.get(ob_id, [])

                total_recognized = sum(
                    Decimal(e["recognized"]) for e in ob_entries
                )
                total_deferred = allocated - total_recognized

                db_schedule = RevenueSchedule(
                    subscription_id=uuid.UUID(state["subscription_id"]),
                    obligation_type=ob_data["obligation_type"],
                    recognition_method=ob_data["recognition_method"],
                    total_amount=allocated,
                    recognized_amount=total_recognized,
                    deferred_amount=max(total_deferred, Decimal("0")),
                    currency=currency,
                    status=ScheduleStatus.ACTIVE,
                )
                session.add(db_schedule)
                await session.flush()

                # Track the first schedule ID for convenience
                if schedule_id is None:
                    schedule_id = str(db_schedule.id)

                for entry in ob_entries:
                    db_entry = RevenueEntry(
                        schedule_id=db_schedule.id,
                        period=entry["period"],
                        amount=Decimal(entry["recognized"]),
                        entry_type=EntryType.RECOGNIZED,
                        gl_debit=entry["gl_debit"],
                        gl_credit=entry["gl_credit"],
                        description=f"Revenue recognition — {entry['method']} — {entry['period']}",
                    )
                    session.add(db_entry)

                    if Decimal(entry["deferred"]) > 0:
                        db_deferred = RevenueEntry(
                            schedule_id=db_schedule.id,
                            period=entry["period"],
                            amount=Decimal(entry["deferred"]),
                            entry_type=EntryType.DEFERRED,
                            gl_debit=entry["gl_debit"],
                            gl_credit=entry["gl_credit"],
                            description=f"Deferred revenue — {entry['method']} — {entry['period']}",
                        )
                        session.add(db_deferred)

            log.info(
                "revenue_agent.schedule_persisted",
                schedule_id=schedule_id,
                subscription_id=state["subscription_id"],
            )

        return {
            "schedule_id": schedule_id,
            "messages": state.get("messages", [])
            + [
                {
                    "role": "system",
                    "content": f"Revenue schedule {schedule_id} persisted successfully",
                }
            ],
        }

    except Exception as exc:
        log.error("revenue_agent.persist_schedule_error", error=str(exc))
        return {"error": f"Failed to persist schedule: {exc}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_data_message(state: RevenueRecState) -> dict[str, Any] | None:
    """Extract the subscription data message from state messages."""
    for msg in state.get("messages", []):
        if isinstance(msg, dict) and msg.get("data"):
            return msg
    return None


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(RevenueRecState)

_builder.add_node("load_subscription", load_subscription)
_builder.add_node("identify_obligations", identify_obligations_node)
_builder.add_node("allocate_prices", allocate_prices_node)
_builder.add_node("generate_schedules", generate_schedules_node)
_builder.add_node("generate_journals", generate_journals_node)
_builder.add_node("persist_schedule", persist_schedule)

_builder.add_edge(START, "load_subscription")
_builder.add_edge("load_subscription", "identify_obligations")
_builder.add_edge("identify_obligations", "allocate_prices")
_builder.add_edge("allocate_prices", "generate_schedules")
_builder.add_edge("generate_schedules", "generate_journals")
_builder.add_edge("generate_journals", "persist_schedule")
_builder.add_edge("persist_schedule", END)

# Compile with MVP checkpointer
memory = MemorySaver()
revenue_graph = _builder.compile(checkpointer=memory)
"""Compiled revenue recognition agent graph — invoke with a ``RevenueRecState`` dict."""


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


async def generate_revenue_schedule(subscription_id: str) -> RevenueRecState:
    """Run the full IFRS 15 revenue recognition flow for a subscription.

    Args:
        subscription_id: The UUID (as string) of the subscription.

    Returns:
        The final ``RevenueRecState`` after the graph completes.
    """
    initial_state: RevenueRecState = {
        "subscription_id": subscription_id,
        "obligations": [],
        "allocations": [],
        "schedule_entries": [],
        "journal_entries": [],
        "schedule_id": None,
        "error": None,
        "messages": [],
    }

    config = {
        "configurable": {
            "thread_id": f"revenue-{subscription_id}-{uuid.uuid4().hex[:8]}",
        }
    }

    result = await revenue_graph.ainvoke(initial_state, config=config)
    log.info(
        "revenue_agent.complete",
        subscription_id=subscription_id,
        schedule_id=result.get("schedule_id"),
        error=result.get("error"),
    )
    return result
