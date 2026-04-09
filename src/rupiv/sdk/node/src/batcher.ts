/**
 * High-throughput event batcher for the Rupiv API.
 *
 * Buffers events in memory and flushes them in batches. Events are flushed
 * automatically when the buffer reaches `maxBatchSize` or every `maxWaitMs`,
 * whichever comes first.
 */

import { randomUUID } from "node:crypto";

import {
  type EventBatcherOptions,
  type TrackEventParams,
  type TrackOutcomeParams,
  RupivError,
} from "./types.js";

const DEFAULT_BASE_URL = "https://api.rupiv.ai";
const DEFAULT_MAX_BATCH_SIZE = 100;
const DEFAULT_MAX_WAIT_MS = 5_000;
const DEFAULT_TIMEOUT_MS = 30_000;
const USER_AGENT = "rupiv-node/0.1.0";

interface EventPayload {
  metric: string;
  customer_id: string;
  type: string;
  properties: Record<string, unknown>;
  idempotency_key: string;
}

export class EventBatcher {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly maxBatchSize: number;
  private readonly maxWaitMs: number;
  private readonly timeoutMs: number;

  private buffer: EventPayload[] = [];
  private closed = false;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(options: EventBatcherOptions) {
    if (!options.apiKey) {
      throw new Error("apiKey is required");
    }
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.headers = {
      Authorization: `Bearer ${options.apiKey}`,
      "Content-Type": "application/json",
      "User-Agent": USER_AGENT,
    };
    this.maxBatchSize = options.maxBatchSize ?? DEFAULT_MAX_BATCH_SIZE;
    this.maxWaitMs = options.maxWaitMs ?? DEFAULT_MAX_WAIT_MS;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

    this.startTimer();
  }

  // -- Public API -----------------------------------------------------------

  /**
   * Add a usage event to the buffer. Triggers an automatic flush when the
   * buffer reaches `maxBatchSize`.
   */
  add(params: TrackEventParams | TrackOutcomeParams & { type?: string }): void {
    if (this.closed) {
      throw new Error("EventBatcher is closed");
    }

    // Determine event type: if caller supplies `type`, use it;
    // otherwise default to "usage" for TrackEventParams.
    const eventType = "type" in params && typeof params.type === "string"
      ? params.type
      : "usage";

    const payload: EventPayload = {
      metric: params.metric,
      customer_id: params.customerId,
      type: eventType,
      properties: params.properties ?? {},
      idempotency_key: params.idempotencyKey ?? randomUUID(),
    };

    this.buffer.push(payload);

    if (this.buffer.length >= this.maxBatchSize) {
      // Fire-and-forget; errors are logged internally.
      void this.flush();
    }
  }

  /**
   * Convenience method to add an event with an explicit type.
   */
  addEvent(params: TrackEventParams): void {
    this.add({ ...params, type: "usage" } as TrackEventParams & { type: string });
  }

  /**
   * Convenience method to add an outcome event.
   */
  addOutcome(params: TrackOutcomeParams): void {
    this.add({ ...params, type: "outcome" } as TrackOutcomeParams & { type: string });
  }

  /**
   * Send all buffered events to the API immediately.
   */
  async flush(): Promise<void> {
    if (this.buffer.length === 0) {
      return;
    }

    const batch = this.buffer.slice();
    this.buffer = [];

    await this.sendBatch(batch);
  }

  /**
   * Flush remaining events and stop the background timer.
   */
  async close(): Promise<void> {
    this.closed = true;
    this.stopTimer();
    await this.flush();
  }

  // -- Internal -------------------------------------------------------------

  private async sendBatch(batch: EventPayload[]): Promise<void> {
    const url = `${this.baseUrl}/v1/events/batch`;

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

      const response = await fetch(url, {
        method: "POST",
        headers: this.headers,
        body: JSON.stringify({ events: batch }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!response.ok) {
        const requestId = response.headers.get("x-request-id") ?? undefined;
        let message: string;
        try {
          const body = (await response.json()) as Record<string, unknown>;
          const errorObj = body.error as Record<string, unknown> | undefined;
          message = (errorObj?.message as string) ?? response.statusText;
        } catch {
          message = response.statusText;
        }
        throw new RupivError(response.status, message, requestId);
      }
    } catch (err) {
      if (err instanceof RupivError) {
        throw err;
      }
      // Network / timeout errors are logged but not re-thrown to avoid
      // crashing the caller when used in fire-and-forget mode.
      console.error(`[rupiv] Failed to flush ${batch.length} events:`, err);
    }
  }

  private startTimer(): void {
    if (this.closed) return;
    this.timer = setInterval(() => {
      void this.flush();
    }, this.maxWaitMs);

    // Allow the Node.js process to exit even if the timer is running.
    if (this.timer && typeof this.timer === "object" && "unref" in this.timer) {
      this.timer.unref();
    }
  }

  private stopTimer(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
