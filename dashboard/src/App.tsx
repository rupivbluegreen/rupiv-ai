import React, { Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Sidebar from './components/Sidebar';
import { ToastProvider } from './components/Toast';

const Overview = React.lazy(() => import('./pages/Overview'));
const Customers = React.lazy(() => import('./pages/Customers'));
const Plans = React.lazy(() => import('./pages/Plans'));
const Events = React.lazy(() => import('./pages/Events'));
const Invoices = React.lazy(() => import('./pages/Invoices'));
const Entities = React.lazy(() => import('./pages/Entities'));
const Quotes = React.lazy(() => import('./pages/Quotes'));
const Revenue = React.lazy(() => import('./pages/Revenue'));
const PricingStudio = React.lazy(() => import('./pages/PricingStudio'));
const Policies = React.lazy(() => import('./pages/Policies'));
const PaymentAnalytics = React.lazy(() => import('./pages/PaymentAnalytics'));
const Onboarding = React.lazy(() => import('./pages/Onboarding'));

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AppLayout() {
  const location = useLocation();
  const isOnboarding = location.pathname === '/onboarding';

  if (isOnboarding) {
    return (
      <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          <Route path="/onboarding" element={<Onboarding />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-8">
        <Suspense fallback={<LoadingSpinner />}>
          <Routes>
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<Overview />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/plans" element={<Plans />} />
            <Route path="/events" element={<Events />} />
            <Route path="/invoices" element={<Invoices />} />
            <Route path="/entities" element={<Entities />} />
            <Route path="/quotes" element={<Quotes />} />
            <Route path="/revenue" element={<Revenue />} />
            <Route path="/pricing-studio" element={<PricingStudio />} />
            <Route path="/policies" element={<Policies />} />
            <Route path="/payment-analytics" element={<PaymentAnalytics />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AppLayout />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
