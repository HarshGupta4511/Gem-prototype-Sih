import { useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  Building2,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  FileCheck,
  FileSpreadsheet,
  FileText,
  Filter,
  Layers,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  Users,
  Plus,
} from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { auditApi, tendersApi, bidsApi, getErrorMessage } from '../lib/api';
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
  BidStatusBadge,
  DecisionBadge,
  RecommendationBadge,
  RiskBadge,
} from '../components/common/badges';
import { ComparisonMatrix } from '../components/tenders/ComparisonMatrix';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
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
        <span className="font-mono font-semibold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
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
      return <span className="text-slate-500 font-mono text-xs">{labelize(e.action)}</span>;
  }
}

export default function TenderDetail() {
  const { id } = useParams<{ id: string }>();
  const tenderId = Number(id);
  const validId = Number.isFinite(tenderId);
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('overview');

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

  // Running weight tally
  const totalWeight = requirements.reduce((acc, r) => acc + (r.weight ?? 0), 0);
  const isWeightValid = Math.round(totalWeight) === 100;
  const mandatoryCount = requirements.filter((r) => r.mandatory).length;

  return (
    <div className="space-y-5">
      {/* 1. Header Navigation & Procurement Dossier Summary */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex items-center gap-2 text-xs text-slate-500 mb-3">
          <Link
            to="/app/tenders"
            className="inline-flex items-center gap-1 font-medium text-blue-800 hover:underline hover:text-blue-900"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Tenders Registry</span>
          </Link>
          <span>/</span>
          <span className="font-mono text-slate-700 font-semibold">{tender.tender_number}</span>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 border-b border-slate-100 pb-4">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="font-mono text-sm font-bold text-blue-950 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                {tender.tender_number}
              </span>
              <span
                className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide border ${
                  tender.status === 'OPEN'
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                    : 'bg-slate-100 text-slate-700 border-slate-300'
                }`}
              >
                {tender.status}
              </span>
              <span className="text-xs text-slate-500 font-medium">
                {tender.tender_type || 'OPEN'} • {tender.bid_type || 'TWO_PACKET'}
              </span>
            </div>
            <h1 className="mt-1.5 text-2xl font-bold tracking-tight text-slate-900 font-serif">
              {tender.title}
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5 text-slate-400" />
              <span>{tender.organization}</span>
              <span className="text-slate-300">•</span>
              <span>{tender.department}</span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveTab('matrix')}
              className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
            >
              <FileSpreadsheet className="mr-1.5 h-3.5 w-3.5 text-blue-700" />
              Compare Bidders
            </Button>
            <Button
              size="sm"
              onClick={() => setActiveTab('bidders')}
              className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium shadow-xs"
            >
              <Users className="mr-1.5 h-3.5 w-3.5" />
              Evaluate Bidders ({bidders.length})
            </Button>
          </div>
        </div>

        {/* Key Metrics Bar */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 pt-1">
          <div className="rounded border border-slate-100 bg-slate-50/70 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 block">
              Estimated Value
            </span>
            <span className="font-mono text-sm font-bold text-slate-900 block mt-0.5">
              {formatINR(tender.estimated_value_inr)}
            </span>
          </div>

          <div className="rounded border border-slate-100 bg-slate-50/70 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 block">
              EMD Amount
            </span>
            <span className="font-mono text-sm font-bold text-slate-900 block mt-0.5">
              {tender.emd_amount_inr ? formatINR(tender.emd_amount_inr) : 'Exempted / Zero'}
            </span>
          </div>

          <div className="rounded border border-slate-100 bg-slate-50/70 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 block">
              Bids Submitted
            </span>
            <span className="font-mono text-sm font-bold text-slate-900 block mt-0.5">
              {stats.bidder_count} participating
            </span>
          </div>

          <div className="rounded border border-slate-100 bg-slate-50/70 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 block">
              Avg Compliance
            </span>
            <span className="font-mono text-sm font-bold text-emerald-800 block mt-0.5">
              {stats.avg_compliance != null ? `${stats.avg_compliance.toFixed(1)}%` : '—'}
            </span>
          </div>

          <div className="rounded border border-slate-100 bg-slate-50/70 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 block">
              High Risk Alerts
            </span>
            <span
              className={`font-mono text-sm font-bold block mt-0.5 ${
                stats.high_risk_count > 0 ? 'text-rose-700' : 'text-slate-900'
              }`}
            >
              {stats.high_risk_count > 0 ? `${stats.high_risk_count} Flagged` : '0 Alerts'}
            </span>
          </div>

          <div className="rounded border border-slate-100 bg-slate-50/70 p-2.5">
            <span className="text-[10.5px] uppercase font-semibold text-slate-500 block">
              Closing Deadline
            </span>
            <span className="font-mono text-xs font-bold text-slate-800 block mt-0.5">
              {formatDate(tender.closing_date)}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Dossier Tabs Container */}
      <div className="rounded-lg border border-slate-200 bg-white shadow-xs overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="border-b border-slate-200 bg-slate-50/80 px-4 pt-2">
            <TabsList className="bg-transparent space-x-1 p-0 h-auto">
              <TabsTrigger
                value="overview"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-4 py-2.5 text-xs font-semibold"
              >
                1. Overview Dossier
              </TabsTrigger>
              <TabsTrigger
                value="requirements"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-4 py-2.5 text-xs font-semibold"
              >
                2. Requirements ({requirements.length})
              </TabsTrigger>
              <TabsTrigger
                value="bidders"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-4 py-2.5 text-xs font-semibold"
              >
                3. Bidders Evaluation ({bidders.length})
              </TabsTrigger>
              <TabsTrigger
                value="matrix"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-4 py-2.5 text-xs font-semibold"
              >
                4. Compliance Matrix
              </TabsTrigger>
              <TabsTrigger
                value="audit"
                className="data-[state=active]:bg-white data-[state=active]:border-b-2 data-[state=active]:border-blue-800 data-[state=active]:text-blue-900 rounded-none px-4 py-2.5 text-xs font-semibold"
              >
                5. Statutory Audit Trail
              </TabsTrigger>
            </TabsList>
          </div>

          {/* TAB 1: OVERVIEW */}
          <TabsContent value="overview" className="p-6 space-y-6">
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs">
              <div className="border-b border-slate-100 pb-3 mb-4 flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                  Tender Information &amp; Commercial Terms
                </h3>
                <span className="text-xs font-mono text-slate-400">ID: #{tender.id}</span>
              </div>

              <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3.5 text-xs">
                <div>
                  <dt className="text-slate-500 font-medium">Procuring Entity</dt>
                  <dd className="font-semibold text-slate-900 mt-0.5">{tender.organization}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Department / Section</dt>
                  <dd className="font-semibold text-slate-900 mt-0.5">{tender.department}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Estimated Package Value</dt>
                  <dd className="font-mono font-bold text-slate-900 mt-0.5">
                    {formatINR(tender.estimated_value_inr)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Issue / Release Date</dt>
                  <dd className="font-mono text-slate-800 mt-0.5">{formatDate(tender.issue_date)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Bid Closing Deadline</dt>
                  <dd className="font-mono font-bold text-rose-800 mt-0.5">
                    {formatDate(tender.closing_date)} (17:30 IST)
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Earnest Money Deposit (EMD)</dt>
                  <dd className="font-mono font-semibold text-slate-900 mt-0.5">
                    {tender.emd_amount_inr != null ? formatINR(tender.emd_amount_inr) : 'Exempted / Zero'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Tender Invitation Type</dt>
                  <dd className="font-semibold text-slate-900 mt-0.5">
                    {tender.tender_type ? labelize(tender.tender_type) : 'OPEN'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Bidding Envelope Mode</dt>
                  <dd className="font-semibold text-slate-900 mt-0.5">
                    {tender.bid_type ? labelize(tender.bid_type) : 'TWO_PACKET'}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500 font-medium">Delivery / Execution Period</dt>
                  <dd className="font-semibold text-slate-900 mt-0.5">{tender.delivery_period ?? '24 Weeks'}</dd>
                </div>
                <div className="sm:col-span-2 lg:col-span-3">
                  <dt className="text-slate-500 font-medium">Consignee &amp; Place of Delivery</dt>
                  <dd className="font-semibold text-slate-900 mt-0.5">
                    {tender.place_of_delivery ?? 'CPCL Manali Refinery, Chennai, Tamil Nadu'}
                  </dd>
                </div>
              </dl>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-2">
                Technical Scope &amp; Specification
              </h3>
              <p className="text-xs leading-relaxed text-slate-700 bg-slate-50 p-4 rounded border border-slate-200">
                {tender.description}
              </p>
            </div>
          </TabsContent>

          {/* TAB 2: REQUIREMENTS */}
          <TabsContent value="requirements" className="p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Deterministic Compliance Rules ({requirements.length})
                  </h3>
                  <SystemLayerTag layer="RULE_ENGINE" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Requirements and evaluation weights configured for this procurement package.
                </p>
              </div>

              <div
                className={`rounded px-3 py-1 text-xs font-mono font-bold border ${
                  isWeightValid
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                    : 'bg-rose-50 text-rose-800 border-rose-300'
                }`}
              >
                Weight Sum: {Math.round(totalWeight)} / 100% {isWeightValid ? '✓' : '⚠️'}
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <Table>
                <TableHeader>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                    <TableHead className="py-2.5 px-3">Requirement</TableHead>
                    <TableHead className="py-2.5 px-3">Category</TableHead>
                    <TableHead className="py-2.5 px-3">Rule Type</TableHead>
                    <TableHead className="py-2.5 px-3">Threshold / Criteria</TableHead>
                    <TableHead className="py-2.5 px-3">Verification Source</TableHead>
                    <TableHead className="py-2.5 px-3 text-center">Mandatory</TableHead>
                    <TableHead className="py-2.5 px-3 text-right">Weight</TableHead>
                  </tr>
                </TableHeader>
                <TableBody>
                  {requirements.map((r) => (
                    <TableRow key={r.id} className="hover:bg-slate-50/60">
                      <TableCell className="py-2.5 px-3 font-semibold text-slate-900 text-xs">
                        {r.requirement_name}
                        {r.description && (
                          <span className="block text-[11px] font-normal text-slate-500 mt-0.5">
                            {r.description}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-xs text-slate-600">
                        {labelize(r.category)}
                      </TableCell>
                      <TableCell className="py-2.5 px-3">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] font-mono text-slate-700 border border-slate-200">
                          {r.rule_type}
                        </span>
                      </TableCell>
                      <TableCell className="py-2.5 px-3 font-medium text-slate-800 text-xs">
                        {r.threshold ?? '—'}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-xs font-mono text-slate-600">
                        {r.verification_source ? (
                          <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-900 border border-blue-200">
                            {r.verification_source}
                          </span>
                        ) : (
                          'Document Extraction'
                        )}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-center">
                        {r.mandatory ? (
                          <span className="rounded bg-rose-50 px-1.5 py-0.2 text-[10px] font-bold text-rose-700 border border-rose-200">
                            MANDATORY
                          </span>
                        ) : (
                          <span className="text-[11px] text-slate-400">Scored</span>
                        )}
                      </TableCell>
                      <TableCell className="py-2.5 px-3 text-right font-mono font-bold text-slate-900 text-xs">
                        {r.weight}%
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </TabsContent>

          {/* TAB 3: BIDDERS EVALUATION */}
          <TabsContent value="bidders" className="p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Participating Bidders Registry ({bidders.length})
                  </h3>
                  <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Select a bidder to review extracted document evidence, verification checks, and record your qualification decision.
                </p>
              </div>

              <Button
                size="sm"
                onClick={() => setRegisterModalOpen(true)}
                className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-semibold shrink-0 h-8 shadow-xs"
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                Register New Bidder
              </Button>
            </div>

            {bidders.length === 0 ? (
              <EmptyState
                title="No bids submitted yet"
                description="Bid submissions from prospective vendors will appear here once submitted."
              />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                      <TableHead className="py-3 px-3">Bidder Identity</TableHead>
                      <TableHead className="py-3 px-3">Statutory IDs</TableHead>
                      <TableHead className="py-3 px-3 text-center">Compliance Score</TableHead>
                      <TableHead className="py-3 px-3 text-center">Risk Level</TableHead>
                      <TableHead className="py-3 px-3 text-center">AI Recommendation</TableHead>
                      <TableHead className="py-3 px-3 text-center">Officer Decision</TableHead>
                      <TableHead className="py-3 px-3 text-center">Submission Status</TableHead>
                      <TableHead className="py-3 px-3 text-right">Action</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {bidders.map((b: TenderBidderRow) => (
                      <TableRow key={b.bid_id} className="hover:bg-blue-50/40 transition-colors">
                        <TableCell className="py-3 px-3">
                          <p className="font-semibold text-slate-900 text-xs">{b.legal_name}</p>
                          {b.trade_name && (
                            <p className="text-[10.5px] text-slate-500 font-medium">{b.trade_name}</p>
                          )}
                          <p className="text-[10px] text-slate-400 font-mono mt-0.5">Bid ID #{b.bid_id}</p>
                        </TableCell>

                        <TableCell className="py-3 px-3 font-mono text-[11px] text-slate-600">
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
                                    ? 'text-emerald-700'
                                    : b.compliance_score >= 60
                                    ? 'text-amber-700'
                                    : 'text-rose-700'
                                }`}
                              >
                                {b.compliance_score.toFixed(1)}%
                              </span>
                              <div className="w-16 bg-slate-200 h-1.5 rounded-full overflow-hidden mt-1">
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
                            <span className="text-[11px] text-slate-400">Pending</span>
                          )}
                        </TableCell>

                        {/* Risk Level */}
                        <TableCell className="py-3 px-3 text-center">
                          <RiskBadge level={b.risk_level} />
                        </TableCell>

                        {/* AI Recommendation */}
                        <TableCell className="py-3 px-3 text-center">
                          <div className="inline-flex flex-col items-center">
                            {(b as any).recommendation ? (
                              <RecommendationBadge rec={(b as any).recommendation} />
                            ) : (
                              <span className="text-[11px] text-slate-400 font-mono">—</span>
                            )}
                            <span className="text-[9px] text-slate-400 mt-0.5">AI Advisory</span>
                          </div>
                        </TableCell>

                        {/* Officer Decision */}
                        <TableCell className="py-3 px-3 text-center">
                          <DecisionBadge decision={b.officer_decision} />
                        </TableCell>

                        {/* Submission Status */}
                        <TableCell className="py-3 px-3 text-center">
                          <BidStatusBadge status={b.bid_status} />
                        </TableCell>

                        {/* Action */}
                        <TableCell className="py-3 px-3 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => navigate(`/app/bids/${b.bid_id}`)}
                            className="border-slate-300 text-blue-900 hover:bg-blue-50 text-xs font-medium h-7 px-2.5 shadow-2xs"
                          >
                            Open Dossier
                            <ChevronRight className="ml-1 h-3 w-3" />
                          </Button>
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
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Tender Action History &amp; Hash-Chain
                  </h3>
                  <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  Every document processing event, rule evaluation, risk score, and officer decision is cryptographically anchored.
                </p>
              </div>
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-800 bg-emerald-50 px-2.5 py-0.5 rounded border border-emerald-200">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
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
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <Table>
                  <TableHeader>
                    <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                      <TableHead className="py-2.5 px-3">Timestamp</TableHead>
                      <TableHead className="py-2.5 px-3">Actor</TableHead>
                      <TableHead className="py-2.5 px-3">Action</TableHead>
                      <TableHead className="py-2.5 px-3">Bidder / Target</TableHead>
                      <TableHead className="py-2.5 px-3">Outcome / Signature</TableHead>
                    </tr>
                  </TableHeader>
                  <TableBody>
                    {(auditQuery.data ?? []).map((e: AuditLog) => (
                      <TableRow key={e.id} className="hover:bg-slate-50/60 text-xs">
                        <TableCell className="py-2.5 px-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                          {formatDateTime(e.timestamp)}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 font-medium text-slate-900">
                          {e.user_name ?? 'System Engine'}
                        </TableCell>
                        <TableCell className="py-2.5 px-3 font-semibold text-slate-800">
                          <span className="rounded bg-slate-100 px-2 py-0.5 text-[10.5px] border border-slate-200">
                            {labelize(e.action)}
                          </span>
                        </TableCell>
                        <TableCell className="py-2.5 px-3 text-slate-700 max-w-[200px] truncate">
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
        <DialogContent className="max-w-md bg-white">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 font-serif">
              Register Participating Bidder
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600">
              Add a new participating enterprise bidder to Tender #{detail?.tender.tender_number}.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleRegisterBidder}>
            <DialogBody className="space-y-3.5 pt-2">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
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
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
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
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
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
                <label className="block text-xs font-semibold text-slate-700 mb-1">
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
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
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
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
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
    </div>
  );
}
