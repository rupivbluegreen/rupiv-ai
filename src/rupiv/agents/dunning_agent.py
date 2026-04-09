"""LangGraph dunning agent — payment retry with escalating delays.

Handles failed invoice payments by retrying with a configurable schedule
(default: 24h, 72h, 168h).  After all attempts are exhausted the invoice
is marked uncollectible.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from rupiv.billing.dunning import DEFAULT_RETRY_DELAYS_HOURS
from rupiv.billing.payment import MollieClient, PaymentResult, charge_invoice
from rupiv.config import get_settings
from rupiv.db import get_db
from rupiv.models.invoice import Invoice, InvoiceStatus

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


class DunningState(TypedDict):
    """State that flows through the dunning agent graph."""

    invoice_id: str
    attempt_number: int
    max_attempts: int
    retry_delays_hours: list[int]  # e.g. [24, 72, 168]
    last_payment_error: str | None
    final_status: str | None  # "paid" | "uncollectible"
    messages: list


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def load_invoice(state: DunningState) -> dict[str, Any]:
    """Load the invoice and check its current status.

    If the invoice is already paid or uncollectible, sets ``final_status``
    immediately to short-circuit the graph.
    """
    log.info(
        "dunning_agent.load_invoice",
        invoice_id=state["invoice_id"],
        attempt_number=state["attempt_number"],
    )

    try:
        async for session in get_db():
            result = await session.execute(
                select(Invoice).where(Invoice.id == state["invoice_id"]),
            )
            invoice = result.scalar_one_or_none()

            if invoice is None:
                return {
                    "final_status": "uncollectible",
                    "last_payment_error": f"Invoice {state['invoice_id']} not found",
                }

            if invoice.status == InvoiceStatus.PAID:
                log.info(
                    "dunning_agent.already_paid",
                    invoice_id=state["invoice_id"],
                )
                return {"final_status": "paid"}

            if invoice.status == InvoiceStatus.UNCOLLECTIBLE:
                log.info(
                    "dunning_agent.already_uncollectible",
                    invoice_id=state["invoice_id"],
                )
                return {"final_status": "uncollectible"}

            return {
                "messages": state.get("messages", [])
                + [
                    {
                        "role": "system",
                        "content": f"Invoice {state['invoice_id']} loaded "
                        f"(status={invoice.status.value}, total={invoice.total})",
                    },
                ],
            }

    except Exception as exc:
        log.error("dunning_agent.load_invoice_error", error=str(exc))
        return {
            "final_status": "uncollectible",
            "last_payment_error": f"Failed to load invoice: {exc}",
        }


async def attempt_payment(state: DunningState) -> dict[str, Any]:
    """Try to charge the invoice via Mollie.

    Records the outcome and increments the attempt counter.
    """
    if state.get("final_status"):
        return {}

    invoice_id = state["invoice_id"]
    attempt = state["attempt_number"]

    log.info(
        "dunning_agent.attempt_payment",
        invoice_id=invoice_id,
        attempt=attempt,
        max_attempts=state["max_attempts"],
    )

    try:
        settings = get_settings()
        if not settings.MOLLIE_API_KEY:
            return {
                "last_payment_error": "Mollie API key not configured",
                "attempt_number": attempt + 1,
            }

        mollie = MollieClient(api_key=settings.MOLLIE_API_KEY)
        try:
            async for session in get_db():
                result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
                invoice = result.scalar_one()

                webhook_base_url = "https://api.rupiv.ai"
                payment_result: PaymentResult = await charge_invoice(
                    mollie=mollie,
                    invoice=invoice,
                    webhook_base_url=webhook_base_url,
                )

                if payment_result.success:
                    log.info(
                        "dunning_agent.payment_succeeded",
                        invoice_id=invoice_id,
                        payment_id=payment_result.payment_id,
                        attempt=attempt,
                    )
                    return {
                        "final_status": "paid",
                        "attempt_number": attempt + 1,
                        "last_payment_error": None,
                    }
                log.warning(
                    "dunning_agent.payment_failed",
                    invoice_id=invoice_id,
                    error=payment_result.error,
                    attempt=attempt,
                )
                return {
                    "last_payment_error": payment_result.error,
                    "attempt_number": attempt + 1,
                }
        finally:
            await mollie.close()

    except Exception as exc:
        log.error("dunning_agent.attempt_payment_error", error=str(exc))
        return {
            "last_payment_error": str(exc),
            "attempt_number": attempt + 1,
        }


async def evaluate_result(state: DunningState) -> dict[str, Any]:
    """Decide the next step based on payment outcome.

    Routes to:
    - END if paid
    - ``schedule_retry`` if failed but attempts remain
    - ``mark_uncollectible`` if all attempts exhausted

    The actual routing is done by the conditional edge.
    """
    log.info(
        "dunning_agent.evaluate_result",
        invoice_id=state["invoice_id"],
        final_status=state.get("final_status"),
        attempt_number=state["attempt_number"],
        max_attempts=state["max_attempts"],
    )
    return {}


async def schedule_retry(state: DunningState) -> dict[str, Any]:
    """Log the next retry time.

    For MVP this sets a flag; real scheduling via BullMQ delayed jobs
    comes later.
    """
    attempt = state["attempt_number"]
    delays = state.get("retry_delays_hours", DEFAULT_RETRY_DELAYS_HOURS)

    # The delay for the *next* attempt (current attempt just finished)
    delay_index = min(attempt - 1, len(delays) - 1)
    next_delay_hours = delays[delay_index] if delay_index < len(delays) else delays[-1]

    log.info(
        "dunning_agent.schedule_retry",
        invoice_id=state["invoice_id"],
        attempt=attempt,
        next_retry_in_hours=next_delay_hours,
    )

    return {
        "messages": state.get("messages", [])
        + [
            {
                "role": "system",
                "content": f"Retry scheduled in {next_delay_hours}h "
                f"(attempt {attempt}/{state['max_attempts']})",
            },
        ],
    }


async def mark_uncollectible(state: DunningState) -> dict[str, Any]:
    """Mark the invoice as uncollectible after all retry attempts are exhausted."""
    invoice_id = state["invoice_id"]

    log.info(
        "dunning_agent.mark_uncollectible",
        invoice_id=invoice_id,
        attempts_made=state["attempt_number"],
    )

    try:
        async for session in get_db():
            result = await session.execute(select(Invoice).where(Invoice.id == invoice_id))
            invoice = result.scalar_one_or_none()
            if invoice:
                invoice.status = InvoiceStatus.UNCOLLECTIBLE
                log.info(
                    "dunning_agent.invoice_marked_uncollectible",
                    invoice_id=invoice_id,
                )

        return {"final_status": "uncollectible"}

    except Exception as exc:
        log.error("dunning_agent.mark_uncollectible_error", error=str(exc))
        return {"final_status": "uncollectible"}


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------


def _route_after_evaluate(
    state: DunningState,
) -> Literal["schedule_retry", "mark_uncollectible", "__end__"]:
    """Route based on payment result and remaining attempts."""
    if state.get("final_status") == "paid":
        return "__end__"

    if state["attempt_number"] >= state["max_attempts"]:
        return "mark_uncollectible"

    return "schedule_retry"


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_builder = StateGraph(DunningState)

_builder.add_node("load_invoice", load_invoice)
_builder.add_node("attempt_payment", attempt_payment)
_builder.add_node("evaluate_result", evaluate_result)
_builder.add_node("schedule_retry", schedule_retry)
_builder.add_node("mark_uncollectible", mark_uncollectible)

_builder.add_edge(START, "load_invoice")
_builder.add_edge("load_invoice", "attempt_payment")
_builder.add_edge("attempt_payment", "evaluate_result")
_builder.add_conditional_edges(
    "evaluate_result",
    _route_after_evaluate,
    {
        "__end__": END,
        "schedule_retry": "schedule_retry",
        "mark_uncollectible": "mark_uncollectible",
    },
)
_builder.add_edge("schedule_retry", END)
_builder.add_edge("mark_uncollectible", END)

# Compile with MVP checkpointer
memory = MemorySaver()
dunning_graph = _builder.compile(checkpointer=memory)
"""Compiled dunning agent graph — invoke with a ``DunningState`` dict."""


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


async def run_dunning_for_invoice(
    invoice_id: str,
    attempt_number: int = 0,
    retry_delays_hours: list[int] | None = None,
) -> DunningState:
    """Run the dunning agent for a single invoice.

    Args:
        invoice_id: The UUID (as string) of the invoice.
        attempt_number: The current attempt number (0-based).
        retry_delays_hours: Custom retry schedule, or ``None`` for defaults.

    Returns:
        The final ``DunningState`` after the graph completes.
    """
    import uuid as _uuid

    delays = retry_delays_hours or list(DEFAULT_RETRY_DELAYS_HOURS)

    initial_state: DunningState = {
        "invoice_id": invoice_id,
        "attempt_number": attempt_number,
        "max_attempts": len(delays),
        "retry_delays_hours": delays,
        "last_payment_error": None,
        "final_status": None,
        "messages": [],
    }

    config = {"configurable": {"thread_id": f"dunning-{invoice_id}-{_uuid.uuid4().hex[:8]}"}}

    result = await dunning_graph.ainvoke(initial_state, config=config)
    log.info(
        "dunning_agent.complete",
        invoice_id=invoice_id,
        final_status=result.get("final_status"),
        attempts=result.get("attempt_number"),
    )
    return result
