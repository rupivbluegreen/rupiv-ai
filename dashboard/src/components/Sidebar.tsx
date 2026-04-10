import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Building2,
  CreditCard,
  FlaskConical,
  ClipboardList,
  Activity,
  FileText,
  BookOpen,
  Shield,
  BarChart3,
  Bell,
  FileOutput,
  Shuffle,
} from 'lucide-react';
import clsx from 'clsx';

const navItems = [
  { to: '/overview', label: 'Overview', icon: LayoutDashboard },
  { to: '/customers', label: 'Customers', icon: Users },
  { to: '/entities', label: 'Entities', icon: Building2 },
  { to: '/plans', label: 'Plans', icon: CreditCard },
  { to: '/pricing-studio', label: 'Pricing Studio', icon: FlaskConical },
  { to: '/quotes', label: 'Quotes', icon: ClipboardList },
  { to: '/events', label: 'Events', icon: Activity },
  { to: '/invoices', label: 'Invoices', icon: FileText },
  { to: '/revenue', label: 'Revenue', icon: BookOpen },
  { to: '/policies', label: 'Policies', icon: Shield },
  { to: '/payment-analytics', label: 'Payment Analytics', icon: BarChart3 },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/erp-export', label: 'ERP Export', icon: FileOutput },
  { to: '/transformations', label: 'Transformations', icon: Shuffle },
];

export default function Sidebar() {
  return (
    <aside className="flex h-screen w-60 flex-col border-r border-gray-200 bg-white">
      <div className="flex h-16 items-center gap-2 border-b border-gray-200 px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
          R
        </div>
        <span className="text-lg font-semibold text-gray-900">Rupiv.ai</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/overview'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              )
            }
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
