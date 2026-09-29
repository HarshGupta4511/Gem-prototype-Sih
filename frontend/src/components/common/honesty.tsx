import { Info } from 'lucide-react';
import { cn } from '../../lib/utils';

/**
 * Honesty / provenance labels required by CONTRACT §19.
 * Always rendered next to verification or AI outputs.
 */
export function MockSourceLabel({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900',
        className,
      )}
    >
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>
        <strong>SOURCE: MOCK GOVERNMENT VERIFICATION</strong> — demo data, not live government systems.
      </span>
    </div>
  );
}

export function AiAssistedLabel({ provider, className }: { provider?: string; className?: string }) {
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900',
        className,
      )}
    >
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>
        <strong>AI-assisted explanation.</strong>
        {provider && (
          <>
            {' '}Provider: <code className="rounded bg-sky-100 px-1 font-mono">{provider}</code>
          </>
        )}
      </span>
    </div>
  );
}

export const OFFICER_FINALITY = 'Final decision remains with the Procurement Officer.';
