import { useState } from 'react';
import { CheckCircle2, XCircle, Play } from 'lucide-react';

interface BillableCondition {
  field: string;
  operator: string;
  value: string | number | boolean;
}

interface PricingRuleMatch {
  metric: string;
  price_per_outcome: number;
  billable_when: BillableCondition[];
}

// Sample pricing rules for local evaluation
const SAMPLE_RULES: PricingRuleMatch[] = [
  {
    metric: 'ticket_resolved',
    price_per_outcome: 0.99,
    billable_when: [
      { field: 'escalated', operator: 'eq', value: false },
      { field: 'resolution_time', operator: 'lt', value: 300 },
      { field: 'csat_score', operator: 'gte', value: 3.0 },
    ],
  },
  {
    metric: 'fraud_prevented',
    price_per_outcome: 2.5,
    billable_when: [
      { field: 'confidence', operator: 'gte', value: 0.85 },
      { field: 'false_positive', operator: 'eq', value: false },
    ],
  },
  {
    metric: 'document_processed',
    price_per_outcome: 0.15,
    billable_when: [
      { field: 'accuracy', operator: 'gte', value: 0.95 },
      { field: 'pages', operator: 'lte', value: 50 },
    ],
  },
];

const DEFAULT_EVENT = JSON.stringify(
  {
    type: 'outcome',
    metric: 'ticket_resolved',
    properties: {
      escalated: false,
      resolution_time: 45,
      csat_score: 4.8,
    },
  },
  null,
  2
);

function evaluateCondition(
  cond: BillableCondition,
  properties: Record<string, unknown>
): boolean {
  const val = properties[cond.field];
  if (val === undefined) return false;

  switch (cond.operator) {
    case 'eq':
      return val === cond.value;
    case 'neq':
      return val !== cond.value;
    case 'lt':
      return Number(val) < Number(cond.value);
    case 'lte':
      return Number(val) <= Number(cond.value);
    case 'gt':
      return Number(val) > Number(cond.value);
    case 'gte':
      return Number(val) >= Number(cond.value);
    default:
      return false;
  }
}

interface RuleResult {
  rule: PricingRuleMatch;
  conditionResults: { condition: BillableCondition; pass: boolean }[];
  allPass: boolean;
}

const operatorLabels: Record<string, string> = {
  lt: '<',
  lte: '<=',
  gt: '>',
  gte: '>=',
  eq: '=',
  neq: '!=',
};

export default function OutcomeValidator() {
  const [eventJson, setEventJson] = useState(DEFAULT_EVENT);
  const [results, setResults] = useState<RuleResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleTest = () => {
    setError(null);
    setResults(null);

    let parsed: { metric?: string; properties?: Record<string, unknown> };
    try {
      parsed = JSON.parse(eventJson);
    } catch {
      setError('Invalid JSON. Please check the format and try again.');
      return;
    }

    const properties = parsed.properties ?? {};
    const metric = parsed.metric;

    const ruleResults: RuleResult[] = SAMPLE_RULES.filter(
      (r) => !metric || r.metric === metric
    ).map((rule) => {
      const conditionResults = rule.billable_when.map((cond) => ({
        condition: cond,
        pass: evaluateCondition(cond, properties),
      }));
      return {
        rule,
        conditionResults,
        allPass: conditionResults.every((cr) => cr.pass),
      };
    });

    setResults(ruleResults);
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="text-base font-semibold text-gray-900">
          Outcome Rule Tester
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          Paste an event payload to test which pricing rules would match and
          whether the outcome is billable.
        </p>

        <div className="mt-4">
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Event Properties (JSON)
          </label>
          <textarea
            value={eventJson}
            onChange={(e) => setEventJson(e.target.value)}
            rows={10}
            className="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none"
            spellCheck={false}
          />
        </div>

        {error && (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="mt-4">
          <button
            onClick={handleTest}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            <Play className="h-4 w-4" />
            Test Rules
          </button>
        </div>
      </div>

      {results !== null && (
        <div className="space-y-4">
          {results.length === 0 ? (
            <div className="rounded-xl border border-gray-200 bg-white px-6 py-12 text-center text-sm text-gray-500">
              No matching pricing rules found for this metric.
            </div>
          ) : (
            results.map((result, idx) => (
              <div
                key={idx}
                className={`rounded-xl border p-5 ${
                  result.allPass
                    ? 'border-green-200 bg-green-50'
                    : 'border-red-200 bg-red-50'
                }`}
              >
                <div className="flex items-center gap-3">
                  {result.allPass ? (
                    <CheckCircle2 className="h-5 w-5 text-green-600" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-600" />
                  )}
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">
                      {result.rule.metric}
                    </h3>
                    <p className="text-xs text-gray-500">
                      Price per outcome: EUR {result.rule.price_per_outcome.toFixed(2)}
                    </p>
                  </div>
                  <span
                    className={`ml-auto rounded-full px-3 py-1 text-xs font-medium ${
                      result.allPass
                        ? 'bg-green-100 text-green-700'
                        : 'bg-red-100 text-red-700'
                    }`}
                  >
                    {result.allPass ? 'Billable' : 'Not billable'}
                  </span>
                </div>

                <div className="mt-4 space-y-2">
                  <p className="text-xs font-medium text-gray-500 uppercase">
                    Conditions
                  </p>
                  {result.conditionResults.map((cr, ci) => (
                    <label
                      key={ci}
                      className="flex items-center gap-3 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={cr.pass}
                        readOnly
                        className="h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
                      />
                      <span
                        className={
                          cr.pass ? 'text-gray-700' : 'text-red-600'
                        }
                      >
                        {cr.condition.field}{' '}
                        {operatorLabels[cr.condition.operator] ??
                          cr.condition.operator}{' '}
                        {String(cr.condition.value)}
                      </span>
                      {cr.pass ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                      ) : (
                        <XCircle className="h-3.5 w-3.5 text-red-500" />
                      )}
                    </label>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
