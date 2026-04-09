/**
 * Synchronous-style (Promise-based) HTTP client for the Rupiv API.
 */

import { randomUUID } from "node:crypto";

import {
  type RupivClientOptions,
  type TrackEventParams,
  type TrackOutcomeParams,
  type CreateQuoteParams,
  type ListInvoicesParams,
  type EventResponse,
  type Customer,
  type Invoice,
  type Quote,
  type CreditBalance,
  RupivError,
} from "./types.js";

const DEFAULT_BASE_URL = "https://api.rupiv.ai";
const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_RETRIES = 3;
const USER_AGENT = "rupiv-node/0.1.0";

/** Initial backoff delay in ms for retry logic. */
const INITIAL_BACKOFF_MS = 250;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildHeaders(apiKey: string): Record<string, string> {
  return {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
    "User-Agent": USER_AGENT,
  };
}

function isRetryable(status: number): boolean {
  return status >= 500 && status < 600;
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class RupivClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly timeoutMs: number;
  private readonly maxRetries: number;

  constructor(options: RupivClientOptions) {
    if (!options.apiKey) {
      throw new Error("apiKey is required");
    }
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.headers = buildHeaders(options.apiKey);
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
  }

  // -- Events ---------------------------------------------------------------

  /**
   * Track a usage event (e.g. API call, message sent).
   */
  async trackEvent(params: TrackEventParams): Promise<EventResponse> {
    const payload = {
      metric: params.metric,
      customer_id: params.customerId,
      type: "usage",
      properties: params.properties ?? {},
      idempotency_key: params.idempotencyKey ?? randomUUID(),
    };
    return this.request<EventResponse>("POST", "/v1/events", payload);
  }

  /**
   * Track a business outcome (e.g. ticket resolved, lead generated).
   */
  async trackOutcome(params: TrackOutcomeParams): Promise<EventResponse> {
    const payload = {
      metric: params.metric,
      customer_id: params.customerId,
      type: "outcome",
      properties: params.properties ?? {},
      idempotency_key: params.idempotencyKey ?? randomUUID(),
    };
    return this.request<EventResponse>("POST", "/v1/events", payload);
  }

  // -- Customers ------------------------------------------------------------

  /**
   * Fetch a customer by ID.
   */
  async getCustomer(customerId: string): Promise<Customer> {
    return this.request<Customer>("GET", `/v1/customers/${encodeURIComponent(customerId)}`);
  }

  // -- Invoices -------------------------------------------------------------

  /**
   * List invoices, optionally filtered by customer.
   */
  async listInvoices(params?: ListInvoicesParams): Promise<Invoice[]> {
    const searchParams = new URLSearchParams();
    if (params?.customerId) {
      searchParams.set("customer_id", params.customerId);
    }
    const query = searchParams.toString();
    const path = query ? `/v1/invoices?${query}` : "/v1/invoices";
    return this.request<Invoice[]>("GET", path);
  }

  // -- Quotes ---------------------------------------------------------------

  /**
   * Create a pricing quote for a customer.
   */
  async createQuote(params: CreateQuoteParams): Promise<Quote> {
    const payload = {
      customer_id: params.customerId,
      plan_id: params.planId,
      metadata: params.metadata ?? {},
    };
    return this.request<Quote>("POST", "/v1/quotes", payload);
  }

  // -- Credits --------------------------------------------------------------

  /**
   * Get the credit balance for a customer.
   */
  async getBalance(customerId: string): Promise<CreditBalance> {
    return this.request<CreditBalance>(
      "GET",
      `/v1/customers/${encodeURIComponent(customerId)}/balance`,
    );
  }

  // -- Internal request engine ----------------------------------------------

  /**
   * Execute an HTTP request with retry logic for 5xx and network errors.
   */
  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    let lastError: unknown;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

        const init: RequestInit = {
          method,
          headers: this.headers,
          signal: controller.signal,
        };
        if (body !== undefined) {
          init.body = JSON.stringify(body);
        }

        const response = await fetch(url, init);
        clearTimeout(timeout);

        if (response.ok) {
          return (await response.json()) as T;
        }

        // Non-retryable client error — throw immediately
        if (!isRetryable(response.status)) {
          throw await this.buildError(response);
        }

        // Retryable 5xx — save error and retry
        lastError = await this.buildError(response);
      } catch (err) {
        lastError = err;
        // RupivError with a 4xx status should not be retried
        if (err instanceof RupivError && !isRetryable(err.statusCode)) {
          throw err;
        }
      }

      // Exponential backoff with jitter before retrying
      if (attempt < this.maxRetries - 1) {
        const backoff = INITIAL_BACKOFF_MS * Math.pow(2, attempt);
        const jitter = backoff * 0.5 * Math.random();
        await sleep(backoff + jitter);
      }
    }

    throw lastError;
  }

  /**
   * Build a RupivError from a failed HTTP response.
   */
  private async buildError(response: Response): Promise<RupivError> {
    const requestId = response.headers.get("x-request-id") ?? undefined;
    let message: string;
    try {
      const body = (await response.json()) as Record<string, unknown>;
      const errorObj = body.error as Record<string, unknown> | undefined;
      message = (errorObj?.message as string) ?? response.statusText;
    } catch {
      message = response.statusText;
    }
    return new RupivError(response.status, message, requestId);
  }
}
