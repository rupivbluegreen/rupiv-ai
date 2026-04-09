import { DollarSign, TrendingUp, Users, Activity } from 'lucide-react';
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

const revenueData = [
  { month: 'Nov', revenue: 12400 },
  { month: 'Dec', revenue: 15800 },
  { month: 'Jan', revenue: 18200 },
  { month: 'Feb', revenue: 21500 },
  { month: 'Mar', revenue: 24800 },
  { month: 'Apr', revenue: 28100 },
];

const recentInvoices = [
  { number: 'INV-0042', customer: 'Acme AI', amount: '$1,250.00', status: 'paid' },
  { number: 'INV-0041', customer: 'NovaMind', amount: '$890.00', status: 'open' },
  { number: 'INV-0040', customer: 'ResolveBot', amount: '$2,100.00', status: 'paid' },
  { number: 'INV-0039', customer: 'DataForge', amount: '$450.00', status: 'draft' },
  { number: 'INV-0038', customer: 'Acme AI', amount: '$1,250.00', status: 'paid' },
  { number: 'INV-0037', customer: 'SentinelAI', amount: '$3,400.00', status: 'paid' },
  { number: 'INV-0036', customer: 'NovaMind', amount: '$890.00', status: 'void' },
  { number: 'INV-0035', customer: 'ClearDesk', amount: '$670.00', status: 'paid' },
  { number: 'INV-0034', customer: 'ResolveBot', amount: '$2,100.00', status: 'paid' },
  { number: 'INV-0033', customer: 'DataForge', amount: '$450.00', status: 'uncollectible' },
];

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  open: 'bg-blue-100 text-blue-700',
  paid: 'bg-green-100 text-green-700',
  void: 'bg-red-100 text-red-700',
  uncollectible: 'bg-orange-100 text-orange-700',
};

export default function Overview() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Overview</h1>
        <p className="mt-1 text-sm text-gray-500">
          Your billing metrics at a glance.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="MRR"
          value="$28,100"
          change="+13.3%"
          changeType="positive"
          icon={DollarSign}
        />
        <StatCard
          title="ARR"
          value="$337,200"
          change="+13.3%"
          changeType="positive"
          icon={TrendingUp}
        />
        <StatCard
          title="Active Customers"
          value="47"
          change="+5"
          changeType="positive"
          icon={Users}
        />
        <StatCard
          title="Events This Month"
          value="128,491"
          change="+22.1%"
          changeType="positive"
          icon={Activity}
        />
      </div>

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
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              />
              <Tooltip
                formatter={(value) => [`$${Number(value).toLocaleString()}`, 'Revenue']}
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
                key={inv.number}
                className="border-b border-gray-100 last:border-b-0 hover:bg-gray-50 transition-colors"
              >
                <td className="px-6 py-4 font-medium text-gray-900">
                  {inv.number}
                </td>
                <td className="px-6 py-4 text-gray-700">{inv.customer}</td>
                <td className="px-6 py-4 text-gray-700">{inv.amount}</td>
                <td className="px-6 py-4">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColors[inv.status]}`}
                  >
                    {inv.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
