import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  ChevronRight,
  Clock,
  ShieldCheck,
  Users,
  Trash2,
} from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { auditApi, tendersApi, bidsApi, complianceApi, getErrorMessage } from '../lib/api';
import { formatDate, formatDateTime, formatINR, labelize } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogBody,
  DialogFooter,
} from '../components/ui/dialog';
import { useToast } from '../components/ui/toaster';
import { useAuth } from '../context/AuthContext';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  EmptyState,
  LoadingBlock,
} from '../components/common/ui-helpers';
import {
  DecisionBadge,
  RecommendationBadge,
  RiskBadge,
} from '../components/common/badges';
import { ComparisonMatrix } from '../components/tenders/ComparisonMatrix';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
import { BidderLogo } from '../components/common/BidderLogo';
import type {
  AuditLog,
  OfficerDecision,
  Recommendation,
  RiskLevel,
  TenderBidderRow,
} from '../types';

function auditResult(e: AuditLog) {
  const m = (e.metadata ?? {}) as Record<string, unknown>;
  const num = (v: unknown): number | null => (typeof v === 'number' ? v : null);
  const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
  switch (e.action) {
    case 'COMPLIANCE_EVALUATED': {
      const score = num(m.compliance_score);
      return score != null ? (
        <span className="font-mono font-semibold text-emerald-800 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-200 dark:border-emerald-800">
          Score {score.toFixed(1)}%
        </span>
      ) : 'Evaluated';
    }
    case 'RISK_ASSESSED': {
      const level = str(m.risk_level) as RiskLevel | null;
      return level ? <RiskBadge level={level} /> : 'Assessed';
    }
    case 'RECOMMENDATION_GENERATED': {
      const rec = str(m.recommendation) as Recommendation | null;
      return rec ? <RecommendationBadge rec={rec} /> : 'Generated';
    }
    case 'OFFICER_DECISION': {
      const d = str(m.decision) as OfficerDecision | null;
      return d ? <DecisionBadge decision={d} /> : 'Recorded';
    }
    case 'DOCUMENT_PROCESSED': {
      if (m.error) return <Badge variant="destructive">Failed</Badge>;
      const n = num(m.fields);
      return n != null ? `${n} fields extracted` : 'Processed';
    }
    case 'VERIFICATION_RUN': {
      const total = num(m.total);
      return total != null ? `${total} checks` : 'Completed';
    }
    default:
      return <span className="text-slate-500 dark:text-slate-400 font-mono text-xs">{labelize(e.action)}</span>;
  }
}

export default function TenderDetail() {
  const { id } = useParams<{ id: string }>();
  const tenderId = Number(id);
  const validId = Number.isFinite(tenderId);
  const navigate = useNavigate();
  const { toast } = useToast();
  const { isOfficer, canVerify } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('overview');

  // Delete Tender confirmation (Procurement Officer only)
  const [deleteTenderOpen, setDeleteTenderOpen] = useState(false);
  const [deletingTender, setDeletingTender] = useState(false);
  // Bulk bidder delete (Procurement Officer only)
  const [selectedBidIds, setSelectedBidIds] = useState<number[]>([]);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  // Manage-bidders selection mode: checkboxes hidden until the officer opts in
  const [manageMode, setManageMode] = useState(false);
  // Bidder table sort (UI-only): 'asc' = Compliance Score Low -> High (default)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  // Clear row selection whenever a different tender is opened
  useEffect(() => {
    setSelectedBidIds([]);
    setBulkDeleteOpen(false);
    setManageMode(false);
  }, [tenderId]);

  // Intelligent evaluation status modal
  const [evalModalOpen, setEvalModalOpen] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [evalProgress, setEvalProgress] = useState<{ done: number; total: number; name: string } | null>(null);

  // Register Bidder Modal state
  const [registerModalOpen, setRegisterModalOpen] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [regName, setRegName] = useState('');
  const [regPan, setRegPan] = useState('');
  const [regGstin, setRegGstin] = useState('');
  const [regUdyam, setRegUdyam] = useState('');
  const [regContact, setRegContact] = useState('');
  const [regEmail, setRegEmail] = useState('');

  const {
    data: detail,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['tender', tenderId],
    queryFn: () => tendersApi.get(tenderId),
    enabled: validId,
  });

  const bidders = detail?.bidders ?? [];

  const comparisonQuery = useQuery({
    queryKey: ['tender-comparison', tenderId],
    queryFn: () => tendersApi.comparison(tenderId),
    enabled: validId,
  });

  const auditQuery = useQuery({
    queryKey: ['tender-audit', tenderId],
    queryFn: () => auditApi.byTender(tenderId).catch(() => [] as AuditLog[]),
    enabled: validId,
  });

  const handleRegisterBidder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regName.trim()) {
      toast({ title: 'Validation Notice', description: 'Legal Business Name is required.' });
      return;
    }
    setRegistering(true);
    try {
      await bidsApi.create({
        tender_id: tenderId,
        legal_name: regName.trim(),
        pan: regPan.trim().toUpperCase() || undefined,
        gstin: regGstin.trim().toUpperCase() || undefined,
        udyam: regUdyam.trim() || undefined,
        contact_name: regContact.trim() || undefined,
        contact_email: regEmail.trim() || undefined,
      });
      queryClient.invalidateQueries({ queryKey: ['tender', tenderId] });
      queryClient.invalidateQueries({ queryKey: ['tenders'] });
      setRegisterModalOpen(false);
      setRegName('');
      setRegPan('');
      setRegGstin('');
      setRegUdyam('');
      setRegContact('');
      setRegEmail('');
      toast({
        title: 'Bidder Registered',
        description: 'Bid submission record created and queued for document evaluation.',
      });
    } catch (err) {
      toast({ title: 'Registration Failed', description: getErrorMessage(err) });
    } finally {
      setRegistering(false);
    }
  };

  const toggleSelectBid = (bidId: number) => {
    setSelectedBidIds((prev) =>
      prev.includes(bidId) ? prev.filter((id) => id !== bidId) : [...prev, bidId]
    );
  };

  const toggleSelectAllBids = () => {
    setSelectedBidIds((prev) =>
      prev.length === bidders.length ? [] : bidders.map((b: TenderBidderRow) => b.bid_id)
    );
  };

  const confirmBulkDeleteBids = async () => {
    if (selectedBidIds.length === 0) return;
    setBulkDeleting(true);
    const failures: string[] = [];
    for (const bidId of selectedBidIds) {
      try {
        await bidsApi.delete(bidId);
      } catch (err) {
        const name = bidders.find((b: TenderBidderRow) => b.bid_id === bidId)?.legal_name ?? `Bid #${bidId}`;
        failures.push(`${name}: ${getErrorMessage(err)}`);
      }
    }
    setBulkDeleting(false);
    setBulkDeleteOpen(false);
    const deleted = selectedBidIds.length - failures.length;
    setSelectedBidIds([]);
    setManageMode(false);
    queryClient.invalidateQueries({ queryKey: ['tender', tenderId] });
    queryClient.invalidateQueries({ queryKey: ['tender-comparison', tenderId] });
    queryClient.invalidateQueries({ queryKey: ['tenders'] });
    if (failures.length === 0) {
      toast({
        title: 'Bidders Removed',
        description: `${deleted} bidder${deleted === 1 ? '' : 's'} and all derived records were deleted. The audit trail is preserved.`,
      });
    } else {
      toast({
        title: 'Partial Delete',
        description: `${deleted} removed, ${failures.length} failed: ${failures.join('; ')}`,
      });
    }
  };

  // ---- Intelligent evaluation state -------------------------------------
  // Derived from real backend data: a bidder counts as evaluated only when the
  // compliance engine has actually produced a score (evaluate_bid persists the
  // score together with the risk assessment in the same pass).
  const evaluatedBids = bidders.filter((b: TenderBidderRow) => b.compliance_score != null);
  const pendingBids = bidders.filter((b: TenderBidderRow) => b.compliance_score == null);

  // UI-only ordering: evaluated bidders by real compliance score, unevaluated
  // (missing score — never treated as 0) grouped consistently at the end.
  const sortedBidders = useMemo(() => {
    const evaluated = bidders.filter((b: TenderBidderRow) => b.compliance_score != null);
    const unevaluated = bidders.filter((b: TenderBidderRow) => b.compliance_score == null);
    evaluated.sort((a, b) =>
      sortDir === 'asc'
        ? (a.compliance_score as number) - (b.compliance_score as number)
        : (b.compliance_score as number) - (a.compliance_score as number)
    );
    return [...evaluated, ...unevaluated];
  }, [bidders, sortDir]);

  const runEvaluation = async (targets: TenderBidderRow[]) => {
    if (targets.length === 0 || evaluating) return;
    setEvaluating(true);
    const failures: string[] = [];
    let done = 0;
    for (const b of targets) {
      setEvalProgress({ done, total: targets.length, name: b.legal_name });
      try {
        await complianceApi.evaluate(b.bid_id);
        done += 1;
        setEvalProgress({ done, total: targets.length, name: b.legal_name });
      } catch (err) {
        failures.push(`${b.legal_name}: ${getErrorMessage(err)}`);
      }
    }
    setEvaluating(false);
    setEvalProgress(null);
    queryClient.invalidateQueries({ queryKey: ['tender', tenderId] });
    queryClient.invalidateQueries({ queryKey: ['tender-comparison', tenderId] });
    queryClient.invalidateQueries({ queryKey: ['tenders'] });
    if (failures.length === 0) {
      toast({
        title: 'Evaluation Complete',
        description: `${done} bidder${done === 1 ? '' : 's'} evaluated through the deterministic rules engine.`,
      });
    } else {
      toast({
        title: 'Evaluation Partial',
        description: `${done} evaluated, ${failures.length} failed: ${failures.join('; ')}`,
      });
    }
  };

  const confirmDeleteTender = async () => {
    setDeletingTender(true);
    try {
      await tendersApi.delete(tenderId);
      queryClient.invalidateQueries({ queryKey: ['tenders'] });
      toast({
        title: 'Tender Deleted',
        description: 'The tender and all its bids and derived records were deleted.',
      });
      navigate('/app/tenders');
    } catch (err) {
      toast({ title: 'Delete Failed', description: getErrorMessage(err) });
    } finally {
      setDeletingTender(false);
      setDeleteTenderOpen(false);
    }
  };

  if (!validId) {
    return (
      <EmptyState
        title="Invalid Tender Reference"
        description="The tender identifier specified in the route is invalid."
        action={
          <Button onClick={() => navigate('/app/tenders')} size="sm">
            Return to Registry
          </Button>
        }
      />
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingBlock rows={8} />
      </div>
    );
  }

  if (isError || !detail) {
    return (
      <EmptyState
        title="Could not load tender dossier"
        description="Failed to retrieve tender record and evaluation status from server."
        action={
          <Button onClick={() => refetch()} size="sm" variant="outline">
            Retry Connection
          </Button>
        }
      />
    );
  }

  const { tender, requirements, stats } = detail;

  const mandatoryCount = requirements.filter((r) => r.mandatory).length;

  // EMD display: the tender's EMD requirement configuration is the
  // authoritative source. Fall back to the legacy tender.emd_amount_inr
  // column for tenders without an EMD requirement row; show
  // "Exempted / Zero" only when neither exists.
  const emdRequirement = requirements.find(
    (r) =>
      r.rule_config?.value_source === 'extracted.emd_amount_inr' ||
      r.requirement_name === 'EMD Amount',
  );
  const emdFromRequirement = emdRequirement?.rule_config?.value;
  const displayEmdAmount =
    typeof emdFromRequirement === 'number' && emdFromRequirement > 0
      ? emdFromRequirement
      : tender.emd_amount_inr;
  const displayEmdLabel = displayEmdAmount
    ? formatINR(displayEmdAmount)
    : 'Exempted / Zero';

  return (
    <div className="space-y-5">
      {/* 1. Header Navigation & Procurement Dossier Summary */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs">
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 mb-3">
          <Link
            to="/app/tenders"
            className="inline-flex items-center gap-1 font-medium text-blue-800 dark:text-blue-300 hover:underline hover:text-blue-900 dark:hover:text-blue-300"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Tenders Registry</span>
          </Link>
          <span>/</span>
          <span className="font-mono text-slate-700 dark:text-slate-200 font-semibold">{tender.tender_number}</span>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-100 dark:border-slate-800 pb-4">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="font-mono text-sm font-bold text-blue-950 dark:text-blue-200 bg-blue-50 dark:bg-blue-950/60 px-2 py-0.5 rounded border border-blue-200 dark:border-blue-800">
                {tender.tender_number}
              </span>
              <span
                className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide border ${
                  tender.status === 'OPEN'
                    ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-700'
                }`}
              >
                {tender.status}
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">
                {tender.tender_type || 'OPEN'}
              </span>
            </div>
            <h1 className="mt-1.5 text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 font-serif">
              {tender.title}
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />
              <span>{tender.organization}</span>
              <span className="text-slate-300 dark:text-slate-700">•</span>
              <span>{tender.department}</span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => setEvalModalOpen(true)}
              disabled={bidders.length === 0}
              className={
                pendingBids.length === 0 && bidders.length > 0
                  ? 'bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-medium shadow-xs'
                  : 'bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium shadow-xs'
              }
              title={
                bidders.length === 0
                  ? 'No bidders to evaluate'
                  : pendingBids.length === 0
                    ? 'All bidders already evaluated — review status or re-evaluate'
                    : `${pendingBids.length} of ${bidders.length} bidders still require evaluation`
              }
            >
              {pendingBids.length === 0 && bidders.length > 0 ? (
                <>
                  <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                  All {bidders.length} Evaluated
                </>
              ) : pendingBids.length === bidders.length ? (
                <>
                  <Users className="mr-1.5 h-3.5 w-3.5" />
                  Evaluate Bidders ({bidders.length})
                </>
              ) : (
                <>
                  <Users className="mr-1.5 h-3.5 w-3.5" />
                  Evaluate {pendingBids.length} Remaining
                </>
              )}
            </Button>
            {isOfficer && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteTenderOpen(true)}
                className="border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/60 text-xs"
                title="Delete this tender"
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                Delete Tender
              </Button>
            )}
          </div>
        </div>

        {/* Key Metrics Bar */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 pt-1">
          <div className="rounded border border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 block">
              Estimated Value
            </span>
            <span className="font-mono text-sm font-bold text-slate-900 dark:text-slate-100 block mt-0.5">
              {formatINR(tender.estimated_value_inr)}
            </span>
          </div>

          <div className="rounded border border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 block">
              EMD Amount
            </span>
            <span className="font-mono text-sm font-bold text-slate-900 dark:text-slate-100 block mt-0.5">
              {displayEmdLabel}
            </span>
          </div>

          <div className="rounded border border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 block">
              Bids Submitted
            </span>
            <span className="font-mono text-sm font-bold text-slate-900 dark:text-slate-100 block mt-0.5">
              {stats.bidder_count} participating
            </span>
          </div>

          <div className="rounded border border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 block">
              Avg Compliance
            </span>
            <span className="font-mono text-sm font-bold text-emerald-800 dark:text-emerald-300 block mt-0.5">
              {stats.avg_compliance != null ? `${stats.avg_compliance.toFixed(1)}%` : '—'}
            </span>
          </div>

          <div className="rounded border border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 block">
              High Risk Alerts
            </span>
            <span
              className={`font-mono text-sm font-bold block mt-0.5 ${
                stats.high_risk_count > 0 ? 'text-rose-700 dark:text-rose-400' : 'text-slate-900 dark:text-slate-100'
              }`}
            >
              {stats.high_risk_count > 0 ? `${stats.high_risk_count} Flagged` : '0 Alerts'}
            </span>
          </div>

          <div className="rounded border border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 dark:text-slate-400 block">
              Closing Deadline
            </span>
            <span className="font-mono text-xs font-bold text-slate-800 dark:text-slate-200 block mt-0.5">
              {formatDate(tender.closing_date)}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Dossier Tabs Container */}
      <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xs overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 px-4 pt-2 dark:bg-slate-800/60">
            <TabsList className="bg-transparent space-x-1 p-0 h-auto">
              <TabsTrigger
                value="overview"
                className="data-[state=active]:bg-white data-[state=active]:dark:bg-slate-900 data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 data-[state=active]:dark:text-blue-300 rounded-none px-4 py-2.5 text-xs font-semibold dark:text-slate-400"
              >
                1. Overview Dossier
              </TabsTrigger>
              <TabsTrigger
                value="requirements"
                className="data-[state=active]:bg-white data-[state=active]:dark:bg-slate-900 data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 data-[state=active]:dark:text-blue-300 rounded-none px-4 py-2.5 text-xs font-semibold dark:text-slate-400"
              >
                2. Requirements ({requirements.length})
              </TabsTrigger>
              <TabsTrigger
                value="bidders"
                className="data-[state=active]:bg-white data-[state=active]:dark:bg-slate-900 data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 data-[state=active]:dark:text-blue-300 rounded-none px-4 py-2.5 text-xs font-semibold dark:text-slate-400"
              >
                3. Bidders Evaluation ({bidders.length})
              </TabsTrigger>
              <TabsTrigger
                value="matrix"
                className="data-[state=active]:bg-white data-[state=active]:dark:bg-slate-900 data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 data-[state=active]:dark:text-blue-300 rounded-none px-4 py-2.5 text-xs font-semibold dark:text-slate-400"
              >
                4. Compliance Matrix
              </TabsTrigger>
              <TabsTrigger
                value="audit"
                className="data-[state=active]:bg-white data-[state=active]:dark:bg-slate-900 data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 data-[state=active]:dark:text-blue-300 rounded-none px-4 py-2.5 text-xs font-semibold dark:text-slate-400"
              >
                5. Statutory Audit Trail
              </TabsTrigger>
            </TabsList>
          </div>

          {/* TAB 1: OVERVIEW */}
          <TabsContent value="overview" className="p-6 space-y-6">
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-2xs">
              <div className="border-b border-slate-100 dark:border-slate-800 pb-3 mb-4 flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                  Tender Information &amp; Commercial Terms
                </h3>
                <span className="text-xs font-mono text-slate-400 dark:text-slate-500">ID: #{tender.id}</span>
              </div>

              <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3.5 text-xs">
                <div>
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Procuring Entity</dt>
                  <dd className="font-semibold text-slate-900 dark:text-slate-100 mt-0.5">{tender.organization}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Department / Section</dt>
                  <dd className="font-semibold text-slate-900 dark:text-slate-100 mt-0.5">{tender.department}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Estimated Package Value</dt>
                  <dd className="font-mono font-bold text-slate-900 dark:text-slate-100 mt-0.5">
                    {formatINR(tender.estimated_value_inr)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Issue / Release Date</dt>
                  <dd className="font-mono text-slate-800 dark:text-slate-200 mt-0.5">{formatDate(tender.issue_date)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Bid Closing Deadline</dt>
                  <dd className="font-mono font-bold text-rose-800 dark:text-rose-300 mt-0.5">
                    {formatDate(tender.closing_date)} (17:30 IST)
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Earnest Money Deposit (EMD)</dt>
                  <dd className="font-mono font-semibold text-slate-900 dark:text-slate-100 mt-0.5">
                    {displayEmdLabel}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Tender Invitation Type</dt>
                  <dd className="font-semibold text-slate-900 dark:text-slate-100 mt-0.5">
                    {tender.tender_type ? labelize(tender.tender_type) : 'OPEN'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Delivery / Execution Period</dt>
                  <dd className="font-semibold text-slate-900 dark:text-slate-100 mt-0.5">{tender.delivery_period ?? '24 Weeks'}</dd>
                </div>
                <div className="sm:col-span-2 lg:col-span-3">
                  <dt className="text-slate-500 dark:text-slate-400 font-medium">Consignee &amp; Place of Delivery</dt>
                  <dd className="font-semibold text-slate-900 dark:text-slate-100 mt-0.5">
                    {tender.place_of_delivery ?? 'CPCL Manali Refinery, Chennai, Tamil Nadu'}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-2xs">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200 mb-2">
                Technical Scope &amp; Specification
              </h3>
              <p className="text-xs leading-relaxed text-slate-700 dark:text-slate-200 bg-slate-50 p-4 rounded border border-slate-200 dark:border-slate-800 dark:bg-slate-800/60">
                {tender.description}
              </p>
            </div>
          </TabsContent>

          {/* TAB 2: REQUIREMENTS */}
          <TabsContent value="requirements" className="p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                    Deterministic Compliance Rules ({requirements.length})
                  </h3>
                  <SystemLayerTag layer="RULE_ENGINE" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  Requirements and evaluation weights configured for this procurement package.
                </p>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
              <Table>
                <TableHeader>
                  <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider dark:bg-slate-800/80">
                    <TableHead className="py-2.5 px-3">Requirement</TableHead>
                    <TableHead className="py-2.5 px-3">Category</TableHead>
                    <TableHead className="py-2.5 px-3">Threshold / Criteria</TableHead>
                    <TableHead className="py-2.5 px-3 text-center">Mandatory</TableHead>
                  </tr>
                </TableHeader>
                <TableBody>
                  {requirements.map((r) => (
                    <TableRow key={r.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/70">
                      <TableCell className="py-2.5 px-3 font-semibold text-slate-900 dark:text-slate-100 text-xs">
                        {r.requirement_name}
                        {r.description && (
                          <span className="block text-[11px] font-normal text-slate-500 dark:text-slate-400 mt-0.5">
                            {r.description}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-xs text-slate-600 dark:text-slate-400">
                        {labelize(r.category)}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 font-medium text-slate-800 dark:text-slate-200 text-xs">
                        {r.threshold && r.threshold.trim() ? r.threshold : '—'}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-center">
                        {r.mandatory ? (
                          <span className="rounded bg-emerald-50 dark:bg-emerald-950/60 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                            Yes
                          </span>
                        ) : (
                          <span className="rounded bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-800">
                            No
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TabsContent>

          {/* TAB 3: BIDDERS EVALUATION */}
          <TabsContent value="bidders" className="p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                    Participating Bidders Registry ({bidders.length})
                  </h3>
                  <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  Select a bidder to review extracted document evidence, verification checks, and record your qualification decision.
                </p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <label className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-600 dark:text-slate-400">
                  Sort by:
                  <select
                    value={sortDir}
                    onChange={(e) => setSortDir(e.target.value as 'asc' | 'desc')}
                    className="h-7 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-1.5 text-[11px] font-medium text-slate-800 dark:text-slate-200 shadow-2xs"
                    aria-label="Sort bidders by compliance score"
                  >
                    <option value="asc">Compliance Score — Low to High</option>
                    <option value="desc">Compliance Score — High to Low</option>
                  </select>
                </label>
                {isOfficer && !manageMode && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setManageMode(true)}
                    className="border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/70 text-xs font-medium h-7"
                  >
                    Manage Bidders
                  </Button>
                )}
                {isOfficer && manageMode && (
                  <>
                    <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-400">
                      {selectedBidIds.length} selected
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setBulkDeleteOpen(true)}
                      disabled={selectedBidIds.length === 0}
                      className="border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/60 text-xs font-medium h-7 disabled:opacity-40"
                    >
                      <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                      Delete Selected
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => { setManageMode(false); setSelectedBidIds([]); }}
                      className="border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800/70 text-xs font-medium h-7"
                    >
                      Cancel
                    </Button>
                  </>
                )}
              </div>
            </div>

            {bidders.length === 0 ? (
              <EmptyState
                title="No bids submitted yet"
                description="Bid submissions from prospective vendors will appear here once submitted."
              />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider dark:bg-slate-800/80">
                      {isOfficer && manageMode && (
                        <TableHead className="py-3 px-3 w-10">
                          <input
                            type="checkbox"
                            checked={bidders.length > 0 && selectedBidIds.length === bidders.length}
                            onChange={toggleSelectAllBids}
                            className="h-3.5 w-3.5 rounded border-slate-300 dark:border-slate-700 accent-blue-800"
                            title="Select all bidders"
                            aria-label="Select all bidders"
                          />
                        </TableHead>
                      )}
                      <TableHead className="py-3 px-3">Bidder Identity</TableHead>
                      <TableHead className="py-3 px-3">Statutory IDs</TableHead>
                      <TableHead className="py-3 px-3 text-center">Compliance Score</TableHead>
                      <TableHead className="py-3 px-3 text-center">Risk Level</TableHead>
                      <TableHead className="py-3 px-3 text-center">Recommendation</TableHead>
                      <TableHead className="py-3 px-3 text-center">Officer Decision</TableHead>
                      <TableHead className="py-3 px-3 text-right">Action</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {sortedBidders.map((b: TenderBidderRow) => (
                      <TableRow key={b.bid_id} className="hover:bg-blue-50/40 dark:hover:bg-blue-950/40 transition-colors">
                        {isOfficer && manageMode && (
                          <TableCell className="py-3 px-3">
                            <input
                              type="checkbox"
                              checked={selectedBidIds.includes(b.bid_id)}
                              onChange={() => toggleSelectBid(b.bid_id)}
                              className="h-3.5 w-3.5 rounded border-slate-300 dark:border-slate-700 accent-blue-800"
                              aria-label={`Select ${b.legal_name}`}
                            />
                          </TableCell>
                        )}
                        <TableCell className="py-3 px-3">
                          <div className="flex items-center gap-2">
                            <BidderLogo bidId={b.bid_id} legalName={b.legal_name} size="sm" />
                            <div className="min-w-0">
                              <p className="font-semibold text-slate-900 dark:text-slate-100 text-xs">{b.legal_name}</p>
                              {b.trade_name && (
                                <p className="text-[10.5px] text-slate-500 dark:text-slate-400 font-medium">{b.trade_name}</p>
                              )}
                              <p className="text-[10px] text-slate-400 dark:text-slate-500 font-mono mt-0.5">Bid ID #{b.bid_id}</p>
                            </div>
                          </div>
                        </TableCell>

                        <TableCell className="py-3 px-3 font-mono text-[11px] text-slate-600 dark:text-slate-400">
                          <div>PAN: {b.pan ?? '—'}</div>
                          <div>GSTIN: {b.gstin ?? '—'}</div>
                        </TableCell>

                        {/* Compliance Score */}
                        <TableCell className="py-3 px-3 text-center">
                          {b.compliance_score != null ? (
                            <div className="inline-flex flex-col items-center">
                              <span
                                className={`font-mono text-xs font-bold ${
                                  b.compliance_score >= 80
                                    ? 'text-emerald-700 dark:text-emerald-400'
                                    : b.compliance_score >= 60
                                    ? 'text-amber-700 dark:text-amber-400'
                                    : 'text-rose-700 dark:text-rose-400'
                                }`}
                              >
                                {b.compliance_score.toFixed(1)}%
                              </span>
                              <div className="w-16 bg-slate-200 dark:bg-slate-800 h-1.5 rounded-full overflow-hidden mt-1">
                                <div
                                  className={`h-full ${
                                    b.compliance_score >= 80
                                      ? 'bg-emerald-600'
                                      : b.compliance_score >= 60
                                      ? 'bg-amber-500'
                                      : 'bg-rose-600'
                                  }`}
                                  style={{ width: `${Math.min(100, b.compliance_score)}%` }}
                                />
                              </div>
                            </div>
                          ) : (
                            <span className="text-[11px] text-slate-400 dark:text-slate-500">Not Evaluated</span>
                          )}
                        </TableCell>

                        {/* Risk Level */}
                        <TableCell className="py-3 px-3 text-center">
                          <RiskBadge level={b.risk_level} />
                        </TableCell>

                        {/* Advisory Recommendation — rules-derived, derived from stored
                            compliance results + risk signals (see recommendation service).
                            Advisory only; the Procurement Officer decides. */}
                        <TableCell className="py-3 px-3 text-center">
                          <div className="inline-flex flex-col items-center">
                            {b.recommendation ? (
                              <RecommendationBadge rec={b.recommendation} />
                            ) : (
                              <span className="text-[11px] text-slate-400 dark:text-slate-500 font-mono">—</span>
                            )}
                            <span className="text-[9px] text-slate-400 dark:text-slate-500 mt-0.5">Rules-derived advisory</span>
                          </div>
                        </TableCell>

                        {/* Officer Decision */}
                        <TableCell className="py-3 px-3 text-center">
                          <DecisionBadge decision={b.officer_decision} />
                        </TableCell>

                        {/* Action */}
                        <TableCell className="py-3 px-3 text-right">
                          <div className="inline-flex items-center gap-1.5">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => navigate(`/app/bids/${b.bid_id}`)}
                              className="border-slate-300 dark:border-slate-700 text-blue-900 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-950/60 text-xs font-medium h-7 px-2.5 shadow-2xs"
                            >
                              View Bid
                              <ChevronRight className="ml-1 h-3 w-3" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>

          {/* TAB 4: COMPLIANCE MATRIX */}
          <TabsContent value="matrix" className="p-6">
            {comparisonQuery.isLoading ? (
              <LoadingBlock rows={6} />
            ) : comparisonQuery.isError || !comparisonQuery.data ? (
              <EmptyState
                title="Matrix unavailable"
                description="Unable to generate the comparative compliance matrix for this tender."
                action={
                  <Button onClick={() => comparisonQuery.refetch()} size="sm">
                    Retry
                  </Button>
                }
              />
            ) : (
              <ComparisonMatrix comparison={comparisonQuery.data} />
            )}
          </TabsContent>

          {/* TAB 5: AUDIT TRAIL */}
          <TabsContent value="audit" className="p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-800 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                    Tender Action History &amp; Hash-Chain
                  </h3>
                  <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  Every document processing event, rule evaluation, risk score, and officer decision is cryptographically anchored.
                </p>
              </div>
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-800 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 px-2.5 py-0.5 rounded border border-emerald-200 dark:border-emerald-800">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                SHA-256 Hash Chain Active
              </span>
            </div>

            {auditQuery.isLoading ? (
              <LoadingBlock rows={4} />
            ) : (auditQuery.data ?? []).length === 0 ? (
              <EmptyState
                title="No audit entries"
                description="Action logs on this tender will be registered here as actions occur."
              />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider dark:bg-slate-800/80">
                      <TableHead className="py-2.5 px-3">Timestamp</TableHead>
                      <TableHead className="py-2.5 px-3">Actor</TableHead>
                      <TableHead className="py-2.5 px-3">Action</TableHead>
                      <TableHead className="py-2.5 px-3">Bidder / Target</TableHead>
                      <TableHead className="py-2.5 px-3">Outcome / Signature</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {(auditQuery.data ?? []).map((e: AuditLog) => (
                      <TableRow key={e.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/70 text-xs">
                        <TableCell className="py-2.5 px-3 font-mono text-[11px] text-slate-500 dark:text-slate-400 whitespace-nowrap">
                          {formatDateTime(e.timestamp)}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 font-medium text-slate-900 dark:text-slate-100">
                          {e.user_name ?? 'System Engine'}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 font-semibold text-slate-800 dark:text-slate-200">
                          <span className="rounded bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10.5px] border border-slate-200 dark:border-slate-800">
                            {labelize(e.action)}
                          </span>
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-slate-700 dark:text-slate-200 max-w-[200px] truncate">
                          {e.target_label ?? '—'}
                        </TableCell>
                        <TableCell className="py-2.5 px-3">
                          {auditResult(e)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Register Bidder Dialog */}
      <Dialog open={registerModalOpen} onOpenChange={setRegisterModalOpen}>
        <DialogContent className="max-w-md bg-white dark:bg-slate-900">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 dark:text-slate-100 font-serif">
              Register Participating Bidder
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600 dark:text-slate-400">
              Add a new participating enterprise bidder to Tender #{detail?.tender.tender_number}.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleRegisterBidder}>
            <DialogBody className="space-y-3.5 pt-2">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                  Legal Enterprise / Company Name *
                </label>
                <Input
                  value={regName}
                  onChange={(e) => setRegName(e.target.value)}
                  placeholder="e.g. Acme Industrial Valves Ltd"
                  className="text-xs"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                    PAN Number
                  </label>
                  <Input
                    value={regPan}
                    onChange={(e) => setRegPan(e.target.value)}
                    placeholder="e.g. AAACA1234A"
                    maxLength={10}
                    className="text-xs font-mono uppercase"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                    GSTIN
                  </label>
                  <Input
                    value={regGstin}
                    onChange={(e) => setRegGstin(e.target.value)}
                    placeholder="e.g. 33AAACA1234A1Z5"
                    maxLength={15}
                    className="text-xs font-mono uppercase"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                  MSME Udyam Registration
                </label>
                <Input
                  value={regUdyam}
                  onChange={(e) => setRegUdyam(e.target.value)}
                  placeholder="e.g. UDYAM-TN-02-0012345"
                  className="text-xs font-mono uppercase"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                    Contact Representative
                  </label>
                  <Input
                    value={regContact}
                    onChange={(e) => setRegContact(e.target.value)}
                    placeholder="Contact person"
                    className="text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-200 mb-1">
                    Official Email
                  </label>
                  <Input
                    type="email"
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    placeholder="tenders@vendor.com"
                    className="text-xs"
                  />
                </div>
              </div>
            </DialogBody>

            <DialogFooter className="mt-4">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setRegisterModalOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                loading={registering}
                className="bg-blue-800 hover:bg-blue-900 text-white font-medium"
              >
                Register &amp; Create Bid
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Tender confirmation (Procurement Officer only) */}
      <Dialog open={deleteTenderOpen} onOpenChange={setDeleteTenderOpen}>
        <DialogContent className="max-w-md bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 dark:text-slate-100 font-serif">
              Delete Tender #{tender.tender_number}?
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600 dark:text-slate-400">
              This permanently removes the tender, its requirements, all {bidders.length} participating
              bidder{bidders.length === 1 ? '' : 's'}, and every derived record (documents, verification
              checks, compliance results, risk assessments). The audit trail is preserved. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800 pt-3">
            <Button variant="outline" size="sm" onClick={() => setDeleteTenderOpen(false)} className="border-slate-300 dark:border-slate-700">
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={confirmDeleteTender}
              loading={deletingTender}
              className="bg-rose-700 hover:bg-rose-800 text-white font-medium text-xs"
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Delete Tender
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk Delete Bidders confirmation (Procurement Officer only) */}
      <Dialog open={bulkDeleteOpen} onOpenChange={(open) => { if (!open) setBulkDeleteOpen(false); }}>
        <DialogContent className="max-w-md bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 dark:text-slate-100 font-serif">
              Remove {selectedBidIds.length} selected bidder{selectedBidIds.length === 1 ? '' : 's'}?
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600 dark:text-slate-400">
              This permanently removes the selected bids and their documents, extracted fields,
              verification checks, compliance results, and risk assessments. The audit trail is
              preserved. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <ul className="max-h-40 overflow-y-auto space-y-1 text-xs text-slate-700 dark:text-slate-200">
              {selectedBidIds.map((bidId) => {
                const b = bidders.find((x: TenderBidderRow) => x.bid_id === bidId);
                return (
                  <li key={bidId} className="flex items-center gap-2 rounded border border-slate-100 dark:border-slate-800 bg-slate-50 px-2 py-1.5 dark:bg-slate-800/70">
                    <Trash2 className="h-3 w-3 text-rose-500 dark:text-rose-400 shrink-0" />
                    <span className="font-medium truncate">{b?.legal_name ?? `Bid #${bidId}`}</span>
                    <span className="ml-auto font-mono text-[10px] text-slate-400 dark:text-slate-500 shrink-0">#{bidId}</span>
                  </li>
                );
              })}
            </ul>
          </DialogBody>
          <DialogFooter className="flex items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800 pt-3">
            <Button variant="outline" size="sm" onClick={() => setBulkDeleteOpen(false)} className="border-slate-300 dark:border-slate-700">
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={confirmBulkDeleteBids}
              loading={bulkDeleting}
              className="bg-rose-700 hover:bg-rose-800 text-white font-medium text-xs"
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Delete Selected ({selectedBidIds.length})
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Intelligent evaluation status modal */}
      <Dialog open={evalModalOpen} onOpenChange={(open) => { if (!open && !evaluating) setEvalModalOpen(false); }}>
        <DialogContent className="max-w-md bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 dark:text-slate-100 font-serif">
              Bidder Evaluation Status
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600 dark:text-slate-400">
              {pendingBids.length === 0 ? (
                <>All {bidders.length} bidder{bidders.length === 1 ? '' : 's'} have compliance scores from the deterministic rules engine. Re-running evaluation replaces stored results (audit history is preserved).</>
              ) : (
                <>{evaluatedBids.length} of {bidders.length} bidders evaluated. {pendingBids.length} still require evaluation.</>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            {evaluating && evalProgress ? (
              <div className="space-y-2 py-2">
                <p className="text-xs font-medium text-slate-700 dark:text-slate-200">
                  Evaluating {evalProgress.done + 1} of {evalProgress.total}: {evalProgress.name}
                </p>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                  <div
                    className="h-full bg-blue-700 transition-all"
                    style={{ width: `${(evalProgress.done / evalProgress.total) * 100}%` }}
                  />
                </div>
              </div>
            ) : (
              <ul className="max-h-56 overflow-y-auto space-y-1">
                {bidders.map((b: TenderBidderRow) => {
                  const evaluated = b.compliance_score != null;
                  return (
                    <li key={b.bid_id} className="flex items-center gap-2 rounded border border-slate-100 dark:border-slate-800 bg-slate-50 px-2 py-1.5 text-xs dark:bg-slate-800/70">
                      {evaluated ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                      ) : (
                        <Clock className="h-3.5 w-3.5 text-amber-500 dark:text-amber-400 shrink-0" />
                      )}
                      <span className="font-medium text-slate-800 dark:text-slate-200 truncate">{b.legal_name}</span>
                      <span className="ml-auto shrink-0">
                        {evaluated ? (
                          <span className="font-mono font-bold text-emerald-700 dark:text-emerald-400">{b.compliance_score!.toFixed(1)}%</span>
                        ) : (
                          <span className="font-medium text-amber-600 dark:text-amber-400">Not Evaluated</span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </DialogBody>
          <DialogFooter className="flex items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800 pt-3">
            <Button
              variant="outline"
              size="sm"
              disabled={evaluating}
              onClick={() => { setEvalModalOpen(false); setActiveTab('bidders'); }}
              className="border-slate-300 dark:border-slate-700"
            >
              View Results
            </Button>
            {canVerify && pendingBids.length > 0 && (
              <Button
                size="sm"
                disabled={evaluating}
                loading={evaluating}
                onClick={() => runEvaluation(pendingBids)}
                className="bg-blue-800 hover:bg-blue-900 text-white font-medium text-xs"
              >
                <Users className="mr-1.5 h-3.5 w-3.5" />
                Evaluate {pendingBids.length} Remaining
              </Button>
            )}
            {canVerify && pendingBids.length === 0 && bidders.length > 0 && (
              <Button
                size="sm"
                variant="outline"
                disabled={evaluating}
                loading={evaluating}
                onClick={() => runEvaluation(bidders)}
                className="border-amber-300 dark:border-amber-800 text-amber-800 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950/60 font-medium text-xs"
              >
                Re-evaluate All
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
