import type { PolicyRule } from '../lib/api';

const actionColors: Record<string, { bg: string; text: string; border: string }> = {
  auto_approve: { bg: 'bg-green-50', text: 'text-green-700', border: 'border-green-200' },
  require_approval: { bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200' },
  reject: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
};

const triggerColors: Record<string, string> = {
  'invoice.generated': 'bg-blue-100 text-blue-700',
  'outcome.validated': 'bg-purple-100 text-purple-700',
  'quote.created': 'bg-cyan-100 text-cyan-700',
};

const operatorLabels: Record<string, string> = {
  lt: '<',
  lte: '<=',
  gt: '>',
  gte: '>=',
  eq: '=',
  neq: '!=',
};

interface PolicyBuilderProps {
  rules: PolicyRule[];
}

export default function PolicyBuilder({ rules }: PolicyBuilderProps) {
  if (rules.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center text-sm text-gray-500">
        No policy rules to display.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {rules.map((rule) => {
        const colors = actionColors[rule.action] ?? {
          bg: 'bg-gray-50',
          text: 'text-gray-700',
          border: 'border-gray-200',
        };

        return (
          <div
            key={rule.id}
            className={`rounded-xl border bg-white p-5 ${
              rule.active ? 'border-gray-200' : 'border-dashed border-gray-300 opacity-60'
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <h3 className="text-sm font-semibold text-gray-900">
                    {rule.name}
                  </h3>
                  {!rule.active && (
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                      Inactive
                    </span>
                  )}
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <span className="text-xs font-medium text-gray-500 uppercase">
                    When
                  </span>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      triggerColors[rule.trigger] ?? 'bg-gray-100 text-gray-700'
                    }`}
                  >
                    {rule.trigger}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium text-gray-500 uppercase">
                    If
                  </span>
                  {rule.conditions.map((cond, i) => (
                    <span key={i}>
                      {i > 0 && (
                        <span className="mr-2 text-xs font-medium text-gray-400">
                          AND
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs">
                        <span className="font-medium text-gray-700">
                          {cond.field}
                        </span>
                        <span className="font-mono text-gray-500">
                          {operatorLabels[cond.operator] ?? cond.operator}
                        </span>
                        <span className="font-semibold text-gray-900">
                          {String(cond.value)}
                        </span>
                      </span>
                    </span>
                  ))}
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <span className="text-xs font-medium text-gray-500 uppercase">
                    Then
                  </span>
                  <span
                    className={`inline-flex rounded-lg border px-3 py-1 text-xs font-medium ${colors.bg} ${colors.text} ${colors.border}`}
                  >
                    {rule.action.replace('_', ' ')}
                    {rule.approver && ` (${rule.approver})`}
                  </span>
                </div>
              </div>

              <div className="flex-shrink-0 text-right">
                <span className="text-xs text-gray-400">Priority</span>
                <p className="font-mono text-lg font-semibold text-gray-600">
                  {rule.priority}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
