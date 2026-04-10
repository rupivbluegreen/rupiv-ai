import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Download, Plus } from 'lucide-react';

const BASE_URL = import.meta.env.VITE_API_URL ?? '/v1';

interface ERPConnection {
  id: string;
  provider: string;
  name: string;
  gl_account_mapping: Record<string, string> | null;
  is_active: boolean;
  last_sync_at: string | null;
  created_at: string;
}

interface ExportLog {
  id: string;
  erp_connection_id: string;
  period: string;
  entry_count: number;
  status: string;
  error_message: string | null;
  created_at: string;
}

async function fetchConnections(): Promise<ERPConnection[]> {
  const res = await fetch(`${BASE_URL}/erp/connections`);
  if (!res.ok) return [];
  return res.json();
}

async function fetchExportLogs(): Promise<ExportLog[]> {
  const res = await fetch(`${BASE_URL}/erp/export-logs`);
  if (!res.ok) return [];
  return res.json();
}

async function createConnection(data: { provider: string; name: string }): Promise<void> {
  await fetch(`${BASE_URL}/erp/connections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

async function triggerExport(connectionId: string, period: string): Promise<Blob> {
  const res = await fetch(`${BASE_URL}/erp/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ connection_id: connectionId, period }),
  });
  if (!res.ok) throw new Error('Export failed');
  return res.blob();
}

export default function ERPExport() {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newProvider, setNewProvider] = useState('csv');

  const { data: connections = [] } = useQuery({
    queryKey: ['erp-connections'],
    queryFn: fetchConnections,
  });

  const { data: logs = [] } = useQuery({
    queryKey: ['erp-export-logs'],
    queryFn: fetchExportLogs,
  });

  const createMutation = useMutation({
    mutationFn: () => createConnection({ provider: newProvider, name: newName }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['erp-connections'] });
      setShowCreate(false);
      setNewName('');
    },
  });

  const handleExport = async (connectionId: string, provider: string) => {
    const blob = await triggerExport(connectionId, period);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `journal-entries-${period}.${provider}`;
    a.click();
    URL.revokeObjectURL(url);
    queryClient.invalidateQueries({ queryKey: ['erp-export-logs'] });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">ERP Export</h1>
          <p className="mt-1 text-sm text-gray-500">
            Export journal entries to your accounting system.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          Add Connection
        </button>
      </div>

      {showCreate && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">New Connection</h2>
          <div className="flex gap-4">
            <select
              value={newProvider}
              onChange={(e) => setNewProvider(e.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="csv">Generic CSV</option>
              <option value="quickbooks">QuickBooks IIF</option>
              <option value="xero">Xero CSV</option>
            </select>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Connection name"
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
            <button
              onClick={() => createMutation.mutate()}
              disabled={!newName}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Create
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Connections</h2>
        <div className="flex items-center gap-4 mb-4">
          <label className="text-sm text-gray-500">Export period:</label>
          <input
            type="month"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>
        {connections.length === 0 ? (
          <p className="text-gray-500 text-sm">No connections configured yet.</p>
        ) : (
          <div className="space-y-3">
            {connections.map((conn) => (
              <div
                key={conn.id}
                className="flex items-center justify-between rounded-lg border border-gray-100 p-4"
              >
                <div>
                  <p className="font-medium text-gray-900">{conn.name}</p>
                  <p className="text-sm text-gray-500">
                    {conn.provider} &middot;{' '}
                    {conn.is_active ? 'Active' : 'Inactive'}
                  </p>
                </div>
                <button
                  onClick={() => handleExport(conn.id, conn.provider)}
                  disabled={!conn.is_active}
                  className="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  <Download className="h-4 w-4" />
                  Export {period}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {logs.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Export History</h2>
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-gray-500">
                <th className="pb-2 font-medium">Period</th>
                <th className="pb-2 font-medium">Entries</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium">Date</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} className="border-b border-gray-100">
                  <td className="py-2 text-gray-900">{log.period}</td>
                  <td className="py-2 text-gray-600">{log.entry_count}</td>
                  <td className="py-2">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        log.status === 'success'
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {log.status}
                    </span>
                  </td>
                  <td className="py-2 text-gray-600">
                    {new Date(log.created_at).toLocaleString()}
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
