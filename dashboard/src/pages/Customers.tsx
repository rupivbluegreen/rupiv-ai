import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, X } from 'lucide-react';
import DataTable, { type Column } from '../components/DataTable';
import { useToast } from '../components/Toast';
import { fetchCustomers, createCustomer, type Customer } from '../lib/api';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const columns: Column<Customer>[] = [
  {
    key: 'name',
    header: 'Name',
    render: (row) => (
      <span className="font-medium text-gray-900">{row.name}</span>
    ),
  },
  { key: 'email', header: 'Email' },
  { key: 'country', header: 'Country' },
  { key: 'currency', header: 'Currency' },
  {
    key: 'created_at',
    header: 'Created',
    render: (row) => new Date(row.created_at).toLocaleDateString(),
  },
];

interface FormErrors {
  name?: string;
  email?: string;
}

export default function Customers() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: '',
    email: '',
    country: '',
    currency: 'EUR',
  });
  const [errors, setErrors] = useState<FormErrors>({});

  const { data: customers = [], isLoading } = useQuery({
    queryKey: ['customers'],
    queryFn: fetchCustomers,
  });

  const mutation = useMutation({
    mutationFn: createCustomer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customers'] });
      queryClient.invalidateQueries({ queryKey: ['overview-stats'] });
      setShowForm(false);
      setForm({ name: '', email: '', country: '', currency: 'EUR' });
      setErrors({});
      showToast('Customer created successfully.', 'success');
    },
    onError: () => {
      showToast('Failed to create customer. Please try again.', 'error');
    },
  });

  const validate = (): boolean => {
    const newErrors: FormErrors = {};
    if (!form.name.trim()) {
      newErrors.name = 'Name is required.';
    }
    if (!form.email.trim()) {
      newErrors.email = 'Email is required.';
    } else if (!EMAIL_REGEX.test(form.email)) {
      newErrors.email = 'Please enter a valid email address.';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    mutation.mutate(form);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Customers</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your customer accounts.
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add Customer
        </button>
      </div>

      {showForm && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900">
              New Customer
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
                Name
              </label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => {
                  setForm({ ...form, name: e.target.value });
                  if (errors.name) setErrors({ ...errors, name: undefined });
                }}
                className={`w-full rounded-lg border px-3 py-2 text-sm focus:ring-1 focus:outline-none ${
                  errors.name
                    ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                    : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'
                }`}
              />
              {errors.name && (
                <p className="mt-1 text-xs text-red-600">{errors.name}</p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Email
              </label>
              <input
                type="text"
                value={form.email}
                onChange={(e) => {
                  setForm({ ...form, email: e.target.value });
                  if (errors.email) setErrors({ ...errors, email: undefined });
                }}
                className={`w-full rounded-lg border px-3 py-2 text-sm focus:ring-1 focus:outline-none ${
                  errors.email
                    ? 'border-red-300 focus:border-red-500 focus:ring-red-500'
                    : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500'
                }`}
              />
              {errors.email && (
                <p className="mt-1 text-xs text-red-600">{errors.email}</p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Country
              </label>
              <input
                type="text"
                required
                value={form.country}
                onChange={(e) => setForm({ ...form, country: e.target.value })}
                placeholder="NL"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Currency
              </label>
              <select
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
              >
                <option value="EUR">EUR</option>
                <option value="USD">USD</option>
                <option value="GBP">GBP</option>
              </select>
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
                disabled={mutation.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {mutation.isPending ? 'Creating...' : 'Create Customer'}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading ? (
        <div className="py-12 text-center text-sm text-gray-500">
          Loading customers...
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={customers}
          emptyMessage="No customers yet. Click 'Add Customer' to create one."
        />
      )}
    </div>
  );
}
