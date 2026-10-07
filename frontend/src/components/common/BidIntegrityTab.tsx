import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { integrityApi } from '../../lib/api';
import { cn, labelize } from '../../lib/utils';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { SystemLayerTag } from './SystemLayerTag';
import { MethodExplainer } from './method';

/**
 * Integrity Findings tab for Bid Detail: renders the integrity signals that
 * touch this bid, using the same evidence-backed signal API as /app/integrity.
 * Read-only here — officer actions (acknowledge/review/investigate/close)
 * remain on the Integrity page.
 */
export function BidIntegrityTab({ bidId }: { bidId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['integrity-bid-signals', bidId],
    queryFn: () => integrityApi.bidSignals(bidId),
    staleTime: 30_000,
  });

  const signals = data ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
              Integrity Findings ({signals.length})
            </h3>
            <SystemLayerTag layer="RULE_ENGINE" size="sm" />
          </div>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            Deterministic patterns detected across tenders, bids and the audit trail. Signals
            require officer review — they are never findings of misconduct and never decide
            bidder qualification.
          </p>
        </div>
        <Link to="/app/integrity">
          <Button size="sm" variant="outline" className="border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-xs">
            <ShieldAlert className="mr-1.5 h-3.5 w-3.5" />
            Review All Signals
          </Button>
        </Link>
      </div>

      <MethodExplainer kind="rule">
        Each signal is produced by a deterministic detector (entity matching, contact
        reuse, award concentration, bid rotation, …) and carries its evidence. The
        Integrity page is where you acknowledge, review, investigate or close a signal —
        closing requires an officer note and is audited.
      </MethodExplainer>

      {isLoading ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading integrity signals…</p>
      ) : signals.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 dark:border-slate-700 p-8 text-center">
          <ShieldAlert className="mx-auto h-8 w-8 text-slate-400 dark:text-slate-500" />
          <p className="mt-2 text-sm font-semibold text-slate-700 dark:text-slate-200">No integrity signals touch this bid</p>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Signals appear here when a cross-tender detector flags a pattern involving this bid.
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {signals.map((s) => (
            <li key={s.id} className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <p className="min-w-0 flex-1 text-sm font-bold text-slate-900 dark:text-slate-100">{s.title}</p>
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[11px]',
                    s.severity === 'REVIEW_REQUIRED'
                      ? 'bg-red-50 dark:bg-red-950/60 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800'
                      : s.severity === 'ELEVATED'
                        ? 'bg-amber-50 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border-amber-200 dark:border-amber-800'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-700'
                  )}
                >
                  {labelize(s.severity)}
                </Badge>
                <Badge variant="outline" className="bg-white dark:bg-slate-900 text-[11px]">
                  {labelize(s.status)}
                </Badge>
              </div>
              <p className="mt-1.5 text-xs text-slate-600 dark:text-slate-400">{s.description}</p>
              {s.rule_logic && (
                <p className="mt-1.5 rounded bg-slate-50 dark:bg-slate-900 px-2 py-1 text-[11px] text-slate-500 dark:text-slate-400">
                  <span className="font-semibold">Detection logic:</span> {s.rule_logic}
                </p>
              )}
              {s.evidence && s.evidence.length > 0 && (
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  <span className="font-semibold">Evidence:</span>{' '}
                  {s.evidence.slice(0, 3).map((e) => e.label).join(' · ')}
                  {s.evidence.length > 3 && ` · +${s.evidence.length - 3} more`}
                </p>
              )}
              {s.officer_note && (
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  <span className="font-semibold">Officer note:</span> {s.officer_note}
                </p>
              )}
              {s.is_demo_history && (
                <p className="mt-1 text-[11px] font-medium text-violet-700">DEMO DATA signal</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
