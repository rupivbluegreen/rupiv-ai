/**
 * Portal API client — sends Bearer JWT for customer-scoped endpoints.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? '/v1';

function getToken(): string | null {
  return localStorage.getItem('rupiv_portal_token');
}

export function setPortalToken(token: string): void {
  localStorage.setItem('rupiv_portal_token', token);
}

export function clearPortalToken(): void {
  localStorage.removeItem('rupiv_portal_token');
}

async function portalRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  if (!token) {
    throw new Error('Not authenticated — no portal token found');
  }

  const res = await fetch(`${BASE_URL}/portal${path}`, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Portal API error ${res.status}: ${body}`);
  }

  return res.json();
}

async function safePortalRequest<T>(path: string, fallback: T): Promise<T> {
  try {
    return await portalRequest<T>(path);
  } catch {
    return fallback;
  }
}

// --- Types ---

export interface PortalCustomer {
  id: string;
  name: string;
  email: string;
  country_code: string;
  currency: string;
  is_business: boolean;
  vat_number: string | null;
}

export interface PortalLineItem {
  description: string;
  metric: string | null;
  quantity: string;
  unit_amount: string;
  amount: string;
}

export interface PortalInvoice {
  id: string;
  status: string;
  currency: string;
  subtotal: string;
  tax_amount: string;
  total: string;
  line_items: PortalLineItem[];
  period_start: string;
  period_end: string;
  due_date: string;
  created_at: string;
}

export interface PortalInvoiceList {
  items: PortalInvoice[];
  total: number;
}

export interface UsageMetricSummary {
  metric: string;
  event_type: string;
  count: number;
}

export interface PortalUsage {
  customer_id: string;
  period_start: string | null;
  period_end: string | null;
  metrics: UsageMetricSummary[];
}

export interface PortalSubscription {
  id: string;
  plan_id: string;
  status: string;
  current_period_start: string;
  current_period_end: string;
  canceled_at: string | null;
  created_at: string;
}

// --- API Functions ---

export function fetchPortalMe(): Promise<PortalCustomer> {
  return portalRequest<PortalCustomer>('/me');
}

export function fetchPortalInvoices(limit = 20, offset = 0): Promise<PortalInvoiceList> {
  return safePortalRequest<PortalInvoiceList>(
    `/invoices?limit=${limit}&offset=${offset}`,
    { items: [], total: 0 },
  );
}

export function fetchPortalInvoice(id: string): Promise<PortalInvoice> {
  return portalRequest<PortalInvoice>(`/invoices/${id}`);
}

export function fetchPortalUsage(): Promise<PortalUsage> {
  return safePortalRequest<PortalUsage>('/usage', {
    customer_id: '',
    period_start: null,
    period_end: null,
    metrics: [],
  });
}

export function fetchPortalSubscription(): Promise<PortalSubscription | null> {
  return safePortalRequest<PortalSubscription | null>('/subscription', null);
}
