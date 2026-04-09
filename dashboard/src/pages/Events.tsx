import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import DataTable, { type Column } from '../components/DataTable';
import { fetchEvents, type Event } from '../lib/api';

const columns: Column<Event>[] = [
  {
    key: 'type',
    header: 'Type',
    render: (row) => (
      <span
        className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
          row.type === 'outcome'
            ? 'bg-purple-100 text-purple-700'
            : 'bg-cyan-100 text-cyan-700'
        }`}
      >
        {row.type}
      </span>
    ),
  },
  {
    key: 'metric',
    header: 'Metric',
    render: (row) => (
      <span className="font-medium text-gray-900">{row.metric}</span>
    ),
  },
  {
    key: 'customer_name',
    header: 'Customer',
    render: (row) => row.customer_name ?? row.customer_id,
  },
  {
    key: 'status',
    header: 'Status',
    render: (row) => {
      const colors: Record<string, string> = {
        processed: 'bg-green-100 text-green-700',
        pending: 'bg-yellow-100 text-yellow-700',
        failed: 'bg-red-100 text-red-700',
      };
      return (
        <span
          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
            colors[row.status] ?? 'bg-gray-100 text-gray-700'
          }`}
        >
          {row.status}
        </span>
      );
    },
  },
  {
    key: 'created_at',
    header: 'Timestamp',
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
];

export default function Events() {
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [metricFilter, setMetricFilter] = useState<string>('');

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['events'],
    queryFn: fetchEvents,
    refetchInterval: 5000,
  });

  const filtered = events.filter((evt: Event) => {
    if (typeFilter !== 'all' && evt.type !== typeFilter) return false;
    if (metricFilter && !evt.metric.toLowerCase().includes(metricFilter.toLowerCase()))
      return false;
    return true;
  });

  const metrics = [...new Set(events.map((e: Event) => e.metric))];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Events</h1>
        <p className="mt-1 text-sm text-gray-500">
          Real-time event stream. Auto-refreshes every 5 seconds.
        </p>
      </div>

      <div className="flex items-center gap-4">
        <div>
          <label className="mr-2 text-sm font-medium text-gray-700">
            Type:
          </label>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
          >
            <option value="all">All</option>
            <option value="usage">Usage</option>
            <option value="outcome">Outcome</option>
          </select>
        </div>
        <div>
          <label className="mr-2 text-sm font-medium text-gray-700">
            Metric:
          </label>
          <select
            value={metricFilter}
            onChange={(e) => setMetricFilter(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
          >
            <option value="">All metrics</option>
            {metrics.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="py-12 text-center text-sm text-gray-500">
          Loading events...
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={filtered}
          pageSize={15}
          emptyMessage="No events recorded yet."
        />
      )}
    </div>
  );
}
