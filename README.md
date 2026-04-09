<p align="center">
  <h1 align="center">Rupiv.ai</h1>
  <p align="center">
    <strong>Outcome-based billing infrastructure for AI companies selling into Europe.</strong>
  </p>
  <p align="center">
    EU VAT &middot; IFRS 15 &middot; GDPR &middot; Agent-native &middot; Developer-first
  </p>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> &middot;
  <a href="#features">Features</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#api-reference">API Reference</a> &middot;
  <a href="#sdks">SDKs</a> &middot;
  <a href="#deployment">Deployment</a>
</p>

---

## The Problem

AI agents are replacing human work. Per-seat billing is dying. **61% of SaaS companies** will use hybrid pricing models by 2026, but no billing platform natively supports outcome-based pricing, EU VAT across 27 member states, or IFRS 15 revenue recognition for variable fees.

Stripe has no concept of an "outcome." Chargebee tracks subscriptions. Zuora is enterprise legacy.

## The Solution

Rupiv.ai lets you charge for **results delivered** -- tickets resolved, fraud prevented, tasks completed -- not seats or API calls. It handles the full billing lifecycle from event ingestion to payment collection, with EU compliance baked in.

```python
import rupiv

client = rupiv.Client(api_key="rp_live_xxxxx")

# Track an outcome event
client.track_outcome(
    metric="ticket_resolved",
    customer_id="cust_abc123",
    properties={
        "resolution_time": 45,
        "csat_score": 4.8,
        "escalated": False,
    },
)
```

At billing period end, Rupiv.ai validates the outcome against your pricing rules, calculates the charge, applies EU VAT, generates the invoice, collects payment via Mollie/Stripe, and creates the IFRS 15 revenue schedule. Automatically.

---

## Features

### Billing Engine

| Model | Description | Example |
|---|---|---|
| **Outcome-based** | Charge per successful result | EUR 0.99/resolved ticket |
| **Usage-based** | Charge per consumption unit | EUR 0.001/API call |
| **Hybrid** | Base subscription + variable | EUR 99/mo + EUR 0.50/resolution |
| **Tiered** | Volume brackets | 0-1K: EUR 0.01, 1K-10K: EUR 0.008 |
| **Credit-based** | Pre-purchased credits | 10,000 credits for EUR 500 |
| **Flat** | Fixed recurring | EUR 49/mo |

All six models can be combined on a single plan.

### Outcome Validation

Outcomes are validated before billing. Define rules to prevent gaming:

```json
{
  "metric": "ticket_resolved",
  "billable_when": {
    "escalated": false,
    "resolution_time_lt": 300,
    "csat_score_gte": 3.0
  },
  "price_per_outcome": 0.99,
  "cap_per_period": 50000
}
```

### EU Tax Compliance

- **27 EU member state VAT rates** with automatic rate selection
- **B2B reverse charge** for cross-border intra-EU transactions
- **VIES validation** for EU VAT ID verification (async, cached)
- **One-Stop Shop (OSS)** for cross-border B2C with EUR 10K threshold
- **ViDA-ready** for 2028 real-time digital reporting mandate

### IFRS 15 Revenue Recognition

- Performance obligation identification (platform access, outcome delivery, usage)
- Transaction price allocation by standalone selling prices
- Revenue schedules: over-time for subscriptions, point-in-time for outcomes
- Variable consideration estimation using expected value method
- GL journal entry generation for accounting export

### Pricing Studio

- **What-if simulation**: replay historical events against new pricing rules
- **A/B test pricing**: deterministic customer assignment with conversion tracking
- **Revenue forecasting**: Monte Carlo projection with P10/P50/P90 bands
- **Pre-built templates**: Support AI, API Platform, Hybrid SaaS, Credit Pack

### Policy Engine

Declarative business rules for billing governance:

```yaml
rules:
  - name: "Auto-approve small invoices"
    trigger: "invoice.generated"
    conditions:
      - field: "invoice.total"
        operator: "lt"
        value: 5000
    action: "auto_approve"

  - name: "CFO approval for large invoices"
    trigger: "invoice.generated"
    conditions:
      - field: "invoice.total"
        operator: "gte"
        value: 50000
    action: "require_approval"
    approver: "cfo"
```

### Multi-Entity

```
AcmeAI Corp
  |-- AcmeAI BV (NL) -- Holding, EUR
  |-- AcmeAI GmbH (DE) -- Subsidiary, EUR
  +-- AcmeAI Ltd (UK) -- Subsidiary, GBP
```

Multi-currency with ECB daily rates. Intercompany billing with transfer pricing.

### Agent-to-Agent Payments

SEPA-native fiat rails for autonomous AI agent transactions via Adyen. Double-entry ledger with reserve-then-settle pattern.

### Payment Integrations

| PSP | Region | Methods |
|---|---|---|
| **Mollie** | EU (primary) | iDEAL, SEPA DD, cards, Bancontact |
| **Stripe** | US expansion | Cards, ACH |
| **Adyen** | A2A SEPA | SEPA credit transfer |

Intelligent payment routing selects the cheapest PSP per transaction.

---

## Architecture

```
                    QUOTE-TO-CASH LIFECYCLE

  QUOTE -----> CONTRACT -----> USAGE -----> INVOICE
    |              |              |              |
  quoting      contract       metering      invoicing
  agent        terms, SLA     events to     line items,
                              ClickHouse    EU VAT
    |              |              |              |
    v              v              v              v
  SIMULATE     POLICY        VALIDATE        PAY
    |              |              |              |
  pricing      approval       outcome       Mollie/
  studio       gates          agent         Stripe
                                                |
                                                v
                                            REVENUE REC
                                                |
                                            IFRS 15
                                            schedules
```

### Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+, async-first |
| Framework | FastAPI (REST + WebSocket) |
| Agent Runtime | LangGraph (7 stateful agents) |
| Database | PostgreSQL 16 |
| Analytics | ClickHouse |
| Queue | Redis 7 |
| Frontend | React 18 + Vite + Tailwind |
| ORM | SQLAlchemy 2.0 (async) |
| Payments | Mollie, Stripe, Adyen |

---

## Quickstart

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Node.js 20+ (for dashboard)

### 1. Clone and setup

```bash
git clone https://github.com/rupivbluegreen/rupiv.ai.git
cd rupiv.ai

# Create virtual environment and install dependencies
uv venv .venv --python 3.12
uv pip install -e "."
uv pip install ruff pyright pytest pytest-asyncio pytest-cov factory-boy faker

# Copy environment config
cp .env.example .env
```

### 2. Start infrastructure

```bash
# Start PostgreSQL, Redis, ClickHouse
docker compose up postgres redis clickhouse -d

# Run database migrations
make migrate

# Seed demo data (5 customers, 4 plans, ~200 events, invoices)
make seed
```

### 3. Run the API

```bash
make dev
# API available at http://localhost:8000
# OpenAPI docs at http://localhost:8000/docs
# ReDoc at http://localhost:8000/redoc
```

### 4. Run the dashboard

```bash
cd dashboard
npm install
npm run dev
# Dashboard at http://localhost:5173
```

### 5. Run tests

```bash
make test
# 306 tests passing
```

---

## API Reference

Base URL: `http://localhost:8000/v1`

### Events

```bash
# Track an outcome event
curl -X POST http://localhost:8000/v1/events \
  -H "X-API-Key: rp_live_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "outcome",
    "metric": "ticket_resolved",
    "customer_id": "550e8400-e29b-41d4-a716-446655440000",
    "properties": {
      "resolution_time": 45,
      "csat_score": 4.8,
      "escalated": false
    },
    "idempotency_key": "evt-unique-key-001"
  }'
```

### Core Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/v1/events` | Ingest usage/outcome events |
| GET/POST | `/v1/customers` | Customer management |
| GET/POST | `/v1/plans` | Plan and pricing rule CRUD |
| GET/POST | `/v1/subscriptions` | Subscription lifecycle |
| GET | `/v1/invoices` | Invoice listing and details |
| POST | `/v1/quotes` | Generate and manage quotes |
| GET | `/v1/revenue/schedules` | IFRS 15 revenue schedules |
| POST | `/v1/simulate` | Pricing simulation |
| GET | `/v1/analytics/mrr` | MRR/ARR metrics |
| POST | `/v1/a2a/intent` | Agent-to-agent payments |
| GET | `/v1/credits/{id}/balance` | Credit balance |
| POST | `/v1/onboarding/signup` | Self-serve signup |

Full interactive documentation available at `/docs` when the API is running.

---

## SDKs

### Python

```bash
pip install rupiv-sdk
```

```python
import rupiv

client = rupiv.Client(api_key="rp_live_xxxxx")

# Track events
client.track_outcome("ticket_resolved", "cust_123", properties={"csat_score": 4.8})
client.track_event("api_call", "cust_123", properties={"tokens": 150})

# Quotes
quote = client.create_quote("cust_123", "plan_456", discount_pct=10, term_months=12)
client.accept_quote(quote.id)

# Credits
balance = client.get_credits("cust_123")
```

### Node.js / TypeScript

```bash
npm install @rupiv/sdk
```

```typescript
import { RupivClient } from '@rupiv/sdk';

const client = new RupivClient({ apiKey: 'rp_live_xxxxx' });

await client.trackOutcome({
  metric: 'ticket_resolved',
  customerId: 'cust_123',
  properties: { csatScore: 4.8 },
});

// High-throughput batching
import { EventBatcher } from '@rupiv/sdk';

const batcher = new EventBatcher({ apiKey: 'rp_live_xxxxx' });
batcher.addOutcome('ticket_resolved', 'cust_123', { csatScore: 4.8 });
// Auto-flushes at 100 events or 5 seconds
```

### Go

```bash
go get github.com/rupiv/rupiv-go
```

```go
client := rupiv.NewClient("rp_live_xxxxx")

resp, err := client.TrackOutcome(ctx, rupiv.TrackOutcomeParams{
    Metric:     "ticket_resolved",
    CustomerID: "cust_123",
    Properties: map[string]interface{}{"csat_score": 4.8},
})
```

---

## Dashboard

The React dashboard provides 12 pages for managing billing operations:

| Page | Description |
|---|---|
| **Overview** | MRR, ARR, outcome metrics, quick actions |
| **Customers** | Customer account management |
| **Entities** | Legal entity hierarchy with tree view |
| **Plans** | Visual plan builder with pricing rules |
| **Pricing Studio** | What-if simulation, forecasting, templates |
| **Quotes** | Quote pipeline (draft / sent / accepted / rejected) |
| **Events** | Real-time event stream with WebSocket |
| **Invoices** | Invoice lifecycle with status filtering |
| **Revenue** | IFRS 15 schedules, journal entries, waterfall chart |
| **Policies** | Policy rule builder with outcome validator |
| **Payment Analytics** | PSP cost comparison, routing recommendations |
| **Onboarding** | Self-serve signup wizard |

---

## Project Structure

```
rupiv.ai/
  src/rupiv/
    api/v1/          18 endpoint modules
    agents/           7 LangGraph agents
    billing/         11 billing engine modules
    tax/              6 EU VAT modules
    policy/           5 policy engine modules
    entities/         5 multi-entity modules
    revenue_recognition/  6 IFRS 15 modules
    pricing_studio/   5 simulation modules
    quoting/          4 quote-to-cash modules
    analytics/        6 business analytics modules
    compliance/       3 audit + GDPR modules
    models/          15 SQLAlchemy models
    workers/          7 background workers
    sdk/              Python, Node.js, Go SDKs
  dashboard/         12 pages, 10 components
  tests/             35 test files, 306 tests
  migrations/         9 Alembic migrations
```

---

## Deployment

### Docker

```bash
# Build and run all services
docker compose up --build

# Services:
# - app: FastAPI API on port 8000
# - worker: BullMQ event processor
# - postgres: PostgreSQL 16 on port 5432
# - redis: Redis 7 on port 6379
# - clickhouse: ClickHouse on ports 8123/9000
```

### Render (Production)

The project includes a `render.yaml` blueprint for one-click deployment to Render's Frankfurt region:

```bash
make deploy
```

### Environment Variables

See `.env.example` for all configuration options. Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `CLICKHOUSE_URL` | ClickHouse HTTP endpoint |
| `MOLLIE_API_KEY` | Mollie payment API key |
| `STRIPE_API_KEY` | Stripe API key (US payments) |
| `ADYEN_API_KEY` | Adyen API key (A2A SEPA) |
| `APP_SECRET_KEY` | Application secret for JWT signing |

---

## Development

```bash
make dev            # Start all services + hot reload
make test           # Run 306 tests
make lint           # ruff check + format check
make format         # Auto-format code
make migrate        # Run database migrations
make seed           # Load demo data
make seed-simulate  # Demo data + pricing simulation
make vat-update     # Refresh EU VAT rates
make docker-build   # Build production Docker image
```

### CI/CD

GitHub Actions runs on every push:
1. **Lint** -- ruff check + format
2. **Test** -- pytest with coverage
3. **Frontend** -- TypeScript check + Vite build
4. **Docker** -- Build image + health check

---

## Competitive Landscape

|  | Outcome Billing | EU VAT | IFRS 15 | Pricing Studio | A2A Payments | Policy Engine |
|---|---|---|---|---|---|---|
| Stripe Billing | -- | Partial | -- | -- | -- | -- |
| Chargebee | -- | Partial | -- | -- | -- | -- |
| Lago | Basic usage | -- | -- | -- | -- | -- |
| Orb | Usage only | -- | -- | -- | -- | -- |
| Flexprice | Partial | -- | -- | -- | -- | -- |
| **Rupiv.ai** | **Full** | **Full** | **Full** | **Full** | **Full** | **Full** |

---

## License

Proprietary. All rights reserved.

---

<p align="center">
  Built in Delft, Netherlands. EU-sovereign.
</p>
