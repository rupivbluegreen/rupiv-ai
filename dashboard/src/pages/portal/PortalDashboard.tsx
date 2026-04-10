import { useQuery } from '@tanstack/react-query';
import {
  fetchPortalMe,
  fetchPortalUsage,
  fetchPortalSubscription,
  fetchPortalInvoices,
} from '../../lib/portal-api';
import type { PortalInvoice } from '../../lib/portal-api';

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    open: 'bg-yellow-100 text-yellow-800',
    paid: 'bg-green-100 text-green-800',
    draft: 'bg-gray-100 text-gray-800',
    void: 'bg-red-100 text-red-800',
    uncollectible: 'bg-red-100 text-red-800',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colors[status] ?? 'bg-gray-100 text-gray-800'}`}
    >
      {status}
    </span>
  );
}

export default function PortalDashboard() {
  const { data: me } = useQuery({ queryKey: ['portal-me'], queryFn: fetchPortalMe });
  const { data: usage } = useQuery({ queryKey: ['portal-usage'], queryFn: fetchPortalUsage });
  const { data: subscription } = useQuery({
    queryKey: ['portal-subscription'],
    queryFn: fetchPortalSubscription,
  });
  const { data: invoiceData } = useQuery({
    queryKey: ['portal-invoices-recent'],
    queryFn: () => fetchPortalInvoices(5, 0),
  });

  const totalEvents = usage?.metrics.reduce((sum, m) => sum + m.count, 0) ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome{me ? `, ${me.name}` : ''}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Your billing overview for the current period.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Subscription" value={subscription?.status ?? 'None'} />
        <StatCard label="Currency" value={me?.currency ?? '-'} />
        <StatCard label="Events this period" value={totalEvents} />
        <StatCard label="Metrics tracked" value={usage?.metrics.length ?? 0} />
      </div>

      {usage && usage.metrics.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-gray-900">Usage by metric</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-500">
                  <th className="pb-2 font-medium">Metric</th>
                  <th className="pb-2 font-medium">Type</th>
                  <th className="pb-2 text-right font-medium">Count</th>
                </tr>
              </thead>
              <tbody>
                {usage.metrics.map((m) => (
                  <tr key={`${m.metric}-${m.event_type}`} className="border-b border-gray-100">
                    <td className="py-2 font-medium text-gray-900">{m.metric}</td>
                    <td className="py-2 text-gray-600">{m.event_type}</td>
                    <td className="py-2 text-right text-gray-900">{m.count.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {invoiceData && invoiceData.items.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-gray-900">Recent invoices</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-500">
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {invoiceData.items.map((inv: PortalInvoice) => (
                  <tr key={inv.id} className="border-b border-gray-100">
                    <td className="py-2 text-gray-900">
                      {new Date(inv.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-2">{statusBadge(inv.status)}</td>
                    <td className="py-2 text-right font-medium text-gray-900">
                      {inv.currency} {parseFloat(inv.total).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
