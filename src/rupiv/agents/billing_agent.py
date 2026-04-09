"""LangGraph billing agent — orchestrates the full billing cycle.

Metering -> pricing -> invoicing -> payment collection, modelled as a
LangGraph ``StateGraph`` with error handling and checkpointing support.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rupiv.billing.aggregation import aggregate_outcomes, aggregate_usage
from rupiv.billing.invoicing import generate_invoice
from rupiv.billing.payment import MollieClient, PaymentResult, charge_invoice
from rupiv.billing.pricing import PricingEngine, PricingModel
from rupiv.config import get_settings
from rupiv.db import get_db
from rupiv.models.invoice import Invoice, InvoiceStatus
from rupiv.models.subscription import Subscription

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class BillingState(TypedDict):
    """State that flows through the billing agent graph."""

    subscription_id: str
    customer_id: str
    period_start: str  # ISO datetime
    period_end: str
    pricing_rules: list[dict]
    aggregated_data: dict[str, dict]
    line_items: list[dict]
    invoice_id: str | None
    invoice_total: str | None  # Decimal as string
    payment_status: str | None  # "pending" | "paid" | "failed"
    error: str | None
    messages: list  # for LangGraph message tracking


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load_subscription(state: BillingState) -> dict[str, Any]:
    """Load the subscription, plan, pricing rules, and customer from the DB.

    Populates ``customer_id``, ``period_start``, ``period_end``, and
    ``pricing_rules`` on the state.
    """
    log.info("billing_agent.load_subscription", subscription_id=state["subscription_id"])

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

            rules: list[dict] = []
            for rule in subscription.plan.pricing_rules:
                rules.append({
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
                "customer_id": str(subscription.customer_id),
                "period_start": subscription.current_period_start.isoformat(),
                "period_end": subscription.current_period_end.isoformat(),
                "pricing_rules": rules,
                "messages": [
                    {
                        "role": "system",
                        "content": f"Loaded subscription {state['subscription_id']} "
                        f"with {len(rules)} pricing rules",
                    }
                ],
            }
    except Exception as exc:
        log.error("billing_agent.load_subscription_error", error=str(exc))
        return {"error": f"Failed to load subscription: {exc}"}


async def aggregate_usage_node(state: BillingState) -> dict[str, Any]:
    """Query ClickHouse for usage and outcome data per pricing rule.

    Populates ``aggregated_data`` keyed by metric name.
    """
    if state.get("error"):
        return {}

    log.info(
        "billing_agent.aggregate_usage",
        subscription_id=state["subscription_id"],
        rule_count=len(state.get("pricing_rules", [])),
    )

    try:
        from clickhouse_connect import get_async_client

        settings = get_settings()
        ch_client = await get_async_client(
            host=settings.CLICKHOUSE_URL.replace("http://", "").split(":")[0],
            port=int(settings.CLICKHOUSE_URL.split(":")[-1])
            if ":" in settings.CLICKHOUSE_URL.rsplit("//", 1)[-1]
            else 8123,
            database=settings.CLICKHOUSE_DATABASE,
        )

        from datetime import datetime

        period_start = datetime.fromisoformat(state["period_start"])
        period_end = datetime.fromisoformat(state["period_end"])

        aggregated: dict[str, dict] = {}

        for rule in state.get("pricing_rules", []):
            metric = rule.get("metric") or ""
            model_val = rule.get("pricing_model", "")

            if metric and metric in aggregated:
                continue

            if model_val in (PricingModel.USAGE.value, PricingModel.TIERED.value):
                qty = await aggregate_usage(
                    client=ch_client,
                    customer_id=state["customer_id"],
                    metric=metric,
                    period_start=period_start,
                    period_end=period_end,
                )
                aggregated[metric] = {"quantity": str(qty)}

            elif model_val == PricingModel.OUTCOME.value:
                outcomes = await aggregate_outcomes(
                    client=ch_client,
                    customer_id=state["customer_id"],
                    metric=metric,
                    period_start=period_start,
                    period_end=period_end,
                )
                aggregated[metric] = {"outcomes": outcomes}

            elif not metric:
                aggregated.setdefault("", {})

        log.info(
            "billing_agent.aggregation_complete",
            metrics=list(aggregated.keys()),
        )
        return {"aggregated_data": aggregated}

    except Exception as exc:
        log.error("billing_agent.aggregate_usage_error", error=str(exc))
        return {"error": f"Failed to aggregate usage: {exc}"}


async def calculate_pricing(state: BillingState) -> dict[str, Any]:
    """Run the PricingEngine on aggregated data to produce line items.

    Converts the serialized state back into objects compatible with
    ``PricingEngine.calculate_line_items``.
    """
    if state.get("error"):
        return {}

    log.info("billing_agent.calculate_pricing", subscription_id=state["subscription_id"])

    try:
        engine = PricingEngine()
        period_label = state["period_start"][:7]  # YYYY-MM

        # Reconstruct aggregated dict with Decimal values
        aggregated: dict[str, dict[str, Any]] = {}
        for metric, data in state.get("aggregated_data", {}).items():
            entry: dict[str, Any] = {}
            if "quantity" in data:
                entry["quantity"] = Decimal(str(data["quantity"]))
            if "outcomes" in data:
                entry["outcomes"] = data["outcomes"]
            aggregated[metric] = entry

        # Build lightweight rule-like objects for the pricing engine
        rule_objects = [_DictPricingRule(r) for r in state.get("pricing_rules", [])]

        line_items = engine.calculate_line_items(
            pricing_rules=rule_objects,
            aggregated=aggregated,
            period=period_label,
        )

        serialized_items: list[dict] = [
            {
                "description": item.description,
                "quantity": str(item.quantity),
                "unit_amount": str(item.unit_amount),
                "amount": str(item.amount),
                "metric": item.metric,
                "pricing_model": item.pricing_model.value,
            }
            for item in line_items
        ]

        log.info(
            "billing_agent.pricing_complete",
            line_item_count=len(serialized_items),
        )
        return {"line_items": serialized_items}

    except Exception as exc:
        log.error("billing_agent.calculate_pricing_error", error=str(exc))
        return {"error": f"Failed to calculate pricing: {exc}"}


async def generate_invoice_node(state: BillingState) -> dict[str, Any]:
    """Create an invoice with line items and EU VAT via the invoicing module.

    Persists the invoice to PostgreSQL and records the ``invoice_id`` and
    ``invoice_total`` on state.
    """
    if state.get("error"):
        return {}

    log.info(
        "billing_agent.generate_invoice",
        subscription_id=state["subscription_id"],
        line_item_count=len(state.get("line_items", [])),
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
            subscription = result.scalar_one()

            # Reconstruct LineItem objects for the invoicing module
            from rupiv.billing.pricing import LineItem

            line_items = [
                LineItem(
                    description=item["description"],
                    quantity=Decimal(item["quantity"]),
                    unit_amount=Decimal(item["unit_amount"]),
                    amount=Decimal(item["amount"]),
                    metric=item.get("metric"),
                    pricing_model=PricingModel(item["pricing_model"]),
                )
                for item in state.get("line_items", [])
            ]

            currency = getattr(subscription.plan, "currency", "EUR") or "EUR"
            invoice = await generate_invoice(
                session=session,
                subscription=subscription,
                line_items=line_items,
                currency=currency,
            )

            log.info(
                "billing_agent.invoice_generated",
                invoice_id=str(invoice.id),
                invoice_number=invoice.invoice_number,
                total=str(invoice.total),
            )

            return {
                "invoice_id": str(invoice.id),
                "invoice_total": str(invoice.total),
                "payment_status": "pending",
            }

    except Exception as exc:
        log.error("billing_agent.generate_invoice_error", error=str(exc))
        return {"error": f"Failed to generate invoice: {exc}"}


async def attempt_payment(state: BillingState) -> dict[str, Any]:
    """Charge the invoice via Mollie.

    Updates ``payment_status`` to ``"paid"`` or ``"failed"`` depending on
    the result from the payment provider.
    """
    if state.get("error"):
        return {}

    invoice_id = state.get("invoice_id")
    if not invoice_id:
        return {"error": "No invoice_id available for payment"}

    log.info(
        "billing_agent.attempt_payment",
        invoice_id=invoice_id,
        total=state.get("invoice_total"),
    )

    try:
        settings = get_settings()
        if not settings.MOLLIE_API_KEY:
            log.warning("billing_agent.mollie_key_missing")
            return {"error": "Mollie API key not configured"}

        mollie = MollieClient(api_key=settings.MOLLIE_API_KEY)
        try:
            async for session in get_db():
                result = await session.execute(
                    select(Invoice).where(Invoice.id == invoice_id)
                )
                invoice = result.scalar_one()

                webhook_base_url = "https://api.rupiv.ai"
                payment_result: PaymentResult = await charge_invoice(
                    mollie=mollie,
                    invoice=invoice,
                    webhook_base_url=webhook_base_url,
                )

                if payment_result.success:
                    invoice.status = InvoiceStatus.OPEN
                    log.info(
                        "billing_agent.payment_initiated",
                        invoice_id=invoice_id,
                        payment_id=payment_result.payment_id,
                    )
                    return {"payment_status": "paid"}
                else:
                    log.warning(
                        "billing_agent.payment_failed",
                        invoice_id=invoice_id,
                        error=payment_result.error,
                    )
                    return {"payment_status": "failed"}
        finally:
            await mollie.close()

    except Exception as exc:
        log.error("billing_agent.attempt_payment_error", error=str(exc))
        return {"payment_status": "failed", "error": f"Payment error: {exc}"}


async def handle_payment_result(state: BillingState) -> dict[str, Any]:
    """Inspect the payment status and prepare routing metadata.

    This is a pass-through node; the actual branching is handled by the
    conditional edge that follows it.
    """
    status = state.get("payment_status")
    log.info(
        "billing_agent.handle_payment_result",
        invoice_id=state.get("invoice_id"),
        payment_status=status,
    )
    return {
        "messages": state.get("messages", [])
        + [{"role": "system", "content": f"Payment result: {status}"}],
    }


async def run_dunning_node(state: BillingState) -> dict[str, Any]:
    """Trigger the dunning retry process for a failed payment.

    For the MVP this schedules the invoice for dunning; the actual retry
    is handled by the dedicated ``dunning_agent``.
    """
    invoice_id = state.get("invoice_id")
    log.info("billing_agent.run_dunning", invoice_id=invoice_id)

    try:
        async for session in get_db():
            result = await session.execute(
                select(Invoice).where(Invoice.id == invoice_id)
            )
            invoice = result.scalar_one_or_none()
            if invoice:
                invoice.status = InvoiceStatus.OPEN
                log.info(
                    "billing_agent.dunning_scheduled",
                    invoice_id=invoice_id,
                )

        return {
            "messages": state.get("messages", [])
            + [
                {
                    "role": "system",
                    "content": f"Invoice {invoice_id} scheduled for dunning",
                }
            ],
        }
    except Exception as exc:
        log.error("billing_agent.run_dunning_error", error=str(exc))
        return {"error": f"Dunning scheduling failed: {exc}"}


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------


def _route_after_payment(state: BillingState) -> Literal["run_dunning", "__end__"]:
    """Route to dunning on failure, or end on success / error."""
    if state.get("error"):
        return "__end__"
    if state.get("payment_status") == "failed":
        return "run_dunning"
    return "__end__"


# ---------------------------------------------------------------------------
# Helper: dict-backed pricing rule object
# ---------------------------------------------------------------------------


class _DictPricingRule:
    """Adapts a serialized dict to the ``PricingRuleLike`` protocol expected
    by the pricing engine."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def pricing_model(self) -> str:
        return self._data.get("pricing_model", "flat")

    @property
    def metric(self) -> str | None:
        return self._data.get("metric")

    @property
    def flat_amount(self) -> Decimal | None:
        v = self._data.get("flat_amount")
        return Decimal(v) if v is not None else None

    @property
    def unit_amount(self) -> Decimal | None:
        v = self._data.get("unit_amount")
        return Decimal(v) if v is not None else None

    @property
    def outcome_rules(self) -> dict[str, Any] | None:
        return self._data.get("outcome_rules")

    @property
    def tiers(self) -> list[dict[str, Any]] | None:
        return self._data.get("tiers")


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(BillingState)

_builder.add_node("load_subscription", load_subscription)
_builder.add_node("aggregate_usage", aggregate_usage_node)
_builder.add_node("calculate_pricing", calculate_pricing)
_builder.add_node("generate_invoice", generate_invoice_node)
_builder.add_node("attempt_payment", attempt_payment)
_builder.add_node("handle_payment_result", handle_payment_result)
_builder.add_node("run_dunning", run_dunning_node)

_builder.add_edge(START, "load_subscription")
_builder.add_edge("load_subscription", "aggregate_usage")
_builder.add_edge("aggregate_usage", "calculate_pricing")
_builder.add_edge("calculate_pricing", "generate_invoice")
_builder.add_edge("generate_invoice", "attempt_payment")
_builder.add_edge("attempt_payment", "handle_payment_result")
_builder.add_conditional_edges(
    "handle_payment_result",
    _route_after_payment,
    {"run_dunning": "run_dunning", "__end__": END},
)
_builder.add_edge("run_dunning", END)

# Compile with MVP checkpointer
memory = MemorySaver()
billing_graph = _builder.compile(checkpointer=memory)
"""Compiled billing agent graph — invoke with a ``BillingState`` dict."""


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


async def run_billing_for_subscription(subscription_id: str) -> BillingState:
    """Run the full billing cycle for a single subscription.

    Args:
        subscription_id: The UUID (as string) of the subscription to bill.

    Returns:
        The final ``BillingState`` after the graph completes.
    """
    import uuid as _uuid

    initial_state: BillingState = {
        "subscription_id": subscription_id,
        "customer_id": "",
        "period_start": "",
        "period_end": "",
        "pricing_rules": [],
        "aggregated_data": {},
        "line_items": [],
        "invoice_id": None,
        "invoice_total": None,
        "payment_status": None,
        "error": None,
        "messages": [],
    }

    config = {"configurable": {"thread_id": f"billing-{subscription_id}-{_uuid.uuid4().hex[:8]}"}}

    result = await billing_graph.ainvoke(initial_state, config=config)
    log.info(
        "billing_agent.complete",
        subscription_id=subscription_id,
        invoice_id=result.get("invoice_id"),
        payment_status=result.get("payment_status"),
        error=result.get("error"),
    )
    return result
