import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, X, List, GitBranch } from 'lucide-react';
import DataTable, { type Column } from '../components/DataTable';
import EntityTree from '../components/EntityTree';
import { useToast } from '../components/Toast';
import {
  fetchEntities,
  createEntity,
  type Entity,
  type CreateEntityInput,
} from '../lib/api';

const ENTITY_TYPES = ['BV', 'GmbH', 'SAS', 'Ltd'] as const;

const TYPE_BADGE_COLORS: Record<string, string> = {
  BV: 'bg-blue-100 text-blue-700',
  GmbH: 'bg-green-100 text-green-700',
  SAS: 'bg-purple-100 text-purple-700',
  Ltd: 'bg-amber-100 text-amber-700',
};

const columns: Column<Entity>[] = [
  {
    key: 'name',
    header: 'Name',
    render: (row) => (
      <span className="font-medium text-gray-900">{row.name}</span>
    ),
  },
  {
    key: 'entity_type',
    header: 'Type',
    render: (row) => {
      const color = TYPE_BADGE_COLORS[row.entity_type] ?? 'bg-gray-100 text-gray-700';
      return (
        <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${color}`}>
          {row.entity_type}
        </span>
      );
    },
  },
  { key: 'country_code', header: 'Country' },
  { key: 'currency', header: 'Currency' },
  {
    key: 'parent_id',
    header: 'Parent',
    render: (row) => (
      <span className="text-gray-500">{row.parent_id ?? '--'}</span>
    ),
  },
  { key: 'vat_number', header: 'VAT Number' },
];

interface FormErrors {
  name?: string;
}

const INITIAL_FORM: CreateEntityInput = {
  name: '',
  entity_type: 'BV',
  country_code: '',
  currency: 'EUR',
  parent_id: undefined,
  vat_number: '',
};

export default function Entities() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [viewMode, setViewMode] = useState<'table' | 'tree'>('table');
  const [form, setForm] = useState<CreateEntityInput>({ ...INITIAL_FORM });
  const [errors, setErrors] = useState<FormErrors>({});
  const [selectedEntityId, setSelectedEntityId] = useState<string>();

  const { data: entities = [], isLoading } = useQuery({
    queryKey: ['entities'],
    queryFn: () => fetchEntities(),
  });

  const mutation = useMutation({
    mutationFn: createEntity,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['entities'] });
      setShowForm(false);
      setForm({ ...INITIAL_FORM });
      setErrors({});
      showToast('Entity created successfully.', 'success');
    },
    onError: () => {
      showToast('Failed to create entity. Please try again.', 'error');
    },
  });

  const validate = (): boolean => {
    const newErrors: FormErrors = {};
    if (!form.name.trim()) {
      newErrors.name = 'Name is required.';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    const data = { ...form };
    if (!data.parent_id) delete data.parent_id;
    mutation.mutate(data);
  };

  // Build a lookup for parent names
  const entityMap = new Map(entities.map((e) => [e.id, e.name]));

  const columnsWithParentName: Column<Entity>[] = columns.map((col) => {
    if (col.key === 'parent_id') {
      return {
        ...col,
        render: (row: Entity) => (
          <span className="text-gray-500">
            {row.parent_id ? entityMap.get(row.parent_id) ?? row.parent_id : '--'}
          </span>
        ),
      };
    }
    return col;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Entities</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your legal entities and organizational hierarchy.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex rounded-lg border border-gray-300 bg-white p-0.5">
            <button
              onClick={() => setViewMode('table')}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                viewMode === 'table'
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <List className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('tree')}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                viewMode === 'tree'
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <GitBranch className="h-4 w-4" />
            </button>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add Entity
          </button>
        </div>
      </div>

      {showForm && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-900">
              New Entity
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
                placeholder="AcmeAI BV"
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
                Entity Type
              </label>
              <select
                value={form.entity_type}
                onChange={(e) =>
                  setForm({ ...form, entity_type: e.target.value as CreateEntityInput['entity_type'] })
                }
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
              >
                {ENTITY_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Country Code
              </label>
              <input
                type="text"
                required
                value={form.country_code}
                onChange={(e) => setForm({ ...form, country_code: e.target.value })}
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
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Parent Entity
              </label>
              <select
                value={form.parent_id ?? ''}
                onChange={(e) =>
                  setForm({ ...form, parent_id: e.target.value || undefined })
                }
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
              >
                <option value="">None (root entity)</option>
                {entities.map((ent) => (
                  <option key={ent.id} value={ent.id}>
                    {ent.name} ({ent.entity_type})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                VAT Number
              </label>
              <input
                type="text"
                required
                value={form.vat_number}
                onChange={(e) => setForm({ ...form, vat_number: e.target.value })}
                placeholder="NL123456789B01"
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
                disabled={mutation.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {mutation.isPending ? 'Creating...' : 'Create Entity'}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading ? (
        <div className="py-12 text-center text-sm text-gray-500">
          Loading entities...
        </div>
      ) : viewMode === 'table' ? (
        <DataTable
          columns={columnsWithParentName}
          data={entities}
          emptyMessage="No entities yet. Click 'Add Entity' to create one."
        />
      ) : (
        <EntityTree
          entities={entities}
          onSelect={setSelectedEntityId}
          selectedId={selectedEntityId}
        />
      )}
    </div>
  );
}
