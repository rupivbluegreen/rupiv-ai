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

// --- Pricing Studio Types ---

export interface SimulateRequest {
  plan_id: string;
  scenario: {
    pricing_rules: {
      metric: string;
      price_per_outcome: number;
      billable_when: Record<string, unknown>;
    }[];
    date_range: { start: string; end: string };
  };
}

export interface SimulationResult {
  current_revenue: number;
  simulated_revenue: number;
  delta: number;
  delta_pct: number;
  current_billable_outcomes: number;
  simulated_billable_outcomes: number;
}

export interface PricingTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  pricing_rules: {
    metric: string;
    model: string;
    unit_price: string;
    billable_when?: Record<string, unknown>;
  }[];
}

export interface ForecastRequest {
  base_mrr: number;
  growth_rate: number;
  churn_rate: number;
  months: number;
}

export interface ForecastResult {
  months: {
    month: number;
    label: string;
    p10: number;
    p50: number;
    p90: number;
  }[];
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

// --- Entity Types ---

export interface Entity {
  id: string;
  name: string;
  entity_type: 'BV' | 'GmbH' | 'SAS' | 'Ltd';
  country_code: string;
  currency: string;
  parent_id: string | null;
  vat_number: string;
  created_at: string;
}

export interface CreateEntityInput {
  name: string;
  entity_type: 'BV' | 'GmbH' | 'SAS' | 'Ltd';
  country_code: string;
  currency: string;
  parent_id?: string;
  vat_number: string;
}

// --- Quote Types ---

export interface QuoteLineItem {
  id: string;
  quote_id: string;
  description: string;
  quantity: number;
  unit_price: string;
  amount: string;
}

export interface Quote {
  id: string;
  customer_id: string;
  customer_name?: string;
  plan_id: string;
  plan_name?: string;
  status: 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired';
  discount_pct: number;
  term_months: number;
  total: string;
  rejection_reason?: string;
  expires_at: string;
  created_at: string;
  line_items?: QuoteLineItem[];
}

export interface CreateQuoteInput {
  customer_id: string;
  plan_id: string;
  discount_pct: number;
  term_months: number;
}

// --- Entity API Functions ---

export function fetchEntities(parentId?: string): Promise<Entity[]> {
  const query = parentId ? `?parent_id=${parentId}` : '';
  return safeRequest<Entity[]>(`/entities${query}`, []);
}

export function createEntity(data: CreateEntityInput): Promise<Entity> {
  return request<Entity>('/entities', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function fetchEntityChildren(id: string): Promise<Entity[]> {
  return safeRequest<Entity[]>(`/entities/${id}/children`, []);
}

export function fetchEntityAncestors(id: string): Promise<Entity[]> {
  return safeRequest<Entity[]>(`/entities/${id}/ancestors`, []);
}

// --- Quote API Functions ---

export function fetchQuotes(customerId?: string, status?: string): Promise<Quote[]> {
  const params = new URLSearchParams();
  if (customerId) params.set('customer_id', customerId);
  if (status && status !== 'all') params.set('status', status);
  const query = params.toString() ? `?${params.toString()}` : '';
  return safeRequest<Quote[]>(`/quotes${query}`, []);
}

export function createQuote(data: CreateQuoteInput): Promise<Quote> {
  return request<Quote>('/quotes', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function acceptQuote(id: string): Promise<Quote> {
  return request<Quote>(`/quotes/${id}/accept`, { method: 'POST' });
}

export function rejectQuote(id: string, reason: string): Promise<Quote> {
  return request<Quote>(`/quotes/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

export function sendQuote(id: string): Promise<Quote> {
  return request<Quote>(`/quotes/${id}/send`, { method: 'POST' });
}

// --- Pricing Studio API Functions ---

export function simulatePricing(data: SimulateRequest): Promise<SimulationResult> {
  return request<SimulationResult>('/simulate', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function getTemplates(): Promise<PricingTemplate[]> {
  return safeRequest<PricingTemplate[]>('/simulate/templates', []);
}

export function forecastRevenue(data: ForecastRequest): Promise<ForecastResult> {
  return request<ForecastResult>('/simulate/forecast', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// --- Revenue Recognition Types ---

export interface RevenueEntry {
  id: string;
  schedule_id: string;
  period: string;
  amount: string;
  type: 'recognized' | 'deferred';
  created_at: string;
}

export interface RevenueSchedule {
  id: string;
  subscription_id: string;
  obligation_type: string;
  method: 'over_time' | 'point_in_time';
  total: string;
  recognized: string;
  deferred: string;
  status: 'active' | 'completed' | 'voided';
  entries: RevenueEntry[];
  created_at: string;
}

export interface JournalEntry {
  id: string;
  date: string;
  debit_account: string;
  credit_account: string;
  amount: string;
  description: string;
  reference: string;
  created_at: string;
}

// --- Revenue Recognition API Functions ---

export function fetchRevenueSchedules(subscriptionId?: string): Promise<RevenueSchedule[]> {
  const query = subscriptionId ? `?subscription_id=${subscriptionId}` : '';
  return safeRequest<RevenueSchedule[]>(`/revenue/schedules${query}`, []);
}

export function generateRevenueSchedule(subscriptionId: string): Promise<RevenueSchedule> {
  return request<RevenueSchedule>('/revenue/schedules/generate', {
    method: 'POST',
    body: JSON.stringify({ subscription_id: subscriptionId }),
  });
}

export function fetchJournalEntries(period: string): Promise<JournalEntry[]> {
  return safeRequest<JournalEntry[]>(`/revenue/journal-entries?period=${period}`, []);
}

// --- Analytics Types ---

export interface MRRData {
  month: string;
  mrr: number;
  new_mrr: number;
  expansion: number;
  contraction: number;
  churn: number;
}

export interface PaymentCostData {
  psp: string;
  method: string;
  transaction_count: number;
  volume: number;
  fees: number;
  blended_rate: number;
}

export interface OutcomeMetric {
  metric: string;
  customer_id?: string;
  total_events: number;
  billable_events: number;
  validation_rate: number;
  total_revenue: number;
  avg_value: number;
  period: string;
}

export interface CohortData {
  cohort_month: string;
  months: { month: number; retention: number; revenue: number }[];
}

export interface RoutingRecommendation {
  id: string;
  method: string;
  current_psp: string;
  recommended_psp: string;
  current_rate: number;
  recommended_rate: number;
  monthly_volume: number;
  estimated_monthly_savings: number;
  reason: string;
}

// --- Policy Types ---

export interface PolicyRule {
  id: string;
  name: string;
  trigger: string;
  conditions: { field: string; operator: string; value: string | number | boolean }[];
  action: 'auto_approve' | 'require_approval' | 'reject';
  approver?: string;
  priority: number;
  active: boolean;
}

// --- Analytics API Functions ---

export function fetchAnalyticsMRR(asOfDate?: string): Promise<MRRData[]> {
  const query = asOfDate ? `?as_of=${asOfDate}` : '';
  return safeRequest<MRRData[]>(`/analytics/mrr${query}`, []);
}

export function fetchAnalyticsARR(asOfDate?: string): Promise<{ arr: number; asOf: string }> {
  const query = asOfDate ? `?as_of=${asOfDate}` : '';
  return safeRequest<{ arr: number; asOf: string }>(`/analytics/arr${query}`, { arr: 0, asOf: '' });
}

export function fetchAnalyticsChurn(start?: string, end?: string): Promise<{ churn_rate: number; churned_customers: number }> {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const query = params.toString() ? `?${params.toString()}` : '';
  return safeRequest<{ churn_rate: number; churned_customers: number }>(`/analytics/churn${query}`, { churn_rate: 0, churned_customers: 0 });
}

export function fetchPaymentCosts(start?: string, end?: string, psp?: string): Promise<PaymentCostData[]> {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (psp) params.set('psp', psp);
  const query = params.toString() ? `?${params.toString()}` : '';
  return safeRequest<PaymentCostData[]>(`/analytics/payment-costs${query}`, []);
}

export function fetchPaymentRecommendations(start?: string, end?: string): Promise<RoutingRecommendation[]> {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const query = params.toString() ? `?${params.toString()}` : '';
  return safeRequest<RoutingRecommendation[]>(`/analytics/payment-recommendations${query}`, []);
}

export function fetchOutcomeMetrics(start?: string, end?: string, customerId?: string, metric?: string): Promise<OutcomeMetric[]> {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (customerId) params.set('customer_id', customerId);
  if (metric) params.set('metric', metric);
  const query = params.toString() ? `?${params.toString()}` : '';
  return safeRequest<OutcomeMetric[]>(`/analytics/outcome-metrics${query}`, []);
}

export function fetchCohorts(startMonth?: string, numMonths?: number): Promise<CohortData[]> {
  const params = new URLSearchParams();
  if (startMonth) params.set('start_month', startMonth);
  if (numMonths) params.set('num_months', String(numMonths));
  const query = params.toString() ? `?${params.toString()}` : '';
  return safeRequest<CohortData[]>(`/analytics/cohorts${query}`, []);
}

export function fetchPolicies(): Promise<PolicyRule[]> {
  return safeRequest<PolicyRule[]>('/policies', []);
}

// --- Onboarding Types ---

export interface SignupInput {
  company_name: string;
  email: string;
  country_code?: string;
  is_business?: boolean;
  vat_number?: string | null;
}

export interface SignupResult {
  customer_id: string;
  subscription_id: string;
  api_key: string;
  dashboard_url: string;
}

export interface SetupBillingInput {
  customer_id: string;
  payment_provider?: string;
  return_url: string;
}

export interface SetupBillingResult {
  redirect_url: string;
}

export interface OnboardingStatusResult {
  has_customer: boolean;
  has_subscription: boolean;
  has_api_key: boolean;
  has_payment_method: boolean;
  has_first_event: boolean;
  completion_pct: number;
}

export interface UpgradeInput {
  customer_id: string;
  plan_id: string;
}

export interface UpgradeResult {
  old_subscription_id: string;
  new_subscription_id: string;
  plan_id: string;
}

// --- Onboarding API Functions ---

export function onboardingSignup(data: SignupInput): Promise<SignupResult> {
  return request<SignupResult>('/onboarding/signup', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function onboardingSetupBilling(data: SetupBillingInput): Promise<SetupBillingResult> {
  return request<SetupBillingResult>('/onboarding/setup-billing', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export function onboardingStatus(customerId: string): Promise<OnboardingStatusResult> {
  return request<OnboardingStatusResult>(`/onboarding/status/${customerId}`);
}

export function onboardingUpgrade(data: UpgradeInput): Promise<UpgradeResult> {
  return request<UpgradeResult>('/onboarding/upgrade', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export interface SendTestEventInput {
  type: 'usage' | 'outcome';
  metric: string;
  customer_id: string;
  properties: Record<string, unknown>;
  idempotency_key: string;
}

export interface SendTestEventResult {
  event_id: string;
  status: string;
}

export function sendTestEvent(data: SendTestEventInput): Promise<SendTestEventResult> {
  return request<SendTestEventResult>('/events', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// --- Overview Stats ---

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
