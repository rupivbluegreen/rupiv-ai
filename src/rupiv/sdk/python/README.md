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
