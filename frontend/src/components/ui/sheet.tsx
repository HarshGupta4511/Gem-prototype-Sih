import * as React from 'react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';

interface SheetContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}
const SheetContext = React.createContext<SheetContextValue>({ open: false, setOpen: () => {} });

export function Sheet({
  open,
  onOpenChange,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onOpenChange(false);
    };
    if (open) window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onOpenChange]);

  React.useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  return <SheetContext.Provider value={{ open, setOpen: onOpenChange }}>{children}</SheetContext.Provider>;
}

export function SheetContent({
  className,
  children,
  title,
}: {
  className?: string;
  children: React.ReactNode;
  title?: React.ReactNode;
}) {
  const { open, setOpen } = React.useContext(SheetContext);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(false)} aria-hidden />
      <aside
        role="dialog"
        aria-modal="true"
        className={cn(
          'absolute right-0 top-0 flex h-full w-full max-w-xl flex-col border-l border-slate-200 bg-white shadow-2xl',
          'animate-in slide-in-from-right',
          className,
        )}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div className="text-base font-semibold text-slate-900">{title}</div>
          <button
            onClick={() => setOpen(false)}
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close panel"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </aside>
    </div>
  );
}
