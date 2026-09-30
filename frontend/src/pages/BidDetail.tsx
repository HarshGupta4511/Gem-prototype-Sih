import * as React from 'react';
import { useQuery, useQueries, useQueryClient } from '@tanstack/react-query';
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom';
import {
  AlertOctagon,
  AlertTriangle,
  ArrowLeft,
  Building2,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  ExternalLink,
  Eye,
  FileCheck,
  FileSearch,
  FileText,
  Filter,
  Gavel,
  History,
  Info,
  Layers,
  MessageSquare,
  MoreHorizontal,
  Play,
  Plus,
  RefreshCw,
  Scale,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Upload,
  UserCheck,
  X,
  XCircle,
} from 'lucide-react';
import type {
  BidDetail as BidDetailData,
  ComplianceResult,
  Document,
  OfficerDecision,
  RecommendationResult,
  DocumentType,
  PolicyCitation,
} from '../types';
import {
  bidsApi,
  documentsApi,
  verificationApi,
  complianceApi,
  recommendationApi,
  officerApi,
  getErrorMessage,
  API_BASE_URL,
} from '../lib/api';
import {
  formatDate,
  formatDateTime,
  labelize,
  timeAgo,
} from '../lib/utils';
import {
  displayActualValue,
  displaySource,
  displayThreshold,
} from '../lib/compliance-display';
import { openDocumentViewer } from '../lib/viewer-context';
import { useAuth } from '../context/AuthContext';
import { DEMO_BIDDER_PROFILES } from '../components/tenders/DemoBiddersModal';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogBody,
  DialogFooter,
} from '../components/ui/dialog';
import { Input, Textarea, Select } from '../components/ui/input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { useToast } from '../components/ui/toaster';
import {
  StatusBadge,
  RiskBadge,
  VerificationBadge,
  BidStatusBadge,
  RecommendationBadge,
  DecisionBadge,
  DocStatusBadge,
  DocTypeBadge,
  MethodBadge,
} from '../components/common/badges';
import { EvidenceDrawer } from '../components/common/EvidenceDrawer';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
import { ReportTab } from '../components/reports/ReportTab';
import { LoadingBlock } from '../components/common/ui-helpers';

export default function BidDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const bidId = Number(id);
  const qc = useQueryClient();
  const { toast } = useToast();
  const { canDecide, canVerify, isAuditor } = useAuth();

  const { data, isLoading, error, refetch } = useQuery<BidDetailData>({
    queryKey: ['bid', bidId],
    queryFn: () => bidsApi.get(bidId),
    enabled: Number.isFinite(bidId) && bidId > 0,
  });

  const invalidate = React.useCallback(
    () => qc.invalidateQueries({ queryKey: ['bid', bidId] }),
    [qc, bidId]
  );

  // States
  const [busy, setBusy] = React.useState<string | null>(null);
  const [selectedResult, setSelectedResult] = React.useState<ComplianceResult | null>(null);
  const [activeTab, setActiveTab] = React.useState(() => {
    // Restore the tab the viewer (or browser back) returns to:
    // explicit navigation state first, then the last tab used for this bid.
    const fromState = (location.state as { tab?: string } | null)?.tab;
    if (fromState) return fromState;
    try {
      return sessionStorage.getItem(`bid-detail-tab:${bidId}`) ?? 'compliance';
    } catch {
      return 'compliance';
    }
  });
  // Remember the tab per bid so browser-back from the document viewer
  // lands on the tab the document was opened from.
  React.useEffect(() => {
    try {
      sessionStorage.setItem(`bid-detail-tab:${bidId}`, activeTab);
    } catch {
      /* storage unavailable — tab just won't persist */
    }
  }, [activeTab, bidId]);

  // Decision Dialog (First decision)
  const [decisionDialog, setDecisionDialog] = React.useState<OfficerDecision | null>(null);
  const [decisionReason, setDecisionReason] = React.useState('');
  const [decisionError, setDecisionError] = React.useState<string | null>(null);

  // Change Decision Dialog (If already decided)
  const [changeOpen, setChangeOpen] = React.useState(false);
  const [newDecision, setNewDecision] = React.useState<'APPROVE' | 'REJECT' | 'ESCALATE'>('REJECT');
  const [changeReason, setChangeReason] = React.useState('');
  const [changeError, setChangeError] = React.useState<string | null>(null);

  // Override Dialog
  const [overrideTarget, setOverrideTarget] = React.useState<ComplianceResult | null>(null);
  const [overrideComment, setOverrideComment] = React.useState('');
  const [overrideError, setOverrideError] = React.useState<string | null>(null);
  // Row action menu (which compliance row's "More" menu is open)
  const [openActionMenu, setOpenActionMenu] = React.useState<number | null>(null);

  // Clarification Dialog
  const [clarifyOpen, setClarifyOpen] = React.useState(false);
  const [clarifySubject, setClarifySubject] = React.useState('');
  const [clarifyBody, setClarifyBody] = React.useState('');

  // Upload state
  const [uploadFile, setUploadFile] = React.useState<File | null>(null);
  // Demo evidence recovery (bid registered without its dossier, e.g. the
  // publish-time seed failed): attach a profile's fictional dossier through
  // the same real backend pipeline.
  const [demoEvidenceOpen, setDemoEvidenceOpen] = React.useState(false);
  const [demoProfileKey, setDemoProfileKey] = React.useState<string>('apex');

  // Query for document fields
  const processedDocs = React.useMemo(
    () => (data ? data.documents.filter((d) => d.processing_status === 'PROCESSED') : []),
    [data]
  );

  const fieldQueries = useQueries({
    queries: processedDocs.map((d) => ({
      queryKey: ['document', d.id],
      queryFn: () => documentsApi.get(d.id),
      staleTime: 60_000,
    })),
  });

  // Extract all fields into flat list
  const allExtractedFields = React.useMemo(() => {
    const list: Array<{
      id: number;
      docId: number;
      docName: string;
      docType: DocumentType;
      fieldName: string;
      fieldValue: string;
      normalizedValue: string;
      confidence: number;
      method: 'REGEX' | 'OCR' | 'LLM' | 'MANUAL';
      page: number | null;
    }> = [];

    fieldQueries.forEach((q, idx) => {
      const doc = processedDocs[idx];
      if (q.data && doc && q.data.extracted_fields) {
        q.data.extracted_fields.forEach((f: any) => {
          list.push({
            id: f.id,
            docId: doc.id,
            docName: doc.filename,
            docType: doc.document_type,
            fieldName: f.field_name,
            fieldValue: f.field_value,
            normalizedValue: f.normalized_value,
            confidence: f.confidence,
            method: f.extraction_method,
            page: f.page_number,
          });
        });
      }
    });

    return list;
  }, [fieldQueries, processedDocs]);

  // Operations
  async function runBusy(name: string, fn: () => Promise<void>) {
    setBusy(name);
    try {
      await fn();
    } catch (err: unknown) {
      const msg = getErrorMessage(err);
      toast({
        title: 'Operation Failed',
        description:
          msg.includes('Network Error')
            ? `Network Error — the backend did not respond at ${API_BASE_URL}. Check that the backend container is running and rebuilt (docker compose up --build), with VPN off.`
            : msg,
      });
    } finally {
      setBusy(null);
    }
  }

  // Verification Run
  const handleRunVerification = () =>
    runBusy('verification', async () => {
      await verificationApi.run(bidId);
      await invalidate();
      toast({ title: 'Verification Completed', description: 'Statutory government adapters executed.' });
    });

  // Compliance Evaluate
  const handleEvaluateCompliance = () =>
    runBusy('compliance', async () => {
      await complianceApi.evaluate(bidId);
      await invalidate();
      toast({ title: 'Compliance Evaluated', description: 'Deterministic scoring & rule matrix updated.' });
    });

  // Recommendation Run
  const handleGenerateRecommendation = () =>
    runBusy('recommendation', async () => {
      await recommendationApi.generate(bidId);
      await invalidate();
      toast({ title: 'AI Advisory Generated', description: 'Advisory recommendation updated from evaluation findings.' });
    });

  // Process Document
  const handleProcessDoc = (docId: number) =>
    runBusy(`doc-${docId}`, async () => {
      await documentsApi.process(docId);
      await invalidate();
      toast({ title: 'Document Processed', description: 'Entity extraction completed.' });
    });

  // Process All Documents
  const handleProcessAll = () =>
    runBusy('process-all', async () => {
      if (!data) return;
      for (const d of data.documents) {
        if (d.processing_status !== 'PROCESSED') {
          await documentsApi.process(d.id);
        }
      }
      await invalidate();
      toast({ title: 'All Documents Processed', description: 'Document extraction completed.' });
    });

  // Demo evidence recovery: attach a profile's fictional dossier when the
  // bid has no documents (e.g. publish-time seeding failed). Uses the real
  // backend pipeline; scores are still derived by the officer's Evaluate.
  const handleAttachDemoEvidence = () =>
    runBusy('demo-evidence', async () => {
      const res = await bidsApi.seedDemoEvidence(bidId, demoProfileKey);
      setDemoEvidenceOpen(false);
      await invalidate();
      toast({
        title: res.seeded ? 'Demo Evidence Attached' : 'Demo Evidence Already Present',
        description: res.seeded
          ? `Dossier document stored and extracted (${res.fields_extracted ?? 0} fields). Run Verification and Evaluate next.`
          : 'This bidder already has its demo dossier attached.',
      });
    });

  // Upload handler
  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) return;
    runBusy('upload', async () => {
      await documentsApi.upload(bidId, uploadFile);
      setUploadFile(null);
      await invalidate();
      toast({ title: 'Document Uploaded', description: `${uploadFile.name} queued for processing.` });
    });
  };

  // Override handlers
  function openOverride(cr: ComplianceResult) {
    setOverrideTarget(cr);
    setOverrideComment('');
    setOverrideError(null);
  }

  async function confirmOverride() {
    if (!overrideTarget) return;
    if (overrideComment.trim().length === 0) {
      setOverrideError('A written officer justification is required to override a rule finding.');
      return;
    }
    runBusy('override', async () => {
      await officerApi.override({
        target_type: 'COMPLIANCE_RESULT',
        target_id: overrideTarget.id,
        officer_comment: overrideComment.trim(),
      });
      setOverrideTarget(null);
      await invalidate();
      toast({ title: 'Officer Override Recorded', description: 'Original finding preserved; override added to the audit trail.' });
    });
  }

  // Clarification handlers
  async function handleCreateClarification(dispatch: boolean) {
    if (!clarifySubject.trim() || !clarifyBody.trim()) return;
    runBusy(dispatch ? 'clarify-dispatch' : 'clarify-create', async () => {
      const created = await officerApi.clarification({
        bid_id: bidId,
        subject: clarifySubject.trim(),
        body: clarifyBody.trim(),
      });
      if (dispatch) {
        await officerApi.sendClarification(created.id);
      }
      setClarifyOpen(false);
      setClarifySubject('');
      setClarifyBody('');
      await invalidate();
      toast({
        title: dispatch ? 'Clarification Dispatched' : 'Clarification Drafted',
        description: dispatch ? 'Vendor notified via portal.' : 'Draft query saved to bidder file.',
      });
    });
  }

  // First Decision Confirmation
  async function confirmFirstDecision() {
    if (!decisionDialog) return;
    const reqReason = decisionDialog !== 'APPROVE';
    if (reqReason && decisionReason.trim().length === 0) {
      setDecisionError(`Reason is required when recording ${labelize(decisionDialog)}.`);
      return;
    }
    runBusy('first-decision', async () => {
      await officerApi.decision({
        bid_id: bidId,
        decision: decisionDialog,
        reason: decisionReason.trim() || 'Approved by Procurement Officer on basis of complete statutory compliance.',
      });
      setDecisionDialog(null);
      setDecisionReason('');
      await invalidate();
      await qc.invalidateQueries({ queryKey: ['tender'] });
      toast({ title: 'Decision Recorded', description: `Bid marked as ${labelize(decisionDialog)}.` });
    });
  }

  // Change Decision Confirmation
  async function confirmChangeDecision() {
    if (!changeReason.trim()) {
      setChangeError('A justification is required to modify a previously recorded decision.');
      return;
    }
    runBusy('change-decision', async () => {
      await officerApi.decision({
        bid_id: bidId,
        decision: newDecision,
        reason: changeReason.trim(),
      });
      setChangeOpen(false);
      setChangeReason('');
      await invalidate();
      await qc.invalidateQueries({ queryKey: ['tender'] });
      toast({ title: 'Decision Updated', description: `Bid updated to ${labelize(newDecision)}.` });
    });
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingBlock rows={8} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-red-800">
        <AlertOctagon className="mx-auto h-8 w-8 text-red-600" />
        <p className="mt-2 text-base font-semibold">Could not load bidder evaluation dossier</p>
        <p className="text-xs text-red-600">The requested bid submission was not found.</p>
        <div className="mt-4">
          <Button onClick={() => navigate('/app/tenders')} size="sm">
            Go to Tenders
          </Button>
        </div>
      </div>
    );
  }

  const { bid, bidder, tender, documents, verification_checks, compliance_results, risk, recommendation, audit } = data;

  const passedCount = compliance_results.filter((c) => c.status === 'PASS').length;
  const totalRules = compliance_results.length;
  const pendingRules = compliance_results.filter((c) => c.status === 'REVIEW_REQUIRED' || c.status === 'MISSING').length;
  const isDecided = bid.officer_decision !== null;

  return (
    <div className="space-y-5">
      {/* 1. Header Navigation & Bidder Identification */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex items-center gap-2 text-xs text-slate-500 mb-3">
          <Link
            to={`/app/tenders/${bid.tender_id}`}
            className="inline-flex items-center gap-1 font-medium text-blue-800 hover:underline hover:text-blue-900"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Tender #{tender.tender_number}</span>
          </Link>
          <span>/</span>
          <span className="font-mono text-slate-700 font-semibold">{bidder.legal_name}</span>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-100 pb-4">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="font-mono text-xs font-bold text-blue-950 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                Bid #{bid.id}
              </span>
              <BidStatusBadge status={bid.status} />
              <span className="text-xs text-slate-500 font-medium">
                Submitted {formatDateTime(bid.submitted_at)}
              </span>
            </div>
            <h1 className="mt-1.5 text-2xl font-bold tracking-tight text-slate-900 font-serif">
              {bidder.legal_name}
            </h1>
            {bidder.trade_name && (
              <p className="text-xs font-medium text-slate-500">Trade: {bidder.trade_name}</p>
            )}
            <p className="mt-1 text-xs text-slate-600 flex items-center gap-2 font-mono">
              <span>PAN: {bidder.pan || '—'}</span>
              <span className="text-slate-300">•</span>
              <span>GSTIN: {bidder.gstin || '—'}</span>
              <span className="text-slate-300">•</span>
              <span>CIN: {bidder.cin || '—'}</span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Tender Scope:
            </span>
            <span className="font-mono text-xs font-bold text-blue-900 bg-slate-100 px-2.5 py-1 rounded border border-slate-200">
              {tender.tender_number}
            </span>
          </div>
        </div>

        {/* 2. EVALUATION SUMMARY BAR (COMPACT METRICS) */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 pt-1">
          {/* Compliance Score */}
          <div className="rounded border border-slate-200 bg-slate-50/70 p-3">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-[10.5px] uppercase font-semibold">Compliance Score</span>
              <Scale className="h-3.5 w-3.5 text-slate-400" />
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-mono text-xl font-bold text-slate-900">
                {bid.compliance_score != null ? `${bid.compliance_score.toFixed(1)}%` : '—'}
              </span>
              <span className="text-[10px] text-slate-500">weighted</span>
            </div>
            <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden mt-2">
              <div
                className={`h-full ${
                  (bid.compliance_score ?? 0) >= 80
                    ? 'bg-emerald-600'
                    : (bid.compliance_score ?? 0) >= 60
                    ? 'bg-amber-500'
                    : 'bg-rose-600'
                }`}
                style={{ width: `${Math.min(100, bid.compliance_score ?? 0)}%` }}
              />
            </div>
          </div>

          {/* Risk Level */}
          <div className="rounded border border-slate-200 bg-slate-50/70 p-3">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-[10.5px] uppercase font-semibold">Risk Classification</span>
              <ShieldAlert className="h-3.5 w-3.5 text-slate-400" />
            </div>
            <div className="mt-1.5">
              <RiskBadge level={bid.risk_level} />
            </div>
            <p className="mt-1.5 text-[10px] text-slate-500">
              {risk?.signals.length ?? 0} risk factor signals detected
            </p>
          </div>

          {/* Passed Requirements */}
          <div className="rounded border border-slate-200 bg-slate-50/70 p-3">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-[10.5px] uppercase font-semibold">Passed Rules</span>
              <FileCheck className="h-3.5 w-3.5 text-slate-400" />
            </div>
            {totalRules === 0 ? (
              <div className="mt-1">
                <span className="font-mono text-xl font-bold text-slate-400">—</span>
                <p className="mt-1 text-[10px] text-slate-500">Not evaluated yet</p>
              </div>
            ) : (
              <>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="font-mono text-xl font-bold text-emerald-800">
                    {passedCount} / {totalRules}
                  </span>
                  <span className="text-[10px] text-emerald-700">rules met</span>
                </div>
                <p className="mt-1 text-[10px] text-slate-500">
                  {totalRules - passedCount} non-pass rules
                </p>
              </>
            )}
          </div>

          {/* Pending Reviews */}
          <div className="rounded border border-slate-200 bg-slate-50/70 p-3">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-[10.5px] uppercase font-semibold">Pending Reviews</span>
              <Clock className="h-3.5 w-3.5 text-slate-400" />
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span
                className={`font-mono text-xl font-bold ${
                  pendingRules > 0 ? 'text-amber-700' : 'text-slate-900'
                }`}
              >
                {pendingRules}
              </span>
              <span className="text-[10px] text-slate-500">rules</span>
            </div>
            <p className="mt-1 text-[10px] text-slate-500">Require officer check</p>
          </div>

          {/* Current Decision Status */}
          <div className="rounded border border-slate-200 bg-slate-50/70 p-3">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-[10.5px] uppercase font-semibold">Officer Decision</span>
              <Gavel className="h-3.5 w-3.5 text-slate-400" />
            </div>
            <div className="mt-1.5">
              {isDecided ? (
                <DecisionBadge decision={bid.officer_decision} />
              ) : (
                <span className="inline-block rounded bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-900 border border-amber-300">
                  Not Decided
                </span>
              )}
            </div>
            <p className="mt-1 text-[10px] text-slate-500 truncate">
              {isDecided ? `Recorded ${formatDate(bid.decided_at || '')}` : 'Sign-off pending'}
            </p>
          </div>
        </div>

        {/* 3. PRIMARY OFFICER ACTIONS BAR: Distinct, Authoritative */}
        <div className="mt-5 rounded-lg border-2 border-blue-900/40 bg-blue-950 p-4 text-white shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-blue-300 font-mono">
                  Primary Procurement Officer Action Bar
                </span>
                <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
              </div>
              <p className="mt-0.5 text-xs text-blue-100/80">
                Record your formal statutory verdict for this bid. All determinations require written justification and update the tamper-evident audit trail.
              </p>
            </div>

            {/* Buttons for Officer Decision */}
            {canDecide ? (
              <div className="flex flex-wrap items-center gap-2">
                {!isDecided ? (
                  <>
                    <Button
                      onClick={() => {
                        setDecisionDialog('APPROVE');
                        setDecisionReason('');
                        setDecisionError(null);
                      }}
                      className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs py-2 px-3.5 shadow-xs"
                    >
                      <Check className="mr-1.5 h-4 w-4" />
                      Approve (Qualify)
                    </Button>

                    <Button
                      onClick={() => {
                        setDecisionDialog('REJECT');
                        setDecisionReason('');
                        setDecisionError(null);
                      }}
                      className="bg-rose-600 hover:bg-rose-700 text-white font-semibold text-xs py-2 px-3.5 shadow-xs"
                    >
                      <X className="mr-1.5 h-4 w-4" />
                      Reject (Disqualify)
                    </Button>

                    <Button
                      onClick={() => {
                        setDecisionDialog('ESCALATE');
                        setDecisionReason('');
                        setDecisionError(null);
                      }}
                      className="bg-amber-600 hover:bg-amber-700 text-white font-semibold text-xs py-2 px-3.5 shadow-xs"
                    >
                      <AlertTriangle className="mr-1.5 h-4 w-4" />
                      Escalate to Committee
                    </Button>

                    <Button
                      onClick={() => {
                        setClarifyOpen(true);
                        setClarifySubject(`Clarification on Tender ${tender.tender_number} - ${bidder.legal_name}`);
                      }}
                      variant="outline"
                      className="bg-slate-800 text-blue-100 hover:bg-slate-700 hover:text-white border-blue-400/40 text-xs py-2 px-3"
                    >
                      <MessageSquare className="mr-1.5 h-4 w-4 text-blue-300" />
                      Request Clarification
                    </Button>
                  </>
                ) : (
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-semibold text-blue-200">
                      Verdict on Record: <DecisionBadge decision={bid.officer_decision} />
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setNewDecision(bid.officer_decision === 'APPROVE' ? 'REJECT' : 'APPROVE');
                        setChangeReason('');
                        setChangeError(null);
                        setChangeOpen(true);
                      }}
                      className="bg-slate-800 text-white hover:bg-slate-700 border-slate-600 text-xs"
                    >
                      Modify Decision
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-blue-200 font-medium bg-blue-900/60 px-3 py-1.5 rounded border border-blue-800">
                Viewing in Auditor / Read-Only Mode (Officer signing privileges required)
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 4. DOSSIER TABS & SECTIONS */}
      <div className="rounded-lg border border-slate-200 bg-white shadow-xs overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="border-b border-slate-200 bg-slate-50/80 px-4 pt-2">
            <TabsList className="bg-transparent space-x-1 p-0 h-auto flex flex-wrap">
              <TabsTrigger
                value="compliance"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                1. Compliance ({compliance_results.length})
              </TabsTrigger>
              <TabsTrigger
                value="verification"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                2. Statutory Verification ({verification_checks.length})
              </TabsTrigger>
              <TabsTrigger
                value="documents"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                3. Documents ({documents.length})
              </TabsTrigger>
              <TabsTrigger
                value="extracted"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                4. Extracted Information ({allExtractedFields.length})
              </TabsTrigger>
              <TabsTrigger
                value="risk"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                5. Risk Analysis
              </TabsTrigger>
              <TabsTrigger
                value="ai"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                6. AI Explanation
              </TabsTrigger>
              <TabsTrigger
                value="report"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                7. Verification Report
              </TabsTrigger>
              <TabsTrigger
                value="audit"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                8. Audit Trail
              </TabsTrigger>
            </TabsList>
          </div>

          {/* SECTION 1: COMPLIANCE EVALUATION */}
          <TabsContent value="compliance" className="p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Compliance Evaluation ({compliance_results.length} requirements)
                  </h3>
                  <SystemLayerTag layer="RULE_ENGINE" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Rule-based evaluation against the tender's requirements. The deterministic
                  rules engine is the authority for these results — not AI.
                </p>
              </div>

              {canVerify && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleEvaluateCompliance}
                  loading={busy === 'compliance'}
                  className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
                >
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  Re-evaluate Compliance
                </Button>
              )}
            </div>

            {compliance_results.length === 0 ? (
              <div className="rounded-md border border-dashed border-slate-300 p-8 text-center">
                <Scale className="mx-auto h-8 w-8 text-slate-400" />
                <p className="mt-2 text-sm font-semibold text-slate-700">No compliance evaluation on file</p>
                <p className="text-xs text-slate-500 mt-1">Run the deterministic evaluation engine to compute rule verdicts.</p>
                <Button onClick={handleEvaluateCompliance} size="sm" className="mt-3">
                  Evaluate Compliance Rules
                </Button>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                      <TableHead className="py-2.5 px-3">Requirement</TableHead>
                      <TableHead className="py-2.5 px-3">Criteria / Threshold</TableHead>
                      <TableHead className="py-2.5 px-3">Actual Finding</TableHead>
                      <TableHead className="py-2.5 px-3 text-center">Status</TableHead>
                      <TableHead className="py-2.5 px-3 text-right">Weight</TableHead>
                      <TableHead className="py-2.5 px-3 text-right">Evidence</TableHead>
                      <TableHead className="py-2.5 px-3 text-right">Action</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {compliance_results.map((c) => {
                      const isOverridden = c.overridden;
                      const reqName = c.requirement?.requirement_name ?? `Requirement #${c.requirement_id}`;
                      const isMandatory = c.requirement?.mandatory ?? false;
                      const firstEvidence = c.evidence?.[0];
                      const actualValue = displayActualValue(firstEvidence?.value, firstEvidence?.field ?? '');
                      return (
                        <TableRow key={c.id} className="hover:bg-slate-50/60 text-xs">
                          <TableCell className="py-2.5 px-3 font-semibold text-slate-900">
                            {reqName}
                            {isMandatory && (
                              <span className="ml-1.5 rounded bg-rose-50 px-1 py-0.2 text-[9px] font-bold text-rose-700 border border-rose-200">
                                MANDATORY
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-slate-700">
                            {displayThreshold(c.requirement?.threshold)}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-slate-900 font-medium">
                            {actualValue}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-center">
                            <StatusBadge status={c.status} />
                            {isOverridden && (
                              <span className="block text-[9px] font-bold text-blue-700 mt-0.5">
                                OVERRIDDEN
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-right font-mono font-semibold">
                            {c.weight}%
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-right">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setSelectedResult(c)}
                              className="text-xs text-blue-800 hover:text-blue-900 hover:bg-blue-50 h-7 px-2"
                            >
                              <FileSearch className="mr-1 h-3.5 w-3.5 text-blue-700" />
                              View Evidence
                            </Button>
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-right">
                            {canDecide && (
                              <div className="relative inline-block">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => setOpenActionMenu(openActionMenu === c.id ? null : c.id)}
                                  className="text-xs text-slate-500 hover:text-slate-900 h-7 px-2"
                                  title="More actions"
                                >
                                  <MoreHorizontal className="h-4 w-4" />
                                </Button>
                                {openActionMenu === c.id && (
                                  <>
                                    <div
                                      className="fixed inset-0 z-40"
                                      onClick={() => setOpenActionMenu(null)}
                                    />
                                    <div className="absolute right-0 z-50 mt-1 w-44 rounded-md border border-slate-200 bg-white py-1 shadow-lg">
                                      <button
                                        className="block w-full px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50"
                                        onClick={() => {
                                          setOpenActionMenu(null);
                                          openOverride(c);
                                        }}
                                      >
                                        Override Finding
                                      </button>
                                    </div>
                                  </>
                                )}
                              </div>
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>

          {/* SECTION 2: STATUTORY VERIFICATION (MOCK SOURCES) */}
          <TabsContent value="verification" className="p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Statutory Government Cross-Checks ({verification_checks.length})
                  </h3>
                  <SystemLayerTag layer="VERIFICATION" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Which statutory source was checked and what was the result. Detailed
                  reasoning for each requirement lives under Compliance → View Evidence.
                </p>
              </div>

              {canVerify && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleRunVerification}
                  loading={busy === 'verification'}
                  className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
                >
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  Run All Verification Checks
                </Button>
              )}
            </div>

            {/* Official Mock Notice Banner */}
            <div className="rounded-lg border border-blue-200 bg-blue-50/70 p-3.5 text-xs text-blue-950 flex items-start gap-2.5">
              <Info className="h-4 w-4 text-blue-700 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-blue-900">Simulated Statutory Data:</span>{' '}
                These checks interface with mock adapters simulating GSTN, PAN, MCA21, EPFO, ESIC, and the GeM Debarment list. No live government APIs are invoked in this environment.
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <Table>
                <TableHeader>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                    <TableHead className="py-2.5 px-3">Source</TableHead>
                    <TableHead className="py-2.5 px-3">Identifier</TableHead>
                    <TableHead className="py-2.5 px-3 text-center">Status</TableHead>
                    <TableHead className="py-2.5 px-3">Finding</TableHead>
                  </tr>
                </TableHeader>
                <TableBody>
                  {verification_checks.map((vc) => (
                    <TableRow key={vc.id} className="hover:bg-slate-50/60 text-xs">
                      <TableCell className="py-2.5 px-3 font-semibold text-slate-900">
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-mono border border-slate-200">
                          {displaySource(vc.source)}
                        </span>
                      </TableCell>
                      <TableCell className="py-2.5 px-3 font-mono text-slate-800">
                        {vc.identifier}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-center">
                        <VerificationBadge status={vc.verification_status} />
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-slate-600 max-w-md">
                        {vc.evidence_reference || '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TabsContent>

          {/* SECTION 3: DOCUMENTS */}
          <TabsContent value="documents" className="p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Bid Submission Documents ({documents.length})
                  </h3>
                  <SystemLayerTag layer="AI_ASSISTED" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Classified bidder uploads with extraction status and document viewer integration.
                </p>
              </div>

              <div className="flex items-center gap-2">
                {documents.length === 0 && canVerify && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setDemoEvidenceOpen(true)}
                    className="border-amber-300 text-amber-800 hover:bg-amber-50 text-xs"
                  >
                    <FileText className="mr-1.5 h-3.5 w-3.5" />
                    Attach Demo Evidence
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleProcessAll}
                  loading={busy === 'process-all'}
                  className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
                >
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  Process All Documents
                </Button>
              </div>
            </div>

            {/* Quick Upload Form */}
            <form onSubmit={handleUpload} className="rounded-lg border border-slate-200 bg-slate-50/60 p-4">
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="flex-1">
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Upload Additional Bidder Attachment (PDF, Images)
                  </label>
                  <input
                    type="file"
                    accept=".pdf,.png,.jpg,.jpeg"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    className="block w-full text-xs text-slate-500 file:mr-4 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-blue-800 file:text-white hover:file:bg-blue-900 cursor-pointer"
                  />
                </div>
                <div className="sm:self-end">
                  <Button
                    type="submit"
                    size="sm"
                    disabled={!uploadFile || busy === 'upload'}
                    loading={busy === 'upload'}
                    className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium"
                  >
                    <Upload className="mr-1.5 h-3.5 w-3.5" />
                    Upload &amp; Classify
                  </Button>
                </div>
              </div>
            </form>

            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <Table>
                <TableHeader>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                    <TableHead className="py-2.5 px-3">Filename</TableHead>
                    <TableHead className="py-2.5 px-3">Classification</TableHead>
                    <TableHead className="py-2.5 px-3 text-center">Status</TableHead>
                    <TableHead className="py-2.5 px-3 text-right">Pages</TableHead>
                    <TableHead className="py-2.5 px-3 text-right">Uploaded</TableHead>
                    <TableHead className="py-2.5 px-3 text-right">Actions</TableHead>
                  </tr>
                </TableHeader>
                <TableBody>
                  {documents.map((doc) => (
                    <TableRow key={doc.id} className="hover:bg-slate-50/60 text-xs">
                      <TableCell className="py-2.5 px-3 font-semibold text-slate-900">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-blue-700 shrink-0" />
                          <span className="truncate max-w-xs">{doc.filename}</span>
                        </div>
                      </TableCell>
                      <TableCell className="py-2.5 px-3">
                        <DocTypeBadge docType={doc.document_type} />
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-center">
                        <DocStatusBadge status={doc.processing_status} />
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-right font-mono text-slate-600">
                        {doc.page_count ?? 1}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-right text-slate-500 font-mono text-[11px]">
                        {formatDate(doc.upload_time)}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {doc.processing_status !== 'PROCESSED' && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleProcessDoc(doc.id)}
                              loading={busy === `doc-${doc.id}`}
                              className="text-xs h-7 px-2"
                            >
                              Process
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              openDocumentViewer(navigate, doc.id, {
                                path: `/app/bids/${bidId}`,
                                label: 'Back to Bid Documents',
                                state: { tab: 'documents' },
                              })
                            }
                            className="text-xs text-blue-700 hover:text-blue-900 h-7 px-2"
                          >
                            <Eye className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TabsContent>

          {/* SECTION 4: EXTRACTED INFORMATION REGISTRY */}
          <TabsContent value="extracted" className="p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Extracted Field Intelligence ({allExtractedFields.length} entities)
                  </h3>
                  <SystemLayerTag layer="AI_ASSISTED" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Data points parsed from statutory filings via Regex, OCR, and AI Document Models.
                </p>
              </div>
            </div>

            {allExtractedFields.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-400">
                No extracted fields available. Process uploaded documents first.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                      <TableHead className="py-2.5 px-3">Field Name</TableHead>
                      <TableHead className="py-2.5 px-3">Extracted Raw Value</TableHead>
                      <TableHead className="py-2.5 px-3">Normalized Value</TableHead>
                      <TableHead className="py-2.5 px-3 text-center">Method</TableHead>
                      <TableHead className="py-2.5 px-3">Source Document</TableHead>
                      <TableHead className="py-2.5 px-3 text-right">Page</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {allExtractedFields.map((f) => (
                      <TableRow key={`${f.docId}-${f.id}`} className="hover:bg-slate-50/60 text-xs">
                        <TableCell className="py-2.5 px-3 font-semibold text-slate-900 font-mono text-[11px]">
                          {f.fieldName}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 font-medium text-slate-800">
                          {f.fieldValue}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-slate-600 font-mono text-[11px]">
                          {f.normalizedValue || '—'}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-center">
                          <MethodBadge method={f.method} />
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-slate-600 truncate max-w-xs">
                          {f.docName}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-right font-mono text-slate-600">
                          {f.page ?? 1}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>

          {/* SECTION 5: RISK ANALYSIS */}
          <TabsContent value="risk" className="p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Risk Analysis
                  </h3>
                  <SystemLayerTag layer="RULE_ENGINE" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Independent of the compliance score — computed from the risk engine's
                  detected signals below.
                </p>
              </div>
              <div className="text-right">
                <span className="text-xs font-semibold text-slate-500">Overall Level:</span>{' '}
                <RiskBadge level={bid.risk_level} />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
                <span className="text-[10.5px] uppercase font-semibold text-slate-500 block">
                  Risk Score
                </span>
                <span className="text-3xl font-mono font-bold text-slate-900 block mt-1">
                  {bid.risk_score != null ? `${Math.round(bid.risk_score)} / 100` : '—'}
                </span>
                <p className="mt-2 text-xs text-slate-500">
                  Deterministic scale: Higher scores indicate compounded statutory risks.
                </p>
              </div>

              <div className="md:col-span-2 rounded-lg border border-blue-200 bg-blue-50/60 p-4">
                <h4 className="text-xs font-bold text-blue-950 uppercase tracking-wide flex items-center gap-1.5">
                  <Scale className="h-4 w-4 text-blue-700" />
                  Independent Risk Methodology Notice
                </h4>
                <p className="mt-1 text-xs text-blue-900 leading-relaxed">
                  Compliance score and risk score are evaluated independently. A bidder with a 100% compliance score can still be classified as <strong>CRITICAL RISK</strong> if debarment lists, GST cancellations, or company liquidation indicators are detected.
                </p>
              </div>
            </div>

            {/* Risk Signals List */}
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-3">
                Detected Risk Factors &amp; Signals ({risk?.signals.length ?? 0})
              </h4>

              {risk && risk.signals.length > 0 ? (
                <div className="divide-y divide-slate-100">
                  {risk.signals.map((sig, idx) => {
                    const sev = sig.severity.toLowerCase();
                    return (
                      <div key={idx} className="py-3 flex items-start gap-3">
                        <span
                          className={`h-2.5 w-2.5 rounded-full mt-1 shrink-0 ${
                            sev === 'critical'
                              ? 'bg-rose-600'
                              : sev === 'high'
                              ? 'bg-orange-500'
                              : sev === 'medium'
                              ? 'bg-amber-500'
                              : 'bg-emerald-500'
                          }`}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-xs text-slate-900">{labelize(sig.code)}</span>
                            <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded border bg-slate-50 text-slate-600 uppercase">
                              {sig.severity} impact
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-slate-600 leading-relaxed">{sig.message}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="p-4 text-center text-xs text-slate-400">
                  No risk signals recorded. Run compliance &amp; risk evaluation.
                </div>
              )}
            </div>
          </TabsContent>

          {/* SECTION 6: AI EXPLANATION & RECOMMENDATION */}
          <TabsContent value="ai" className="p-6 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    AI-Assisted Policy Explanation &amp; Advisory
                  </h3>
                  <SystemLayerTag layer="AI_ASSISTED" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Advisory summary derived from the deterministic evaluation findings.
                  Decision support only — it never replaces the officer's verdict.
                </p>
              </div>

              {canVerify && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleGenerateRecommendation}
                loading={busy === 'recommendation'}
                className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
              >
                <Sparkles className="mr-1.5 h-3.5 w-3.5 text-blue-700" />
                Refresh AI Recommendation
              </Button>
              )}
            </div>

            {/* AI Recommendation Box — structured advisory */}
            {recommendation ? (
            <div className="rounded-lg border-2 border-indigo-200 bg-indigo-50/50 p-5 shadow-2xs">
              <div className="flex items-center gap-2 border-b border-indigo-100 pb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-indigo-950">
                  Overall:
                </span>
                <RecommendationBadge rec={recommendation.recommendation} />
              </div>

              <div className="mt-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-950 mb-2">
                  Key Findings
                </h4>
                {(() => {
                  const flagged = compliance_results.filter((c) => c.status !== 'PASS');
                  if (flagged.length === 0) {
                    return (
                      <p className="text-xs text-indigo-950 leading-relaxed">
                        All evaluated requirements returned PASS. No blocking findings were detected
                        by the rules engine.
                      </p>
                    );
                  }
                  return (
                    <ol className="space-y-3">
                      {flagged.map((c, idx) => (
                        <li key={c.id} className="flex items-start gap-2.5">
                          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[10px] font-bold text-white">
                            {idx + 1}
                          </span>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs font-semibold text-indigo-950">
                                {c.requirement?.requirement_name ?? `Requirement #${c.requirement_id}`}
                              </span>
                              <StatusBadge status={c.status} />
                            </div>
                            <p className="mt-0.5 text-xs text-indigo-900/80 leading-relaxed">
                              <span className="font-semibold text-indigo-950">Evidence:</span>{' '}
                              {c.explanation || 'No explanation recorded.'}
                            </p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  );
                })()}
              </div>

              {(() => {
                const flagged = compliance_results.filter((c) => c.status !== 'PASS');
                if (flagged.length === 0) return null;
                return (
                  <div className="mt-4 rounded-md bg-white/70 border border-indigo-100 p-3">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-950 mb-1.5">
                      Officer Guidance
                    </h4>
                    <ul className="space-y-1 text-xs text-indigo-950 leading-relaxed list-disc pl-4">
                      {flagged.map((c) => (
                        <li key={c.id}>
                          Review the {labelize(c.status).toLowerCase()}{' '}
                          {(c.requirement?.requirement_name ?? 'requirement').toLowerCase()}.
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })()}

              <div className="mt-4 border-t border-indigo-100 pt-3 text-[11px] text-indigo-800 font-medium">
                Procurement Officer retains final decision authority. This advisory does not
                qualify or disqualify any bidder.
              </div>
            </div>
            ) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
              <p className="text-sm font-semibold text-slate-700">No AI recommendation generated yet.</p>
              <p className="mt-1 text-xs text-slate-500">
                Click “Refresh AI Recommendation” above to generate an advisory recommendation for this bid.
              </p>
            </div>
            )}

            {/* Policy Citations (source-grounded retrieval) */}
            {(() => {
              const citations = ((recommendation as any)?.policy_context || []) as PolicyCitation[];
              if (citations.length === 0) {
                return (
                  <p className="text-xs text-slate-500 italic">
                    No relevant authoritative policy guidance was retrieved for this finding.
                  </p>
                );
              }
              return (
                <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-1 flex items-center gap-1.5">
                    <FileText className="h-4 w-4 text-blue-700" />
                    Relevant Policy References
                  </h4>
                  <p className="text-[11px] text-slate-500 mb-3">
                    Retrieved authoritative provisions relevant to the flagged findings above. Advisory context only — they do not change the compliance result or the recommendation.
                  </p>
                  <div className="space-y-3">
                    {citations.map((ctx, idx) => (
                      <div key={idx} className="rounded border border-slate-200 bg-slate-50 p-3 text-xs">
                        <p className="font-semibold text-slate-900">{ctx.title}</p>
                        <p className="mt-0.5 text-[11px] text-slate-500">
                          Authority: {ctx.authority}{ctx.section ? ` · Reference: ${ctx.section}` : ''}
                        </p>
                        {ctx.why_relevant && (
                          <p className="mt-1.5 text-[11px] text-slate-600">
                            <span className="font-semibold">Why relevant:</span> {ctx.why_relevant}
                          </p>
                        )}
                        {ctx.excerpt && (
                          <p className="mt-1.5 text-slate-700 leading-relaxed font-serif italic text-[11.5px] line-clamp-4">
                            “{ctx.excerpt}”
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
                          {ctx.version && <span>{ctx.version}</span>}
                          {ctx.effective_date && <span>Effective: {ctx.effective_date}</span>}
                          {ctx.source_url && (
                            <a
                              href={ctx.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 font-semibold text-blue-700 hover:underline"
                            >
                              View Source <ExternalLink className="h-3 w-3" />
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </TabsContent>

          {/* SECTION 8: AUDIT TRAIL */}
          <TabsContent value="audit" className="p-6 space-y-5">
            <div className="flex items-center gap-2 border-b border-slate-200 pb-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                Audit Trail ({audit.length})
              </h3>
              <SystemLayerTag layer="AUDIT_CHAIN" size="sm" />
            </div>
            <p className="text-xs text-slate-500">
              Tamper-evident record of every action on this bid — evaluations, overrides,
              clarifications and decisions.
            </p>

            {audit.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No audit events recorded yet.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                      <TableHead className="py-2.5 px-3">Time</TableHead>
                      <TableHead className="py-2.5 px-3">Actor</TableHead>
                      <TableHead className="py-2.5 px-3">Action</TableHead>
                      <TableHead className="py-2.5 px-3">Record</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {audit.map((a) => (
                      <TableRow key={a.id} className="hover:bg-slate-50/60 text-xs">
                        <TableCell className="py-2.5 px-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                          {formatDateTime(a.timestamp)}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-slate-700">
                          {a.user_name || 'System'}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 font-semibold text-slate-900">
                          {labelize(a.action)}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-slate-600">
                          {labelize(a.entity_type)}{a.entity_id ? ` #${a.entity_id}` : ''}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </TabsContent>
          {/* SECTION 8: VERIFICATION REPORT HANDOFF */}
          <TabsContent value="report" className="p-6 space-y-5">
            <ReportTab bidId={bidId} />
          </TabsContent>
        </Tabs>
      </div>

      {/* 5. MODAL DIALOGS */}
      {/* First Decision Confirmation Dialog */}
      <Dialog open={decisionDialog !== null} onOpenChange={() => setDecisionDialog(null)}>
        <DialogContent className="max-w-lg bg-white border border-slate-300">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 font-serif">
              Record Formal Officer Verdict: {decisionDialog && labelize(decisionDialog)}
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600">
              This action qualifies or disqualifies {bidder.legal_name} for tender #{tender.tender_number} and will be permanently recorded in the SHA-256 audit ledger.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-4 pt-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Statutory Justification / Findings *
              </label>
              <Textarea
                rows={4}
                value={decisionReason}
                onChange={(e) => setDecisionReason(e.target.value)}
                placeholder="Detail the technical evaluation findings, verification status, and basis of qualification or disqualification."
                className="text-xs border-slate-300 leading-relaxed"
              />
              {decisionError && <p className="mt-1 text-xs text-rose-600">{decisionError}</p>}
            </div>
          </DialogBody>

          <DialogFooter className="flex items-center justify-between border-t border-slate-100 pt-3">
            <Button variant="ghost" size="sm" onClick={() => setDecisionDialog(null)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={confirmFirstDecision}
              loading={busy === 'first-decision'}
              className="bg-blue-800 hover:bg-blue-900 text-white font-medium text-xs"
            >
              Sign &amp; Confirm Verdict
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change Decision Dialog */}
      <Dialog open={changeOpen} onOpenChange={setChangeOpen}>
        <DialogContent className="max-w-lg bg-white border border-slate-300">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 font-serif">
              Modify Previous Officer Decision
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600">
              Current Verdict: {bid.officer_decision && labelize(bid.officer_decision)}. State the administrative reasons justifying the amendment.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-4 pt-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">New Verdict</label>
              <Select
                value={newDecision}
                onChange={(e) => setNewDecision(e.target.value as 'APPROVE' | 'REJECT' | 'ESCALATE')}
                className="text-xs"
              >
                <option value="APPROVE">Approve (Qualify Bidder)</option>
                <option value="REJECT">Reject (Disqualify Bidder)</option>
                <option value="ESCALATE">Escalate (Refer to Tender Committee)</option>
              </Select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Amendment Justification *
              </label>
              <Textarea
                rows={4}
                value={changeReason}
                onChange={(e) => setChangeReason(e.target.value)}
                placeholder="Explain the review basis, newly produced documents, or committee deliberations."
                className="text-xs border-slate-300"
              />
              {changeError && <p className="mt-1 text-xs text-rose-600">{changeError}</p>}
            </div>
          </DialogBody>

          <DialogFooter className="flex items-center justify-between border-t border-slate-100 pt-3">
            <Button variant="ghost" size="sm" onClick={() => setChangeOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={confirmChangeDecision}
              loading={busy === 'change-decision'}
              className="bg-blue-800 hover:bg-blue-900 text-white font-medium text-xs"
            >
              Confirm Amendment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Override Dialog */}
      <Dialog open={overrideTarget !== null} onOpenChange={() => setOverrideTarget(null)}>
        <DialogContent className="max-w-lg bg-white border border-slate-300">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 font-serif">
              Override Finding
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600">
              {overrideTarget?.requirement?.requirement_name ?? `Requirement #${overrideTarget?.requirement_id}`}
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-4 pt-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-600">Current Result:</span>
              {overrideTarget && <StatusBadge status={overrideTarget.status} />}
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              The original automated result is preserved. Your override, justification and
              identity are recorded in the audit trail alongside it.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Justification *
              </label>
              <Textarea
                rows={3}
                value={overrideComment}
                onChange={(e) => setOverrideComment(e.target.value)}
                placeholder="Record the reason for overriding this finding."
                className="text-xs border-slate-300"
              />
              {overrideError && <p className="mt-1 text-xs text-rose-600">{overrideError}</p>}
            </div>
          </DialogBody>

          <DialogFooter className="flex items-center justify-between border-t border-slate-100 pt-3">
            <Button variant="ghost" size="sm" onClick={() => setOverrideTarget(null)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={confirmOverride}
              loading={busy === 'override'}
              className="bg-blue-800 hover:bg-blue-900 text-white font-medium text-xs"
            >
              Confirm Override
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Clarification Request Modal */}
      <Dialog open={clarifyOpen} onOpenChange={setClarifyOpen}>
        <DialogContent className="max-w-lg bg-white border border-slate-300">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 font-serif">
              Issue Formal Clarification Query
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600">
              Transmit a technical query to {bidder.legal_name} regarding tender requirements.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-4 pt-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Subject</label>
              <Input
                value={clarifySubject}
                onChange={(e) => setClarifySubject(e.target.value)}
                className="text-xs border-slate-300"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Query Content</label>
              <Textarea
                rows={4}
                value={clarifyBody}
                onChange={(e) => setClarifyBody(e.target.value)}
                placeholder="Specify the document, discrepancy, or requirement requiring bidder clarification."
                className="text-xs border-slate-300"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex items-center justify-between border-t border-slate-100 pt-3">
            <Button variant="ghost" size="sm" onClick={() => setClarifyOpen(false)}>
              Cancel
            </Button>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleCreateClarification(false)}
                loading={busy === 'clarify-create'}
                className="text-xs"
              >
                Save Draft
              </Button>
              <Button
                size="sm"
                onClick={() => handleCreateClarification(true)}
                loading={busy === 'clarify-dispatch'}
                className="bg-blue-800 hover:bg-blue-900 text-white font-medium text-xs"
              >
                <Send className="mr-1 h-3 w-3" />
                Save &amp; Dispatch
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Evidence Drawer Modal */}
      {selectedResult && (
        <EvidenceDrawer
          result={selectedResult}
          documents={documents}
          onClose={() => setSelectedResult(null)}
        />
      )}

      {/* Attach Demo Evidence Modal (recovery when publish-time seeding failed) */}
      <Dialog open={demoEvidenceOpen} onOpenChange={setDemoEvidenceOpen}>
        <DialogContent className="max-w-lg bg-white border border-slate-300">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 font-serif">
              Attach Demo Evidence Dossier
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600">
              This bid has no documents. Select the fictional demo profile whose
              evidence dossier should be attached for {bidder.legal_name}. The
              dossier is stored as a normal document and run through the real
              extraction pipeline; verification, compliance and recommendation
              are still derived when you run them.
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-2 pt-3">
            {DEMO_BIDDER_PROFILES.map((p) => (
              <label
                key={p.profile_key}
                className={`flex items-start gap-3 rounded-md border p-3 cursor-pointer transition-colors ${
                  demoProfileKey === p.profile_key
                    ? 'border-blue-700 bg-blue-50/60'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <input
                  type="radio"
                  name="demo-profile"
                  checked={demoProfileKey === p.profile_key}
                  onChange={() => setDemoProfileKey(p.profile_key)}
                  className="mt-1"
                />
                <div>
                  <p className="text-xs font-bold text-slate-900">{p.legal_name}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">{p.scenario_description}</p>
                </div>
              </label>
            ))}
          </DialogBody>

          <DialogFooter className="flex items-center justify-between border-t border-slate-100 pt-3">
            <Button variant="ghost" size="sm" onClick={() => setDemoEvidenceOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleAttachDemoEvidence}
              loading={busy === 'demo-evidence'}
              className="bg-amber-600 hover:bg-amber-700 text-white font-medium text-xs"
            >
              Attach &amp; Extract
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
