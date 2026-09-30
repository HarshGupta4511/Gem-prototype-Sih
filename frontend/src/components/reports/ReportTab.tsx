import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { FileCheck2, Send, Plus, Eye } from 'lucide-react';
import { reportsApi, getErrorMessage } from '../../lib/api';
import { useToast } from '../ui/toaster';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { cn, labelize } from '../../lib/utils';
import type { ReportStatus } from '../../types';

const STATUS_META: Record<ReportStatus, { label: string; classes: string }> = {
  DRAFT: { label: 'Draft', classes: 'bg-slate-100 text-slate-700 border-slate-300' },
  GENERATED: { label: 'Generated', classes: 'bg-blue-50 text-blue-800 border-blue-200' },
  SENT: { label: 'Sent to Procurement Officer', classes: 'bg-amber-50 text-amber-800 border-amber-200' },
  RECEIVED: { label: 'Received by Officer', classes: 'bg-teal-50 text-teal-800 border-teal-200' },
  UNDER_REVIEW: { label: 'Under Officer Review', classes: 'bg-indigo-50 text-indigo-800 border-indigo-200' },
  DECISION: { label: 'Decision Made', classes: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
};

export function ReportTab({ bidId }: { bidId: number }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();
  const { canReport } = useAuth();
  const [observation, setObservation] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['report-lifecycle', bidId],
    queryFn: () => reportsApi.lifecycle(bidId),
  });

  async function runAction(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ['report-lifecycle', bidId] });
      await qc.invalidateQueries({ queryKey: ['verification-report', bidId] });
      await qc.invalidateQueries({ queryKey: ['reports-inbox'] });
    } catch (e) {
      toast('error', `${label} failed`, getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (isLoading || !data) {
    return <p className="text-sm text-slate-500">Loading report status…</p>;
  }

  const status = data.status;
  const meta = STATUS_META[status];
  const canObserve = canReport && (status === 'DRAFT' || status === 'GENERATED');
  const canGenerate = canReport && status === 'DRAFT';
  const canSend = canReport && status === 'GENERATED';

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900">Verification Report Handoff</h3>
          <p className="text-xs text-slate-500">
            The verifier prepares the evidence-based report; the Procurement Officer reviews it and decides.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className={cn(meta.classes)}>
            {meta.label}
          </Badge>
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate(`/app/bids/${bidId}/report`)}
            className="border-slate-300 text-slate-700 text-xs"
          >
            <Eye className="mr-1.5 h-3.5 w-3.5" />
            Open Full Report
          </Button>
        </div>
      </div>

      {/* Lifecycle timeline */}
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        {(['DRAFT', 'GENERATED', 'SENT', 'RECEIVED', 'UNDER_REVIEW', 'DECISION'] as ReportStatus[]).map(
          (s, i, arr) => {
            const reached = arr.indexOf(status) >= i;
            return (
              <React.Fragment key={s}>
                <span
                  className={cn(
                    'rounded-full border px-2 py-0.5 font-semibold',
                    reached ? 'border-brand-300 bg-brand-50 text-brand-800' : 'border-slate-200 bg-white text-slate-400'
                  )}
                >
                  {STATUS_META[s].label}
                </span>
                {i < arr.length - 1 && <span className="text-slate-300">→</span>}
              </React.Fragment>
            );
          }
        )}
      </div>

      {/* Observations */}
      <div>
        <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Verifier Observations</h4>
        {data.observations.length > 0 ? (
          <ul className="space-y-2">
            {data.observations.map((o, i) => (
              <li key={i} className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2.5">
                <p className="text-sm text-slate-800">“{o.text}”</p>
                <p className="mt-1 text-xs text-slate-500">— {o.added_by ?? 'Verifier'}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No observations recorded yet.</p>
        )}
        {canObserve && (
          <div className="mt-2 flex gap-2">
            <input
              value={observation}
              onChange={(e) => setObservation(e.target.value)}
              maxLength={2000}
              placeholder="Add a short professional observation…"
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-600 focus:outline-none"
            />
            <Button
              size="sm"
              onClick={() =>
                runAction('Add observation', async () => {
                  const text = observation.trim();
                  if (!text) throw new Error('Observation text is required');
                  await reportsApi.addObservation(bidId, text);
                  setObservation('');
                  toast('success', 'Observation recorded');
                })
              }
              disabled={busy || !observation.trim()}
              className="bg-brand-700 hover:bg-brand-800 text-white"
            >
              <Plus className="mr-1 h-3.5 w-3.5" />
              Add
            </Button>
          </div>
        )}
      </div>

      {/* Verifier actions */}
      {canReport && (
        <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-4">
          {canGenerate && (
            <Button
              size="sm"
              onClick={() =>
                runAction('Generate report', async () => {
                  await reportsApi.generate(bidId);
                  toast('success', 'Verification report generated', 'Review it, then send to the Procurement Officer.');
                })
              }
              disabled={busy}
              className="bg-brand-700 hover:bg-brand-800 text-white"
            >
              <FileCheck2 className="mr-1.5 h-4 w-4" />
              Generate Verification Report
            </Button>
          )}
          {canSend && (
            <Button
              size="sm"
              onClick={() =>
                runAction('Send report', async () => {
                  await reportsApi.send(bidId);
                  toast('success', 'Report sent to Procurement Officer');
                })
              }
              disabled={busy}
              className="bg-amber-600 hover:bg-amber-700 text-white"
            >
              <Send className="mr-1.5 h-4 w-4" />
              Send to Procurement Officer
            </Button>
          )}
          {(status === 'SENT' || status === 'RECEIVED' || status === 'UNDER_REVIEW' || status === 'DECISION') && (
            <p className="w-full text-xs text-slate-500">
              {status === 'DECISION'
                ? 'The Procurement Officer has recorded a final decision.'
                : 'Report sent — it is now with the Procurement Officer for review and decision.'}
            </p>
          )}
        </div>
      )}

      {!canReport && status === 'DRAFT' && (
        <p className="text-xs text-slate-500">
          The verifier is still preparing this report. {labelize(status)}.
        </p>
      )}
    </div>
  );
}
