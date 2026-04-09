import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';
import { formatEUR } from '../lib/api';

interface RevenueWaterfallProps {
  recognized: number;
  deferred: number;
  newDeferred: number;
}

interface WaterfallItem {
  name: string;
  value: number;
  base: number;
  color: string;
}

export default function RevenueWaterfall({
  recognized,
  deferred,
  newDeferred,
}: RevenueWaterfallProps) {
  const openingDeferred = deferred;
  const closingDeferred = openingDeferred - recognized + newDeferred;

  const data: WaterfallItem[] = [
    {
      name: 'Opening Deferred',
      value: openingDeferred,
      base: 0,
      color: '#F97316', // orange
    },
    {
      name: 'Recognized',
      value: recognized,
      base: openingDeferred - recognized,
      color: '#16A34A', // green
    },
    {
      name: 'New Deferred',
      value: newDeferred,
      base: openingDeferred - recognized,
      color: '#2563EB', // blue
    },
    {
      name: 'Closing Deferred',
      value: closingDeferred,
      base: 0,
      color: '#F97316', // orange
    },
  ];

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <h2 className="text-base font-semibold text-gray-900">
        Revenue Waterfall
      </h2>
      <p className="mt-1 text-sm text-gray-500">
        Deferred revenue flow for the selected period
      </p>

      <div className="mt-2 flex gap-6 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-green-600" />
          Recognized
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-orange-500" />
          Deferred
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-blue-600" />
          Adjustments
        </span>
      </div>

      <div className="mt-4 h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barCategoryGap="25%">
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
            <XAxis
              dataKey="name"
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
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(value: any) => [formatEUR(Number(value)), 'Amount']}
              contentStyle={{
                borderRadius: '8px',
                border: '1px solid #E5E7EB',
                fontSize: '13px',
              }}
            />
            <ReferenceLine y={0} stroke="#E5E7EB" />
            <Bar dataKey="base" stackId="waterfall" fill="transparent" />
            <Bar dataKey="value" stackId="waterfall" radius={[4, 4, 0, 0]}>
              {data.map((entry, index) => (
                <Cell key={index} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
