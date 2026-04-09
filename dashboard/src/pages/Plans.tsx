import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, X } from 'lucide-react';
import DataTable, { type Column } from '../components/DataTable';
import {
  fetchPlans,
  createPlan,
  type Plan,
  type PricingRule,
} from '../lib/api';

const columns: Column<Plan>[] = [
  {
    key: 'name',
    header: 'Name',
    render: (row) => (
      <span className="font-medium text-gray-900">{row.name}</span>
    ),
  },
  {
    key: 'pricing_rules',
    header: 'Pricing Models',
    render: (row) => (
      <div className="flex flex-wrap gap-1.5">
        {row.pricing_rules.map((rule: PricingRule, i: number) => (
          <span
            key={i}
            className="inline-flex rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700"
          >
            {rule.model}: {rule.metric}
          </span>
        ))}
        {row.pricing_rules.length === 0 && (
          <span className="text-gray-400">None</span>
        )}
      </div>
    ),
  },
  { key: 'currency', header: 'Currency' },
  {
    key: 'created_at',
    header: 'Created',
    render: (row) => new Date(row.created_at).toLocaleDateString(),
  },
];

const emptyRule: PricingRule = { metric: '', model: 'flat', unit_price: '' };

export default function Plans() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: '',
    currency: 'EUR',
    pricing_rules: [{ ...emptyRule }] as PricingRule[],
  });

  const { data: plans = [], isLoading } = useQuery({
    queryKey: ['plans'],
    queryFn: fetchPlans,
  });

  const mutation = useMutation({
    mutationFn: createPlan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plans'] });
      setShowForm(false);
      setForm({ name: '', currency: 'EUR', pricing_rules: [{ ...emptyRule }] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(form);
  };

  const updateRule = (idx: number, field: keyof PricingRule, value: string) => {
    const rules = [...form.pricing_rules];
    rules[idx] = { ...rules[idx], [field]: value };
    setForm({ ...form, pricing_rules: rules });
  };

  const addRule = () => {
    setForm({
      ...form,
      pricing_rules: [...form.pricing_rules, { ...emptyRule }],
    });
  };

  const removeRule = (idx: number) => {
    setForm({
      ...form,
      pricing_rules: form.pricing_rules.filter((_, i) => i !== idx),
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Plans</h1>
          <p className="mt-1 text-sm text-gray-500">
            Define pricing plans and billing rules.
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Create Plan
        </button>
      </div>

      {showForm && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900">New Plan</h2>
            <button
              onClick={() => setShowForm(false)}
              className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Plan Name
                </label>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Currency
                </label>
                <select
                  value={form.currency}
                  onChange={(e) =>
                    setForm({ ...form, currency: e.target.value })
                  }
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                >
                  <option value="EUR">EUR</option>
                  <option value="USD">USD</option>
                  <option value="GBP">GBP</option>
                </select>
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700">
                  Pricing Rules
                </label>
                <button
                  type="button"
                  onClick={addRule}
                  className="text-sm font-medium text-blue-600 hover:text-blue-700"
                >
                  + Add Rule
                </button>
              </div>
              <div className="space-y-3">
                {form.pricing_rules.map((rule, idx) => (
                  <div
                    key={idx}
                    className="flex items-end gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3"
                  >
                    <div className="flex-1">
                      <label className="mb-1 block text-xs text-gray-500">
                        Metric
                      </label>
                      <input
                        type="text"
                        required
                        value={rule.metric}
                        onChange={(e) =>
                          updateRule(idx, 'metric', e.target.value)
                        }
                        placeholder="e.g. ticket_resolved"
                        className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                      />
                    </div>
                    <div className="w-36">
                      <label className="mb-1 block text-xs text-gray-500">
                        Model
                      </label>
                      <select
                        value={rule.model}
                        onChange={(e) =>
                          updateRule(idx, 'model', e.target.value)
                        }
                        className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                      >
                        <option value="flat">Flat</option>
                        <option value="usage">Usage</option>
                        <option value="outcome">Outcome</option>
                        <option value="tiered">Tiered</option>
                      </select>
                    </div>
                    <div className="w-32">
                      <label className="mb-1 block text-xs text-gray-500">
                        Unit Price
                      </label>
                      <input
                        type="text"
                        required
                        value={rule.unit_price}
                        onChange={(e) =>
                          updateRule(idx, 'unit_price', e.target.value)
                        }
                        placeholder="0.99"
                        className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                      />
                    </div>
                    {form.pricing_rules.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeRule(idx)}
                        className="rounded-md p-1.5 text-gray-400 hover:bg-gray-200 hover:text-gray-600"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={mutation.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {mutation.isPending ? 'Creating...' : 'Create Plan'}
              </button>
            </div>
          </form>
          {mutation.isError && (
            <p className="mt-3 text-sm text-red-600">
              Failed to create plan. Please try again.
            </p>
          )}
        </div>
      )}

      {isLoading ? (
        <div className="py-12 text-center text-sm text-gray-500">
          Loading plans...
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={plans}
          emptyMessage="No plans yet. Click 'Create Plan' to define one."
        />
      )}
    </div>
  );
}
