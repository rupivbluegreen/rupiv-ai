import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { fetchPortalUsage } from '../../lib/portal-api';

export default function PortalUsage() {
  const { data: usage, isLoading } = useQuery({
    queryKey: ['portal-usage'],
    queryFn: fetchPortalUsage,
  });

  const chartData =
    usage?.metrics.map((m) => ({
      name: `${m.metric} (${m.event_type})`,
      count: m.count,
    })) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Usage</h1>
        {usage?.period_start && usage?.period_end && (
          <p className="mt-1 text-sm text-gray-500">
            Current period: {new Date(usage.period_start).toLocaleDateString()} &ndash;{' '}
            {new Date(usage.period_end).toLocaleDateString()}
          </p>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
        </div>
      ) : chartData.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white py-12 text-center text-gray-500">
          No usage data for the current period.
        </div>
      ) : (
        <>
          <div className="rounded-xl border border-gray-200 bg-white p-6">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">Events by metric</h2>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ left: 120 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-6">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">Details</h2>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-gray-500">
                    <th className="pb-2 font-medium">Metric</th>
                    <th className="pb-2 font-medium">Type</th>
                    <th className="pb-2 text-right font-medium">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {usage!.metrics.map((m) => (
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
        </>
      )}
    </div>
  );
}
