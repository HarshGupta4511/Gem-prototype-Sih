import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { consistencyApi, getErrorMessage } from '../../lib/api';
import { useToast } from '../ui/toaster';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { MethodExplainer } from './method';
import { labelize } from '../../lib/utils';

const RESULT_STYLES: Record<string, string> = {
  MATCH: 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
  MISMATCH: 'bg-red-50 dark:bg-red-950/60 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800',
  REVIEW_REQUIRED: 'bg-amber-50 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border-amber-200 dark:border-amber-800',
};

/**
 * Cross-document consistency panel for a bid's Documents tab.
 * Runs deterministic checks over extracted fields and shows every check with
 * its mismatches explained — AI explains findings elsewhere, never here.
 */
export function ConsistencyPanel({ bidId }: { bidId: number }) {
  const { canVerify } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ['consistency', bidId],
    queryFn: () => consistencyApi.get(bidId),
    staleTime: 30_000,
  });

  const runMutation = useMutation({
    mutationFn: () => consistencyApi.run(bidId),
    onSuccess: (res) => {
      toast(
        'success',
        `Consistency check complete — ${res.mismatches} mismatch${res.mismatches === 1 ? '' : 'es'}`,
        `${res.checks_run} checks compared extracted fields across documents`,
      );
      queryClient.invalidateQueries({ queryKey: ['consistency', bidId] });
    },
    onError: (err) => toast('error', 'Consistency check failed', getErrorMessage(err)),
  });

  React.useEffect(() => {
    if (error) toast('error', 'Could not load consistency checks', getErrorMessage(error)); }, [error, toast]); const checks = data?.checks ?? []; const mismatches = data?.mismatches ?? 0; const busy = runMutation.isPending || isRefetching; return ( <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4"> <div className="flex flex-wrap items-center justify-between gap-2"> <div> <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 dark:text-slate-200"> Cross-Document Consistency {checks.length > 0 && ( <span className="ml-2 font-semibold normal-case tracking-normal text-slate-500 dark:text-slate-400 dark:text-slate-400"> {checks.length} checks · {mismatches} mismatch{mismatches === 1 ?'' : 'es'} </span> )} </h3> <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400"> Deterministic comparison of extracted fields across documents — entity names, identifiers, dates, values. </p> </div> <div className="flex items-center gap-2"> <Button size="sm" variant="outline" onClick={() => refetch()} disabled={busy} className="border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/70 text-xs" > <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isRefetching ?'animate-spin' : ''}`} /> Refresh </Button> {canVerify && ( <Button size="sm" onClick={() => runMutation.mutate()} disabled={busy} className="bg-brand-700 hover:bg-brand-800 text-white text-xs" > <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${runMutation.isPending ?'animate-spin' : ''}`} />
              {runMutation.isPending ? 'Checking…' : 'Run Consistency Check'}
            </Button>
          )}
        </div>
      </div>

      <div className="mt-3">
        <MethodExplainer kind="rule" title="How consistency checks work">
          Extracted fields are compared across the bid's processed documents using shared
          normalisation (entity resolution). Name variants like “Pvt. Ltd.” and “Private
          Limited” match; materially different entities are flagged. Numeric values agree
          within documented tolerances. Every mismatch explains exactly what disagreed.
        </MethodExplainer>
      </div>

      {isLoading ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Loading checks…</p>
      ) : checks.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          No consistency checks have been run for this bid yet.
          {canVerify ? ' Run a check to compare extracted fields across documents.' : ''}
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead className="bg-slate-50 dark:bg-slate-900 text-slate-500 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2 font-semibold">Check</th>
                <th className="px-3 py-2 font-semibold">Document A</th>
                <th className="px-3 py-2 font-semibold">Document B</th>
                <th className="px-3 py-2 font-semibold">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {checks.map((c) => (
                <tr key={c.id} className={c.result === 'MISMATCH' ? 'bg-red-50/40 dark:bg-red-950/60' : undefined}>
                  <td className="px-3 py-2.5">
                    <p className="font-medium text-slate-800 dark:text-slate-200">{c.check_label}</p>
                    <p className="mt-0.5 max-w-md leading-relaxed text-slate-500 dark:text-slate-400">{c.reason}</p>
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <p className="font-medium text-slate-700 dark:text-slate-200">{c.doc1.name ?? '—'}</p>
                    <p className="mt-0.5 break-words text-slate-600 dark:text-slate-400">{c.value1 ?? '—'}</p>
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <p className="font-medium text-slate-700 dark:text-slate-200">{c.doc2.name ?? '—'}</p>
                    <p className="mt-0.5 break-words text-slate-600 dark:text-slate-400">{c.value2 ?? '—'}</p>
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <Badge variant="outline" className={RESULT_STYLES[c.result] ?? RESULT_STYLES.REVIEW_REQUIRED}>
                      {labelize(c.result)}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {mismatches > 0 && (
        <p className="mt-3 flex items-start gap-1.5 text-xs text-amber-800 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {mismatches} inconsistency{mismatches === 1 ? '' : 'ies'} require officer review. Mismatches are recorded in the audit trail.
        </p>
      )}
      {checks.length > 0 && mismatches === 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="h-3.5 w-3.5" />
          All checks consistent across documents.
        </p>
      )}
    </div>
  );
}
