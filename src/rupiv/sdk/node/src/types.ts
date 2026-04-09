/**
 * Type definitions for the Rupiv SDK.
 */

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

/** Raised when the Rupiv API returns a non-2xx response. */
export class RupivError extends Error {
  /** HTTP status code returned by the API. */
  readonly statusCode: number;
  /** Unique request identifier for support troubleshooting. */
  readonly requestId: string | undefined;

  constructor(
    statusCode: number,
    message: string,
    requestId?: string,
  ) {
    const suffix = requestId ? ` (requestId=${requestId})` : "";
    super(`[${statusCode}] ${message}${suffix}`);
    this.name = "RupivError";
    this.statusCode = statusCode;
    this.requestId = requestId;

    // Maintain proper prototype chain for instanceof checks
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

// ---------------------------------------------------------------------------
// Request parameter types
// ---------------------------------------------------------------------------

export interface TrackEventParams {
  /** The metric name, e.g. "api_call", "message_sent". */
  metric: string;
  /** Customer identifier. */
  customerId: string;
  /** Arbitrary key-value properties attached to the event. */
  properties?: Record<string, unknown>;
  /** Optional idempotency key. Auto-generated if omitted. */
  idempotencyKey?: string;
}

export interface TrackOutcomeParams {
  /** The outcome metric, e.g. "ticket_resolved", "fraud_prevented". */
  metric: string;
  /** Customer identifier. */
  customerId: string;
  /** Arbitrary key-value properties attached to the outcome. */
  properties?: Record<string, unknown>;
  /** Optional idempotency key. Auto-generated if omitted. */
  idempotencyKey?: string;
}

export interface CreateQuoteParams {
  /** Customer identifier to generate the quote for. */
  customerId: string;
  /** Plan identifier to base the quote on. */
  planId: string;
  /** Optional metadata for the quote. */
  metadata?: Record<string, unknown>;
}

export interface ListInvoicesParams {
  /** Filter invoices by customer. */
  customerId?: string;
}

// ---------------------------------------------------------------------------
// Client options
// ---------------------------------------------------------------------------

export interface RupivClientOptions {
  /** API key for authentication (e.g. "rp_live_xxx"). */
  apiKey: string;
  /** Base URL of the Rupiv API. Defaults to https://api.rupiv.ai. */
  baseUrl?: string;
  /** Request timeout in milliseconds. Defaults to 30000. */
  timeoutMs?: number;
  /** Maximum number of retry attempts for 5xx / network errors. Defaults to 3. */
  maxRetries?: number;
}

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

export interface EventResponse {
  id: string;
  type: string;
  metric: string;
  customer_id: string;
  properties: Record<string, unknown> | null;
  idempotency_key: string | null;
  created_at: string;
}

export interface Plan {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface Customer {
  id: string;
  external_id: string;
  name: string | null;
  email: string | null;
  plan: Plan | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface InvoiceLineItem {
  [key: string]: unknown;
}

export interface Invoice {
  id: string;
  customer_id: string;
  status: string;
  currency: string;
  amount_due: number;
  amount_paid: number;
  line_items: InvoiceLineItem[];
  period_start: string;
  period_end: string;
  created_at: string;
}

export interface Quote {
  id: string;
  customer_id: string;
  plan_id: string;
  status: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface CreditBalance {
  customer_id: string;
  balance: number;
  currency: string;
}

// ---------------------------------------------------------------------------
// Batcher options
// ---------------------------------------------------------------------------

export interface EventBatcherOptions {
  /** API key for authentication. */
  apiKey: string;
  /** Base URL of the Rupiv API. Defaults to https://api.rupiv.ai. */
  baseUrl?: string;
  /** Maximum events in a batch before auto-flush. Defaults to 100. */
  maxBatchSize?: number;
  /** Maximum wait in milliseconds before auto-flush. Defaults to 5000. */
  maxWaitMs?: number;
  /** Request timeout in milliseconds. Defaults to 30000. */
  timeoutMs?: number;
}
