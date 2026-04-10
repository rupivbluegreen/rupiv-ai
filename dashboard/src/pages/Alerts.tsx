import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Bell, CheckCircle, Eye } from 'lucide-react';
import clsx from 'clsx';

const BASE_URL = import.meta.env.VITE_API_URL ?? '/v1';

interface Alert {
  id: string;
  alert_type: string;
  severity: 'warning' | 'critical';
  customer_id: string | null;
  title: string;
  description: string | null;
  metric_name: string | null;
  expected_value: string | null;
  actual_value: string | null;
  status: 'open' | 'acknowledged' | 'resolved';
  resolved_at: string | null;
  created_at: string;
}

interface AlertList {
  items: Alert[];
  total: number;
}

async function fetchAlerts(status?: string): Promise<AlertList> {
  const params = new URLSearchParams();
  if (status && status !== 'all') params.set('status', status);
  const query = params.toString() ? `?${params.toString()}` : '';
  const res = await fetch(`${BASE_URL}/alerts${query}`);
  if (!res.ok) return { items: [], total: 0 };
  return res.json();
}

async function updateAlert(id: string, status: string): Promise<void> {
  await fetch(`${BASE_URL}/alerts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}

const severityStyles: Record<string, string> = {
  critical: 'bg-red-100 text-red-800',
  warning: 'bg-yellow-100 text-yellow-800',
};

const statusStyles: Record<string, string> = {
  open: 'bg-red-50 text-red-700 border-red-200',
  acknowledged: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  resolved: 'bg-green-50 text-green-700 border-green-200',
};

export default function Alerts() {
  const [filter, setFilter] = useState<string>('open');
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['alerts', filter],
    queryFn: () => fetchAlerts(filter),
  });

  const mutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateAlert(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  });

  const alerts = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Alerts</h1>
          <p className="mt-1 text-sm text-gray-500">
            Revenue leakage and anomaly detection — {total} alert{total !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          {['all', 'open', 'acknowledged', 'resolved'].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={clsx(
                'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                filter === s
                  ? 'bg-blue-100 text-blue-700'
                  : 'text-gray-600 hover:bg-gray-100',
              )}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white py-12 text-center text-gray-500">
          <Bell className="mx-auto mb-2 h-8 w-8 text-gray-300" />
          No {filter !== 'all' ? filter : ''} alerts.
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={clsx(
                'rounded-xl border bg-white p-5 transition-colors',
                statusStyles[alert.status] ?? 'border-gray-200',
              )}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <AlertTriangle
                    className={clsx(
                      'mt-0.5 h-5 w-5',
                      alert.severity === 'critical' ? 'text-red-600' : 'text-yellow-600',
                    )}
                  />
                  <div>
                    <h3 className="font-semibold text-gray-900">{alert.title}</h3>
                    {alert.description && (
                      <p className="mt-1 text-sm text-gray-600">{alert.description}</p>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      <span
                        className={clsx(
                          'inline-flex items-center rounded-full px-2 py-0.5 font-medium',
                          severityStyles[alert.severity],
                        )}
                      >
                        {alert.severity}
                      </span>
                      <span className="text-gray-400">
                        {alert.alert_type.replace(/_/g, ' ')}
                      </span>
                      {alert.metric_name && (
                        <span className="text-gray-400">metric: {alert.metric_name}</span>
                      )}
                      {alert.expected_value && alert.actual_value && (
                        <span className="text-gray-400">
                          expected {parseFloat(alert.expected_value).toFixed(2)} / actual{' '}
                          {parseFloat(alert.actual_value).toFixed(2)}
                        </span>
                      )}
                      <span className="text-gray-400">
                        {new Date(alert.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex gap-2">
                  {alert.status === 'open' && (
                    <button
                      onClick={() => mutation.mutate({ id: alert.id, status: 'acknowledged' })}
                      className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Acknowledge
                    </button>
                  )}
                  {alert.status !== 'resolved' && (
                    <button
                      onClick={() => mutation.mutate({ id: alert.id, status: 'resolved' })}
                      className="flex items-center gap-1 rounded-lg border border-green-200 bg-green-50 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-100"
                    >
                      <CheckCircle className="h-3.5 w-3.5" />
                      Resolve
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
