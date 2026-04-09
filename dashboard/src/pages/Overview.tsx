import { Link } from 'react-router-dom';
import {
  DollarSign,
  TrendingUp,
  Users,
  Activity,
  CheckCircle,
  Target,
  Banknote,
  UserPlus,
  CreditCard,
  FlaskConical,
  FileText,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import StatCard from '../components/StatCard';
import {
  fetchAnalyticsMRR,
  fetchEvents,
  fetchOutcomeMetrics,
  fetchInvoices,
  formatEUR,
  type Invoice,
  type MRRData,
} from '../lib/api';

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  open: 'bg-blue-100 text-blue-700',
  paid: 'bg-green-100 text-green-700',
  void: 'bg-red-100 text-red-700',
  uncollectible: 'bg-orange-100 text-orange-700',
};

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-4 w-16 rounded bg-gray-200" />
        <div className="h-10 w-10 rounded-lg bg-gray-100" />
      </div>
      <div className="mt-3">
        <div className="h-7 w-28 rounded bg-gray-200" />
      </div>
    </div>
  );
}

function SkeletonChart() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 animate-pulse">
      <div className="h-5 w-48 rounded bg-gray-200" />
      <div className="mt-4 h-72 rounded bg-gray-100" />
    </div>
  );
}

function SkeletonTable() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white animate-pulse">
      <div className="border-b border-gray-200 px-6 py-4">
        <div className="h-5 w-36 rounded bg-gray-200" />
      </div>
      <div className="space-y-4 p-6">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex gap-4">
            <div className="h-4 w-20 rounded bg-gray-200" />
            <div className="h-4 w-24 rounded bg-gray-200" />
            <div className="h-4 w-16 rounded bg-gray-200" />
            <div className="h-4 w-14 rounded bg-gray-200" />
          </div>
        ))}
      </div>
    </div>
  );
}

function SkeletonSection() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 animate-pulse">
      <div className="h-5 w-40 rounded bg-gray-200" />
      <div className="mt-4 grid grid-cols-3 gap-4">
        <div className="h-16 rounded bg-gray-100" />
        <div className="h-16 rounded bg-gray-100" />
        <div className="h-16 rounded bg-gray-100" />
      </div>
    </div>
  );
}

/** Build chart data from MRR trend response */
function buildMRRChart(mrrData: MRRData[]): { month: string; revenue: number }[] {
  if (mrrData.length === 0) return [];
  return mrrData.map((d) => ({
    month: d.month,
    revenue: d.mrr,
  }));
}

/** Generate date strings for the last N months */
function lastNMonthDates(n: number): string[] {
  const dates: string[] = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    dates.push(d.toISOString().split('T')[0]);
  }
  return dates;
}

const quickActions = [
  { to: '/customers', label: 'Create Customer', icon: UserPlus, desc: 'Add a new customer account' },
  { to: '/plans', label: 'Create Plan', icon: CreditCard, desc: 'Define a new pricing plan' },
  { to: '/pricing-studio', label: 'Run Simulation', icon: FlaskConical, desc: 'Test pricing scenarios' },
  { to: '/quotes', label: 'Generate Quote', icon: FileText, desc: 'Create a customer proposal' },
];

export default function Overview() {
  // Fetch MRR from analytics endpoint
  const {
    data: mrrResponse,
    isLoading: mrrLoading,
    isError: mrrError,
  } = useQuery({
    queryKey: ['analytics-mrr'],
    queryFn: () => fetchAnalyticsMRR(),
  });

  // Fetch MRR trend for last 6 months
  const monthDates = lastNMonthDates(6);
  const {
    data: mrrTrend = [],
    isLoading: trendLoading,
    isError: trendError,
  } = useQuery({
    queryKey: ['analytics-mrr-trend', monthDates],
    queryFn: async () => {
      const results = await Promise.all(
        monthDates.map((date) => fetchAnalyticsMRR(date))
      );
      // Each call returns MRRData[], flatten and take the first item from each
      return results.map((arr, idx) => {
        const d = new Date(monthDates[idx]);
        const label = d.toLocaleString('en-US', { month: 'short' });
        if (arr.length > 0) {
          return { month: label, mrr: arr[0].mrr };
        }
        return { month: label, mrr: 0 };
      });
    },
  });

  // Fetch events for this month count
  const {
    data: events = [],
    isLoading: eventsLoading,
  } = useQuery({
    queryKey: ['events'],
    queryFn: () => fetchEvents(),
  });

  // Fetch outcome metrics
  const {
    data: outcomeMetrics = [],
    isLoading: outcomesLoading,
    isError: outcomesError,
  } = useQuery({
    queryKey: ['analytics-outcome-metrics'],
    queryFn: () => fetchOutcomeMetrics(),
  });

  // Fetch invoices for recent invoices table
  const {
    data: invoices = [],
    isLoading: invoicesLoading,
    isError: invoicesError,
  } = useQuery({
    queryKey: ['invoices'],
    queryFn: () => fetchInvoices(),
  });

  // Derive stat card values
  const latestMRR = mrrResponse && mrrResponse.length > 0 ? mrrResponse[0] : null;
  const totalMRR = latestMRR?.mrr ?? 0;
  const totalARR = totalMRR * 12;
  const customerCount = latestMRR?.new_mrr !== undefined
    ? (mrrResponse?.reduce((sum, d) => sum + (d.new_mrr ?? 0), 0) ?? 0)
    : 0;

  // Use a fallback: if MRR response has no customer count info, count from events
  const now = new Date();
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const eventsThisMonth = events.filter(
    (evt) => new Date(evt.created_at) >= startOfMonth
  ).length;

  // Outcome metrics aggregated
  const outcomeAgg = outcomeMetrics.reduce(
    (acc, m) => ({
      totalEvents: acc.totalEvents + m.total_events,
      billableEvents: acc.billableEvents + m.billable_events,
      totalRevenue: acc.totalRevenue + m.total_revenue,
      validationRate: m.validation_rate, // use latest
    }),
    { totalEvents: 0, billableEvents: 0, totalRevenue: 0, validationRate: 0 }
  );
  const successRate =
    outcomeMetrics.length > 0
      ? outcomeMetrics.reduce((s, m) => s + m.validation_rate, 0) / outcomeMetrics.length
      : 0;

  const revenueChartData = buildMRRChart(
    mrrTrend.map((t) => ({
      month: t.month,
      mrr: t.mrr,
      new_mrr: 0,
      expansion: 0,
      contraction: 0,
      churn: 0,
    }))
  );

  const recentInvoices = [...invoices]
    .sort((a: Invoice, b: Invoice) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 10);

  const statsLoading = mrrLoading || eventsLoading;
  const statsError = mrrError;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Overview</h1>
        <p className="mt-1 text-sm text-gray-500">
          Your billing metrics at a glance.
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statsLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : statsError ? (
          <div className="col-span-4 rounded-xl border border-red-200 bg-red-50 px-6 py-8 text-center text-sm text-red-600">
            Failed to load overview stats. Please try again later.
          </div>
        ) : (
          <>
            <StatCard
              title="MRR"
              value={formatEUR(totalMRR)}
              icon={DollarSign}
            />
            <StatCard
              title="ARR"
              value={formatEUR(totalARR)}
              icon={TrendingUp}
            />
            <StatCard
              title="Active Customers"
              value={new Intl.NumberFormat('de-DE').format(customerCount)}
              icon={Users}
            />
            <StatCard
              title="Events This Month"
              value={new Intl.NumberFormat('de-DE').format(eventsThisMonth)}
              icon={Activity}
            />
          </>
        )}
      </div>

      {/* Revenue Chart */}
      {trendLoading ? (
        <SkeletonChart />
      ) : trendError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-8 text-center text-sm text-red-600">
          Failed to load revenue data.
        </div>
      ) : revenueChartData.every((d) => d.revenue === 0) ? (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center text-sm text-gray-500">
          No revenue data yet. MRR data will appear here once billing is active.
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-base font-semibold text-gray-900">
            MRR Trend (Last 6 Months)
          </h2>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={revenueChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 12, fill: '#6B7280' }}
                  axisLine={{ stroke: '#E5E7EB' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 12, fill: '#6B7280' }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => formatEUR(v)}
                />
                <Tooltip
                  formatter={(value) => [formatEUR(Number(value)), 'MRR']}
                  contentStyle={{
                    borderRadius: '8px',
                    border: '1px solid #E5E7EB',
                    fontSize: '13px',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="revenue"
                  stroke="#2563EB"
                  strokeWidth={2}
                  dot={{ fill: '#2563EB', r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Outcome Metrics */}
      {outcomesLoading ? (
        <SkeletonSection />
      ) : outcomesError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-8 text-center text-sm text-red-600">
          Failed to load outcome metrics.
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-base font-semibold text-gray-900">
            Outcome Metrics
          </h2>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-500">
                <Target className="h-4 w-4" />
                Success Rate
              </div>
              <p className="mt-2 text-xl font-semibold text-gray-900">
                {outcomeMetrics.length > 0
                  ? `${(successRate * 100).toFixed(1)}%`
                  : '--'}
              </p>
            </div>
            <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-500">
                <CheckCircle className="h-4 w-4" />
                Validated
              </div>
              <p className="mt-2 text-xl font-semibold text-gray-900">
                {new Intl.NumberFormat('de-DE').format(outcomeAgg.billableEvents)}
              </p>
            </div>
            <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-500">
                <Activity className="h-4 w-4" />
                Total Events
              </div>
              <p className="mt-2 text-xl font-semibold text-gray-900">
                {new Intl.NumberFormat('de-DE').format(outcomeAgg.totalEvents)}
              </p>
            </div>
            <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-500">
                <Banknote className="h-4 w-4" />
                Outcome Revenue
              </div>
              <p className="mt-2 text-xl font-semibold text-gray-900">
                {formatEUR(outcomeAgg.totalRevenue)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Recent Invoices */}
      {invoicesLoading ? (
        <SkeletonTable />
      ) : invoicesError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-8 text-center text-sm text-red-600">
          Failed to load invoices.
        </div>
      ) : recentInvoices.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center text-sm text-gray-500">
          No invoices yet. They will appear here once billing begins.
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white">
          <div className="border-b border-gray-200 px-6 py-4">
            <h2 className="text-base font-semibold text-gray-900">
              Recent Invoices
            </h2>
          </div>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-6 py-3 text-xs font-medium tracking-wide text-gray-500 uppercase">
                  Invoice
                </th>
                <th className="px-6 py-3 text-xs font-medium tracking-wide text-gray-500 uppercase">
                  Customer
                </th>
                <th className="px-6 py-3 text-xs font-medium tracking-wide text-gray-500 uppercase">
                  Amount
                </th>
                <th className="px-6 py-3 text-xs font-medium tracking-wide text-gray-500 uppercase">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {recentInvoices.map((inv) => (
                <tr
                  key={inv.id}
                  className="border-b border-gray-100 last:border-b-0 hover:bg-gray-50 transition-colors"
                >
                  <td className="px-6 py-4 font-medium text-gray-900">
                    {inv.number}
                  </td>
                  <td className="px-6 py-4 text-gray-700">
                    {inv.customer_name ?? inv.customer_id}
                  </td>
                  <td className="px-6 py-4 text-gray-700">
                    {formatEUR(parseFloat(inv.amount || '0'))}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColors[inv.status] ?? 'bg-gray-100 text-gray-700'}`}
                    >
                      {inv.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Quick Actions */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="text-base font-semibold text-gray-900">Quick Actions</h2>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {quickActions.map((action) => (
            <Link
              key={action.to}
              to={action.to}
              className="group flex items-start gap-3 rounded-lg border border-gray-200 p-4 transition-colors hover:border-blue-300 hover:bg-blue-50"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600 transition-colors group-hover:bg-blue-100">
                <action.icon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900">{action.label}</p>
                <p className="mt-0.5 text-xs text-gray-500">{action.desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
