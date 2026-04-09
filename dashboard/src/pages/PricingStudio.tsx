import { FlaskConical } from 'lucide-react';

export default function PricingStudio() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Pricing Studio</h1>
        <p className="mt-1 text-sm text-gray-500">
          Simulate pricing scenarios and forecast revenue impact.
        </p>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center">
        <FlaskConical className="mx-auto h-10 w-10 text-gray-300" />
        <p className="mt-3 text-sm text-gray-500">
          Pricing simulation tools are coming soon.
        </p>
      </div>
    </div>
  );
}
