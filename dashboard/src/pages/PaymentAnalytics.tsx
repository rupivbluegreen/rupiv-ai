import { BarChart3 } from 'lucide-react';

export default function PaymentAnalytics() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Payment Analytics</h1>
        <p className="mt-1 text-sm text-gray-500">
          PSP cost comparison, routing optimization, and payment insights.
        </p>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center">
        <BarChart3 className="mx-auto h-10 w-10 text-gray-300" />
        <p className="mt-3 text-sm text-gray-500">
          Payment analytics views are coming soon.
        </p>
      </div>
    </div>
  );
}
