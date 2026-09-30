import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams, Link } from 'react-router-dom';
import {
  FileCheck2,
  Send,
  Plus,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  MessageSquare,
  Eye,
} from 'lucide-react';
import { reportsApi, officerApi, getErrorMessage } from '../lib/api';
import { useToast } from '../components/ui/toaster';
import { useAuth } from '../context/AuthContext';
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

const STATUS_META: Record<ReportStatus, { label: string; classes: string }> = {
  DRAFT: { label: 'Draft', classes: 'bg-slate-100 text-slate-700 border-slate-300' },
  GENERATED: { label: 'Generated', classes: 'bg-blue-50 text-blue-800 border-blue-200' },
  SENT: { label: 'Sent to Procurement Officer', classes: 'bg-amber-50 text-amber-800 border-amber-200' },
  RECEIVED: { label: 'Received by Officer', classes: 'bg-teal-50 text-teal-800 border-teal-200' },
  UNDER_REVIEW: { label: 'Under Officer Review', classes: 'bg-indigo-50 text-indigo-800 border-indigo-200' },
  DECISION: { label: 'Decision Made', classes: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
};

const LIFECYCLE_STEPS: ReportStatus[] = ['DRAFT', 'GENERATED', 'SENT', 'RECEIVED', 'UNDER_REVIEW', 'DECISION'];

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
    <section className="rounded-lg border border-slate-200 bg-white shadow-xs">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-3.5">
        <h2 className="text-sm font-bold text-slate-900">{title}</h2>
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
      <dt className="shrink-0 text-slate-500">{k}</dt>
      <dd className="text-right font-medium text-slate-900">{v}</dd>
    </div>
  );
}

export default function VerificationReport() {
  const { bidId } = useParams<{ bidId: string }>();
  const bid_id = Number(bidId);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();
  const { canReport, isOfficer, isAuditor } = useAuth();

  const [observation, setObservation] = React.useState('');
  const [sendOpen, setSendOpen] = React.useState(false);
  const [decisionDialog, setDecisionDialog] = React.useState<OfficerDecision | null>(null);
  const [decisionReason, setDecisionReason] = React.useState('');
  const [decisionError, setDecisionError] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const openedRef = React.useRef(false);

  const { data: report, isLoading, error, refetch } = useQuery({
    queryKey: ['verification-report', bid_id],
    queryFn: () => reportsApi.get(bid_id),
    enabled: Number.isFinite(bid_id),
  });

  // Officer opening a RECEIVED report marks it RECEIVED -> UNDER REVIEW (idempotent).
  // A SENT report stays at SENT until the officer explicitly acknowledges
  // receipt — auto-open must never skip the RECEIVED stage.
  React.useEffect(() => {
    if (isOfficer && report && report.status === 'RECEIVED' && !openedRef.current) {
      openedRef.current = true;
      reportsApi
        .markOpened(bid_id)
        .then(() => {
          qc.invalidateQueries({ queryKey: ['verification-report', bid_id] });
          qc.invalidateQueries({ queryKey: ['reports-inbox'] });
        })
        .catch(() => {});
    }
  }, [isOfficer, report, bid_id, qc]);

  React.useEffect(() => {
    if (error) toast('error', 'Could not load report', getErrorMessage(error));
  }, [error, toast]);

  async function runAction(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ['verification-report', bid_id] });
      await qc.invalidateQueries({ queryKey: ['reports-inbox'] });
    } catch (e) {
      toast('error', `${label} failed`, getErrorMessage(e));
    } finally {
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
      await reportsApi.addObservation(bid_id, text);
      setObservation('');
      toast('success', 'Observation recorded');
    });
  }

  async function confirmSend() {
    setSendOpen(false);
    await runAction('Send report', async () => {
      await reportsApi.send(bid_id);
      toast('success', 'Report sent to Procurement Officer', 'The officer has been notified for review.');
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
        reason: decisionReason.trim() || 'Approved by Procurement Officer after reviewing the verification report.',
      });
      setDecisionDialog(null);
      setDecisionReason('');
      await qc.invalidateQueries({ queryKey: ['verification-report', bid_id] });
      await qc.invalidateQueries({ queryKey: ['reports-inbox'] });
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
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-sm text-red-800">
        Verification report could not be loaded.
      </div>
    );
  }

  const statusMeta = STATUS_META[report.status];
  const reachedIdx = LIFECYCLE_STEPS.indexOf(report.status);
  const canGenerate = canReport && (report.status === 'DRAFT' || report.status === 'GENERATED');
  const canSend = canReport && report.status === 'GENERATED';
  const canObserve = canReport && (report.status === 'DRAFT' || report.status === 'GENERATED');
  const showDecisionBar =
    isOfficer && !report.decision && (report.status === 'SENT' || report.status === 'RECEIVED' || report.status === 'UNDER_REVIEW');

  const decisionButtons: { decision: OfficerDecision; label: string; icon: React.ReactNode; classes: string }[] = [
    { decision: 'APPROVE', label: 'Approve Bid', icon: <CheckCircle2 className="mr-1.5 h-4 w-4" />, classes: 'bg-emerald-700 hover:bg-emerald-800 text-white' },
    { decision: 'REJECT', label: 'Reject Bid', icon: <XCircle className="mr-1.5 h-4 w-4" />, classes: 'bg-red-700 hover:bg-red-800 text-white' },
    { decision: 'ESCALATE', label: 'Escalate', icon: <AlertTriangle className="mr-1.5 h-4 w-4" />, classes: 'bg-amber-600 hover:bg-amber-700 text-white' },
    { decision: 'REQUEST_CLARIFICATION', label: 'Request Clarification', icon: <MessageSquare className="mr-1.5 h-4 w-4" />, classes: 'border-slate-300 text-slate-700 hover:bg-slate-50' },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Verification Report"
        description="Evidence-based handoff from the verifier. The Procurement Officer reviews the evidence and makes the final decision."
        back={<BackLink to={`/app/bids/${bid_id}`} label="Back to Bid" />}
        actions={
          <Badge variant="outline" className={cn('text-xs', statusMeta.classes)}>
            {statusMeta.label}
          </Badge>
        }
      />

      {/* Lifecycle timeline */}
      <div className="rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-xs">
        <div className="flex items-center justify-between gap-1">
          {LIFECYCLE_STEPS.map((step, i) => {
            const reached = i <= reachedIdx;
            return (
              <React.Fragment key={step}>
                <div className="flex min-w-0 flex-col items-center gap-1 text-center">
                  <div
                    className={cn(
                      'flex h-7 w-7 items-center justify-center rounded-full border text-[11px] font-bold',
                      reached ? 'border-brand-700 bg-brand-700 text-white' : 'border-slate-200 bg-slate-50 text-slate-400'
                    )}
                  >
                    {i + 1}
                  </div>
                  <span className={cn('text-[10px] font-medium leading-tight', reached ? 'text-slate-900' : 'text-slate-400')}>
                    {STATUS_META[step].label}
                  </span>
                </div>
                {i < LIFECYCLE_STEPS.length - 1 && (
                  <div className={cn('mb-5 h-0.5 min-w-4 flex-1 rounded', i < reachedIdx ? 'bg-brand-700' : 'bg-slate-200')} />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Bid information */}
      <SectionCard title="Bid Information" badge={<ProvenanceBadge kind="verified" />}>
        <dl className="divide-y divide-slate-100">
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
          <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3 text-center">
            <p className="text-2xl font-bold text-slate-900">{report.documents.submitted_count}</p>
            <p className="text-xs text-slate-500">Documents Submitted</p>
          </div>
          <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3 text-center">
            <p className="text-2xl font-bold text-slate-900">{report.documents.processed_count}</p>
            <p className="text-xs text-slate-500">Documents Processed</p>
          </div>
          <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3 text-center">
            <p className="text-2xl font-bold text-slate-900">{report.documents.issues.length}</p>
            <p className="text-xs text-slate-500">Flagged for Review</p>
          </div>
        </div>
        {report.documents.items.length > 0 ? (
          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 text-left text-slate-500">
                  <th className="px-3 py-2 font-semibold">Document</th>
                  <th className="px-3 py-2 font-semibold">Type</th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2 font-semibold">Fields Extracted</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {report.documents.items.map((d) => (
                  <tr key={d.id}>
                    <td className="px-3 py-2 font-medium text-slate-900">{d.file_name}</td>
                    <td className="px-3 py-2 text-slate-600">{d.document_type}</td>
                    <td className="px-3 py-2 text-slate-600">{labelize(d.status)}</td>
                    <td className="px-3 py-2 text-slate-600">{d.extracted_field_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">No documents have been submitted for this bid yet.</p>
        )}
        {report.documents.issues.length > 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-900">
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
            <div className="overflow-x-auto rounded-md border border-slate-200">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-slate-50 text-left text-slate-500">
                    <th className="px-3 py-2 font-semibold">Field</th>
                    <th className="px-3 py-2 font-semibold">Value</th>
                    <th className="px-3 py-2 font-semibold">Source Document</th>
                    <th className="px-3 py-2 font-semibold">Method</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {report.extracted_fields.items.map((f, i) => (
                    <tr key={i}>
                      <td className="px-3 py-2 font-medium text-slate-900">{f.field_name}</td>
                      <td className="px-3 py-2 text-slate-700">{f.field_value ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-600">{f.document_name ?? '—'}</td>
                      <td className="px-3 py-2 text-slate-600">{f.extraction_method}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {report.extracted_fields.total > report.extracted_fields.items.length && (
              <p className="text-xs text-slate-500">
                Showing {report.extracted_fields.items.length} of {report.extracted_fields.total} extracted fields.
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-slate-500">No information has been extracted yet.</p>
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
          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 text-left text-slate-500">
                  <th className="px-3 py-2 font-semibold">Source</th>
                  <th className="px-3 py-2 font-semibold">Identifier</th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2 font-semibold">Observation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {report.verification.map((v, i) => (
                  <tr key={i}>
                    <td className="px-3 py-2 font-medium text-slate-900">
                      {v.source} {v.is_mock && <MockSourceLabel />}
                    </td>
                    <td className="px-3 py-2 font-mono text-slate-700">{v.identifier}</td>
                    <td className="px-3 py-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          v.status === 'VERIFIED'
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                            : v.status === 'MISMATCH' || v.status === 'FAILED'
                              ? 'bg-red-50 text-red-800 border-red-200'
                              : 'bg-amber-50 text-amber-800 border-amber-200'
                        )}
                      >
                        {labelize(v.status)}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-slate-600">{v.observation ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">Verification has not been run for this bid yet.</p>
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
        {report.compliance.length > 0 ? (
          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-50 text-left text-slate-500">
                  <th className="px-3 py-2 font-semibold">Requirement</th>
                  <th className="px-3 py-2 font-semibold">Result</th>
                  <th className="px-3 py-2 font-semibold">Evidence</th>
                  <th className="px-3 py-2 font-semibold">Observation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {report.compliance.map((c, i) => (
                  <tr key={i}>
                    <td className="px-3 py-2 font-medium text-slate-900">{c.requirement}</td>
                    <td className="px-3 py-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          c.result === 'PASS'
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                            : c.result === 'FAIL'
                              ? 'bg-red-50 text-red-800 border-red-200'
                              : 'bg-amber-50 text-amber-800 border-amber-200'
                        )}
                      >
                        {labelize(c.result)}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-slate-600">
                      {Array.isArray(c.evidence) && c.evidence.length > 0
                        ? c.evidence.map((e) => String(e)).join(', ')
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{c.observation || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">Compliance has not been evaluated for this bid yet.</p>
        )}
      </SectionCard>

      {/* Risk */}
      <SectionCard title="Risk Assessment" badge={<ProvenanceBadge kind="rule" />}>
        {report.risk ? (
          <dl className="divide-y divide-slate-100">
            <KeyValue
              k="Risk Level"
              v={
                <Badge
                  variant="outline"
                  className={cn(
                    report.risk.level === 'LOW'
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                      : report.risk.level === 'CRITICAL'
                        ? 'bg-red-50 text-red-800 border-red-200'
                        : 'bg-amber-50 text-amber-800 border-amber-200'
                  )}
                >
                  {labelize(report.risk.level)}
                </Badge>
              }
            />
            <KeyValue k="Risk Factors" v={report.risk.factors.length > 0 ? report.risk.factors.join('; ') : 'None flagged'} />
            {report.risk.explanation && <KeyValue k="Explanation" v={report.risk.explanation} />}
          </dl>
        ) : (
          <p className="text-sm text-slate-500">Risk has not been assessed for this bid yet.</p>
        )}
      </SectionCard>

      {/* Verifier observations */}
      <SectionCard title="Verifier Observations" badge={<ProvenanceBadge kind="officer" />}>
        {report.observations.length > 0 ? (
          <ul className="space-y-2.5">
            {report.observations.map((o, i) => (
              <li key={i} className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2.5">
                <p className="text-sm text-slate-800">“{o.text}”</p>
                <p className="mt-1 text-xs text-slate-500">
                  — {o.added_by ?? 'Verifier'} · {formatDateTime(o.added_at)}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">No verifier observations recorded yet.</p>
        )}
        {canObserve && (
          <div className="rounded-md border border-dashed border-slate-300 p-3">
            <label className="mb-1.5 block text-xs font-semibold text-slate-700">
              Add a professional observation
            </label>
            <textarea
              value={observation}
              onChange={(e) => setObservation(e.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="e.g. All submitted statutory documents were reviewed. GST and Udyam records were successfully verified. PAN/entity-name mismatch requires officer attention."
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none"
            />
            <div className="mt-2 flex justify-end">
              <Button size="sm" onClick={addObservation} disabled={busy || !observation.trim()} className="bg-brand-700 hover:bg-brand-800 text-white">
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                Add Observation
              </Button>
            </div>
          </div>
        )}
      </SectionCard>

      {/* AI summary */}
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
          <p className="text-sm text-slate-500">
            Consistency checks have not been run for this bid yet. They can be run from the bid's Documents tab.
          </p>
        ) : report.consistency.mismatches === 0 ? (
          <p className="text-sm text-emerald-700">
            {report.consistency.checks_run} check{report.consistency.checks_run === 1 ? '' : 's'} run — no mismatches detected.
          </p>
        ) : (
          <ul className="space-y-2.5">
            {report.consistency.items.map((m, i) => (
              <li key={i} className="rounded-md border border-red-200 bg-red-50/50 px-3 py-2.5">
                <p className="text-sm font-semibold text-red-900">{m.check}</p>
                <p className="mt-0.5 text-xs text-slate-700">{m.reason}</p>
                <p className="mt-1 text-xs text-slate-500">
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
          <p className="text-sm text-slate-500">
            No active integrity signals touch this bid.
          </p>
        ) : (
          <ul className="space-y-2">
            {report.integrity.items.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2 rounded-md border border-amber-200 bg-amber-50/60 px-3 py-2.5">
                <span className="min-w-0 flex-1 text-sm font-medium text-slate-900">{s.title}</span>
                <Badge variant="outline" className="bg-white text-[11px]">{labelize(s.severity)}</Badge>
                <Badge variant="outline" className="bg-white text-[11px]">{labelize(s.status)}</Badge>
                <Link to="/app/integrity" className="text-xs font-medium text-brand-700 hover:text-brand-800">
                  Review →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title="AI Summary"
        badge={<ProvenanceBadge kind="ai" />}
        explainer={
          <MethodExplainer kind="ai">
            This section shows the already-generated AI recommendation for the bid. It explains and summarises findings only — it never decides. The final decision always rests with the Procurement Officer.
          </MethodExplainer>
        }
      >
        {report.ai_summary ? (
          <dl className="divide-y divide-slate-100">
            <KeyValue k="AI Recommendation" v={labelize(report.ai_summary.recommendation)} />
            {report.ai_summary.reason && <KeyValue k="Reasoning" v={report.ai_summary.reason} />}
          </dl>
        ) : (
          <p className="text-sm text-slate-500">
            No AI recommendation has been generated for this bid yet. It can be generated from the bid detail page.
          </p>
        )}
      </SectionCard>

      {/* Verifier handoff actions */}
      {canReport && (
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
          <h2 className="text-sm font-bold text-slate-900">Verifier Handoff</h2>
          <p className="mt-1 text-xs text-slate-500">
            {report.status === 'DRAFT' && 'Finalise the report from the current evidence, then send it to the Procurement Officer.'}
            {report.status === 'GENERATED' && 'The report is ready. Send it to the Procurement Officer for review and decision.'}
            {report.status === 'SENT' && 'Report sent. It is now with the Procurement Officer — the verifier’s responsibility ends here.'}
            {report.status === 'RECEIVED' && 'Receipt acknowledged. Open the report to begin the officer review.'}
            {report.status === 'UNDER_REVIEW' && 'The Procurement Officer has opened the report and is reviewing it.'}
            {report.status === 'DECISION' && 'The Procurement Officer has recorded a final decision.'}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {canGenerate && (
              <Button
                size="sm"
                onClick={() =>
                  runAction('Generate report', async () => {
                    await reportsApi.generate(bid_id);
                    toast('success', 'Verification report generated');
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
              <Button size="sm" onClick={() => setSendOpen(true)} disabled={busy} className="bg-amber-600 hover:bg-amber-700 text-white">
                <Send className="mr-1.5 h-4 w-4" />
                Send to Procurement Officer
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => navigate(`/app/bids/${bid_id}`)} className="border-slate-300 text-slate-700">
              <Eye className="mr-1.5 h-4 w-4" />
              Open Bid Detail
            </Button>
          </div>
        </div>
      )}

      {/* Officer receipt acknowledgement */}
      {isOfficer && report.status === 'SENT' && (
        <div className="rounded-lg border border-teal-200 bg-teal-50/60 p-5">
          <h2 className="text-sm font-bold text-slate-900">Acknowledge Receipt</h2>
          <p className="mt-1 text-xs text-slate-600">
            Confirm you have received this verification report. This moves it from Sent to Received in the report lifecycle.
          </p>
          <div className="mt-3">
            <Button
              size="sm"
              disabled={busy}
              onClick={() =>
                runAction('Acknowledge receipt', async () => {
                  await reportsApi.markReceived(bid_id);
                  toast('success', 'Receipt acknowledged');
                })
              }
              className="bg-teal-700 hover:bg-teal-800 text-white"
            >
              <CheckCircle2 className="mr-1.5 h-4 w-4" />
              Acknowledge Receipt
            </Button>
          </div>
        </div>
      )}

      {/* Officer decision bar */}
      {showDecisionBar && (
        <div className="rounded-lg border-2 border-brand-200 bg-brand-50/50 p-5">
          <h2 className="text-sm font-bold text-slate-900">Procurement Officer Decision</h2>
          <p className="mt-1 text-xs text-slate-600">
            You are the final decision maker. The report above is decision <em>support</em> — review the evidence before deciding.
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

      {isOfficer && report.decision && (
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
          <h2 className="text-sm font-bold text-slate-900">Recorded Decision</h2>
          <dl className="mt-2 divide-y divide-slate-100">
            <KeyValue k="Decision" v={labelize(report.decision.decision)} />
            {report.decision.reason && <KeyValue k="Reason" v={report.decision.reason} />}
            <KeyValue k="Decided By" v={report.decision.decided_by ?? '—'} />
            <KeyValue k="Decided At" v={formatDateTime(report.decision.decided_at)} />
          </dl>
          <p className="mt-2 text-xs text-slate-500">
            To change this decision, use the Change Decision workflow on the bid detail page.
          </p>
        </div>
      )}

      {isAuditor && (
        <p className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
          You are viewing this report in a read-only capacity as Auditor.
        </p>
      )}

      {/* Send confirmation */}
      <Dialog open={sendOpen} onOpenChange={setSendOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send this verification report to the Procurement Officer?</DialogTitle>
            <DialogDescription>
              The report will be handed over for officer review and final decision.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <dl className="divide-y divide-slate-100 rounded-md border border-slate-200 px-4">
              <KeyValue k="Bidder" v={report.bid_info.bidder_name ?? '—'} />
              <KeyValue k="Tender" v={report.bid_info.tender_number ?? '—'} />
              <KeyValue k="Report status" v={STATUS_META[report.status].label} />
            </dl>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSendOpen(false)} className="border-slate-300">
              Cancel
            </Button>
            <Button onClick={confirmSend} disabled={busy} className="bg-amber-600 hover:bg-amber-700 text-white">
              <Send className="mr-1.5 h-4 w-4" />
              Send Report
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Decision confirmation */}
      <Dialog open={decisionDialog !== null} onOpenChange={(o) => !o && setDecisionDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{decisionDialog ? `${labelize(decisionDialog)} this bid?` : ''}</DialogTitle>
            <DialogDescription>
              This records the final procurement decision. The report remains available as decision support.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <dl className="divide-y divide-slate-100 rounded-md border border-slate-200 px-4">
              <KeyValue k="Bidder" v={report.bid_info.bidder_name ?? '—'} />
              <KeyValue k="Tender" v={`${report.bid_info.tender_number ?? ''} · ${report.bid_info.tender_title ?? ''}`} />
              <KeyValue
                k="Compliance Score"
                v={report.compliance_score != null ? `${report.compliance_score.toFixed(1)} / 100` : 'Not evaluated'}
              />
              <KeyValue k="Risk Level" v={report.risk ? labelize(report.risk.level) : 'Not assessed'} />
              <KeyValue k="Verification Report" v={STATUS_META[report.status].label} />
            </dl>
            <div>
              <label className="mb-1.5 block text-xs font-semibold text-slate-700">
                Decision reason {decisionDialog !== 'APPROVE' && <span className="text-red-600">*</span>}
              </label>
              <textarea
                value={decisionReason}
                onChange={(e) => setDecisionReason(e.target.value)}
                rows={3}
                placeholder="Record the basis for this decision…"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none"
              />
              {decisionError && <p className="mt-1 text-xs text-red-600">{decisionError}</p>}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDecisionDialog(null)} className="border-slate-300">
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
