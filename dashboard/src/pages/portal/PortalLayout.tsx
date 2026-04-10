import { Outlet, NavLink } from 'react-router-dom';
import { FileText, Activity, LayoutDashboard, LogOut } from 'lucide-react';
import clsx from 'clsx';
import { clearPortalToken } from '../../lib/portal-api';

const portalNavItems = [
  { to: '/portal', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/portal/invoices', label: 'Invoices', icon: FileText, end: false },
  { to: '/portal/usage', label: 'Usage', icon: Activity, end: false },
];

export default function PortalLayout() {
  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="flex h-screen w-56 flex-col border-r border-gray-200 bg-white">
        <div className="flex h-16 items-center gap-2 border-b border-gray-200 px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
            R
          </div>
          <span className="text-lg font-semibold text-gray-900">Portal</span>
        </div>

        <nav className="flex-1 space-y-1 px-3 py-4">
          {portalNavItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-blue-50 text-blue-600'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                )
              }
            >
              <Icon className="h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-gray-200 p-3">
          <button
            onClick={() => {
              clearPortalToken();
              window.location.href = '/';
            }}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
          >
            <LogOut className="h-5 w-5" />
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}
