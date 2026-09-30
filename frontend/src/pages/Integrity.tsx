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
  Eye,
  Search,
  XCircle,
  StickyNote,
} from 'lucide-react';
import { integrityApi, getErrorMessage } from '../lib/api';
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
  REVIEW_REQUIRED: 'bg-red-50 text-red-800 border-red-200',
  ELEVATED: 'bg-amber-50 text-amber-800 border-amber-200',
  INFORMATIONAL: 'bg-slate-100 text-slate-700 border-slate-200',
};

const STATUS_STYLES: Record<string, string> = {
  OPEN: 'bg-blue-50 text-blue-800 border-blue-200',
  ACKNOWLEDGED: 'bg-slate-100 text-slate-700 border-slate-200',
  UNDER_REVIEW: 'bg-indigo-50 text-indigo-800 border-indigo-200',
  INVESTIGATING: 'bg-purple-50 text-purple-800 border-purple-200',
  CLOSED: 'bg-emerald-50 text-emerald-800 border-emerald-200',
};

const SIGNAL_LABELS: Record<string, string> = {
  RECURRING_BIDDER_COHORT: 'Recurring Bidder Cohort',
  REPEATED_PARTICIPATION: 'Repeated Participation',
  BID_ROTATION_PATTERN: 'Possible Bid Rotation',
  BIDDER_RELATIONSHIP: 'Bidder Relationship',
  OFFICER_BIDDER_ASSOCIATION: 'Officer–Bidder Association',
  CROSS_TENDER_CONCENTRATION: 'Cross-Tender Concentration',
  DOCUMENT_IDENTITY_RELATIONSHIP: 'Document/Identity Relationship',
};

const ACTIONS = [
  { key: 'acknowledge', label: 'Acknowledge', icon: Eye, needsNote: false },
  { key: 'mark_review', label: 'Mark for Review', icon: Search, needsNote: false },
  { key: 'investigate', label: 'Investigate', icon: ShieldAlert, needsNote: false },
  { key: 'close', label: 'Close Signal', icon: CheckCircle2, needsNote: true },
  { key: 'add_note', label: 'Add Review Note', icon: StickyNote, needsNote: true },
] as const;

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
  const [dialogAction, setDialogAction] = React.useState<(typeof ACTIONS)[number] | null>(null);
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
    if (!dialogAction) return;
    if (dialogAction.needsNote && !note.trim()) {
      toast('error', 'A review note is required for this action');
      return;
    }
    actionMutation.mutate({ action: dialogAction.key, note: note.trim() || undefined });
  };

  return (
    <Card className="border-slate-200">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-sm font-semibold text-slate-900">
              {finding.title}
            </CardTitle>
            <p className="mt-0.5 text-xs text-slate-500">
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
              <Badge variant="outline" className="bg-violet-50 text-violet-800 border-violet-200">
                DEMO DATA
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-1">
        <p className="text-sm leading-relaxed text-slate-700">{finding.description}</p>

        {finding.affected_tenders.length > 0 && (
          <div className="text-xs text-slate-600">
            <span className="font-medium text-slate-700">Tenders: </span>
            {finding.affected_tenders.map((t) => t.tender_number).join(', ')}
            {finding.is_demo_history && (
              <span className="ml-1 text-violet-700">(synthetic DEMO history)</span>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 text-xs font-medium text-brand-700 hover:text-brand-800"
          aria-expanded={expanded}
        >
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`} />
          {expanded ? 'Hide evidence & rule logic' : 'View evidence & rule logic'}
        </button>

        {expanded && (
          <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Supporting evidence</p>
              <ul className="mt-1.5 space-y-1.5">
                {finding.evidence.map((e, i) => (
                  <li key={i} className="text-xs leading-relaxed text-slate-700">
                    <span className="font-medium">{e.label}:</span> {e.detail}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Rule / signal logic</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{finding.rule_logic}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Recommended procedural action</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{finding.recommended_action}</p>
            </div>
            {finding.officer_note && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Officer note</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-700">{finding.officer_note}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  Last reviewed {formatDateTime(finding.reviewed_at)}
                </p>
              </div>
            )}
          </div>
        )}

        {isOfficer && finding.status !== 'CLOSED' && (
          <div className="flex flex-wrap gap-1.5 border-t border-slate-100 pt-3">
            {ACTIONS.map((a) => (
              <Button
                key={a.key}
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => setDialogAction(a)}
                disabled={actionMutation.isPending}
              >
                <a.icon className="mr-1 h-3 w-3" />
                {a.label}
              </Button>
            ))}
          </div>
        )}

        <Dialog open={dialogAction !== null} onOpenChange={(o) => !o && setDialogAction(null)}>
          <DialogContent className="max-w-md bg-white">
            <DialogHeader>
              <DialogTitle className="text-base font-bold text-slate-900">
                {dialogAction?.label}
              </DialogTitle>
              <DialogDescription className="text-sm text-slate-600">
                This action is recorded in the audit trail. Signals are patterns requiring
                review — they are not findings of misconduct.
              </DialogDescription>
            </DialogHeader>
            <div className="py-2">
              <label className="mb-1 block text-xs font-medium text-slate-700">
                Officer note {dialogAction?.needsNote ? '(required)' : '(optional)'}
              </label>
              <Input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Record the basis for this action…"
                className="text-sm"
              />
            </div>
            <DialogFooter>
              <Button variant="outline" size="sm" onClick={() => setDialogAction(null)}>
                Cancel
              </Button>
              <Button size="sm" onClick={submit} disabled={actionMutation.isPending}>
                {actionMutation.isPending ? 'Saving…' : 'Confirm'}
              </Button>
            </DialogFooter>
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
    onError: (err) => toast('error', 'Analysis failed', getErrorMessage(err)),
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
              className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
            >
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
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
          <Card className="border-slate-200">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500">Open signals</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">{overview.open_signals}</p>
            </CardContent>
          </Card>
          <Card className="border-slate-200">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500">Requiring review</p>
              <p className="mt-1 text-2xl font-bold text-red-700">{overview.high_priority_signals}</p>
            </CardContent>
          </Card>
          <Card className="border-slate-200">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500">Records analysed</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">
                {overview.tenders_analyzed}
                <span className="text-sm font-medium text-slate-500"> tenders</span>
              </p>
              <p className="text-xs text-slate-500">
                {overview.bidders_analyzed} bidders · {overview.bids_analyzed} bids
              </p>
            </CardContent>
          </Card>
          <Card className="border-slate-200">
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-slate-500">Last analysis</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
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
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-700"
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {['OPEN', 'ACKNOWLEDGED', 'UNDER_REVIEW', 'INVESTIGATING', 'CLOSED'].map((s) => (
            <option key={s} value={s}>{labelize(s)}</option>
          ))}
        </select>
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-700"
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
        <p className="text-xs text-slate-500">
          <FileText className="mr-1 inline h-3 w-3" />
          Every officer action on a signal is recorded in the audit trail with its basis note.
        </p>
      )}
    </div>
  );
}
