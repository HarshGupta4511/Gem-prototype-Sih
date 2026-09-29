import * as React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, FileSearch, Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Skeleton } from '../ui/misc';

/** Contextual "← Back to …" link rendered above the page title. */
export function BackLink({ to, label, state }: { to: string; label: string; state?: unknown }) {
  return (
    <Link
      to={to}
      state={state}
      className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-900 hover:underline"
    >
      <ArrowLeft className="h-4 w-4" /> {label}
    </Link>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  back,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  back?: React.ReactNode;
}) {
  return (
    <div className="mb-6">
      {back && <div className="mb-2">{back}</div>}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
          {description && <p className="mt-1 max-w-3xl text-sm text-slate-500">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
      <div className="mb-3 rounded-full bg-slate-100 p-3 text-slate-400">
        {icon ?? <FileSearch className="h-6 w-6" />}
      </div>
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      {description && <p className="mt-1 max-w-md text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function LoadingBlock({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-3', className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}

export function LoadingOverlay({ label = 'Working…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <Loader2 className="h-5 w-5 animate-spin text-brand-700" />
      {label}
    </div>
  );
}

/** Circular compliance score ring (SVG). */
export function ScoreRing({
  score,
  size = 92,
  label,
}: {
  score: number | null | undefined;
  size?: number;
  label?: string;
}) {
  const v = score ?? 0;
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  const color = v >= 85 ? '#059669' : v >= 70 ? '#d97706' : '#dc2626';
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={9} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={9}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (c * Math.min(100, Math.max(0, v))) / 100}
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-bold text-slate-900 tnum">{score === null || score === undefined ? '—' : Math.round(v)}</span>
        {label && <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</span>}
      </div>
    </div>
  );
}

/** Key-value definition row used across detail pages. */
export function DetailRow({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <dt className="shrink-0 text-sm text-slate-500">{label}</dt>
      <dd className={cn('text-right text-sm font-medium text-slate-900', mono && 'font-mono text-[13px]')}>{value}</dd>
    </div>
  );
}
