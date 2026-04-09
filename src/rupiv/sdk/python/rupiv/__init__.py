"""Rupiv Python SDK -- outcome-based billing for modern software."""

from .client import AsyncClient, Client
from .events import EventBatcher
from .quotes import AsyncQuoteClient, QuoteClient
from .types import (
    AcceptResponse,
    CreditBalanceResponse,
    CustomerResponse,
    EntityResponse,
    EventResponse,
    InvoiceResponse,
    PlanResponse,
    QuoteLineItemResponse,
    QuoteResponse,
    RevenueScheduleResponse,
    RupivError,
    SimulationResult,
)

__all__ = [
    "AcceptResponse",
    "AsyncClient",
    "AsyncQuoteClient",
    "Client",
    "CreditBalanceResponse",
    "CustomerResponse",
    "EntityResponse",
    "EventBatcher",
    "EventResponse",
    "InvoiceResponse",
    "PlanResponse",
    "QuoteClient",
    "QuoteLineItemResponse",
    "QuoteResponse",
    "RevenueScheduleResponse",
    "RupivError",
    "SimulationResult",
    "track_event",
    "track_outcome",
]

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Module-level convenience helpers
# ---------------------------------------------------------------------------

_default_client: Client | None = None


def _get_default_client() -> Client:
    if _default_client is None:
        raise RuntimeError(
            "No default client configured. "
            "Call rupiv.init(api_key=...) or use rupiv.Client() directly."
        )
    return _default_client


def init(api_key: str, base_url: str = "https://api.rupiv.ai") -> None:
    """Initialise the module-level default client."""
    global _default_client
    if _default_client is not None:
        _default_client.close()
    _default_client = Client(api_key=api_key, base_url=base_url)


def track_event(
    metric: str,
    customer_id: str,
    properties: dict | None = None,
    idempotency_key: str | None = None,
) -> EventResponse:
    """Track a usage event using the default client."""
    return _get_default_client().track_event(
        metric=metric,
        customer_id=customer_id,
        properties=properties,
        idempotency_key=idempotency_key,
    )


def track_outcome(
    metric: str,
    customer_id: str,
    properties: dict | None = None,
    idempotency_key: str | None = None,
) -> EventResponse:
    """Track a business outcome using the default client."""
    return _get_default_client().track_outcome(
        metric=metric,
        customer_id=customer_id,
        properties=properties,
        idempotency_key=idempotency_key,
    )
