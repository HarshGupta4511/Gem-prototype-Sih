import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { integrityApi } from '../../lib/api';
import { labelize } from '../../lib/utils';

/**
 * Compact integrity banner shown on Bid Detail when active (non-closed)
 * integrity signals touch the bid. Renders nothing when there are none.
 */
export function IntegrityWidget({ bidId }: { bidId: number }) {
  const { data } = useQuery({
    queryKey: ['integrity-bid-signals', bidId],
    queryFn: () => integrityApi.bidSignals(bidId),
    staleTime: 30_000,
  });

  const signals = data ?? [];
  if (signals.length === 0) return null;

  const reviewCount = signals.filter((s) => s.severity === 'REVIEW_REQUIRED').length;

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/60 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldAlert className="h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400" />
        <p className="min-w-0 flex-1 text-sm text-amber-900 dark:text-amber-300">
          <span className="font-semibold">
            {signals.length} integrity signal{signals.length === 1 ? '' : 's'}
            {reviewCount > 0 && ` (${reviewCount} requiring review)`}
          </span>{' '}
          touch this bid — {signals.slice(0, 2).map((s) => s.title).join('; ')}
          {signals.length > 2 && `; +${signals.length - 2} more`}
          {signals.some((s) => s.is_demo_history) && (
            <span className="ml-1 font-medium text-violet-700">(includes DEMO DATA signals)</span>
          )}
        </p>
        <Link
          to="/app/integrity"
          className="text-xs font-semibold text-amber-800 dark:text-amber-300 underline-offset-2 hover:underline"
        >
          Review signals →
        </Link>
      </div>
      <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
        Integrity signals are {signals.every((s) => s.status !== 'OPEN') ? '' : 'patterns requiring review — '}
        they are never findings of misconduct and never decide qualification. Statuses:{' '}
        {signals.map((s) => labelize(s.status)).join(', ')}.
      </p>
    </div>
  );
}
