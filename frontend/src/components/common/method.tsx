import * as React from 'react';
import { Sparkles, Cog, ShieldCheck, UserCheck, ChevronDown, Info } from 'lucide-react';
import { cn } from '../../lib/utils';

/**
 * Subtle visual distinction between AI-powered operations, deterministic
 * systems and human decisions. Used sparingly — for transparency, not decoration.
 *
 * - "AI Assisted"      → LLM/document-AI understanding, extraction, explanation
 * - "Rule Engine"      → deterministic compliance scoring & risk classification
 * - "System Verified"  → government-source / mock verification checks
 * - "Procurement Officer" → the final human decision
 */
export type MethodKind = 'ai' | 'rule' | 'verified' | 'officer';

const METHOD_META: Record<
  MethodKind,
  { label: string; icon: React.ComponentType<{ className?: string }>; classes: string }
> = {
  ai: {
    label: 'AI Assisted',
    icon: Sparkles,
    classes: 'bg-violet-50 text-violet-800 border-violet-200',
  },
  rule: {
    label: 'Rule Engine',
    icon: Cog,
    classes: 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-700',
  },
  verified: {
    label: 'System Verified',
    icon: ShieldCheck,
    classes: 'bg-sky-50 text-sky-800 border-sky-200',
  },
  officer: {
    label: 'Procurement Officer',
    icon: UserCheck,
    classes: 'bg-brand-50 text-brand-800 border-brand-200',
  },
};

export function ProvenanceBadge({ kind, className }: { kind: MethodKind; className?: string }) {
  const meta = METHOD_META[kind];
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold',
        meta.classes,
        className,
      )}
      title={
        kind === 'ai'
          ? 'This step uses AI/document understanding. Results are advisory.'
          : kind === 'rule'
            ? 'This step uses the deterministic rules engine. No LLM decides the outcome.'
            : kind === 'verified'
              ? 'Checked against verification sources (mock data in this prototype).'
              : 'Final decision rests with the Procurement Officer.'
      }
    >
      <Icon className="h-3 w-3" />
      {meta.label}
    </span>
  );
}

/**
 * Small "How this result was generated" disclosure. Collapsed by default —
 * placed where it improves understanding, never as a giant panel.
 */
export function MethodExplainer({
  kind,
  title = 'How this result was generated',
  children,
  defaultOpen = false,
  className,
}: {
  kind: MethodKind;
  title?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className={cn('rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100"
        aria-expanded={open}
      >
        <Info className="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" />
        <span className="flex-1">{title}</span>
        <ProvenanceBadge kind={kind} />
        <ChevronDown className={cn('h-3.5 w-3.5 text-slate-400 dark:text-slate-500 transition-transform', open && 'rotate-180')} />
      </button>
      {open && <div className="border-t border-slate-200 dark:border-slate-800 px-3 py-2.5 text-xs leading-relaxed text-slate-600 dark:text-slate-400">{children}</div>}
    </div>
  );
}
