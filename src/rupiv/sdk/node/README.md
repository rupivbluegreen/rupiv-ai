# @rupiv/sdk

Node.js / TypeScript SDK for [Rupiv.ai](https://rupiv.ai) outcome-based billing.

## Installation

```bash
npm install @rupiv/sdk
```

Requires Node.js 18+ (uses built-in `fetch`).

## Quick Start

```ts
import { RupivClient } from "@rupiv/sdk";

const client = new RupivClient({ apiKey: "rp_live_xxx" });

// Track a usage event
await client.trackEvent({
  metric: "api_call",
  customerId: "cust_123",
  properties: { tokens: 150 },
});

// Track a business outcome
await client.trackOutcome({
  metric: "ticket_resolved",
  customerId: "cust_123",
  properties: { resolution_time: 45, csat_score: 4.8 },
});

// Fetch a customer
const customer = await client.getCustomer("cust_123");

// List invoices
const invoices = await client.listInvoices({ customerId: "cust_123" });

// Create a quote
const quote = await client.createQuote({
  customerId: "cust_123",
  planId: "plan_pro",
});

// Get credit balance
const balance = await client.getBalance("cust_123");
```

## High-Throughput Batching

For high-volume event ingestion, use the `EventBatcher` which buffers events
in memory and flushes them in batches:

```ts
import { EventBatcher } from "@rupiv/sdk";

const batcher = new EventBatcher({
  apiKey: "rp_live_xxx",
  maxBatchSize: 100,  // flush when buffer hits 100 events
  maxWaitMs: 5000,    // or flush every 5 seconds
});

// Add events — they are buffered and sent in batches
batcher.addEvent({
  metric: "api_call",
  customerId: "cust_123",
  properties: { tokens: 150 },
});

batcher.addOutcome({
  metric: "ticket_resolved",
  customerId: "cust_123",
  properties: { resolution_time: 45 },
});

// Flush remaining events and stop the timer when done
await batcher.close();
```

## Error Handling

```ts
import { RupivClient, RupivError } from "@rupiv/sdk";

const client = new RupivClient({ apiKey: "rp_live_xxx" });

try {
  await client.trackEvent({ metric: "api_call", customerId: "cust_123" });
} catch (err) {
  if (err instanceof RupivError) {
    console.error(err.statusCode);  // HTTP status code
    console.error(err.message);     // Error message from the API
    console.error(err.requestId);   // Request ID for support
  }
}
```

## Configuration

```ts
const client = new RupivClient({
  apiKey: "rp_live_xxx",           // required
  baseUrl: "https://api.rupiv.ai", // optional, defaults to production
  timeoutMs: 30000,                // optional, request timeout in ms
  maxRetries: 3,                   // optional, retries for 5xx / network errors
});
```

## TypeScript Types

All request and response types are fully typed and exported:

```ts
import type {
  TrackEventParams,
  TrackOutcomeParams,
  CreateQuoteParams,
  EventResponse,
  Customer,
  Invoice,
  Quote,
  CreditBalance,
  Plan,
} from "@rupiv/sdk";
```
