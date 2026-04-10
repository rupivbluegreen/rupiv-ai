import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchPortalInvoices } from '../../lib/portal-api';
import type { PortalInvoice } from '../../lib/portal-api';

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

export default function PortalInvoices() {
  const [page, setPage] = useState(0);
  const limit = 20;

  const { data, isLoading } = useQuery({
    queryKey: ['portal-invoices', page],
    queryFn: () => fetchPortalInvoices(limit, page * limit),
  });

  const invoices = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / limit);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Invoices</h1>
        <p className="mt-1 text-sm text-gray-500">
          {total} invoice{total !== 1 ? 's' : ''} total
        </p>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
          </div>
        ) : invoices.length === 0 ? (
          <div className="py-12 text-center text-gray-500">No invoices yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left text-gray-500">
                  <th className="px-6 py-3 font-medium">Period</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                  <th className="px-6 py-3 font-medium">Due date</th>
                  <th className="px-6 py-3 font-medium">Subtotal</th>
                  <th className="px-6 py-3 font-medium">Tax</th>
                  <th className="px-6 py-3 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv: PortalInvoice) => (
                  <tr key={inv.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-6 py-3 text-gray-900">
                      {new Date(inv.period_start).toLocaleDateString()} &ndash;{' '}
                      {new Date(inv.period_end).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-3">{statusBadge(inv.status)}</td>
                    <td className="px-6 py-3 text-gray-600">
                      {new Date(inv.due_date).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-3 text-gray-900">
                      {inv.currency} {parseFloat(inv.subtotal).toFixed(2)}
                    </td>
                    <td className="px-6 py-3 text-gray-600">
                      {inv.currency} {parseFloat(inv.tax_amount).toFixed(2)}
                    </td>
                    <td className="px-6 py-3 text-right font-medium text-gray-900">
                      {inv.currency} {parseFloat(inv.total).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-gray-200 px-6 py-3">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="text-sm font-medium text-blue-600 disabled:text-gray-400"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="text-sm font-medium text-blue-600 disabled:text-gray-400"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
