import { useEffect, useState, useCallback, createContext, useContext } from 'react';

interface ToastItem {
  id: number;
  message: string;
  variant: 'success' | 'error';
}

interface ToastContextType {
  showToast: (message: string, variant: 'success' | 'error') => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

let toastId = 0;

export function useToast(): ToastContextType {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((message: string, variant: 'success' | 'error') => {
    const id = ++toastId;
    setToasts((prev) => [...prev, { id, message, variant }]);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <ToastMessage key={toast.id} toast={toast} onDismiss={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastMessage({
  toast,
  onDismiss,
}: {
  toast: ToastItem;
  onDismiss: (id: number) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 3000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const bgColor =
    toast.variant === 'success'
      ? 'bg-green-600'
      : 'bg-red-600';

  return (
    <div
      className={`${bgColor} rounded-lg px-4 py-3 text-sm font-medium text-white shadow-lg transition-all animate-in fade-in slide-in-from-bottom-2`}
      role="alert"
    >
      {toast.message}
    </div>
  );
}
