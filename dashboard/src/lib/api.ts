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

// --- API Functions ---

export function fetchCustomers(): Promise<Customer[]> {
  return request<Customer[]>('/customers');
}

export function fetchPlans(): Promise<Plan[]> {
  return request<Plan[]>('/plans');
}

export function fetchInvoices(): Promise<Invoice[]> {
  return request<Invoice[]>('/invoices');
}

export function fetchEvents(): Promise<Event[]> {
  return request<Event[]>('/events');
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
