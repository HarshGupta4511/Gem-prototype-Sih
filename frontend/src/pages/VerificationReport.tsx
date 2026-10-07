import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams, Link } from 'react-router-dom';
import {
  FileCheck2,
  Plus,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  MessageSquare,
  Eye,
  RefreshCw,
} from 'lucide-react';
import { summariesApi, officerApi, getErrorMessage } from '../lib/api';
import { useToast } from '../components/ui/toaster';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { PageHeader, BackLink, LoadingBlock } from '../components/common/ui-helpers';
import { ProvenanceBadge, MethodExplainer } from '../components/common/method';
import { MockSourceLabel } from '../components/common/honesty';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogBody,
  DialogFooter,
} from '../components/ui/dialog';
import { cn, labelize } from '../lib/utils';
import type { ReportStatus, OfficerDecision } from '../types';

// Officer-owned: the Procurement Officer generates the verification
// summary directly. There is no report handoff — the officer generates,states.
const STATUS_META: Record<ReportStatus, { label: string; classes: string }> = {
  DRAFT: { label: 'Draft', classes: 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-700' },
  GENERATED: { label: 'Generated', classes: 'bg-blue-50 dark:bg-blue-950/60 text-blue-800 dark:text-blue-400 border-blue-200 dark:border-blue-800' },
  UPDATED: { label: 'Updated', classes: 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800' },
};

const LIFECYCLE_STEPS: ReportStatus[] = ['DRAFT', 'GENERATED', 'UPDATED'];

function formatDateTime(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function SectionCard({
  title,
  badge,
  explainer,
  children,
}: {
  title: string;
  badge: React.ReactNode;
  explainer?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xs">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 dark:border-slate-800 px-5 py-3.5">
        <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">{title}</h2>
        <span className="ml-auto">{badge}</span>
      </div>
      <div className="space-y-3 px-5 py-4">
        {explainer}
        {children}
      </div>
    </section>
  );
}

function KeyValue({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 text-sm">
      <dt className="shrink-0 text-slate-500 dark:text-slate-400">{k}</dt>
      <dd className="text-right font-medium text-slate-900 dark:text-slate-100">{v}</dd>
    </div>
  );
}

export default function VerificationReport() {
  const { bidId } = useParams<{ bidId: string }>();
  const bid_id = Number(bidId);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();

  const [observation, setObservation] = React.useState('');
  const [decisionDialog, setDecisionDialog] = React.useState<OfficerDecision | null>(null);
  const [decisionReason, setDecisionReason] = React.useState('');
  const [decisionError, setDecisionError] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [regenerating, setRegenerating] = React.useState(false);

  const { data: report, isLoading, error, refetch } = useQuery({
    queryKey: ['verification-summary', bid_id],
    queryFn: () => summariesApi.get(bid_id),
    enabled: Number.isFinite(bid_id),
  });

  React.useEffect(() => {
    if (error) toast('error', 'Could not load summary', getErrorMessage(error));
  }, [error, toast]);

  async function runAction(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ['verification-summary', bid_id] });
      await qc.invalidateQueries({ queryKey: ['summary-lifecycle', bid_id] });
      await qc.invalidateQueries({ queryKey: ['dashboard'] });
    } catch (e) {
      toast('error', `${label} failed`, getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRegenerate() {
    if (regenerating || busy) return; // prevent duplicate clicks
    setRegenerating(true);
    setBusy(true);
    try {
      await summariesApi.regenerate(bid_id);
      await qc.invalidateQueries({ queryKey: ['verification-summary', bid_id] });
      await qc.invalidateQueries({ queryKey: ['summary-lifecycle', bid_id] });
      await qc.invalidateQueries({ queryKey: ['dashboard'] });
      toast('success', 'Verification summary regenerated successfully.');
    } catch (e) {
      // Previous valid summary is preserved — the query data is untouched.
      toast('error', 'Regenerate summary failed', getErrorMessage(e));
    } finally {
      setRegenerating(false);
      setBusy(false);
    }
  }

  async function addObservation() {
    const text = observation.trim();
    if (!text) {
      toast('warning', 'Observation is empty', 'Write a short professional observation first.');
      return;
    }
    await runAction('Add observation', async () => {
      await summariesApi.addObservation(bid_id, text);
      setObservation('');
      toast('success', 'Observation recorded');
    });
  }

  async function confirmDecision() {
    if (!decisionDialog) return;
    const needsReason = decisionDialog !== 'APPROVE';
    if (needsReason && decisionReason.trim().length === 0) {
      setDecisionError(`A reason is required when recording ${labelize(decisionDialog)}.`);
      return;
    }
    setDecisionError('');
    setBusy(true);
    try {
      await officerApi.decision({
        bid_id,
        decision: decisionDialog,
        reason: decisionReason.trim() || 'Approved by Procurement Officer after reviewing the verification summary.',
      });
      setDecisionDialog(null);
      setDecisionReason('');
      await qc.invalidateQueries({ queryKey: ['verification-summary', bid_id] });
      await qc.invalidateQueries({ queryKey: ['bid', bid_id] });
      toast('success', 'Decision recorded', `Bid marked as ${labelize(decisionDialog)}.`);
    } catch (e) {
      setDecisionError(getErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingBlock rows={10} />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/60 p-6 text-center text-sm text-red-800 dark:text-red-400">
        Verification summary could not be loaded.
      </div>
    );
  }

  const statusMeta = STATUS_META[report.status];
  const reachedIdx = LIFECYCLE_STEPS.indexOf(report.status);
  const canGenerate = report.status === 'DRAFT';
  const canRegenerate = report.status === 'GENERATED' || report.status === 'UPDATED';
  const showDecisionBar = !report.decision;

  const decisionButtons: { decision: OfficerDecision; label: string; icon: React.ReactNode; classes: string }[] = [
    { decision: 'APPROVE', label: 'Approve Bid', icon: <CheckCircle2 className="mr-1.5 h-4 w-4" />, classes: 'bg-emerald-700 hover:bg-emerald-800 text-white' },
    { decision: 'REJECT', label: 'Reject Bid', icon: <XCircle className="mr-1.5 h-4 w-4" />, classes: 'bg-red-700 hover:bg-red-800 text-white' },
    { decision: 'ESCALATE', label: 'Escalate', icon: <AlertTriangle className="mr-1.5 h-4 w-4" />, classes: 'bg-amber-600 hover:bg-amber-700 text-white' },
    { decision: 'REQUEST_CLARIFICATION', label: 'Request Clarification', icon: <MessageSquare className="mr-1.5 h-4 w-4" />, classes: 'border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/70' },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Verification Summary"
        description="Evidence-backed summary generated directly by the Procurement Officer. Decision support — the final decision always rests with the officer."
        back={<BackLink to={`/app/bids/${bid_id}`} label="Back to Bid" />}
        actions={
          <Badge variant="outline" className={cn('text-xs', statusMeta.classes)}>
            {statusMeta.label}
          </Badge>
        }
      />

      {/* Lifecycle timeline */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-5 py-4 shadow-xs">
        <div className="flex items-center justify-between gap-1">
          {LIFECYCLE_STEPS.map((step, i) => {
            const reached = i <= reachedIdx;
            return (
              <React.Fragment key={step}>
                <div className="flex min-w-0 flex-col items-center gap-1 text-center">
                  <div
                    className={cn(
                      'flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-bold',
                      reached ? 'border-brand-700 bg-brand-700 text-white' : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-400 dark:text-slate-500'
                    )}
                  >
                    {i + 1}
                  </div>
                  <span className={cn('text-[10px] font-medium leading-tight', reached ? 'text-slate-900 dark:text-slate-100' : 'text-slate-400 dark:text-slate-500')}>
                    {STATUS_META[step].label}
                  </span>
                </div>
                {i < LIFECYCLE_STEPS.length - 1 && (
                  <div className={cn('mb-5 h-0.5 min-w-4 flex-1 rounded', i < reachedIdx ? 'bg-brand-700' : 'bg-slate-200 dark:bg-slate-700')} />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Summary history — audit-sourced timeline of generate/regenerate events */}
      {report.timeline && report.timeline.length > 0 && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-5 py-4 shadow-xs">
          <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Summary History</h2>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            Every generation and regeneration is recorded in the audit trail. The latest event determines the current status.
          </p>
          <ul className="mt-3 space-y-2">
            {report.timeline.map((t, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-slate-800 dark:text-slate-200">{labelize(t.action)}</span>
                <Badge variant="outline" className="text-[10px]">{labelize(t.status_after)}</Badge>
                <span className="text-slate-500 dark:text-slate-400">
                  {t.actor ?? 'System'} · {formatDateTime(t.at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Officer summary actions */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
        <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Summary Actions</h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {report.status === 'DRAFT' && 'Generate the summary from the current evidence for this bid.'}
          {report.status !== 'DRAFT' && 'Regenerate the summary at any time to pick up the latest evidence.'}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {canGenerate && (
            <Button
              size="sm"
              onClick={() =>
                runAction('Generate summary', async () => {
                  await summariesApi.generate(bid_id);
                  toast('success', 'Verification summary generated');
                })
              }
              disabled={busy}
              className="bg-brand-700 hover:bg-brand-800 text-white"
            >
              <FileCheck2 className="mr-1.5 h-4 w-4" />
              Generate Verification Summary
            </Button>
          )}
          {canRegenerate && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleRegenerate}
              disabled={busy || regenerating}
              className="border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200"
            >
              <RefreshCw className={cn('mr-1.5 h-4 w-4', regenerating && 'animate-spin')} />
              {regenerating ? 'Regenerating Summary...' : 'Regenerate Summary'}
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => navigate(`/app/bids/${bid_id}`)} className="border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200">
            <Eye className="mr-1.5 h-4 w-4" />
            Open Bid Detail
          </Button>
        </div>
      </div>

      {/* Bid information */}
      <SectionCard title="Bid Information" badge={<ProvenanceBadge kind="verified" />}>
        <dl className="divide-y divide-slate-100 dark:divide-slate-800">
          <KeyValue k="Tender Number" v={report.bid_info.tender_number ?? '—'} />
          <KeyValue k="Tender Title" v={report.bid_info.tender_title ?? '—'} />
          <KeyValue k="Bidder" v={report.bid_info.bidder_name ?? '—'} />
          <KeyValue k="Submission Date" v={formatDateTime(report.bid_info.submission_date)} />
          <KeyValue k="Review Date" v={formatDateTime(report.generated_at)} />
          <KeyValue
            k="Compliance Score"
            v={report.compliance_score != null ? `${report.compliance_score.toFixed(1)} / 100` : 'Not evaluated yet'}
          />
        </dl>
      </SectionCard>

      {/* Document review */}
      <SectionCard
        title="Document Review"
        badge={<ProvenanceBadge kind="verified" />}
        explainer={
          <MethodExplainer kind="verified">
            Counts come straight from the document register — submitted, processed and flagged files. Nothing is inferred.
          </MethodExplainer>
        }
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 p-3 text-center">
            <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{report.documents.submitted_count}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Documents Submitted</p>
          </div>
          <div className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 p-3 text-center">
            <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{report.documents.processed_count}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Documents Processed</p>
          </div>
          <div className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 p-3 text-center">
            <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">{report.documents.issues.length}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Flagged for Review</p>
          </div>
        </div>
        {report.documents.items.length > 0 ? (
          <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
                  <th className="px-3 py-2 font-semibold">Document</th>
                  <th className="px-3 py-2 font-semibold">Type</th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2 font-semibold">Fields Extracted</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {report.documents.items.map((d) => (
                  <tr key={d.id}>
                    <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{d.file_name}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{d.document_type}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{labelize(d.status)}</td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{d.extracted_field_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">No documents have been submitted for this bid yet.</p>
        )}
        {report.documents.issues.length > 0 && (
          <div className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/60 px-3 py-2.5 text-xs text-amber-900 dark:text-amber-300">
            <span className="font-semibold">Document issues: </span>
            {report.documents.issues.map((d) => `${d.file_name} (${labelize(d.status)})`).join('; ')}
          </div>
        )}
      </SectionCard>

      {/* Extracted information */}
      <SectionCard
        title="Extracted Information"
        badge={<ProvenanceBadge kind="ai" />}
        explainer={
          <MethodExplainer kind="ai">
            Fields extracted by document AI (OCR + regex + LLM extraction where configured). Values are shown as extracted, with the source document — the officer should treat unusual values with caution.
          </MethodExplainer>
        }
      >
        {report.extracted_fields.items.length > 0 ? (
          <>
            <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-slate-50 dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
                    <th className="px-3 py-2 font-semibold">Field</th>
                    <th className="px-3 py-2 font-semibold">Value</th>
                    <th className="px-3 py-2 font-semibold">Source Document</th>
                    <th className="px-3 py-2 font-semibold">Method</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {report.extracted_fields.items.map((f, i) => (
                    <tr key={i}>
                      <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{f.field_name}</td>
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-200">{f.field_value ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{f.document_name ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{f.extraction_method}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {report.extracted_fields.total > report.extracted_fields.items.length && (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Showing {report.extracted_fields.items.length} of {report.extracted_fields.total} extracted fields.
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">No information has been extracted yet.</p>
        )}
      </SectionCard>

      {/* Verification results */}
      <SectionCard
        title="Verification Results"
        badge={<ProvenanceBadge kind="verified" />}
        explainer={
          <MethodExplainer kind="verified">
            Cross-verification of identifiers against government sources. In this prototype the adapters are <MockSourceLabel /> — every check is labelled so mock data is never mistaken for live verification.
          </MethodExplainer>
        }
      >
        {report.verification.length > 0 ? (
          <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
                  <th className="px-3 py-2 font-semibold">Source</th>
                  <th className="px-3 py-2 font-semibold">Identifier</th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2 font-semibold">Observation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {report.verification.map((v, i) => (
                  <tr key={i}>
                    <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">
                      {v.source} {v.is_mock && <MockSourceLabel />}
                    </td>
                    <td className="px-3 py-2 font-mono text-slate-700 dark:text-slate-200">{v.identifier}</td>
                    <td className="px-3 py-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          v.status === 'VERIFIED'
                            ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800'
                            : v.status === 'MISMATCH' || v.status === 'FAILED'
                              ? 'bg-red-50 dark:bg-red-950/60 text-red-800 dark:text-red-400 border-red-200 dark:border-red-800'
                              : 'bg-amber-50 dark:bg-amber-950/60 text-amber-800 dark:text-amber-400 border-amber-200 dark:border-amber-800'
                        )}
                      >
                        {labelize(v.status)}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{v.observation ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Verification has not been run for this bid yet.</p>
        )}
      </SectionCard>

      {/* Compliance review */}
      <SectionCard
        title="Compliance Review"
        badge={<ProvenanceBadge kind="rule" />}
        explainer={
          <MethodExplainer kind="rule">
            Evaluated by the deterministic rules engine against the tender requirements. No AI model participates in the pass/fail scoring.
          </MethodExplainer>
        }
      >
        {(() => {
          const total = report.compliance.length;
          const pass = report.compliance.filter((c) => c.result === 'PASS').length;
          const fail = report.compliance.filter((c) => c.result === 'FAIL').length;
          const missing = report.compliance.filter((c) => c.result === 'MISSING').length;
          const review = report.compliance.filter((c) => c.result === 'REVIEW_REQUIRED').length;
          const other = total - pass - fail - missing - review;
          const overall = fail > 0 ? 'FAIL' : missing > 0 ? 'INCOMPLETE' : review > 0 || other > 0 ? 'REVIEW REQUIRED' : total > 0 ? 'PASS' : 'NOT EVALUATED';
          const stats: { label: string; value: number; classes: string }[] = [
            { label: 'Total', value: total, classes: 'text-slate-900 dark:text-slate-100' },
            { label: 'Pass', value: pass, classes: 'text-emerald-700 dark:text-emerald-400' },
            { label: 'Fail', value: fail, classes: 'text-red-700 dark:text-red-400' },
            { label: 'Missing', value: missing, classes: 'text-amber-700 dark:text-amber-400' },
            { label: 'Review Required', value: review, classes: 'text-amber-700 dark:text-amber-400' },
          ];
          return (
            <div className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 px-4 py-3">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                {stats.map((s) => (
                  <div key={s.label} className="flex items-baseline gap-1.5">
                    <span className={cn('text-lg font-bold', s.classes)}>{s.value}</span>
                    <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{s.label}</span>
                  </div>
                ))}
                <div className="ml-auto flex items-center gap-2">
                  <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Overall</span>
                  <Badge variant="outline" className="text-[11px] font-bold">{labelize(overall)}</Badge>
                </div>
              </div>
            </div>
          );
        })()}
        {report.compliance.length > 0 ? (
          <div className="overflow-x-auto rounded-md border border-slate-200 dark:border-slate-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
                  <th className="px-3 py-2 font-semibold">Requirement</th>
                  <th className="px-3 py-2 font-semibold">Result</th>
                  <th className="px-3 py-2 font-semibold">Evidence</th>
                  <th className="px-3 py-2 font-semibold">Observation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {report.compliance.map((c, i) => (
                  <tr key={i}>
                    <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{c.requirement}</td>
                    <td className="px-3 py-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          c.result === 'PASS'
                            ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800'
                            : c.result === 'FAIL'
                              ? 'bg-red-50 dark:bg-red-950/60 text-red-800 dark:text-red-400 border-red-200 dark:border-red-800'
                              : 'bg-amber-50 dark:bg-amber-950/60 text-amber-800 dark:text-amber-400 border-amber-200 dark:border-amber-800'
                        )}
                      >
                        {labelize(c.result)}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-400">
                      {Array.isArray(c.evidence) && c.evidence.length > 0
                        ? c.evidence.map((e) => String(e)).join(', ')
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{c.observation || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Compliance has not been evaluated for this bid yet.</p>
        )}
      </SectionCard>

      {/* Key findings / exceptions — aggregated from live evidence */}
      <SectionCard
        title="Key Findings / Exceptions"
        badge={<ProvenanceBadge kind="rule" />}
        explainer={
          <MethodExplainer kind="rule">
            Important failures, mismatches, missing evidence and review-required items,
            collected from the compliance evaluation, statutory verification and document
            register above. Each item links back to its source section.
          </MethodExplainer>
        }
      >
        {(() => {
          const findings: { label: string; detail: string; tone: 'red' | 'amber' }[] = [];
          report.compliance
            .filter((c) => c.result === 'FAIL' || c.result === 'MISMATCH')
            .forEach((c) =>
              findings.push({
                label: c.requirement,
                detail: `Compliance ${labelize(c.result)} — ${c.observation || 'see compliance review'}`,
                tone: 'red',
              }),
            );
          report.compliance
            .filter((c) => c.result === 'REVIEW_REQUIRED' || c.result === 'MISSING')
            .forEach((c) =>
              findings.push({
                label: c.requirement,
                detail: `Compliance ${labelize(c.result)} — ${c.observation || 'see compliance review'}`,
                tone: 'amber',
              }),
            );
          report.verification
            .filter((v) => v.status === 'MISMATCH' || v.status === 'FAILED')
            .forEach((v) =>
              findings.push({
                label: `${v.source} verification`,
                detail: `${labelize(v.status)} for ${v.identifier} — ${v.observation || 'see verification results'}`,
                tone: 'red',
              }),
            );
          report.documents.issues.forEach((d) =>
            findings.push({
              label: d.file_name,
              detail: `Document ${labelize(d.status)} — see document review`,
              tone: 'amber',
            }),
          );
          if (findings.length === 0) {
            return (
              <p className="text-sm text-emerald-700 dark:text-emerald-400">
                No exceptions — every evaluated requirement passed, all verifications clear,
                and no documents are flagged.
              </p>
            );
          }
          return (
            <ul className="space-y-2">
              {findings.map((f, i) => (
                <li
                  key={i}
                  className={cn(
                    'rounded-md border px-3 py-2.5',
                    f.tone === 'red'
                      ? 'border-red-200 dark:border-red-800 bg-red-50/60 dark:bg-red-950/40'
                      : 'border-amber-200 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-950/40',
                  )}
                >
                  <p
                    className={cn(
                      'text-sm font-semibold',
                      f.tone === 'red' ? 'text-red-900 dark:text-red-300' : 'text-amber-900 dark:text-amber-300',
                    )}
                  >
                    {f.label}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">{f.detail}</p>
                </li>
              ))}
            </ul>
          );
        })()}
      </SectionCard>

      {/* Risk */}
      <SectionCard title="Risk Assessment" badge={<ProvenanceBadge kind="rule" />}>
        {report.risk ? (
          <dl className="divide-y divide-slate-100 dark:divide-slate-800">
            <KeyValue
              k="Risk Level"
              v={
                <Badge
                  variant="outline"
                  className={cn(
                    report.risk.level === 'LOW'
                      ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800'
                      : report.risk.level === 'CRITICAL'
                        ? 'bg-red-50 dark:bg-red-950/60 text-red-800 dark:text-red-400 border-red-200 dark:border-red-800'
                        : 'bg-amber-50 dark:bg-amber-950/60 text-amber-800 dark:text-amber-400 border-amber-200 dark:border-amber-800'
                  )}
                >
                  {labelize(report.risk.level)}
                </Badge>
              }
            />
            <KeyValue k="Risk Factors" v={report.risk.factors.length > 0 ? report.risk.factors.map(f => typeof f === 'string' ? f : f.message).join('; ') : 'None flagged'} />
            {report.risk.explanation && <KeyValue k="Explanation" v={report.risk.explanation} />}
          </dl>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">Risk has not been assessed for this bid yet.</p>
        )}
      </SectionCard>

      {/* Officer observations */}
      <SectionCard title="Officer Observations" badge={<ProvenanceBadge kind="officer" />}>
        {report.officer_observations.length > 0 ? (
          <ul className="space-y-2.5">
            {report.officer_observations.map((o, i) => (
              <li key={i} className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 px-3 py-2.5">
                <p className="text-sm text-slate-800 dark:text-slate-200">“{o.text}”</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  — {o.added_by ?? 'Procurement Officer'} · {formatDateTime(o.added_at)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">No officer observations recorded yet.</p>
        )}
        <div className="rounded-md border border-dashed border-slate-300 dark:border-slate-700 p-3">
          <label className="mb-1.5 block text-xs font-semibold text-slate-700 dark:text-slate-200">
            Add a professional observation
          </label>
          <textarea
            value={observation}
            onChange={(e) => setObservation(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="e.g. All submitted statutory documents were reviewed. GST and Udyam records were successfully verified. PAN/entity-name mismatch requires officer attention."
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none"
          />
          <div className="mt-2 flex justify-end">
            <Button size="sm" onClick={addObservation} disabled={busy || !observation.trim()} className="bg-brand-700 hover:bg-brand-800 text-white">
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Add Observation
            </Button>
          </div>
        </div>
      </SectionCard>

      {/* Cross-document consistency (mismatches only) */}
      <SectionCard
        title="Cross-Document Consistency"
        badge={<ProvenanceBadge kind="rule" />}
        explainer={
          <MethodExplainer kind="rule">
            Deterministic comparison of extracted fields across this bid's documents —
            entity names, GSTIN ↔ PAN structure, identifiers, dates and numeric values.
            Only mismatches are listed here; the full check list is on the bid's Documents tab.
          </MethodExplainer>
        }
      >
        {!report.consistency || report.consistency.checks_run === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Consistency checks have not been run for this bid yet. They can be run from the bid's Documents tab.
          </p>
        ) : report.consistency.mismatches === 0 ? (
          <p className="text-sm text-emerald-700 dark:text-emerald-400">
            {report.consistency.checks_run} check{report.consistency.checks_run === 1 ? '' : 's'} run — no mismatches detected.
          </p>
        ) : (
          <ul className="space-y-2.5">
            {report.consistency.items.map((m, i) => (
              <li key={i} className="rounded-md border border-red-200 dark:border-red-800 bg-red-50/50 px-3 py-2.5">
                <p className="text-sm font-semibold text-red-900 dark:text-red-300">{m.check}</p>
                <p className="mt-0.5 text-xs text-slate-700 dark:text-slate-200">{m.reason}</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {m.document_1 ?? '—'}: <span className="font-medium">{m.value_1 ?? '—'}</span>
                  {m.document_2 && (
                    <> · {m.document_2}: <span className="font-medium">{m.value_2 ?? '—'}</span></>
                  )}
                </p>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      {/* Integrity signals */}
      <SectionCard
        title="Integrity Signals"
        badge={<ProvenanceBadge kind="rule" />}
        explainer={
          <MethodExplainer kind="rule">
            Deterministic, evidence-backed patterns detected from tender, bid and audit data.
            Signals require officer review — they are never findings of misconduct and never
            decide bidder qualification.
          </MethodExplainer>
        }
      >
        {!report.integrity || report.integrity.active_signals === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No active integrity signals touch this bid.
          </p>
        ) : (
          <ul className="space-y-2">
            {report.integrity.items.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2 rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50/60 px-3 py-2.5">
                <span className="min-w-0 flex-1 text-sm font-medium text-slate-900 dark:text-slate-100">{s.title}</span>
                <Badge variant="outline" className="bg-white dark:bg-slate-900 text-[11px]">{labelize(s.severity)}</Badge>
                <Badge variant="outline" className="bg-white dark:bg-slate-900 text-[11px]">{labelize(s.status)}</Badge>
                <Link to="/app/integrity" className="text-xs font-medium text-brand-700 dark:text-brand-300 hover:text-brand-800 dark:hover:text-brand-300">
                  Review →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title="Advisory Summary"
        badge={<ProvenanceBadge kind="rule" />}
        explainer={
          <MethodExplainer kind="rule">
            This section shows the already-generated advisory recommendation for the bid, produced by the deterministic rules engine with retrieved policy citations — no AI model generated it. It explains and summarises findings only — it never decides. The final decision always rests with the Procurement Officer.
          </MethodExplainer>
        }
      >
        {report.ai_summary ? (
          <dl className="divide-y divide-slate-100 dark:divide-slate-800">
            <KeyValue k="Recommendation" v={labelize(report.ai_summary.recommendation)} />
            {report.ai_summary.reason && <KeyValue k="Reasoning" v={report.ai_summary.reason} />}
          </dl>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No advisory recommendation has been generated for this bid yet. It can be generated from the bid detail page.
          </p>
        )}
      </SectionCard>

      {/* Officer decision bar */}
      {showDecisionBar && (
        <div className="rounded-lg border-2 border-brand-200 dark:border-brand-800 bg-brand-50/50 dark:bg-brand-950/40 p-5">
          <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Procurement Officer Decision</h2>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            You are the final decision maker. The summary above is decision <em>support</em> — review the evidence before deciding.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {decisionButtons.map((b) => (
              <Button key={b.decision} size="sm" onClick={() => setDecisionDialog(b.decision)} disabled={busy} className={b.classes}>
                {b.icon}
                {b.label}
              </Button>
            ))}
          </div>
        </div>
      )}

      {report.decision && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
          <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">Recorded Decision</h2>
          <dl className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
            <KeyValue k="Decision" v={labelize(report.decision.decision)} />
            {report.decision.reason && <KeyValue k="Reason" v={report.decision.reason} />}
            <KeyValue k="Decided By" v={report.decision.decided_by ?? '—'} />
            <KeyValue k="Decided At" v={formatDateTime(report.decision.decided_at)} />
          </dl>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            To change this decision, use the Modify Decision workflow on the bid detail page.
          </p>
        </div>
      )}

      {/* Decision confirmation */}
      <Dialog open={decisionDialog !== null} onOpenChange={(o) => !o && setDecisionDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{decisionDialog ? `${labelize(decisionDialog)} this bid?` : ''}</DialogTitle>
            <DialogDescription>
              This records the final procurement decision. The summary remains available as decision support.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <dl className="divide-y divide-slate-100 dark:divide-slate-800 rounded-md border border-slate-200 dark:border-slate-800 px-4">
              <KeyValue k="Bidder" v={report.bid_info.bidder_name ?? '—'} />
              <KeyValue k="Tender" v={`${report.bid_info.tender_number ?? ''} · ${report.bid_info.tender_title ?? ''}`} />
              <KeyValue
                k="Compliance Score"
                v={report.compliance_score != null ? `${report.compliance_score.toFixed(1)} / 100` : 'Not evaluated'}
              />
              <KeyValue k="Risk Level" v={report.risk ? labelize(report.risk.level) : 'Not assessed'} />
              <KeyValue k="Verification Summary" v={STATUS_META[report.status].label} />
            </dl>
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-slate-700 dark:text-slate-200">
                Decision reason {decisionDialog !== 'APPROVE' && <span className="text-red-600 dark:text-red-400">*</span>}
              </label>
              <textarea
                value={decisionReason}
                onChange={(e) => setDecisionReason(e.target.value)}
                rows={3}
                placeholder="Record the basis for this decision…"
                className="w-full rounded-md border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none"
              />
              {decisionError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{decisionError}</p>}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDecisionDialog(null)} className="border-slate-300 dark:border-slate-700">
              Cancel
            </Button>
            <Button onClick={confirmDecision} disabled={busy} className="bg-brand-700 hover:bg-brand-800 text-white">
              Confirm {decisionDialog ? labelize(decisionDialog) : ''}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
