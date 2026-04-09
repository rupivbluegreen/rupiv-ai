"""LangGraph quoting agent — generates quotes with policy evaluation.

Loads customer + plan context, evaluates policy rules, builds quotes via
the quote builder, and routes through approval gates before finalising.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.db import get_db
from rupiv.models.customer import Customer
from rupiv.models.plan import Plan
from rupiv.models.policy_rule import PolicyRule
from rupiv.policy.engine import PolicyEngine, PolicyRuleData
from rupiv.policy.rules import Condition
from rupiv.quoting.quote_builder import build_quote

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class QuotingState(TypedDict):
    """State that flows through the quoting agent graph."""

    customer_id: str
    plan_id: str
    discount_pct: str  # Decimal as string
    term_months: int
    overrides: dict
    quote_id: str | None
    policy_result: dict | None  # PolicyResult as dict
    requires_approval: bool
    approval_status: str | None  # "approved" | "pending" | "rejected"
    error: str | None
    messages: list


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _policy_rule_orm_to_data(rule: PolicyRule) -> PolicyRuleData:
    """Convert a PolicyRule ORM instance to a PolicyRuleData for evaluation."""
    conditions: list[Condition] = []
    raw_conditions = rule.conditions or []
    for c in raw_conditions:
        conditions.append(Condition(**c))

    return PolicyRuleData(
        name=rule.name,
        trigger=rule.trigger,
        conditions=conditions,
        action=rule.action,  # type: ignore[arg-type]
        approver=rule.approver,
        escalation_after_hours=rule.escalation_after_hours,
        priority=rule.priority,
    )


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load_context(state: QuotingState) -> dict[str, Any]:
    """Load customer and plan from the database, prepare context for policy evaluation."""
    log.info(
        "quoting_agent.load_context",
        customer_id=state["customer_id"],
        plan_id=state["plan_id"],
    )

    try:
        async for session in get_db():
            # Load customer
            result = await session.execute(
                select(Customer).where(Customer.id == state["customer_id"])
            )
            customer = result.scalar_one_or_none()
            if customer is None:
                return {"error": f"Customer {state['customer_id']} not found"}

            # Load plan
            result = await session.execute(
                select(Plan).where(Plan.id == state["plan_id"])
            )
            plan = result.scalar_one_or_none()
            if plan is None:
                return {"error": f"Plan {state['plan_id']} not found"}

            return {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"Loaded customer {customer.name} "
                            f"and plan {plan.name} for quoting"
                        ),
                    }
                ],
            }
    except Exception as exc:
        log.error("quoting_agent.load_context_error", error=str(exc))
        return {"error": f"Failed to load context: {exc}"}


async def check_policies(state: QuotingState) -> dict[str, Any]:
    """Load active PolicyRules for trigger='quote.created' and evaluate them.

    Sets ``requires_approval`` if any rule returns ``require_approval``.
    Sets ``approval_status`` to ``rejected`` if any rule rejects.
    """
    if state.get("error"):
        return {}

    log.info(
        "quoting_agent.check_policies",
        customer_id=state["customer_id"],
        discount_pct=state["discount_pct"],
    )

    try:
        async for session in get_db():
            # Load active policy rules for quote creation
            result = await session.execute(
                select(PolicyRule).where(
                    PolicyRule.trigger == "quote.created",
                    PolicyRule.is_active.is_(True),
                )
            )
            orm_rules = result.scalars().all()

            if not orm_rules:
                log.debug("quoting_agent.no_policy_rules")
                return {
                    "policy_result": {
                        "rule_name": "__default__",
                        "action": "allow",
                        "reason": "No matching rules — default pass-through",
                        "matched": False,
                    },
                    "requires_approval": False,
                    "approval_status": "approved",
                }

            # Build context for policy evaluation
            # Re-load customer and plan for context fields
            cust_result = await session.execute(
                select(Customer).where(Customer.id == state["customer_id"])
            )
            customer = cust_result.scalar_one()

            plan_result = await session.execute(
                select(Plan).where(Plan.id == state["plan_id"])
            )
            plan = plan_result.scalar_one()

            context: dict[str, Any] = {
                "quote": {
                    "discount_pct": state["discount_pct"],
                    "term_months": state["term_months"],
                },
                "customer": {
                    "id": str(customer.id),
                    "name": customer.name,
                    "country_code": customer.country_code,
                    "is_business": customer.is_business,
                },
                "plan": {
                    "id": str(plan.id),
                    "name": plan.name,
                    "currency": plan.currency,
                },
            }

            # Convert ORM rules to PolicyRuleData
            policy_rules = [_policy_rule_orm_to_data(r) for r in orm_rules]

            # Evaluate
            engine = PolicyEngine()
            policy_result = engine.evaluate(context=context, rules=policy_rules)

            result_dict: dict[str, Any] = {
                "rule_name": policy_result.rule_name,
                "action": policy_result.action,
                "approver": policy_result.approver,
                "reason": policy_result.reason,
                "matched": policy_result.matched,
            }

            requires_approval = policy_result.action == "require_approval"
            if policy_result.action == "reject":
                approval_status: str = "rejected"
            elif requires_approval:
                approval_status = "pending"
            else:
                approval_status = "approved"

            log.info(
                "quoting_agent.policy_evaluated",
                action=policy_result.action,
                rule_name=policy_result.rule_name,
                requires_approval=requires_approval,
                approval_status=approval_status,
            )

            return {
                "policy_result": result_dict,
                "requires_approval": requires_approval,
                "approval_status": approval_status,
            }

    except Exception as exc:
        log.error("quoting_agent.check_policies_error", error=str(exc))
        return {"error": f"Policy evaluation failed: {exc}"}


async def build_quote_node(state: QuotingState) -> dict[str, Any]:
    """Call quote_builder.build_quote() with the parameters from state.

    Skips if the policy rejected the quote.
    """
    if state.get("error"):
        return {}

    if state.get("approval_status") == "rejected":
        return {"error": "Quote rejected by policy — skipping build"}

    log.info(
        "quoting_agent.build_quote",
        customer_id=state["customer_id"],
        plan_id=state["plan_id"],
        discount_pct=state["discount_pct"],
        term_months=state["term_months"],
    )

    try:
        # Convert override values to Decimal
        overrides: dict[str, Decimal] = {}
        for key, value in (state.get("overrides") or {}).items():
            overrides[key] = Decimal(str(value))

        async for session in get_db():
            quote = await build_quote(
                session=session,
                customer_id=uuid.UUID(state["customer_id"]),
                plan_id=uuid.UUID(state["plan_id"]),
                overrides=overrides,
                discount_pct=Decimal(state["discount_pct"]),
                term_months=state["term_months"],
            )

            log.info(
                "quoting_agent.quote_built",
                quote_id=str(quote.id),
                estimated_monthly=str(quote.estimated_monthly),
                estimated_total=str(quote.estimated_total),
            )

            return {
                "quote_id": str(quote.id),
                "messages": state.get("messages", [])
                + [
                    {
                        "role": "system",
                        "content": (
                            f"Quote {quote.id} built — "
                            f"monthly: {quote.estimated_monthly}, "
                            f"total: {quote.estimated_total}"
                        ),
                    }
                ],
            }

    except Exception as exc:
        log.error("quoting_agent.build_quote_error", error=str(exc))
        return {"error": f"Failed to build quote: {exc}"}


async def finalize(state: QuotingState) -> dict[str, Any]:
    """Set quote status to 'draft' or 'sent' based on approval status."""
    if state.get("error"):
        return {}

    quote_id = state.get("quote_id")
    if not quote_id:
        return {"error": "No quote_id available for finalization"}

    approval_status = state.get("approval_status", "approved")

    log.info(
        "quoting_agent.finalize",
        quote_id=quote_id,
        approval_status=approval_status,
    )

    try:
        from rupiv.models.quote import Quote, QuoteStatus

        async for session in get_db():
            result = await session.execute(
                select(Quote).where(Quote.id == quote_id)
            )
            quote = result.scalar_one_or_none()
            if quote is None:
                return {"error": f"Quote {quote_id} not found for finalization"}

            if approval_status == "approved":
                quote.status = QuoteStatus.SENT
            else:
                quote.status = QuoteStatus.DRAFT

            await session.flush()

            log.info(
                "quoting_agent.finalized",
                quote_id=quote_id,
                status=quote.status.value,
            )

            return {
                "messages": state.get("messages", [])
                + [
                    {
                        "role": "system",
                        "content": f"Quote {quote_id} finalized as {quote.status.value}",
                    }
                ],
            }

    except Exception as exc:
        log.error("quoting_agent.finalize_error", error=str(exc))
        return {"error": f"Failed to finalize quote: {exc}"}


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------


def _route_approval(state: QuotingState) -> Literal["build_quote", "__end__"]:
    """Route based on policy evaluation result.

    - If rejected → END (error is already set by check_policies or build_quote)
    - If pending (requires_approval) → END (caller must await approval)
    - If approved / auto_approve / allow → proceed to build_quote
    """
    if state.get("error"):
        return "__end__"

    approval_status = state.get("approval_status")

    if approval_status == "rejected":
        return "__end__"

    if approval_status == "pending":
        # Requires approval — stop here, caller must handle
        return "__end__"

    # approved, auto_approve, allow — proceed
    return "build_quote"


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(QuotingState)

_builder.add_node("load_context", load_context)
_builder.add_node("check_policies", check_policies)
_builder.add_node("build_quote", build_quote_node)
_builder.add_node("finalize", finalize)

_builder.add_edge(START, "load_context")
_builder.add_edge("load_context", "check_policies")
_builder.add_conditional_edges(
    "check_policies",
    _route_approval,
    {"build_quote": "build_quote", "__end__": END},
)
_builder.add_edge("build_quote", "finalize")
_builder.add_edge("finalize", END)

# Compile with MVP checkpointer
memory = MemorySaver()
quoting_graph = _builder.compile(checkpointer=memory)
"""Compiled quoting agent graph — invoke with a ``QuotingState`` dict."""


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


async def generate_quote(
    customer_id: str,
    plan_id: str,
    discount_pct: str = "0",
    term_months: int = 12,
    overrides: dict | None = None,
) -> QuotingState:
    """Run the full quoting pipeline for a customer and plan.

    Args:
        customer_id: The UUID (as string) of the customer.
        plan_id: The UUID (as string) of the plan.
        discount_pct: Discount percentage as a string (e.g. ``"10"``).
        term_months: Contract term in months.
        overrides: Estimated quantities keyed by metric name.

    Returns:
        The final ``QuotingState`` after the graph completes.
    """
    import uuid as _uuid

    initial_state: QuotingState = {
        "customer_id": customer_id,
        "plan_id": plan_id,
        "discount_pct": discount_pct,
        "term_months": term_months,
        "overrides": overrides or {},
        "quote_id": None,
        "policy_result": None,
        "requires_approval": False,
        "approval_status": None,
        "error": None,
        "messages": [],
    }

    config = {
        "configurable": {
            "thread_id": f"quoting-{customer_id}-{_uuid.uuid4().hex[:8]}",
        }
    }

    result = await quoting_graph.ainvoke(initial_state, config=config)
    log.info(
        "quoting_agent.complete",
        customer_id=customer_id,
        plan_id=plan_id,
        quote_id=result.get("quote_id"),
        approval_status=result.get("approval_status"),
        requires_approval=result.get("requires_approval"),
        error=result.get("error"),
    )
    return result
