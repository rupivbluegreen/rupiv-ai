import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, X, Send, Check, XCircle } from 'lucide-react';
import DataTable, { type Column } from '../components/DataTable';
import { useToast } from '../components/Toast';
import {
  fetchQuotes,
  createQuote,
  sendQuote,
  acceptQuote,
  rejectQuote,
  fetchCustomers,
  fetchPlans,
  formatEUR,
  type Quote,
  type CreateQuoteInput,
} from '../lib/api';

const STATUS_BADGES: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  sent: 'bg-blue-100 text-blue-700',
  accepted: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  expired: 'bg-orange-100 text-orange-700',
};

interface FormErrors {
  customer_id?: string;
  plan_id?: string;
}

const INITIAL_FORM: CreateQuoteInput = {
  customer_id: '',
  plan_id: '',
  discount_pct: 0,
  term_months: 12,
};

export default function Quotes() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreateQuoteInput>({ ...INITIAL_FORM });
  const [errors, setErrors] = useState<FormErrors>({});
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const { data: quotes = [], isLoading } = useQuery({
    queryKey: ['quotes'],
    queryFn: () => fetchQuotes(),
  });

  const { data: customers = [] } = useQuery({
    queryKey: ['customers'],
    queryFn: fetchCustomers,
  });

  const { data: plans = [] } = useQuery({
    queryKey: ['plans'],
    queryFn: fetchPlans,
  });

  const invalidateQuotes = () => {
    queryClient.invalidateQueries({ queryKey: ['quotes'] });
  };

  const createMutation = useMutation({
    mutationFn: createQuote,
    onSuccess: () => {
      invalidateQuotes();
      setShowForm(false);
      setForm({ ...INITIAL_FORM });
      setErrors({});
      showToast('Quote created successfully.', 'success');
    },
    onError: () => {
      showToast('Failed to create quote. Please try again.', 'error');
    },
  });

  const sendMutation = useMutation({
    mutationFn: sendQuote,
    onSuccess: () => {
      invalidateQuotes();
      showToast('Quote sent successfully.', 'success');
    },
    onError: () => {
      showToast('Failed to send quote.', 'error');
    },
  });

  const acceptMutation = useMutation({
    mutationFn: acceptQuote,
    onSuccess: () => {
      invalidateQuotes();
      showToast('Quote accepted.', 'success');
    },
    onError: () => {
      showToast('Failed to accept quote.', 'error');
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      rejectQuote(id, reason),
    onSuccess: () => {
      invalidateQuotes();
      setRejectingId(null);
      setRejectReason('');
      showToast('Quote rejected.', 'success');
    },
    onError: () => {
      showToast('Failed to reject quote.', 'error');
    },
  });

  const validate = (): boolean => {
    const newErrors: FormErrors = {};
    if (!form.customer_id) newErrors.customer_id = 'Customer is required.';
    if (!form.plan_id) newErrors.plan_id = 'Plan is required.';
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    createMutation.mutate(form);
  };

  const customerMap = new Map(customers.map((c) => [c.id, c.name]));
  const planMap = new Map(plans.map((p) => [p.id, p.name]));

  const columns: Column<Quote>[] = [
    {
      key: 'customer_id',
      header: 'Customer',
      render: (row) => (
        <span className="font-medium text-gray-900">
          {row.customer_name ?? customerMap.get(row.customer_id) ?? row.customer_id}
        </span>
      ),
    },
    {
      key: 'plan_id',
      header: 'Plan',
      render: (row) => (
        <span className="text-gray-700">
          {row.plan_name ?? planMap.get(row.plan_id) ?? row.plan_id}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => {
        const color = STATUS_BADGES[row.status] ?? 'bg-gray-100 text-gray-700';
        return (
          <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${color}`}>
            {row.status}
          </span>
        );
      },
    },
    {
      key: 'discount_pct',
      header: 'Discount',
      render: (row) => (
        <span className="text-gray-700">
          {row.discount_pct > 0 ? `${row.discount_pct}%` : '--'}
        </span>
      ),
    },
    {
      key: 'total',
      header: 'Total',
      render: (row) => (
        <span className="font-medium text-gray-900">
          {formatEUR(parseFloat(row.total || '0'))}
        </span>
      ),
    },
    {
      key: 'expires_at',
      header: 'Expires',
      render: (row) =>
        row.expires_at ? new Date(row.expires_at).toLocaleDateString() : '--',
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (row) => new Date(row.created_at).toLocaleDateString(),
    },
    {
      key: 'actions',
      header: 'Actions',
      render: (row) => (
        <div className="flex items-center gap-1">
          {row.status === 'draft' && (
            <button
              onClick={() => sendMutation.mutate(row.id)}
              disabled={sendMutation.isPending}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50 transition-colors"
              title="Send quote"
            >
              <Send className="h-3.5 w-3.5" />
              Send
            </button>
          )}
          {row.status === 'sent' && (
            <button
              onClick={() => acceptMutation.mutate(row.id)}
              disabled={acceptMutation.isPending}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-50 transition-colors"
              title="Accept quote"
            >
              <Check className="h-3.5 w-3.5" />
              Accept
            </button>
          )}
          {(row.status === 'draft' || row.status === 'sent') && (
            <button
              onClick={() => setRejectingId(row.id)}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 transition-colors"
              title="Reject quote"
            >
              <XCircle className="h-3.5 w-3.5" />
              Reject
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Quotes</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your quote pipeline from draft to acceptance.
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Create Quote
        </button>
      </div>

      {showForm && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900">
              New Quote
            </h2>
            <button
              onClick={() => {
                setShowForm(false);
                setErrors({});
              }}
              className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Customer
              </label>
              <select
                value={form.customer_id}
                onChange={(e) => {
                  setForm({ ...form, customer_id: e.target.value });
                  if (errors.customer_id)
                    setErrors({ ...errors, customer_id: undefined });
                }}
                className={`w-full rounded-lg border px-3 py-2 text-sm focus:ring-1 focus:outline-none ${
                  errors.customer_id
                    ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                    : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'
                }`}
              >
                <option value="">Select a customer</option>
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              {errors.customer_id && (
                <p className="mt-1 text-xs text-red-600">{errors.customer_id}</p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Plan
              </label>
              <select
                value={form.plan_id}
                onChange={(e) => {
                  setForm({ ...form, plan_id: e.target.value });
                  if (errors.plan_id)
                    setErrors({ ...errors, plan_id: undefined });
                }}
                className={`w-full rounded-lg border px-3 py-2 text-sm focus:ring-1 focus:outline-none ${
                  errors.plan_id
                    ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                    : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'
                }`}
              >
                <option value="">Select a plan</option>
                {plans.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              {errors.plan_id && (
                <p className="mt-1 text-xs text-red-600">{errors.plan_id}</p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Discount (%)
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={form.discount_pct}
                onChange={(e) =>
                  setForm({ ...form, discount_pct: Number(e.target.value) })
                }
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Term (months)
              </label>
              <input
                type="number"
                min={1}
                max={60}
                value={form.term_months}
                onChange={(e) =>
                  setForm({ ...form, term_months: Number(e.target.value) })
                }
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div className="col-span-2 flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  setErrors({});
                }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {createMutation.isPending ? 'Creating...' : 'Create Quote'}
              </button>
            </div>
          </form>
        </div>
      )}

      {rejectingId && (
        <div className="rounded-xl border border-red-200 bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900">
              Reject Quote
            </h2>
            <button
              onClick={() => {
                setRejectingId(null);
                setRejectReason('');
              }}
              className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Reason for rejection
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={3}
                placeholder="Please provide a reason..."
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setRejectingId(null);
                  setRejectReason('');
                }}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  rejectMutation.mutate({
                    id: rejectingId,
                    reason: rejectReason,
                  })
                }
                disabled={rejectMutation.isPending}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {rejectMutation.isPending ? 'Rejecting...' : 'Reject Quote'}
              </button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="py-12 text-center text-sm text-gray-500">
          Loading quotes...
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={quotes}
          emptyMessage="No quotes yet. Click 'Create Quote' to get started."
        />
      )}
    </div>
  );
}
