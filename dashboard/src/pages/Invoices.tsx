import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import DataTable, { type Column } from '../components/DataTable';
import { fetchInvoices, formatEUR, type Invoice } from '../lib/api';

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  open: 'bg-blue-100 text-blue-700',
  paid: 'bg-green-100 text-green-700',
  void: 'bg-red-100 text-red-700',
  uncollectible: 'bg-orange-100 text-orange-700',
};

const columns: Column<Invoice>[] = [
  {
    key: 'number',
    header: 'Invoice #',
    render: (row) => (
      <span className="font-medium text-gray-900">{row.number}</span>
    ),
  },
  {
    key: 'customer_name',
    header: 'Customer',
    render: (row) => row.customer_name ?? row.customer_id,
  },
  {
    key: 'amount',
    header: 'Amount',
    render: (row) => (
      <span>{formatEUR(parseFloat(row.amount || '0'))}</span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    render: (row) => (
      <span
        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
          statusColors[row.status] ?? 'bg-gray-100 text-gray-700'
        }`}
      >
        {row.status}
      </span>
    ),
  },
  {
    key: 'due_date',
    header: 'Due Date',
    render: (row) => new Date(row.due_date).toLocaleDateString(),
  },
];

const statusOptions = ['all', 'draft', 'open', 'paid', 'void', 'uncollectible'];

export default function Invoices() {
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const { data: invoices = [], isLoading } = useQuery({
    queryKey: ['invoices', statusFilter],
    queryFn: () => fetchInvoices(statusFilter),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Invoices</h1>
          <p className="mt-1 text-sm text-gray-500">
            View and manage invoices.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <label className="text-sm font-medium text-gray-700">Status:</label>
        <div className="flex gap-1.5">
          {statusOptions.map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                statusFilter === status
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-sm text-gray-500">
          Loading invoices...
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={invoices}
          emptyMessage="No invoices found."
        />
      )}
    </div>
  );
}
