import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Sidebar from './components/Sidebar';
import { ToastProvider } from './components/Toast';
import Overview from './pages/Overview';
import Customers from './pages/Customers';
import Plans from './pages/Plans';
import Events from './pages/Events';
import Invoices from './pages/Invoices';
import Entities from './pages/Entities';
import Quotes from './pages/Quotes';
import Revenue from './pages/Revenue';
import PricingStudio from './pages/PricingStudio';
import Policies from './pages/Policies';
import PaymentAnalytics from './pages/PaymentAnalytics';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <div className="flex h-screen bg-gray-50">
            <Sidebar />
            <main className="flex-1 overflow-y-auto p-8">
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
            </main>
          </div>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
