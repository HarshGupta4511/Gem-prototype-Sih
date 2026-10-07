import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  ShieldAlert,
  RefreshCw,
  Play,
  ChevronDown,
  FileText,
  CheckCircle2,
  Database,
  Eye,
  Search,
  XCircle,
  StickyNote,
} from 'lucide-react';
import { integrityApi, demoVarietyApi, getErrorMessage, getErrorStatus } from '../lib/api';
import { useToast } from '../components/ui/toaster';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../components/ui/dialog';
import { PageHeader, BackLink, LoadingBlock, EmptyState } from '../components/common/ui-helpers';
import { MethodExplainer } from '../components/common/method';
import { labelize } from '../lib/utils';
import type { IntegrityFinding } from '../types';

const SEVERITY_STYLES: Record<string, string> = {
  REVIEW_REQUIRED: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-400 dark:border-red-900',
  ELEVATED: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-400 dark:border-amber-900',
  INFORMATIONAL: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:border-slate-700',
};

const STATUS_STYLES: Record<string, string> = {
  OPEN: 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-900',
  ACKNOWLEDGED: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:border-slate-700',
  UNDER_REVIEW: 'bg-indigo-50 text-indigo-800 border-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-300 dark:border-indigo-900',
  INVESTIGATING: 'bg-purple-50 text-purple-800 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-900',
  CLOSED: 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-400 dark:border-emerald-900',
};

const SIGNAL_LABELS: Record<string, string> = {
  RECURRING_BIDDER_COHORT: 'Cross-Tender Co-Participation',
  REPEATED_PARTICIPATION: 'Repeated Participation',
  BID_ROTATION_PATTERN: 'Possible Bid Rotation',
  BIDDER_RELATIONSHIP: 'Bidder Relationship',
  OFFICER_BIDDER_ASSOCIATION: 'Officer–Bidder Association',
  CROSS_TENDER_CONCENTRATION: 'Cross-Tender Concentration',
  DOCUMENT_IDENTITY_RELATIONSHIP: 'Duplicate / Related Bidder Identity',
  CROSS_BID_DOCUMENT_SIMILARITY: 'Cross-Bid Document Similarity',
  IDENTITY_REGISTRATION_INCONSISTENCY: 'Identity / Registration Inconsistency',
  REPEATED_HISTORICAL_ANOMALIES: 'Repeated Historical Anomalies',
};

interface SignalAction {
  key: 'acknowledge' | 'mark_review' | 'investigate' | 'close' | 'add_note';
  label: string;
  icon: typeof Eye;
  purpose: string;
  needsNote?: boolean;
  uiOnly?: boolean;
  enabledFor?: readonly string[];
}

const ACTIONS: SignalAction[] = [
  {
    key: 'acknowledge', label: 'Acknowledge', icon: Eye,
    purpose: 'I have seen this signal.',
    needsNote: false, enabledFor: ['OPEN'],
  },
  {
    key: 'mark_review', label: 'Mark for Review', icon: Search,
    purpose: 'This signal requires formal examination.',
    needsNote: false, enabledFor: ['OPEN', 'ACKNOWLEDGED'],
  },
  {
    key: 'investigate', label: 'Investigate', icon: ShieldAlert,
    purpose: 'Open the supporting evidence and investigate the underlying records.',
    uiOnly: true,
  },
  {
    key: 'close', label: 'Close Signal', icon: CheckCircle2,
    purpose: 'Review completed; close this signal with a recorded reason.',
    needsNote: true, enabledFor: ['OPEN', 'ACKNOWLEDGED', 'UNDER_REVIEW'],
  },
  {
    key: 'add_note', label: 'Add Review Note', icon: StickyNote,
    purpose: 'Add evidence-based officer comments.',
    needsNote: true, enabledFor: ['OPEN', 'ACKNOWLEDGED', 'UNDER_REVIEW'],
  },
];

function formatDateTime(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function FindingCard({ finding }: { finding: IntegrityFinding }) {
  const { isOfficer } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = React.useState(false);
  const [dialogAction, setDialogAction] = React.useState<SignalAction | null>(null);
  const [note, setNote] = React.useState('');

  const actionMutation = useMutation({
    mutationFn: (vars: { action: string; note?: string }) =>
      integrityApi.officerAction(finding.id, vars.action, vars.note),
    onSuccess: () => {
      toast('success', 'Signal updated');
      queryClient.invalidateQueries({ queryKey: ['integrity-findings'] });
      queryClient.invalidateQueries({ queryKey: ['integrity-overview'] });
      setDialogAction(null);
      setNote('');
    },
    onError: (err) => toast('error', 'Action failed', getErrorMessage(err)),
  });

  const submit = () => {
    if (!dialogAction || dialogAction.uiOnly) return;
    if (dialogAction.needsNote && !note.trim()) {
      toast('error',
        dialogAction.key === 'close'
          ? 'A closure reason is required to close a signal'
          : 'A review note is required for this action');
      return;
    }
    actionMutation.mutate({ action: dialogAction.key, note: note.trim() || undefined });
  };

  const handleActionClick = (a: SignalAction) => {
    if (a.uiOnly) {
      // Investigate opens the evidence panel — it is not a status change.
      setExpanded(true);
      return;
    }
    setDialogAction(a);
  };

  return (
    <Card className="border-slate-200 dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              {finding.title}
            </CardTitle>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {SIGNAL_LABELS[finding.signal_type] ?? labelize(finding.signal_type)} ·{' '}
              detected {formatDateTime(finding.created_at)}
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline" className={SEVERITY_STYLES[finding.severity] ?? SEVERITY_STYLES.INFORMATIONAL}>
              {labelize(finding.severity)}
            </Badge>
            <Badge variant="outline" className={STATUS_STYLES[finding.status] ?? STATUS_STYLES.OPEN}>
              {labelize(finding.status)}
            </Badge>
            {finding.is_demo_history && (
              <Badge variant="outline" className="bg-violet-50 text-violet-800 border-violet-200 dark:bg-violet-950/60 dark:text-violet-300 dark:border-violet-900">
                DEMO DATA
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-1">
        <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">{finding.description}</p>

        {finding.affected_tenders.length > 0 && (
          <div className="text-xs text-slate-600 dark:text-slate-400">
            <span className="font-medium text-slate-700 dark:text-slate-200">Tenders: </span>
            {finding.affected_tenders.map((t, i) => (
              <span key={t.tender_id}>
                {i > 0 && ', '}
                <Link
                  to={`/app/tenders/${t.tender_id}`}
                  className="text-brand-700 hover:text-brand-800 hover:underline dark:text-brand-400 dark:hover:text-brand-300"
                >
                  {t.tender_number}
                </Link>
              </span>
            ))}
            {finding.is_demo_history && (
              <span className="ml-1 text-violet-700 dark:text-violet-400">(synthetic DEMO history)</span>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 text-xs font-medium text-brand-700 hover:text-brand-800 dark:text-brand-400 dark:hover:text-brand-300"
          aria-expanded={expanded}
        >
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`} />
          {expanded ? 'Hide evidence & rule logic' : 'View evidence & rule logic'}
        </button>

        {expanded && (
          <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-950/60">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Supporting evidence</p>
              <ul className="mt-1.5 space-y-1.5">
                {finding.evidence.map((e, i) => (
                  <li key={i} className="text-xs leading-relaxed text-slate-700 dark:text-slate-200">
                    <span className="font-medium">{e.label}:</span> {e.detail}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Rule / signal logic</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">{finding.rule_logic}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Recommended procedural action</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400">{finding.recommended_action}</p>
            </div>
            {finding.officer_note && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Officer note</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-700 dark:text-slate-200">{finding.officer_note}</p>
                <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                  Last reviewed {formatDateTime(finding.reviewed_at)}
                </p>
              </div>
            )}
          </div>
        )}

        {isOfficer && finding.status !== 'CLOSED' && (
          <div className="flex flex-wrap gap-1.5 border-t border-slate-100 pt-3 dark:border-slate-800">
            {ACTIONS.map((a) => {
              const gated = a.enabledFor !== undefined && !a.enabledFor.includes(finding.status);
              return (
                <Button
                  key={a.key}
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  title={a.purpose}
                  onClick={() => handleActionClick(a)}
                  disabled={actionMutation.isPending || gated}
                >
                  <a.icon className="mr-1 h-3 w-3" />
                  {a.label}
                </Button>
              );
            })}
          </div>
        )}

        <Dialog open={dialogAction !== null} onOpenChange={(o) => !o && setDialogAction(null)}>
          <DialogContent className="max-w-md bg-white dark:bg-slate-900">
            <DialogHeader>
              <DialogTitle className="text-base font-bold text-slate-900 dark:text-slate-100">
                {dialogAction?.key === 'close' ? 'Close Integrity Signal?' : dialogAction?.label}
              </DialogTitle>
              <DialogDescription className="text-sm text-slate-600 dark:text-slate-400">
                {dialogAction?.key === 'close'
                  ? 'Add a brief closure reason before closing this signal.'
                  : dialogAction?.purpose}
              </DialogDescription>
            </DialogHeader>
            {!dialogAction?.uiOnly && (
              <>
                <div className="py-2">
                  <label className="mb-1 block text-xs font-medium text-slate-700 dark:text-slate-200">
                    {dialogAction?.key === 'close'
                      ? 'Closure reason (required)'
                      : <>Officer note {dialogAction?.needsNote ? '(required)' : '(optional)'}</>}
                  </label>
                  <Input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder={
                      dialogAction?.key === 'close'
                        ? 'e.g. Verified bidder records; no further action needed…'
                        : 'Record the basis for this action…'
                    }
                    className="text-sm"
                  />
                </div>
                <DialogFooter>
                  <Button variant="outline" size="sm" onClick={() => setDialogAction(null)}>
                    Cancel
                  </Button>
                  <Button size="sm" onClick={submit} disabled={actionMutation.isPending}>
                    {actionMutation.isPending
                      ? 'Saving…'
                      : dialogAction?.key === 'close'
                        ? 'Close Signal'
                        : 'Confirm'}
                  </Button>
                </DialogFooter>
              </>
            )}
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

export default function Integrity() {
  const { canVerify, isOfficer } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = React.useState('');
  const [severityFilter, setSeverityFilter] = React.useState('');

  const overviewQuery = useQuery({
    queryKey: ['integrity-overview'],
    queryFn: integrityApi.overview,
    staleTime: 30_000,
  });
  const findingsQuery = useQuery({
    queryKey: ['integrity-findings', statusFilter, severityFilter],
    queryFn: () =>
      integrityApi.findings({
        status: statusFilter || undefined,
        severity: severityFilter || undefined,
      }),
    staleTime: 30_000,
  });

  const analyzeMutation = useMutation({
    mutationFn: integrityApi.analyze,
    onSuccess: (res) => {
      toast(
        'success',
        `Analysis complete — ${res.new_signals} new signal${res.new_signals === 1 ? '' : 's'}`,
        `${res.signals_detected} pattern(s) detected across ${res.tenders_analyzed} tenders`,
      );
      queryClient.invalidateQueries({ queryKey: ['integrity-findings'] });
      queryClient.invalidateQueries({ queryKey: ['integrity-overview'] });
    },
    onError: (err) => {
      // 409 = analysis already running (double-click protection) — not a failure.
      if (getErrorStatus(err) === 409) {
        toast('info', 'Analysis already running', 'Please wait for the current run to finish.');
        return;
      }
      toast('error', 'Analysis failed', getErrorMessage(err));
    },
  });

  const dedupeMutation = useMutation({
    mutationFn: integrityApi.dedupe,
    onSuccess: (res) => {
      toast(
        'success',
        res.removed_duplicates > 0
          ? `Removed ${res.removed_duplicates} duplicate signal${res.removed_duplicates === 1 ? '' : 's'}`
          : 'No duplicate signals found',
        `${res.remaining_open} open signals remain`,
      );
      queryClient.invalidateQueries({ queryKey: ['integrity-findings'] });
      queryClient.invalidateQueries({ queryKey: ['integrity-overview'] });
    },
    onError: (err) => toast('error', 'Cleanup failed', getErrorMessage(err)),
  });

  const cleanupMutation = useMutation({
    mutationFn: integrityApi.cleanupStale,
    onSuccess: (res) => {
      const parts: string[] = [];
      const r = res as Record<string, number>;
      if (r.demo_tenders) parts.push(`${r.demo_tenders} demo tenders`);
      if (r.orphan_findings) parts.push(`${r.orphan_findings} orphan signals`);
      if (r.demo_findings) parts.push(`${r.demo_findings} stale signals`);
      if (r.duplicate_findings_removed) parts.push(`${r.duplicate_findings_removed} duplicates`);
      toast(
        'success',
        parts.length > 0 ? 'Stale integrity data cleaned' : 'Integrity data is clean',
        parts.length > 0 ? parts.join(' · ') : 'No stale records found',
      );
      queryClient.invalidateQueries({ queryKey: ['integrity-findings'] });
      queryClient.invalidateQueries({ queryKey: ['integrity-overview'] });
    },
    onError: (err) => toast('error', 'Cleanup failed', getErrorMessage(err)),
  });

  const varietyStatusQuery = useQuery({
    queryKey: ['variety-demo-status'],
    queryFn: demoVarietyApi.datasetStatus,
    staleTime: 30_000,
    retry: 1,
  });
  const varietyLoaded = varietyStatusQuery.data?.loaded === true;

  const loadVarietyMutation = useMutation({
    mutationFn: demoVarietyApi.loadDataset,
    onSuccess: (res: unknown) => {
      const r = (res ?? {}) as Record<string, unknown>;
      const parts: string[] = [];
      for (const [k, v] of Object.entries(r)) {
        if (typeof v === 'number') parts.push(`${v} ${k.replace(/_/g, ' ')}`);
      }
      toast(
        'success',
        'Variety demo dataset loaded',
        parts.length > 0 ? parts.join(' \u00b7 ') : undefined,
      );
      queryClient.invalidateQueries({ queryKey: ['variety-demo-status'] });
      analyzeMutation.mutate();
    },
    onError: (err) => {
      if (getErrorStatus(err) === 409) {
        toast('info', 'Load already in progress', 'Please wait for the current load to finish.');
        return;
      }
      toast('error', 'Variety dataset load failed', getErrorMessage(err));
    },
  });

  const [varietyResetDialogOpen, setVarietyResetDialogOpen] = React.useState(false);

  const resetVarietyMutation = useMutation({
    mutationFn: demoVarietyApi.resetDataset,
    onSuccess: () => {
      toast('success', 'Variety demo dataset reset successfully.');
      setVarietyResetDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ['variety-demo-status'] });
      queryClient.invalidateQueries({ queryKey: ['integrity-findings'] });
      queryClient.invalidateQueries({ queryKey: ['integrity-overview'] });
    },
    onError: (err) => {
      const msg = getErrorMessage(err);
      const hint = !getErrorStatus(err)
        ? 'The request did not reach the server. Check that the backend is running and reachable, then try again.'
        : undefined;
      toast('error', 'Variety dataset reset failed', hint ? `${msg} \u2014 ${hint}` : msg);
    },
  });

  const refreshAll = () => {
    overviewQuery.refetch();
    findingsQuery.refetch();
  };
  const refreshing = overviewQuery.isRefetching || findingsQuery.isRefetching;

  React.useEffect(() => {
    if (overviewQuery.error) toast('error', 'Could not load integrity overview', getErrorMessage(overviewQuery.error));
  }, [overviewQuery.error, toast]);
  React.useEffect(() => {
    if (findingsQuery.error) toast('error', 'Could not load signals', getErrorMessage(findingsQuery.error));
  }, [findingsQuery.error, toast]);

  const overview = overviewQuery.data;
  const findings = findingsQuery.data ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Procurement Integrity"
        description="Deterministic, evidence-backed integrity signals from tender, bid and audit data. Signals require officer review — they are never findings of misconduct."
        back={<BackLink to="/app/dashboard" label="Back to Dashboard" />}
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={refreshAll}
              disabled={refreshing}
              className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            {canVerify && !varietyLoaded && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadVarietyMutation.mutate()}
                disabled={loadVarietyMutation.isPending || varietyStatusQuery.isLoading}
                className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                <Database className={`mr-1.5 h-3.5 w-3.5 ${loadVarietyMutation.isPending ? 'animate-pulse' : ''}`} />
                {loadVarietyMutation.isPending ? 'Loading variety data…' : 'Load Variety Demo Data'}
              </Button>
            )}
            {canVerify && varietyLoaded && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  disabled
                  className="border-emerald-300 text-emerald-700 text-xs dark:border-emerald-800 dark:text-emerald-400 cursor-default"
                >
                  <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                  Variety Demo Data Loaded
                </Button>
                <button
                  type="button"
                  onClick={() => setVarietyResetDialogOpen(true)}
                  disabled={resetVarietyMutation.isPending}
                  className="self-center text-xs font-medium text-red-700 hover:text-red-800 hover:underline disabled:opacity-50 dark:text-red-400 dark:hover:text-red-300"
                >
                  {resetVarietyMutation.isPending ? 'Resetting Variety Data…' : 'Reset'}
                </button>
              </>
            )}
            {canVerify && (
              <Button
                size="sm"
                onClick={() => analyzeMutation.mutate()}
                disabled={analyzeMutation.isPending}
                className="text-xs"
              >
                <Play className={`mr-1.5 h-3.5 w-3.5 ${analyzeMutation.isPending ? 'animate-spin' : ''}`} />
                {analyzeMutation.isPending ? 'Analysing…' : 'Run Analysis'}
              </Button>
            )}
            {canVerify && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => dedupeMutation.mutate()}
                disabled={dedupeMutation.isPending}
                className="text-xs"
                title="Remove duplicate integrity signals, keeping the oldest of each"
              >
                {dedupeMutation.isPending ? 'Cleaning…' : 'Clean Duplicates'}
              </Button>
            )}
            {canVerify && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => cleanupMutation.mutate()}
                disabled={cleanupMutation.isPending}
                className="text-xs"
                title="Remove demo-history tenders, orphan signals and stale records"
              >
                {cleanupMutation.isPending ? 'Cleaning…' : 'Clean Stale Data'}
              </Button>
            )}
          </div>
        }
      />

      <MethodExplainer kind="rule" title="How integrity signals are generated">
        Signals are computed by deterministic rules over existing tender, bid, bidder and
        audit records (recurring bidder cohorts, repeated participation, possible rotation
        patterns, shared identifiers, award concentration). Every signal carries its
        supporting evidence, the exact rule logic, and a recommended procedural action.
        The Procurement Officer — and only the officer — reviews and closes signals.
        Nothing here decides bidder qualification.
      </MethodExplainer>

      {overviewQuery.isLoading ? (
        <LoadingBlock rows={4} />
      ) : overview ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Card className="border-slate-200 dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Open signals</p>
              <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">{overview.open_signals}</p>
            </CardContent>
          </Card>
          <Card className="border-slate-200 dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Requiring review</p>
              <p className="mt-1 text-2xl font-bold text-red-700 dark:text-red-400">{overview.high_priority_signals}</p>
            </CardContent>
          </Card>
          <Card className="border-slate-200 dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Records analysed</p>
              <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">
                {overview.tenders_analyzed}
                <span className="text-sm font-medium text-slate-500 dark:text-slate-400"> tenders</span>
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {overview.bidders_analyzed} bidders · {overview.bids_analyzed} bids
              </p>
            </CardContent>
          </Card>
          <Card className="border-slate-200 dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Last analysis</p>
              <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
                {formatDateTime(overview.last_analysis_at)}
              </p>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {['OPEN', 'ACKNOWLEDGED', 'UNDER_REVIEW', 'CLOSED'].map((s) => (
            <option key={s} value={s}>{labelize(s)}</option>
          ))}
        </select>
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
          aria-label="Filter by severity"
        >
          <option value="">All severities</option>
          {['REVIEW_REQUIRED', 'ELEVATED', 'INFORMATIONAL'].map((s) => (
            <option key={s} value={s}>{labelize(s)}</option>
          ))}
        </select>
      </div>

      {findingsQuery.isLoading ? (
        <LoadingBlock rows={5} />
      ) : findings.length === 0 ? (
        <EmptyState
          icon={<ShieldAlert className="h-6 w-6" />}
          title="No integrity signals"
          description={
            overview?.last_analysis_at
              ? 'The last analysis detected no patterns requiring review in the current data.'
              : 'Run an integrity analysis to scan tender, bid and audit records for review patterns.'
          }
        />
      ) : (
        <div className="space-y-3">
          {findings.map((f) => (
            <FindingCard key={f.id} finding={f} />
          ))}
        </div>
      )}

      {isOfficer && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          <FileText className="mr-1 inline h-3 w-3" />
          Every officer action on a signal is recorded in the audit trail with its basis note.
        </p>
      )}

      {/* Variety reset confirmation is handled below */}

      {/* Reset variety demo dataset confirmation */}
      <Dialog open={varietyResetDialogOpen} onOpenChange={(o) => !o && setVarietyResetDialogOpen(false)}>
        <DialogContent className="max-w-md bg-white dark:bg-slate-900">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 dark:text-slate-100">
              Reset the Variety demo dataset?
            </DialogTitle>
            <DialogDescription className="text-sm text-slate-600 dark:text-slate-400">
              This removes only the 6 synthetic Variety demo tenders (VAR-DEMO-2026-01..06),
              their 42 bids and all associated documents, verification, compliance, risk,
              recommendation and integrity records. Existing records are untouched.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setVarietyResetDialogOpen(false)}
              disabled={resetVarietyMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => resetVarietyMutation.mutate()}
              disabled={resetVarietyMutation.isPending}
              className="bg-red-700 hover:bg-red-800 text-white"
            >
              {resetVarietyMutation.isPending ? 'Resetting Variety Data…' : 'Reset Variety Data'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
