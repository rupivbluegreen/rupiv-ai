"""LangGraph outcome validation agent.

Validates whether an outcome event is genuinely billable by checking it
against the ``billable_when`` conditions defined in the pricing rule's
``outcome_rules`` JSONB column.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from rupiv.db import get_db
from rupiv.models.event import Event, EventType, OutcomeStatus
from rupiv.models.subscription import Subscription

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class OutcomeValidationState(TypedDict):
    """State that flows through the outcome validation graph."""

    event_id: str
    customer_id: str
    metric: str
    properties: dict
    pricing_rule: dict  # outcome_rules from the pricing rule
    validation_result: str | None  # "validated" | "rejected"
    rejection_reason: str | None
    messages: list


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load_event(state: OutcomeValidationState) -> dict[str, Any]:
    """Load the event and its subscription's outcome pricing rules from the DB.

    Populates ``customer_id``, ``metric``, ``properties``, and
    ``pricing_rule`` on the state.
    """
    log.info("outcome_agent.load_event", event_id=state["event_id"])

    try:
        async for session in get_db():
            result = await session.execute(select(Event).where(Event.id == state["event_id"]))
            event = result.scalar_one_or_none()

            if event is None:
                return {"error": f"Event {state['event_id']} not found"}

            if event.event_type != EventType.OUTCOME:
                return {
                    "validation_result": "rejected",
                    "rejection_reason": f"Event is not an outcome event (type={event.event_type.value})",
                }

            # Find the subscription and its outcome pricing rules
            pricing_rule_data: dict[str, Any] = {}
            if event.subscription_id:
                sub_result = await session.execute(
                    select(Subscription)
                    .options(selectinload(Subscription.plan))
                    .where(Subscription.id == event.subscription_id),
                )
                subscription = sub_result.scalar_one_or_none()

                if subscription and subscription.plan:
                    for rule in subscription.plan.pricing_rules:
                        model_val = rule.pricing_model
                        if hasattr(model_val, "value"):
                            model_val = model_val.value
                        if model_val == "outcome" and rule.metric == event.metric:
                            pricing_rule_data = rule.outcome_rules or {}
                            break

            log.info(
                "outcome_agent.event_loaded",
                event_id=state["event_id"],
                metric=event.metric,
                has_pricing_rule=bool(pricing_rule_data),
            )

            return {
                "customer_id": str(event.customer_id),
                "metric": event.metric,
                "properties": event.properties or {},
                "pricing_rule": pricing_rule_data,
                "messages": [
                    {
                        "role": "system",
                        "content": f"Loaded event {state['event_id']} (metric={event.metric})",
                    },
                ],
            }

    except Exception as exc:
        log.error("outcome_agent.load_event_error", error=str(exc))
        return {
            "validation_result": "rejected",
            "rejection_reason": f"Failed to load event: {exc}",
        }


async def check_rules(state: OutcomeValidationState) -> dict[str, Any]:
    """Apply ``billable_when`` conditions from the outcome pricing rules.

    Each condition key in ``billable_when`` is matched against the event's
    ``properties``.  Supports exact equality, ``_lt`` (less than),
    ``_lte`` (less than or equal), ``_gt`` (greater than),
    ``_gte`` (greater than or equal) suffixed conditions.
    """
    if state.get("validation_result"):
        # Already decided (e.g. rejected at load time)
        return {}

    pricing_rule = state.get("pricing_rule", {})
    billable_when: dict[str, Any] = pricing_rule.get("billable_when", {})
    properties = state.get("properties", {})

    log.info(
        "outcome_agent.check_rules",
        event_id=state["event_id"],
        condition_count=len(billable_when),
    )

    if not billable_when:
        # No conditions defined — all outcomes are billable
        log.info("outcome_agent.no_conditions", event_id=state["event_id"])
        return {
            "validation_result": "validated",
            "rejection_reason": None,
        }

    failed_conditions: list[str] = []

    for condition_key, expected_value in billable_when.items():
        # Parse suffixed comparison operators
        if condition_key.endswith("_lt"):
            prop_key = condition_key[:-3]
            prop_val = properties.get(prop_key)
            if prop_val is None or not (float(prop_val) < float(expected_value)):
                failed_conditions.append(f"{prop_key} ({prop_val}) is not < {expected_value}")

        elif condition_key.endswith("_lte"):
            prop_key = condition_key[:-4]
            prop_val = properties.get(prop_key)
            if prop_val is None or not (float(prop_val) <= float(expected_value)):
                failed_conditions.append(f"{prop_key} ({prop_val}) is not <= {expected_value}")

        elif condition_key.endswith("_gt"):
            prop_key = condition_key[:-3]
            prop_val = properties.get(prop_key)
            if prop_val is None or not (float(prop_val) > float(expected_value)):
                failed_conditions.append(f"{prop_key} ({prop_val}) is not > {expected_value}")

        elif condition_key.endswith("_gte"):
            prop_key = condition_key[:-4]
            prop_val = properties.get(prop_key)
            if prop_val is None or not (float(prop_val) >= float(expected_value)):
                failed_conditions.append(f"{prop_key} ({prop_val}) is not >= {expected_value}")

        else:
            # Exact match
            prop_val = properties.get(condition_key)
            if prop_val != expected_value:
                failed_conditions.append(
                    f"{condition_key}: expected {expected_value!r}, got {prop_val!r}",
                )

    if failed_conditions:
        reason = "; ".join(failed_conditions)
        log.info(
            "outcome_agent.conditions_failed",
            event_id=state["event_id"],
            failures=failed_conditions,
        )
        return {
            "validation_result": "rejected",
            "rejection_reason": reason,
        }

    log.info("outcome_agent.conditions_passed", event_id=state["event_id"])
    return {
        "validation_result": "validated",
        "rejection_reason": None,
    }


async def decide(state: OutcomeValidationState) -> dict[str, Any]:
    """Conditional node that logs the decision.

    The actual routing is handled by the conditional edges that follow.
    """
    result = state.get("validation_result", "rejected")
    log.info(
        "outcome_agent.decide",
        event_id=state["event_id"],
        result=result,
        rejection_reason=state.get("rejection_reason"),
    )
    return {
        "messages": state.get("messages", [])
        + [
            {
                "role": "system",
                "content": f"Outcome decision: {result}"
                + (f" — {state.get('rejection_reason')}" if state.get("rejection_reason") else ""),
            },
        ],
    }


async def update_status(state: OutcomeValidationState) -> dict[str, Any]:
    """Update ``event.outcome_status`` in PostgreSQL.

    Sets the status to ``validated`` or ``rejected`` depending on the
    validation result.
    """
    result = state.get("validation_result", "rejected")
    event_id = state["event_id"]

    log.info(
        "outcome_agent.update_status",
        event_id=event_id,
        status=result,
    )

    try:
        async for session in get_db():
            db_result = await session.execute(select(Event).where(Event.id == event_id))
            event = db_result.scalar_one_or_none()

            if event is not None:
                if result == "validated":
                    event.outcome_status = OutcomeStatus.VALIDATED
                else:
                    event.outcome_status = OutcomeStatus.REJECTED

                log.info(
                    "outcome_agent.status_updated",
                    event_id=event_id,
                    outcome_status=event.outcome_status.value,
                )

        return {
            "messages": state.get("messages", [])
            + [
                {
                    "role": "system",
                    "content": f"Event {event_id} status updated to {result}",
                },
            ],
        }

    except Exception as exc:
        log.error("outcome_agent.update_status_error", event_id=event_id, error=str(exc))
        return {}


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------


def _route_after_decide(
    state: OutcomeValidationState,
) -> Literal["update_status"]:
    """Always route to update_status — both validated and rejected events
    need their status persisted."""
    return "update_status"


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(OutcomeValidationState)

_builder.add_node("load_event", load_event)
_builder.add_node("check_rules", check_rules)
_builder.add_node("decide", decide)
_builder.add_node("update_status", update_status)

_builder.add_edge(START, "load_event")
_builder.add_edge("load_event", "check_rules")
_builder.add_edge("check_rules", "decide")
_builder.add_conditional_edges(
    "decide",
    _route_after_decide,
    {"update_status": "update_status"},
)
_builder.add_edge("update_status", END)

# Compile with MVP checkpointer
memory = MemorySaver()
outcome_graph = _builder.compile(checkpointer=memory)
"""Compiled outcome validation graph — invoke with an ``OutcomeValidationState`` dict."""


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


async def validate_outcome(event_id: str) -> OutcomeValidationState:
    """Validate a single outcome event.

    Args:
        event_id: The UUID (as string) of the outcome event to validate.

    Returns:
        The final ``OutcomeValidationState`` after the graph completes.
    """
    import uuid as _uuid

    initial_state: OutcomeValidationState = {
        "event_id": event_id,
        "customer_id": "",
        "metric": "",
        "properties": {},
        "pricing_rule": {},
        "validation_result": None,
        "rejection_reason": None,
        "messages": [],
    }

    config = {"configurable": {"thread_id": f"outcome-{event_id}-{_uuid.uuid4().hex[:8]}"}}

    result = await outcome_graph.ainvoke(initial_state, config=config)
    log.info(
        "outcome_agent.complete",
        event_id=event_id,
        validation_result=result.get("validation_result"),
        rejection_reason=result.get("rejection_reason"),
    )
    return result
