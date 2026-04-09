import { TrendingUp } from 'lucide-react';

export default function Revenue() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Revenue Recognition</h1>
        <p className="mt-1 text-sm text-gray-500">
          IFRS 15 revenue schedules and journal entries.
        </p>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center">
        <TrendingUp className="mx-auto h-10 w-10 text-gray-300" />
        <p className="mt-3 text-sm text-gray-500">
          Revenue recognition views are coming soon.
        </p>
      </div>
    </div>
  );
}
