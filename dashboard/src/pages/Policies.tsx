import { Shield } from 'lucide-react';

export default function Policies() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Policies</h1>
        <p className="mt-1 text-sm text-gray-500">
          Business rules, approval workflows, and threshold management.
        </p>
      </div>
      <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center">
        <Shield className="mx-auto h-10 w-10 text-gray-300" />
        <p className="mt-3 text-sm text-gray-500">
          Policy management is coming soon.
        </p>
      </div>
    </div>
  );
}
