import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Play, Trash2 } from 'lucide-react';

const BASE_URL = import.meta.env.VITE_API_URL ?? '/v1';

interface TransformationRule {
  id: string;
  name: string;
  description: string | null;
  source_metric: string;
  target_metric: string;
  is_active: boolean;
  priority: number;
  steps: Record<string, unknown>[];
  created_at: string;
}

interface TestResult {
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  dropped: boolean;
}

async function fetchRules(): Promise<TransformationRule[]> {
  const res = await fetch(`${BASE_URL}/transformations`);
  if (!res.ok) return [];
  return res.json();
}

async function testTransformation(
  event: Record<string, unknown>,
  steps: Record<string, unknown>[],
): Promise<TestResult> {
  const res = await fetch(`${BASE_URL}/transformations/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event, steps }),
  });
  return res.json();
}

export default function Transformations() {
  const queryClient = useQueryClient();
  const [testInput, setTestInput] = useState('{\n  "metric": "raw_event",\n  "properties": {\n    "status": "completed",\n    "value": 100\n  }\n}');
  const [testSteps, setTestSteps] = useState('[{"type": "filter", "field": "properties.status", "operator": "eq", "value": "completed"}]');
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  const { data: rules = [] } = useQuery({
    queryKey: ['transformation-rules'],
    queryFn: fetchRules,
  });

  const handleTest = async () => {
    try {
      const event = JSON.parse(testInput);
      const steps = JSON.parse(testSteps);
      const result = await testTransformation(event, steps);
      setTestResult(result);
    } catch (e) {
      setTestResult({ input: {}, output: null, dropped: false });
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Data Transformations</h1>
        <p className="mt-1 text-sm text-gray-500">
          Define rules to transform raw events into billing-ready format.
        </p>
      </div>

      {/* Test/Preview Panel */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Preview</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Sample Event (JSON)</label>
            <textarea
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              rows={6}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Steps (JSON array)</label>
            <textarea
              value={testSteps}
              onChange={(e) => setTestSteps(e.target.value)}
              rows={6}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-sm"
            />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-4">
          <button
            onClick={handleTest}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            <Play className="h-4 w-4" />
            Run Preview
          </button>
          {testResult && (
            <div className="flex-1">
              {testResult.dropped ? (
                <p className="text-sm font-medium text-red-600">Event was dropped by filter</p>
              ) : (
                <pre className="rounded-lg bg-gray-50 p-3 text-xs overflow-auto max-h-40">
                  {JSON.stringify(testResult.output, null, 2)}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Rules list */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Rules ({rules.length})</h2>
        {rules.length === 0 ? (
          <p className="text-sm text-gray-500">
            No transformation rules defined. Create rules via the API.
          </p>
        ) : (
          <div className="space-y-3">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-center justify-between rounded-lg border border-gray-100 p-4"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-gray-900">{rule.name}</p>
                    {!rule.is_active && (
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
                        inactive
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500">
                    {rule.source_metric} &rarr; {rule.target_metric} &middot;{' '}
                    {rule.steps.length} step{rule.steps.length !== 1 ? 's' : ''} &middot;{' '}
                    priority {rule.priority}
                  </p>
                  {rule.description && (
                    <p className="mt-1 text-xs text-gray-400">{rule.description}</p>
                  )}
                </div>
                <div className="text-xs text-gray-400">
                  {new Date(rule.created_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
