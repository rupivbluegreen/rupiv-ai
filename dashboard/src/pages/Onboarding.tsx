import { useState, useCallback } from 'react';
import {
  onboardingSignup,
  onboardingUpgrade,
  sendTestEvent,
  fetchPlans,
  type SignupResult,
  type Plan,
} from '../lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Step = 1 | 2 | 3 | 4 | 5;

interface FormData {
  company_name: string;
  email: string;
  country_code: string;
  is_business: boolean;
  vat_number: string;
}

// ---------------------------------------------------------------------------
// CSS-only confetti animation (injected once)
// ---------------------------------------------------------------------------

const confettiCSS = `
@keyframes confetti-fall {
  0%   { transform: translateY(-20px) rotate(0deg); opacity: 1; }
  100% { transform: translateY(600px) rotate(720deg); opacity: 0; }
}
@keyframes confetti-fade-out {
  0%   { opacity: 1; }
  80%  { opacity: 1; }
  100% { opacity: 0; }
}
.confetti-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 50;
  animation: confetti-fade-out 4s ease-out forwards;
}
.confetti-piece {
  position: absolute;
  width: 10px;
  height: 10px;
  top: -20px;
  animation: confetti-fall 3s ease-in forwards;
}
`;

function Confetti() {
  const colors = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
  const pieces = Array.from({ length: 40 }, (_, i) => ({
    id: i,
    left: `${Math.random() * 100}%`,
    delay: `${Math.random() * 1.5}s`,
    color: colors[i % colors.length],
    rotation: Math.random() > 0.5 ? 'rounded-full' : '',
    size: 6 + Math.random() * 8,
  }));

  return (
    <>
      <style>{confettiCSS}</style>
      <div className="confetti-container">
        {pieces.map((p) => (
          <div
            key={p.id}
            className={`confetti-piece ${p.rotation}`}
            style={{
              left: p.left,
              animationDelay: p.delay,
              backgroundColor: p.color,
              width: p.size,
              height: p.size,
              borderRadius: p.rotation ? '50%' : '2px',
            }}
          />
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Step indicator
// ---------------------------------------------------------------------------

const STEP_LABELS = [
  'Create Account',
  'API Key',
  'First Event',
  'Choose Plan',
  'All Set',
];

function StepIndicator({ current }: { current: Step }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-10">
      {STEP_LABELS.map((label, idx) => {
        const stepNum = (idx + 1) as Step;
        const isActive = stepNum === current;
        const isDone = stepNum < current;
        return (
          <div key={label} className="flex items-center gap-2">
            {idx > 0 && (
              <div
                className={`h-px w-8 ${isDone ? 'bg-indigo-500' : 'bg-gray-300'}`}
              />
            )}
            <div className="flex flex-col items-center">
              <div
                className={`
                  w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold
                  ${isActive ? 'bg-indigo-600 text-white' : ''}
                  ${isDone ? 'bg-indigo-500 text-white' : ''}
                  ${!isActive && !isDone ? 'bg-gray-200 text-gray-500' : ''}
                `}
              >
                {isDone ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  stepNum
                )}
              </div>
              <span
                className={`text-xs mt-1 whitespace-nowrap ${
                  isActive ? 'text-indigo-700 font-medium' : 'text-gray-400'
                }`}
              >
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1 : Create Your Account
// ---------------------------------------------------------------------------

function Step1({
  form,
  setForm,
  onSubmit,
  loading,
  error,
}: {
  form: FormData;
  setForm: React.Dispatch<React.SetStateAction<FormData>>;
  onSubmit: () => void;
  loading: boolean;
  error: string | null;
}) {
  return (
    <div className="max-w-md mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Create Your Account</h2>
      <p className="text-gray-500 mb-8">
        Start billing for outcomes in under 5 minutes. No credit card required.
      </p>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Company name
          </label>
          <input
            type="text"
            value={form.company_name}
            onChange={(e) => setForm((f) => ({ ...f, company_name: e.target.value }))}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
            placeholder="Acme AI B.V."
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Work email
          </label>
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
            placeholder="you@acme-ai.com"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Country
            </label>
            <select
              value={form.country_code}
              onChange={(e) => setForm((f) => ({ ...f, country_code: e.target.value }))}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none bg-white"
            >
              <option value="NL">Netherlands</option>
              <option value="DE">Germany</option>
              <option value="FR">France</option>
              <option value="BE">Belgium</option>
              <option value="AT">Austria</option>
              <option value="ES">Spain</option>
              <option value="IT">Italy</option>
              <option value="IE">Ireland</option>
              <option value="SE">Sweden</option>
              <option value="FI">Finland</option>
              <option value="PT">Portugal</option>
              <option value="GB">United Kingdom</option>
              <option value="US">United States</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Account type
            </label>
            <select
              value={form.is_business ? 'business' : 'personal'}
              onChange={(e) =>
                setForm((f) => ({ ...f, is_business: e.target.value === 'business' }))
              }
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none bg-white"
            >
              <option value="business">Business (B2B)</option>
              <option value="personal">Personal</option>
            </select>
          </div>
        </div>

        {form.is_business && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              VAT number <span className="text-gray-400">(optional)</span>
            </label>
            <input
              type="text"
              value={form.vat_number}
              onChange={(e) => setForm((f) => ({ ...f, vat_number: e.target.value }))}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
              placeholder="NL123456789B01"
            />
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          onClick={onSubmit}
          disabled={loading || !form.company_name.trim() || !form.email.trim()}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Creating your account...' : 'Get Started'}
        </button>
      </div>

      <p className="text-xs text-gray-400 text-center mt-6">
        Free tier includes 10,000 events/month and 3 customers. No credit card required.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2 : Your API Key
// ---------------------------------------------------------------------------

function Step2({
  apiKey,
  onNext,
}: {
  apiKey: string;
  onNext: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(apiKey).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [apiKey]);

  const maskedKey = apiKey.slice(0, 12) + '...' + apiKey.slice(-6);

  return (
    <div className="max-w-lg mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Your API Key</h2>
      <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800 mb-6">
        <strong>Important:</strong> This key is shown only once. Copy it now and store it securely.
        You will not be able to see it again.
      </div>

      <div className="rounded-lg bg-gray-900 p-4 mb-6">
        <div className="flex items-center justify-between">
          <code className="text-green-400 text-sm font-mono break-all">{apiKey}</code>
          <button
            onClick={handleCopy}
            className="ml-3 shrink-0 rounded-md bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-200 hover:bg-gray-600 transition-colors"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
      </div>

      <h3 className="text-sm font-semibold text-gray-700 mb-3">Quick Start</h3>
      <div className="rounded-lg bg-gray-50 border border-gray-200 p-4 mb-6">
        <pre className="text-sm text-gray-800 overflow-x-auto whitespace-pre">
{`pip install rupiv-sdk

import rupiv
client = rupiv.Client(api_key="${maskedKey}")
client.track_outcome("ticket_resolved", customer_id="cust_123")`}
        </pre>
      </div>

      <button
        onClick={onNext}
        className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
      >
        I've saved my key
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3 : Send Your First Event
// ---------------------------------------------------------------------------

function Step3({
  signupResult,
  onNext,
}: {
  signupResult: SignupResult;
  onNext: () => void;
}) {
  const [metric, setMetric] = useState('ticket_resolved');
  const [custId, setCustId] = useState('cust_123');
  const [propsJson, setPropsJson] = useState('{"resolution_time": 45, "csat_score": 4.8}');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  const handleSend = async () => {
    setSending(true);
    setResult(null);
    try {
      let properties: Record<string, unknown> = {};
      try {
        properties = JSON.parse(propsJson);
      } catch {
        setResult({ success: false, message: 'Invalid JSON in properties field' });
        setSending(false);
        return;
      }

      const res = await sendTestEvent({
        type: 'outcome',
        metric,
        customer_id: signupResult.customer_id,
        properties: { ...properties, test_customer_id: custId },
        idempotency_key: `onb_test_${Date.now()}`,
      });
      setResult({
        success: true,
        message: `Event accepted (ID: ${res.event_id.slice(0, 8)}...)`,
      });
    } catch (err) {
      setResult({
        success: false,
        message: err instanceof Error ? err.message : 'Failed to send event',
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Send Your First Event</h2>
      <p className="text-gray-500 mb-6">
        Try sending a test event to see how outcome tracking works.
      </p>

      <div className="space-y-4 mb-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Metric</label>
          <input
            type="text"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Customer ID</label>
          <input
            type="text"
            value={custId}
            onChange={(e) => setCustId(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Properties (JSON)</label>
          <textarea
            value={propsJson}
            onChange={(e) => setPropsJson(e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none resize-none"
          />
        </div>
      </div>

      {result && (
        <div
          className={`rounded-lg border p-3 text-sm mb-4 ${
            result.success
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}
        >
          {result.success ? (
            <span>
              <svg className="w-4 h-4 inline mr-1 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              {result.message}
            </span>
          ) : (
            result.message
          )}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={handleSend}
          disabled={sending || !metric.trim()}
          className="flex-1 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {sending ? 'Sending...' : 'Send Test Event'}
        </button>
        <button
          onClick={onNext}
          className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          Skip for now
        </button>
      </div>

      {result?.success && (
        <button
          onClick={onNext}
          className="w-full mt-3 rounded-lg bg-green-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-green-700 transition-colors"
        >
          Continue
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 4 : Choose Your Plan
// ---------------------------------------------------------------------------

interface PlanCard {
  id: string | null;
  name: string;
  price: string;
  period: string;
  features: string[];
  isCurrent: boolean;
  cta: string;
  highlight: boolean;
}

const DEFAULT_PLANS: PlanCard[] = [
  {
    id: null,
    name: 'Free',
    price: '0',
    period: '/mo',
    features: ['10,000 events/month', '3 customers', 'Community support', 'Basic analytics'],
    isCurrent: true,
    cta: 'Current plan',
    highlight: false,
  },
  {
    id: null,
    name: 'Growth',
    price: '149',
    period: '/mo',
    features: ['100,000 events/month', '50 customers', 'Email support', 'Full analytics', 'Pricing Studio'],
    isCurrent: false,
    cta: 'Upgrade',
    highlight: true,
  },
  {
    id: null,
    name: 'Scale',
    price: '499',
    period: '/mo',
    features: ['1M events/month', 'Unlimited customers', 'Priority support', 'IFRS 15 compliance', 'Multi-entity', 'Custom integrations'],
    isCurrent: false,
    cta: 'Upgrade',
    highlight: false,
  },
  {
    id: null,
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    features: ['Unlimited events', 'Unlimited customers', 'Dedicated support', 'SLA guarantee', 'Custom contracts', 'On-premise option'],
    isCurrent: false,
    cta: 'Contact Sales',
    highlight: false,
  },
];

function Step4({
  signupResult,
  onNext,
}: {
  signupResult: SignupResult;
  onNext: () => void;
}) {
  const [plans, setPlans] = useState<PlanCard[]>(DEFAULT_PLANS);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [upgraded, setUpgraded] = useState(false);

  // Attempt to load real plans and map them to the card layout
  useState(() => {
    fetchPlans()
      .then((apiPlans: Plan[]) => {
        if (apiPlans.length === 0) return;
        const mapped = DEFAULT_PLANS.map((card) => {
          const match = apiPlans.find(
            (p) => p.name.toLowerCase() === card.name.toLowerCase()
          );
          return match ? { ...card, id: match.id } : card;
        });
        setPlans(mapped);
      })
      .catch(() => {
        // keep defaults
      });
  });

  const handleUpgrade = async (plan: PlanCard) => {
    if (!plan.id || plan.name === 'Enterprise') return;
    setUpgrading(plan.name);
    try {
      await onboardingUpgrade({
        customer_id: signupResult.customer_id,
        plan_id: plan.id,
      });
      setUpgraded(true);
      setPlans((prev) =>
        prev.map((p) => ({
          ...p,
          isCurrent: p.name === plan.name,
          cta: p.name === plan.name ? 'Current plan' : p.cta,
        }))
      );
    } catch {
      // Silently handle - user can retry
    } finally {
      setUpgrading(null);
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">Choose Your Plan</h2>
      <p className="text-gray-500 mb-8 text-center">
        You're on the Free plan. Upgrade anytime to unlock more capacity.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {plans.map((plan) => (
          <div
            key={plan.name}
            className={`
              rounded-xl border p-5 flex flex-col
              ${plan.highlight ? 'border-indigo-500 ring-2 ring-indigo-100 bg-white' : 'border-gray-200 bg-white'}
              ${plan.isCurrent ? 'border-green-300 bg-green-50/30' : ''}
            `}
          >
            {plan.highlight && (
              <span className="text-xs font-semibold text-indigo-600 mb-2">Most popular</span>
            )}
            <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
            <div className="mt-2 mb-4">
              {plan.price === 'Custom' ? (
                <span className="text-2xl font-bold text-gray-900">Custom</span>
              ) : (
                <>
                  <span className="text-3xl font-bold text-gray-900">
                    {plan.price === '0' ? 'Free' : `\u20AC${plan.price}`}
                  </span>
                  {plan.period && (
                    <span className="text-sm text-gray-500">{plan.period}</span>
                  )}
                </>
              )}
            </div>
            <ul className="space-y-2 mb-6 flex-1">
              {plan.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm text-gray-600">
                  <svg className="w-4 h-4 text-green-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  {f}
                </li>
              ))}
            </ul>
            {plan.isCurrent ? (
              <div className="rounded-lg bg-green-100 text-green-700 text-center py-2 text-sm font-medium">
                Current plan
              </div>
            ) : plan.name === 'Enterprise' ? (
              <a
                href="mailto:sales@rupiv.ai"
                className="block rounded-lg border border-gray-300 text-center py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Contact Sales
              </a>
            ) : (
              <button
                onClick={() => handleUpgrade(plan)}
                disabled={upgrading === plan.name || !plan.id}
                className={`
                  w-full rounded-lg py-2 text-sm font-semibold transition-colors
                  ${plan.highlight
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                    : 'border border-indigo-600 text-indigo-600 hover:bg-indigo-50'
                  }
                  disabled:opacity-50 disabled:cursor-not-allowed
                `}
              >
                {upgrading === plan.name ? 'Upgrading...' : plan.cta}
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="text-center">
        <button
          onClick={onNext}
          className={`
            rounded-lg px-6 py-2.5 text-sm font-semibold transition-colors
            ${upgraded
              ? 'bg-indigo-600 text-white hover:bg-indigo-700'
              : 'text-gray-500 hover:text-gray-700 underline underline-offset-2'
            }
          `}
        >
          {upgraded ? 'Continue' : 'Continue with Free'}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 5 : You're All Set!
// ---------------------------------------------------------------------------

function Step5({ signupResult }: { signupResult: SignupResult }) {
  return (
    <div className="max-w-md mx-auto text-center">
      <Confetti />

      {/* Checkmark circle */}
      <div className="mx-auto w-20 h-20 rounded-full bg-green-100 flex items-center justify-center mb-6">
        <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      </div>

      <h2 className="text-2xl font-bold text-gray-900 mb-2">You're All Set!</h2>
      <p className="text-gray-500 mb-8">
        Your Rupiv.ai account is ready. Here's a summary of what was created:
      </p>

      <div className="rounded-xl border border-gray-200 bg-white p-5 text-left mb-8 space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Customer ID</span>
          <code className="text-gray-800 font-mono text-xs">
            {signupResult.customer_id.slice(0, 8)}...
          </code>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Subscription</span>
          <code className="text-gray-800 font-mono text-xs">
            {signupResult.subscription_id.slice(0, 8)}...
          </code>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">API Key</span>
          <span className="text-green-600 font-medium text-xs">Saved securely</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <a
          href={signupResult.dashboard_url}
          className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
        >
          Open Dashboard
        </a>
        <a
          href="/docs"
          className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          API Docs
        </a>
        <a
          href="https://github.com/rupiv/rupiv-sdk-python"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          SDK Guide
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Onboarding Wizard
// ---------------------------------------------------------------------------

export default function Onboarding() {
  const [step, setStep] = useState<Step>(1);
  const [form, setForm] = useState<FormData>({
    company_name: '',
    email: '',
    country_code: 'NL',
    is_business: true,
    vat_number: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signupResult, setSignupResult] = useState<SignupResult | null>(null);

  const handleSignup = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await onboardingSignup({
        company_name: form.company_name.trim(),
        email: form.email.trim(),
        country_code: form.country_code,
        is_business: form.is_business,
        vat_number: form.vat_number.trim() || null,
      });
      setSignupResult(result);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Signup failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-indigo-50/30 flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white/80 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <span className="text-white font-bold text-sm">R</span>
            </div>
            <span className="font-bold text-gray-900">Rupiv.ai</span>
          </div>
          <span className="text-sm text-gray-400">Self-serve onboarding</span>
        </div>
      </header>

      {/* Body */}
      <main className="flex-1 flex flex-col justify-center px-6 py-12">
        <div className="max-w-5xl mx-auto w-full">
          <StepIndicator current={step} />

          {step === 1 && (
            <Step1
              form={form}
              setForm={setForm}
              onSubmit={handleSignup}
              loading={loading}
              error={error}
            />
          )}

          {step === 2 && signupResult && (
            <Step2
              apiKey={signupResult.api_key}
              onNext={() => setStep(3)}
            />
          )}

          {step === 3 && signupResult && (
            <Step3
              signupResult={signupResult}
              onNext={() => setStep(4)}
            />
          )}

          {step === 4 && signupResult && (
            <Step4
              signupResult={signupResult}
              onNext={() => setStep(5)}
            />
          )}

          {step === 5 && signupResult && (
            <Step5 signupResult={signupResult} />
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-100 py-4">
        <p className="text-center text-xs text-gray-400">
          Rupiv.ai -- Outcome-based billing for AI companies in Europe
        </p>
      </footer>
    </div>
  );
}
