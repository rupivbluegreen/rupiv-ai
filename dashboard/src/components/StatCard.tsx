import type { LucideIcon } from 'lucide-react';
import clsx from 'clsx';

interface StatCardProps {
  title: string;
  value: string;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  icon: LucideIcon;
}

export default function StatCard({
  title,
  value,
  change,
  changeType = 'neutral',
  icon: Icon,
}: StatCardProps) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-500">{title}</span>
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-50">
          <Icon className="h-5 w-5 text-gray-400" />
        </div>
      </div>
      <div className="mt-3">
        <span className="text-2xl font-semibold text-gray-900">{value}</span>
        {change && (
          <span
            className={clsx(
              'ml-2 text-sm font-medium',
              changeType === 'positive' && 'text-green-600',
              changeType === 'negative' && 'text-red-600',
              changeType === 'neutral' && 'text-gray-500'
            )}
          >
            {change}
          </span>
        )}
      </div>
    </div>
  );
}
