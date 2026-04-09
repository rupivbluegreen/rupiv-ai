# Rupiv Python SDK

Python SDK for [Rupiv.ai](https://rupiv.ai) outcome-based billing.

## Installation

```bash
pip install rupiv-sdk
```

## Quick Start

### Sync Client

```python
import rupiv

client = rupiv.Client(api_key="rp_live_xxx", base_url="https://api.rupiv.ai")

# Track a usage event
client.track_event(
    metric="api_call",
    customer_id="cust_123",
    properties={"tokens": 150},
)

# Track a business outcome
client.track_outcome(
    metric="ticket_resolved",
    customer_id="cust_123",
    properties={"resolution_time": 45, "csat_score": 4.8},
)

# Fetch a customer
customer = client.get_customer("cust_123")

# List invoices
invoices = client.list_invoices(customer_id="cust_123")

client.close()
```

Use as a context manager to close automatically:

```python
with rupiv.Client(api_key="rp_live_xxx") as client:
    client.track_event(metric="api_call", customer_id="cust_123")
```

### Async Client

```python
import asyncio
import rupiv

async def main():
    async with rupiv.AsyncClient(api_key="rp_live_xxx") as client:
        await client.track_event(
            metric="api_call",
            customer_id="cust_123",
            properties={"tokens": 150},
        )

        await client.track_outcome(
            metric="ticket_resolved",
            customer_id="cust_123",
            properties={"resolution_time": 45},
        )

asyncio.run(main())
```

### Module-Level Convenience

```python
import rupiv

rupiv.init(api_key="rp_live_xxx")

rupiv.track_event(metric="api_call", customer_id="cust_123")
rupiv.track_outcome(metric="ticket_resolved", customer_id="cust_123")
```

### High-Throughput Batching

```python
from rupiv import EventBatcher

batcher = EventBatcher(api_key="rp_live_xxx", max_batch_size=100, max_wait_seconds=5)

for request in incoming_requests:
    batcher.add("api_call", request.customer_id, "usage", {"tokens": request.tokens})

batcher.close()  # flushes remaining events
```

## Quotes

Create, send, and manage pricing quotes through the full quote-to-cash lifecycle.

```python
from rupiv import Client

client = Client(api_key="rp_live_xxx")

# Create a quote
quote = client.create_quote(
    customer_id="cust_123",
    plan_id="plan_abc",
    discount_pct=10.0,
    term_months=12,
)

# Send it to the customer
quote = client.send_quote(quote.id)

# List quotes filtered by status
drafts = client.list_quotes(status="draft")

# Accept a quote (creates subscription + revenue schedule)
result = client.accept_quote(quote.id)
print(result.subscription_id)
print(result.revenue_schedule_id)

# Reject a quote
rejected = client.reject_quote(quote.id, reason="Budget constraints")
```

### Standalone QuoteClient

For applications that only need quote operations:

```python
from rupiv import QuoteClient

with QuoteClient(api_key="rp_live_xxx") as qc:
    quote = qc.create_quote(customer_id="cust_123", plan_id="plan_abc")
    qc.send_quote(quote.id)
```

## Credits

Manage pre-purchased credit balances for credit-based billing.

```python
from rupiv import Client

client = Client(api_key="rp_live_xxx")

# Check a customer's credit balance
balance = client.get_credits("cust_123")
print(f"Available credits: {balance.balance}")

# Purchase credits
updated = client.purchase_credits(customer_id="cust_123", amount=10000)
print(f"New balance: {updated.balance}")
```

## Entities

Manage legal entities for multi-entity billing (BV, GmbH, SAS, Ltd).

```python
from rupiv import Client

client = Client(api_key="rp_live_xxx")

# List all entities
entities = client.list_entities()

# Create a new entity
entity = client.create_entity({
    "name": "AcmeAI GmbH",
    "legal_form": "GmbH",
    "country_code": "DE",
    "vat_id": "DE123456789",
    "currency": "eur",
})
print(f"Created entity: {entity.id}")
```

## Simulation

Run pricing simulations to forecast revenue impact of pricing changes.

```python
from rupiv import Client

client = Client(api_key="rp_live_xxx")

result = client.simulate_pricing(
    plan_id="plan_abc",
    scenario={
        "pricing_rules": [
            {
                "metric": "ticket_resolved",
                "price_per_outcome": 1.50,
                "billable_when": {"csat_score_gte": 4.0, "escalated": False},
            }
        ],
        "date_range": {"start": "2026-01-01", "end": "2026-03-31"},
    },
)
print(f"Projected revenue: {result.projected_revenue}")
print(f"Projected events: {result.projected_events}")
```

## Error Handling

```python
from rupiv import Client, RupivError

client = Client(api_key="rp_live_xxx")

try:
    client.track_event(metric="api_call", customer_id="cust_123")
except RupivError as e:
    print(e.status_code)  # HTTP status code
    print(e.message)      # Error message from the API
    print(e.request_id)   # Request ID for support
```
