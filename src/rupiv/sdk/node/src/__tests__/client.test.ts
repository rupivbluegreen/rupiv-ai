import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RupivClient } from "../client.js";
import { RupivError } from "../types.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jsonResponse(body: unknown, status = 200, headers?: Record<string, string>): Response {
  return new Response(JSON.stringify(body), {
    status,
    statusText: status === 200 ? "OK" : "Error",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  });
}

const MOCK_EVENT_RESPONSE = {
  id: "evt_abc123",
  type: "usage",
  metric: "api_call",
  customer_id: "cust_123",
  properties: { tokens: 150 },
  idempotency_key: "key-1",
  created_at: "2026-01-15T12:00:00Z",
};

const MOCK_OUTCOME_RESPONSE = {
  ...MOCK_EVENT_RESPONSE,
  id: "evt_def456",
  type: "outcome",
  metric: "ticket_resolved",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("RupivClient", () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, "fetch");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -- trackEvent -----------------------------------------------------------

  it("test_track_event — sends correct POST /v1/events with type=usage", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(MOCK_EVENT_RESPONSE));

    const client = new RupivClient({ apiKey: "rp_test_key", baseUrl: "https://test.rupiv.ai" });

    const result = await client.trackEvent({
      metric: "api_call",
      customerId: "cust_123",
      properties: { tokens: 150 },
      idempotencyKey: "key-1",
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://test.rupiv.ai/v1/events");
    expect(init.method).toBe("POST");

    const headers = init.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer rp_test_key");
    expect(headers["Content-Type"]).toBe("application/json");

    const body = JSON.parse(init.body as string);
    expect(body.type).toBe("usage");
    expect(body.metric).toBe("api_call");
    expect(body.customer_id).toBe("cust_123");
    expect(body.properties).toEqual({ tokens: 150 });
    expect(body.idempotency_key).toBe("key-1");

    expect(result.id).toBe("evt_abc123");
    expect(result.type).toBe("usage");
  });

  // -- trackOutcome ---------------------------------------------------------

  it("test_track_outcome — sends correct POST /v1/events with type=outcome", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(MOCK_OUTCOME_RESPONSE));

    const client = new RupivClient({ apiKey: "rp_test_key", baseUrl: "https://test.rupiv.ai" });

    const result = await client.trackOutcome({
      metric: "ticket_resolved",
      customerId: "cust_123",
      properties: { resolution_time: 45 },
    });

    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.type).toBe("outcome");
    expect(body.metric).toBe("ticket_resolved");
    expect(body.customer_id).toBe("cust_123");

    expect(result.id).toBe("evt_def456");
    expect(result.type).toBe("outcome");
  });

  // -- Auto idempotency key -------------------------------------------------

  it("test_auto_idempotency_key — generates UUID when not provided", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(MOCK_EVENT_RESPONSE));

    const client = new RupivClient({ apiKey: "rp_test_key", baseUrl: "https://test.rupiv.ai" });

    await client.trackEvent({
      metric: "api_call",
      customerId: "cust_123",
    });

    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);

    // Should be a valid UUID v4 format
    expect(body.idempotency_key).toBeDefined();
    expect(body.idempotency_key).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
  });

  // -- Error handling -------------------------------------------------------

  it("test_error_handling — throws RupivError on 400 response", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(
        { error: { message: "Invalid metric name" } },
        400,
        { "x-request-id": "req_bad" },
      ),
    );

    const client = new RupivClient({ apiKey: "rp_test_key", baseUrl: "https://test.rupiv.ai" });

    await expect(
      client.trackEvent({ metric: "", customerId: "cust_123" }),
    ).rejects.toThrow(RupivError);

    try {
      fetchSpy.mockResolvedValueOnce(
        jsonResponse(
          { error: { message: "Invalid metric name" } },
          400,
          { "x-request-id": "req_bad2" },
        ),
      );
      await client.trackEvent({ metric: "", customerId: "cust_123" });
    } catch (err) {
      expect(err).toBeInstanceOf(RupivError);
      const rupivErr = err as RupivError;
      expect(rupivErr.statusCode).toBe(400);
      expect(rupivErr.message).toContain("Invalid metric name");
      expect(rupivErr.requestId).toBe("req_bad2");
    }
  });

  // -- Retry on 500 ---------------------------------------------------------

  it("test_retry_on_500 — retries on 5xx then succeeds", async () => {
    // First call: 500, second call: 200
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({ error: { message: "Internal error" } }, 500),
      )
      .mockResolvedValueOnce(jsonResponse(MOCK_EVENT_RESPONSE));

    const client = new RupivClient({
      apiKey: "rp_test_key",
      baseUrl: "https://test.rupiv.ai",
      maxRetries: 3,
    });

    const result = await client.trackEvent({
      metric: "api_call",
      customerId: "cust_123",
    });

    // fetch was called twice: first 500, then 200
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(result.id).toBe("evt_abc123");
  });

  // -- No retry on 4xx ------------------------------------------------------

  it("does not retry on 4xx errors", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({ error: { message: "Not found" } }, 404),
    );

    const client = new RupivClient({
      apiKey: "rp_test_key",
      baseUrl: "https://test.rupiv.ai",
      maxRetries: 3,
    });

    await expect(
      client.getCustomer("nonexistent"),
    ).rejects.toThrow(RupivError);

    // Should only be called once — no retries for 4xx
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  // -- getCustomer ----------------------------------------------------------

  it("fetches a customer by ID", async () => {
    const mockCustomer = {
      id: "cust_123",
      external_id: "ext_123",
      name: "Acme AI",
      email: "billing@acme.ai",
      plan: null,
      metadata: null,
      created_at: "2026-01-01T00:00:00Z",
    };

    fetchSpy.mockResolvedValueOnce(jsonResponse(mockCustomer));

    const client = new RupivClient({ apiKey: "rp_test_key", baseUrl: "https://test.rupiv.ai" });
    const result = await client.getCustomer("cust_123");

    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://test.rupiv.ai/v1/customers/cust_123");
    expect(result.name).toBe("Acme AI");
  });

  // -- listInvoices ---------------------------------------------------------

  it("lists invoices with optional customer filter", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse([]));

    const client = new RupivClient({ apiKey: "rp_test_key", baseUrl: "https://test.rupiv.ai" });
    await client.listInvoices({ customerId: "cust_123" });

    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://test.rupiv.ai/v1/invoices?customer_id=cust_123");
  });

  // -- createQuote ----------------------------------------------------------

  it("creates a quote with correct payload", async () => {
    const mockQuote = {
      id: "qt_abc",
      customer_id: "cust_123",
      plan_id: "plan_pro",
      status: "draft",
      metadata: {},
      created_at: "2026-01-15T12:00:00Z",
    };

    fetchSpy.mockResolvedValueOnce(jsonResponse(mockQuote));

    const client = new RupivClient({ apiKey: "rp_test_key", baseUrl: "https://test.rupiv.ai" });
    const result = await client.createQuote({
      customerId: "cust_123",
      planId: "plan_pro",
    });

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://test.rupiv.ai/v1/quotes");
    const body = JSON.parse(init.body as string);
    expect(body.customer_id).toBe("cust_123");
    expect(body.plan_id).toBe("plan_pro");
    expect(result.status).toBe("draft");
  });

  // -- Constructor validation -----------------------------------------------

  it("throws if apiKey is empty", () => {
    expect(() => new RupivClient({ apiKey: "" })).toThrow("apiKey is required");
  });
});
