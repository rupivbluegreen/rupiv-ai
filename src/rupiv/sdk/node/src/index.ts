/**
 * @rupiv/sdk — Node.js SDK for Rupiv.ai outcome-based billing.
 *
 * @example
 * ```ts
 * import { RupivClient } from "@rupiv/sdk";
 *
 * const client = new RupivClient({ apiKey: "rp_live_xxx" });
 * await client.trackEvent({ metric: "api_call", customerId: "cust_123" });
 * ```
 */

export { RupivClient } from "./client.js";
export { EventBatcher } from "./batcher.js";

export {
  RupivError,
  type RupivClientOptions,
  type TrackEventParams,
  type TrackOutcomeParams,
  type CreateQuoteParams,
  type ListInvoicesParams,
  type EventBatcherOptions,
  type EventResponse,
  type Customer,
  type Invoice,
  type Quote,
  type CreditBalance,
  type Plan,
  type InvoiceLineItem,
} from "./types.js";
