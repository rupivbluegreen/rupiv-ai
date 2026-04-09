import { DollarSign, TrendingUp, Users, Activity } from 'lucide-react';
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
import { fetchOverviewStats, fetchInvoices, formatEUR, type Invoice } from '../lib/api';

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  open: 'bg-blue-100 text-blue-700',
  paid: 'bg-green-100 text-green-700',
  void: 'bg-red-100 text-red-700',
  uncollectible: 'bg-orange-100 text-orange-700',
};

function buildRevenueChart(invoices: Invoice[]): { month: string; revenue: number }[] {
  const now = new Date();
  const months: { month: string; revenue: number }[] = [];

  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const label = d.toLocaleString('en-US', { month: 'short' });
    const year = d.getFullYear();
    const month = d.getMonth();

    const total = invoices
      .filter((inv) => {
        const created = new Date(inv.created_at);
        return (
          created.getFullYear() === year &&
          created.getMonth() === month &&
          (inv.status === 'paid' || inv.status === 'open')
        );
      })
      .reduce((sum, inv) => sum + parseFloat(inv.amount || '0'), 0);

    months.push({ month: label, revenue: total });
  }

  return months;
}

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

export default function Overview() {
  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
  } = useQuery({
    queryKey: ['overview-stats'],
    queryFn: fetchOverviewStats,
  });

  const {
    data: invoices = [],
    isLoading: invoicesLoading,
    isError: invoicesError,
  } = useQuery({
    queryKey: ['invoices'],
    queryFn: () => fetchInvoices(),
  });

  const revenueData = buildRevenueChart(invoices);
  const recentInvoices = [...invoices]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 10);

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
              value={formatEUR(stats?.mrr ?? 0)}
              icon={DollarSign}
            />
            <StatCard
              title="ARR"
              value={formatEUR(stats?.arr ?? 0)}
              icon={TrendingUp}
            />
            <StatCard
              title="Active Customers"
              value={String(stats?.activeCustomers ?? 0)}
              icon={Users}
            />
            <StatCard
              title="Events This Month"
              value={new Intl.NumberFormat('de-DE').format(stats?.eventsThisMonth ?? 0)}
              icon={Activity}
            />
          </>
        )}
      </div>

      {/* Revenue Chart */}
      {invoicesLoading ? (
        <SkeletonChart />
      ) : invoicesError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-6 py-8 text-center text-sm text-red-600">
          Failed to load revenue data.
        </div>
      ) : revenueData.every((d) => d.revenue === 0) ? (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center text-sm text-gray-500">
          No revenue data yet. Invoices will appear here once created.
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-base font-semibold text-gray-900">
            Revenue (Last 6 Months)
          </h2>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={revenueData}>
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
                  formatter={(value) => [formatEUR(Number(value)), 'Revenue']}
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
    </div>
  );
}
