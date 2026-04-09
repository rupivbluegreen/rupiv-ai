import { useState } from 'react';
import { Plus, X, Play } from 'lucide-react';
import type { PricingRule } from '../lib/api';

interface ScenarioRule {
  metric: string;
  price_per_outcome: number;
  conditions: { key: string; value: string }[];
}

interface PricingSimulatorProps {
  planId: string;
  currentRules: PricingRule[];
  onSimulate: (scenario: {
    pricing_rules: {
      metric: string;
      price_per_outcome: number;
      billable_when: Record<string, unknown>;
    }[];
    date_range: { start: string; end: string };
  }) => void;
  isPending: boolean;
}

function conditionsToRecord(conditions: { key: string; value: string }[]): Record<string, unknown> {
  const record: Record<string, unknown> = {};
  for (const c of conditions) {
    if (!c.key) continue;
    const num = Number(c.value);
    if (c.value === 'true') record[c.key] = true;
    else if (c.value === 'false') record[c.key] = false;
    else if (!isNaN(num) && c.value !== '') record[c.key] = num;
    else record[c.key] = c.value;
  }
  return record;
}

export default function PricingSimulator({
  currentRules,
  onSimulate,
  isPending,
}: PricingSimulatorProps) {
  const today = new Date();
  const threeMonthsAgo = new Date(today.getFullYear(), today.getMonth() - 3, 1);
  const formatDate = (d: Date) => d.toISOString().split('T')[0];

  const [scenarioRules, setScenarioRules] = useState<ScenarioRule[]>(
    currentRules.map((r) => ({
      metric: r.metric,
      price_per_outcome: parseFloat(r.unit_price) || 0,
      conditions: [],
    }))
  );
  const [startDate, setStartDate] = useState(formatDate(threeMonthsAgo));
  const [endDate, setEndDate] = useState(formatDate(today));

  const updateRule = (idx: number, field: keyof ScenarioRule, value: unknown) => {
    const updated = [...scenarioRules];
    updated[idx] = { ...updated[idx], [field]: value };
    setScenarioRules(updated);
  };

  const addCondition = (ruleIdx: number) => {
    const updated = [...scenarioRules];
    updated[ruleIdx] = {
      ...updated[ruleIdx],
      conditions: [...updated[ruleIdx].conditions, { key: '', value: '' }],
    };
    setScenarioRules(updated);
  };

  const removeCondition = (ruleIdx: number, condIdx: number) => {
    const updated = [...scenarioRules];
    updated[ruleIdx] = {
      ...updated[ruleIdx],
      conditions: updated[ruleIdx].conditions.filter((_, i) => i !== condIdx),
    };
    setScenarioRules(updated);
  };

  const updateCondition = (
    ruleIdx: number,
    condIdx: number,
    field: 'key' | 'value',
    val: string
  ) => {
    const updated = [...scenarioRules];
    const conds = [...updated[ruleIdx].conditions];
    conds[condIdx] = { ...conds[condIdx], [field]: val };
    updated[ruleIdx] = { ...updated[ruleIdx], conditions: conds };
    setScenarioRules(updated);
  };

  const addRule = () => {
    setScenarioRules([
      ...scenarioRules,
      { metric: '', price_per_outcome: 0, conditions: [] },
    ]);
  };

  const removeRule = (idx: number) => {
    setScenarioRules(scenarioRules.filter((_, i) => i !== idx));
  };

  const handleSubmit = () => {
    onSimulate({
      pricing_rules: scenarioRules.map((r) => ({
        metric: r.metric,
        price_per_outcome: r.price_per_outcome,
        billable_when: conditionsToRecord(r.conditions),
      })),
      date_range: { start: startDate, end: endDate },
    });
  };

  return (
    <div className="space-y-5">
      {/* Current Rules (read-only) */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-700">
          Current Pricing Rules
        </h3>
        {currentRules.length === 0 ? (
          <p className="text-sm text-gray-400">No rules defined on this plan.</p>
        ) : (
          <div className="space-y-2">
            {currentRules.map((rule, idx) => (
              <div
                key={idx}
                className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm"
              >
                <span className="inline-flex rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
                  {rule.model}
                </span>
                <span className="font-medium text-gray-900">{rule.metric}</span>
                <span className="text-gray-500">at</span>
                <span className="font-mono text-gray-900">{rule.unit_price}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Scenario Section */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700">
            Scenario Rules
          </h3>
          <button
            type="button"
            onClick={addRule}
            className="text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            + Add Rule
          </button>
        </div>
        <div className="space-y-3">
          {scenarioRules.map((rule, ruleIdx) => (
            <div
              key={ruleIdx}
              className="rounded-lg border border-gray-200 bg-white p-4"
            >
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label className="mb-1 block text-xs text-gray-500">Metric</label>
                  <input
                    type="text"
                    value={rule.metric}
                    onChange={(e) => updateRule(ruleIdx, 'metric', e.target.value)}
                    placeholder="e.g. ticket_resolved"
                    className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                  />
                </div>
                <div className="w-40">
                  <label className="mb-1 block text-xs text-gray-500">
                    Price per Outcome
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={rule.price_per_outcome}
                    onChange={(e) =>
                      updateRule(ruleIdx, 'price_per_outcome', parseFloat(e.target.value) || 0)
                    }
                    className="w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                  />
                </div>
                {scenarioRules.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeRule(ruleIdx)}
                    className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>

              {/* Conditions */}
              <div className="mt-3">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-xs text-gray-500">Billable When Conditions</span>
                  <button
                    type="button"
                    onClick={() => addCondition(ruleIdx)}
                    className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700"
                  >
                    <Plus className="h-3 w-3" />
                    Add Condition
                  </button>
                </div>
                {rule.conditions.length === 0 && (
                  <p className="text-xs text-gray-400">No conditions (all outcomes billable).</p>
                )}
                <div className="space-y-2">
                  {rule.conditions.map((cond, condIdx) => (
                    <div key={condIdx} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={cond.key}
                        onChange={(e) =>
                          updateCondition(ruleIdx, condIdx, 'key', e.target.value)
                        }
                        placeholder="e.g. csat_score_gte"
                        className="flex-1 rounded-md border border-gray-300 px-2.5 py-1.5 text-xs focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                      />
                      <input
                        type="text"
                        value={cond.value}
                        onChange={(e) =>
                          updateCondition(ruleIdx, condIdx, 'value', e.target.value)
                        }
                        placeholder="e.g. 4.0"
                        className="w-32 rounded-md border border-gray-300 px-2.5 py-1.5 text-xs focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => removeCondition(ruleIdx, condIdx)}
                        className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Date Range */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Start Date
          </label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            End Date
          </label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Run Button */}
      <button
        onClick={handleSubmit}
        disabled={isPending || scenarioRules.length === 0}
        className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
      >
        <Play className="h-4 w-4" />
        {isPending ? 'Running...' : 'Run Simulation'}
      </button>
    </div>
  );
}
