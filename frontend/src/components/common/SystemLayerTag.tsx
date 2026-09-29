import React from 'react';
import { Sparkles, Scale, ShieldCheck, UserCheck, FileText, ScrollText, Globe } from 'lucide-react';
import { cn } from '../../lib/utils';

export type SystemLayer =
  | 'AI_ASSISTED'
  | 'RULE_ENGINE'
  | 'VERIFICATION'
  | 'HUMAN_DECISION'
  | 'DOCUMENT_INGESTION'
  | 'AUDIT_CHAIN'
  | 'GOVERNMENT_ADAPTER';

interface SystemLayerTagProps {
  layer: SystemLayer;
  className?: string;
  size?: 'sm' | 'md';
}

const LAYER_CONFIG: Record<
  SystemLayer,
  { label: string; icon: React.ComponentType<{ className?: string }>; bg: string; text: string; border: string }
> = {
  AI_ASSISTED: {
    label: 'AI-Assisted',
    icon: Sparkles,
    bg: 'bg-indigo-50',
    text: 'text-indigo-800',
    border: 'border-indigo-200',
  },
  RULE_ENGINE: {
    label: 'Rule Engine',
    icon: Scale,
    bg: 'bg-slate-100',
    text: 'text-slate-800',
    border: 'border-slate-300',
  },
  VERIFICATION: {
    label: 'Verification Check',
    icon: ShieldCheck,
    bg: 'bg-sky-50',
    text: 'text-sky-800',
    border: 'border-sky-200',
  },
  HUMAN_DECISION: {
    label: 'Officer Decision',
    icon: UserCheck,
    bg: 'bg-emerald-50',
    text: 'text-emerald-800',
    border: 'border-emerald-200',
  },
  DOCUMENT_INGESTION: {
    label: 'Document Ingestion',
    icon: FileText,
    bg: 'bg-amber-50',
    text: 'text-amber-800',
    border: 'border-amber-200',
  },
  AUDIT_CHAIN: {
    label: 'Cryptographic Audit',
    icon: ScrollText,
    bg: 'bg-purple-50',
    text: 'text-purple-800',
    border: 'border-purple-200',
  },
  GOVERNMENT_ADAPTER: {
    label: 'Statutory Adapter',
    icon: Globe,
    bg: 'bg-teal-50',
    text: 'text-teal-800',
    border: 'border-teal-200',
  },
};

export function SystemLayerTag({ layer, className, size = 'sm' }: SystemLayerTagProps) {
  const conf = LAYER_CONFIG[layer];
  const Icon = conf.icon;
  const isSm = size === 'sm';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 font-medium border rounded',
        conf.bg,
        conf.text,
        conf.border,
        isSm ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs',
        className
      )}
    >
      <Icon className={isSm ? 'w-3 h-3' : 'w-3.5 h-3.5'} />
      <span>{conf.label}</span>
    </span>
  );
}
