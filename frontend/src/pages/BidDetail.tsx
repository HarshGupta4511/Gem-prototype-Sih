import * as React from 'react';
import { useQuery, useQueries, useQueryClient } from '@tanstack/react-query';
import { useParams, Link, useNavigate } from 'react-router-dom';
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
} from '../types';
import {
  bidsApi,
  documentsApi,
  verificationApi,
  complianceApi,
  recommendationApi,
  officerApi,
  getErrorMessage,
} from '../lib/api';
import {
  formatDate,
  formatDateTime,
  labelize,
  timeAgo,
} from '../lib/utils';
import { useAuth } from '../context/AuthContext';
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
  const [expandedCheck, setExpandedCheck] = React.useState<number | null>(null);
  const [activeTab, setActiveTab] = React.useState('compliance');

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
  const [overrideDocId, setOverrideDocId] = React.useState('');
  const [overrideError, setOverrideError] = React.useState<string | null>(null);

  // Clarification Dialog
  const [clarifyOpen, setClarifyOpen] = React.useState(false);
  const [clarifySubject, setClarifySubject] = React.useState('');
  const [clarifyBody, setClarifyBody] = React.useState('');
  const [sendId, setSendId] = React.useState<number | null>(null);

  // Upload state
  const [uploadFile, setUploadFile] = React.useState<File | null>(null);

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
      toast({ title: 'Operation Failed', description: getErrorMessage(err) });
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
      toast({ title: 'AI Advisory Generated', description: 'Policy citations and evidence synthesis updated.' });
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
    setOverrideDocId('');
    setOverrideError(null);
  }

  async function confirmOverride() {
    if (!overrideTarget) return;
    if (overrideComment.trim().length === 0) {
      setOverrideError('A detailed officer justification is mandatory to override deterministic rules.');
      return;
    }
    runBusy('override', async () => {
      await officerApi.override({
        target_type: 'COMPLIANCE_RESULT',
        target_id: overrideTarget.id,
        officer_comment: overrideComment.trim(),
        supporting_document_id: overrideDocId ? Number(overrideDocId) : undefined,
      });
      setOverrideTarget(null);
      await invalidate();
      toast({ title: 'Officer Override Recorded', description: 'Audit chain updated with justification.' });
    });
  }

  // Clarification handlers
  async function handleCreateClarification(e: React.FormEvent) {
    e.preventDefault();
    if (!clarifySubject.trim() || !clarifyBody.trim()) return;
    runBusy('clarify-create', async () => {
      await officerApi.clarification({
        bid_id: bidId,
        subject: clarifySubject.trim(),
        body: clarifyBody.trim(),
      });
      setClarifyOpen(false);
      setClarifySubject('');
      setClarifyBody('');
      await invalidate();
      toast({ title: 'Clarification Drafted', description: 'Draft query saved to bidder file.' });
    });
  }

  async function handleSendClarification(clarifyId: number) {
    runBusy(`clarify-send-${clarifyId}`, async () => {
      await officerApi.sendClarification(clarifyId);
      setSendId(null);
      await invalidate();
      toast({ title: 'Clarification Dispatched', description: 'Vendor notified via portal.' });
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

  const { bid, bidder, tender, documents, verification_checks, compliance_results, risk, recommendation, overrides, clarifications } = data;

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
            <div className="mt-1 flex items-baseline gap-2">
              <span className="font-mono text-xl font-bold text-emerald-800">
                {passedCount} / {totalRules}
              </span>
              <span className="text-[10px] text-emerald-700">rules met</span>
            </div>
            <p className="mt-1 text-[10px] text-slate-500">
              {totalRules - passedCount} non-pass rules
            </p>
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
                4. Extracted Info ({allExtractedFields.length})
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
                6. AI Explanation &amp; Advisory
              </TabsTrigger>
              <TabsTrigger
                value="overrides"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                7. Overrides &amp; Clarifications ({overrides.length + clarifications.length})
              </TabsTrigger>
              <TabsTrigger
                value="report"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-3.5 py-2.5 text-xs font-semibold"
              >
                8. Verification Report
              </TabsTrigger>
            </TabsList>
          </div>

          {/* SECTION 1: COMPLIANCE EVALUATION */}
          <TabsContent value="compliance" className="p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Deterministic Compliance Results ({compliance_results.length} rules)
                  </h3>
                  <SystemLayerTag layer="RULE_ENGINE" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Calculated against tender-specific requirements using strict numerical &amp; document matching.
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
                      <TableHead className="py-2.5 px-3">Rule Type</TableHead>
                      <TableHead className="py-2.5 px-3">Required Threshold</TableHead>
                      <TableHead className="py-2.5 px-3">Actual Value</TableHead>
                      <TableHead className="py-2.5 px-3 text-center">Status</TableHead>
                      <TableHead className="py-2.5 px-3 text-right">Weight</TableHead>
                      <TableHead className="py-2.5 px-3 text-right">Evidence</TableHead>
                      <TableHead className="py-2.5 px-3 text-right">Override</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {compliance_results.map((c) => {
                      const isOverridden = c.overridden;
                      const reqName = c.requirement?.requirement_name ?? `Requirement #${c.requirement_id}`;
                      const isMandatory = c.requirement?.mandatory ?? false;
                      const ruleType = c.requirement?.rule_type ?? c.rule_applied;
                      const threshold = c.requirement?.threshold ?? '—';
                      const actualValue = c.evidence?.[0]?.value ?? c.explanation ?? 'Not Found';
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
                          <TableCell className="py-2.5 px-3">
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] font-mono text-slate-700 border border-slate-200">
                              {ruleType}
                            </span>
                          </TableCell>
                          <TableCell className="py-2.5 px-3 font-mono text-slate-700">
                            {threshold}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 font-mono text-slate-900 font-medium">
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
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => openOverride(c)}
                                className="text-xs text-slate-600 hover:text-slate-900 h-7 px-2 border-slate-300"
                              >
                                Override
                              </Button>
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
                  Automated verification checks cross-referenced against statutory portal registries.
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
                    <TableHead className="py-2.5 px-3">Statutory Source</TableHead>
                    <TableHead className="py-2.5 px-3">Check Type / Scope</TableHead>
                    <TableHead className="py-2.5 px-3">Identifier Checked</TableHead>
                    <TableHead className="py-2.5 px-3 text-center">Outcome Status</TableHead>
                    <TableHead className="py-2.5 px-3">Verification Detail</TableHead>
                    <TableHead className="py-2.5 px-3 text-right">Raw Payload</TableHead>
                  </tr>
                </TableHeader>
                <TableBody>
                  {verification_checks.map((vc) => {
                    const isExpanded = expandedCheck === vc.id;
                    return (
                      <React.Fragment key={vc.id}>
                        <TableRow className="hover:bg-slate-50/60 text-xs">
                          <TableCell className="py-2.5 px-3 font-semibold text-slate-900">
                            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-mono border border-slate-200">
                              {vc.source}
                            </span>
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-slate-700">
                            {labelize(vc.source)}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 font-mono text-slate-800">
                            {vc.identifier}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-center">
                            <VerificationBadge status={vc.verification_status} />
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-slate-600 max-w-xs truncate">
                            {vc.evidence_reference || (vc.response_payload ? JSON.stringify(vc.response_payload) : 'External verification verified.')}
                          </TableCell>
                          <TableCell className="py-2.5 px-3 text-right">
                            <button
                              type="button"
                              onClick={() => setExpandedCheck(isExpanded ? null : vc.id)}
                              className="text-xs font-semibold text-blue-700 hover:underline"
                            >
                              {isExpanded ? 'Hide Payload' : 'View Payload'}
                            </button>
                          </TableCell>
                        </TableRow>

                        {isExpanded && (
                          <TableRow className="bg-slate-50">
                            <TableCell colSpan={6} className="p-4">
                              <div className="rounded border border-slate-200 bg-slate-900 p-3 text-slate-200 font-mono text-[11px] overflow-x-auto">
                                <pre>{JSON.stringify(vc.response_payload, null, 2)}</pre>
                              </div>
                            </TableCell>
                          </TableRow>
                        )}
                      </React.Fragment>
                    );
                  })}
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
                    <TableHead className="py-2.5 px-3 text-center">Confidence</TableHead>
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
                      <TableCell className="py-2.5 px-3 text-center font-mono">
                        {doc.extraction_confidence != null
                          ? `${Math.round(doc.extraction_confidence * 100)}%`
                          : '—'}
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
                            onClick={() => navigate(`/app/viewer/${doc.id}`)}
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
                      <TableHead className="py-2.5 px-3 text-center">Confidence</TableHead>
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
                        <TableCell className="py-2.5 px-3 text-center font-mono">
                          {Math.round(f.confidence * 100)}%
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
                    Independent Risk Classification Profile
                  </h3>
                  <SystemLayerTag layer="AI_ASSISTED" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Multi-signal anomaly detection covering statutory debarment, financial health, and submission timing.
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
                  Calculated Risk Score
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
                            <span className="font-semibold text-xs text-slate-900 font-mono">{sig.code}</span>
                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded border bg-slate-50 text-slate-600 uppercase">
                              {sig.severity}
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
                  Grounds evaluation findings against CPCL procurement policy and GFR 2017 provisions using RAG retrieval.
                </p>
              </div>

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
            </div>

            {/* AI Recommendation Box */}
            <div className="rounded-lg border-2 border-indigo-200 bg-indigo-50/50 p-5 shadow-2xs">
              <div className="flex items-center justify-between border-b border-indigo-100 pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-indigo-950">
                    AI Advisory Recommendation:
                  </span>
                  <RecommendationBadge rec={recommendation.recommendation} />
                </div>
                <span className="text-[10px] font-mono text-indigo-700 bg-white px-2 py-0.5 rounded border border-indigo-200">
                  Provider: {(recommendation as any).provider || 'gemini-2.0-flash'}
                </span>
              </div>

              <div className="mt-3">
                <p className="text-xs text-indigo-950 leading-relaxed font-medium">
                  {recommendation.reason || 'No recommendation generated yet.'}
                </p>
              </div>

              <div className="mt-4 border-t border-indigo-100 pt-3 flex items-center justify-between text-[11px] text-indigo-800">
                <span>Advisory recommendation only. The Procurement Officer retains sole statutory award authority.</span>
              </div>
            </div>

            {/* Policy Citations (RAG) */}
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-3 flex items-center gap-1.5">
                <FileText className="h-4 w-4 text-blue-700" />
                Retrieved Policy Citations (RAG Knowledge Base)
              </h4>

              {(recommendation as any).policy_context && (recommendation as any).policy_context.length > 0 ? (
                <div className="space-y-3">
                  {(recommendation as any).policy_context.map((ctx: any, idx: number) => (
                    <div key={idx} className="rounded border border-slate-200 bg-slate-50 p-3 text-xs">
                      <p className="font-semibold text-slate-900">{ctx.title}</p>
                      <p className="mt-1 text-slate-600 leading-relaxed font-serif italic text-[11.5px]">
                        "{ctx.chunk}"
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 text-center text-xs text-slate-400">
                  No policy citations retrieved for this evaluation.
                </div>
              )}
            </div>
          </TabsContent>

          {/* SECTION 7: OVERRIDES & CLARIFICATIONS */}
          <TabsContent value="overrides" className="p-6 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Procurement Officer Overrides &amp; Clarification Queries
                  </h3>
                  <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Recorded administrative justifications modifying automated rule evaluation results.
                </p>
              </div>

              {canDecide && (
                <Button
                  size="sm"
                  onClick={() => {
                    setClarifyOpen(true);
                    setClarifySubject(`Clarification Query - ${bidder.legal_name}`);
                  }}
                  className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium"
                >
                  <MessageSquare className="mr-1.5 h-3.5 w-3.5" />
                  New Clarification Query
                </Button>
              )}
            </div>

            {/* Overrides Table */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-3">
                Recorded Administrative Overrides ({overrides.length})
              </h4>

              {overrides.length === 0 ? (
                <p className="text-xs text-slate-400 italic">No officer overrides recorded for this bidder.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                        <th className="py-2 px-2">Timestamp</th>
                        <th className="py-2 px-2">Target</th>
                        <th className="py-2 px-2">Original Status</th>
                        <th className="py-2 px-2">Justification / Comment</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {overrides.map((ov) => (
                        <tr key={ov.id}>
                          <td className="py-2 px-2 font-mono text-[11px] text-slate-500">
                            {formatDateTime(ov.created_at)}
                          </td>
                          <td className="py-2 px-2 font-semibold text-slate-900">{ov.target_type}</td>
                          <td className="py-2 px-2">
                            <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 border border-rose-200">
                              {ov.original_status}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-slate-700 leading-relaxed">{ov.officer_comment}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Clarifications Table */}
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-3">
                Vendor Clarification Enquiries ({clarifications.length})
              </h4>

              {clarifications.length === 0 ? (
                <p className="text-xs text-slate-400 italic">No clarification requests issued.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 font-semibold">
                        <th className="py-2 px-2">Created</th>
                        <th className="py-2 px-2">Subject</th>
                        <th className="py-2 px-2">Query</th>
                        <th className="py-2 px-2">Status</th>
                        <th className="py-2 px-2 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {clarifications.map((cl) => (
                        <tr key={cl.id}>
                          <td className="py-2 px-2 font-mono text-[11px] text-slate-500">
                            {formatDateTime(cl.created_at)}
                          </td>
                          <td className="py-2 px-2 font-semibold text-slate-900">{cl.subject}</td>
                          <td className="py-2 px-2 text-slate-700 max-w-sm truncate">{cl.body}</td>
                          <td className="py-2 px-2">
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                cl.status === 'SENT'
                                  ? 'bg-blue-50 text-blue-800 border border-blue-200'
                                  : 'bg-slate-100 text-slate-600 border border-slate-200'
                              }`}
                            >
                              {cl.status}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-right">
                            {cl.status === 'DRAFT' && canDecide && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleSendClarification(cl.id)}
                                loading={busy === `clarify-send-${cl.id}`}
                                className="text-xs h-7 px-2"
                              >
                                <Send className="mr-1 h-3 w-3" />
                                Dispatch
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
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
              Administrative Rule Override
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600">
              Override finding for requirement: <strong>{overrideTarget?.requirement?.requirement_name ?? `Requirement #${overrideTarget?.requirement_id}`}</strong> (Currently {overrideTarget?.status})
            </DialogDescription>
          </DialogHeader>

          <DialogBody className="space-y-4 pt-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Officer Justification for Override *
              </label>
              <Textarea
                rows={3}
                value={overrideComment}
                onChange={(e) => setOverrideComment(e.target.value)}
                placeholder="Record statutory exception, authorized exemption, or verified alternative document."
                className="text-xs border-slate-300"
              />
              {overrideError && <p className="mt-1 text-xs text-rose-600">{overrideError}</p>}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Supporting Submitted Document (Optional)
              </label>
              <Select
                value={overrideDocId}
                onChange={(e) => setOverrideDocId(e.target.value)}
                className="text-xs"
              >
                <option value="">None selected</option>
                {documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename} ({d.document_type})
                  </option>
                ))}
              </Select>
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
              Record Override in Ledger
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
            <Button
              size="sm"
              onClick={handleCreateClarification}
              loading={busy === 'clarify-create'}
              className="bg-blue-800 hover:bg-blue-900 text-white font-medium text-xs"
            >
              Save Query
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Evidence Drawer Modal */}
      {selectedResult && (
        <EvidenceDrawer
          result={selectedResult}
          onClose={() => setSelectedResult(null)}
        />
      )}
    </div>
  );
}
