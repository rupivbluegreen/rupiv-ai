const BASE_URL = import.meta.env.VITE_API_URL ?? '/v1';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  return res.json();
}

/** Safe wrapper that returns a fallback on network/API errors */
async function safeRequest<T>(path: string, fallback: T, options?: RequestInit): Promise<T> {
  try {
    return await request<T>(path, options);
  } catch {
    return fallback;
  }
}

// --- Types ---

export interface Customer {
  id: string;
  name: string;
  email: string;
  country: string;
  currency: string;
  created_at: string;
}

export interface PricingRule {
  metric: string;
  model: string;
  unit_price: string;
  tiers?: { up_to: number; unit_price: string }[];
}

export interface Plan {
  id: string;
  name: string;
  currency: string;
  pricing_rules: PricingRule[];
  created_at: string;
}

export interface Event {
  id: string;
  type: 'usage' | 'outcome';
  metric: string;
  customer_id: string;
  customer_name?: string;
  properties: Record<string, unknown>;
  status: string;
  outcome_status?: 'pending' | 'validated' | 'rejected';
  created_at: string;
}

export interface Invoice {
  id: string;
  number: string;
  customer_id: string;
  customer_name?: string;
  amount: string;
  currency: string;
  status: 'draft' | 'open' | 'paid' | 'void' | 'uncollectible';
  due_date: string;
  created_at: string;
}

export interface Subscription {
  id: string;
  customer_id: string;
  plan_id: string;
  status: string;
  created_at: string;
}

export interface CreateCustomerInput {
  name: string;
  email: string;
  country: string;
  currency: string;
}

export interface CreatePlanInput {
  name: string;
  currency: string;
  pricing_rules: PricingRule[];
}

export interface CreateSubscriptionInput {
  customer_id: string;
  plan_id: string;
}

export interface OverviewStats {
  mrr: number;
  arr: number;
  activeCustomers: number;
  eventsThisMonth: number;
}

// --- Currency Formatting ---

export const formatEUR = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
}).format;

// --- API Functions ---

export function fetchCustomers(): Promise<Customer[]> {
  return safeRequest<Customer[]>('/customers', []);
}

export function fetchPlans(): Promise<Plan[]> {
  return safeRequest<Plan[]>('/plans', []);
}

export function fetchInvoices(status?: string): Promise<Invoice[]> {
  const query = status && status !== 'all' ? `?status=${status}` : '';
  return safeRequest<Invoice[]>(`/invoices${query}`, []);
}

export function fetchEvents(): Promise<Event[]> {
  return safeRequest<Event[]>('/events', []);
}

export function fetchSubscriptions(customerId?: string): Promise<Subscription[]> {
  const query = customerId ? `?customer_id=${customerId}` : '';
  return safeRequest<Subscription[]>(`/subscriptions${query}`, []);
}

export function createCustomer(data: CreateCustomerInput): Promise<Customer> {
  return request<Customer>('/customers', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function createPlan(data: CreatePlanInput): Promise<Plan> {
  return request<Plan>('/plans', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function createSubscription(data: CreateSubscriptionInput): Promise<Subscription> {
  return request<Subscription>('/subscriptions', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function fetchOverviewStats(): Promise<OverviewStats> {
  const [customers, invoices, events] = await Promise.all([
    safeRequest<Customer[]>('/customers', []),
    safeRequest<Invoice[]>('/invoices', []),
    safeRequest<Event[]>('/events', []),
  ]);

  const now = new Date();
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

  // MRR: sum of paid + open invoice amounts (approximation from recent invoices)
  const mrr = invoices
    .filter((inv) => inv.status === 'paid' || inv.status === 'open')
    .reduce((sum, inv) => sum + parseFloat(inv.amount || '0'), 0);

  const eventsThisMonth = events.filter(
    (evt) => new Date(evt.created_at) >= startOfMonth
  ).length;

  return {
    mrr,
    arr: mrr * 12,
    activeCustomers: customers.length,
    eventsThisMonth,
  };
}
