import * as React from 'react';
import { CheckCircle2, XCircle, Info, AlertTriangle } from 'lucide-react';
import { cn } from '../../lib/utils';

type ToastKind = 'success' | 'error' | 'info' | 'warning';

interface ToastAction {
  label: string;
  onClick: () => void;
}

interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  description?: string;
  actions?: ToastAction[];
}

export type ToastOptions = {
  title: string;
  description?: string;
  variant?: 'default' | 'destructive' | 'success';
  actions?: ToastAction[];
  durationMs?: number;
};

interface ToastFn {
  (kind: ToastKind, title: string, description?: string): void;
  (options: ToastOptions): void;
}

const ToastContext = React.createContext<{
  toast: ToastFn;
}>({ toast: () => {} });

export const useToast = () => React.useContext(ToastContext);

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);

  const toast: ToastFn = React.useCallback(
    (kindOrOptions: ToastKind | ToastOptions, maybeTitle?: string, maybeDesc?: string) => {
      let kind: ToastKind = 'info';
      let title = '';
      let description: string | undefined = undefined;

      if (typeof kindOrOptions === 'object') {
        title = kindOrOptions.title;
        description = kindOrOptions.description;
        kind = kindOrOptions.variant === 'destructive' ? 'error' : kindOrOptions.variant === 'success' ? 'success' : 'info';
      } else {
        kind = kindOrOptions;
        title = maybeTitle || '';
        description = maybeDesc;
      }

      const id = nextId++;
      const actions = typeof kindOrOptions === 'object' ? kindOrOptions.actions : undefined;
      const durationMs = (typeof kindOrOptions === 'object' && kindOrOptions.durationMs) || 5200;
      setToasts((t) => [...t, { id, kind, title, description, actions }]);
      window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), durationMs);
    },
    []
  );

  const dismiss = (id: number) => setToasts((t) => t.filter((x) => x.id !== id));

  const icons: Record<ToastKind, React.ReactNode> = {
    success: <CheckCircle2 className="h-5 w-5 text-emerald-600" />,
    error: <XCircle className="h-5 w-5 text-red-600" />,
    info: <Info className="h-5 w-5 text-brand-700" />,
    warning: <AlertTriangle className="h-5 w-5 text-amber-600" />,
  };

  const borders: Record<ToastKind, string> = {
    success: 'border-emerald-200',
    error: 'border-red-200',
    info: 'border-brand-200',
    warning: 'border-amber-200',
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto flex items-start gap-3 rounded-lg border bg-white p-4 shadow-lg',
              borders[t.kind],
            )}
          >
            <div className="mt-0.5 shrink-0">{icons[t.kind]}</div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-slate-900">{t.title}</div>
              {t.description && <div className="mt-0.5 break-words text-sm text-slate-600">{t.description}</div>}
              {t.actions && t.actions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {t.actions.map((a, i) => (
                    <button
                      key={i}
                      onClick={() => {
                        a.onClick();
                        dismiss(t.id);
                      }}
                      className={cn(
                        'rounded-md px-2.5 py-1 text-xs font-semibold transition-colors',
                        i === 0
                          ? 'bg-brand-700 text-white hover:bg-brand-800'
                          : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                      )}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              aria-label="Dismiss notification"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
