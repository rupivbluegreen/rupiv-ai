-- ClickHouse initialization script for Rupiv.ai
-- Runs automatically on first container start via docker-entrypoint-initdb.d

CREATE DATABASE IF NOT EXISTS rupiv;

-- Events table: stores usage and outcome events for billing aggregation.
-- Uses ReplacingMergeTree for deduplication by idempotency_key.
-- Partitioned by day for efficient time-range queries and TTL management.
CREATE TABLE IF NOT EXISTS rupiv.events
(
    event_id          UUID DEFAULT generateUUIDv4(),
    idempotency_key   String,
    customer_id       UUID,
    subscription_id   UUID,
    event_type        Enum8('usage' = 1, 'outcome' = 2),
    metric            String,
    value             Decimal64(4),
    properties        String,  -- JSON string of event properties
    billable          UInt8 DEFAULT 0,  -- 0 = pending validation, 1 = billable
    created_at        DateTime64(3) DEFAULT now64(3),
    received_at       DateTime64(3) DEFAULT now64(3),
    billing_period    Date DEFAULT toDate(now())
)
ENGINE = ReplacingMergeTree(received_at)
PARTITION BY toYYYYMMDD(created_at)
ORDER BY (customer_id, metric, created_at, idempotency_key)
TTL toDate(created_at) + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;

-- Index for fast lookups by idempotency key (dedup check on ingest)
ALTER TABLE rupiv.events ADD INDEX idx_idempotency idempotency_key TYPE bloom_filter GRANULARITY 4;

-- Index for subscription-based queries
ALTER TABLE rupiv.events ADD INDEX idx_subscription subscription_id TYPE bloom_filter GRANULARITY 4;
