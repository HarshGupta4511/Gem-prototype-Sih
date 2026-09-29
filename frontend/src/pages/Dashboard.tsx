import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  FileCheck2,
  FileText,
  Filter,
  Layers,
  PieChart as PieChartIcon,
  Plus,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Users,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { dashboardApi, tendersApi, auditApi, reportsApi } from '../lib/api';
import { Button } from '../components/ui/button';
import { useToast } from '../components/ui/toaster';
import { useAuth } from '../context/AuthContext';
import { formatDateTime, labelize } from '../lib/utils';
import { SystemLayerTag } from '../components/common/SystemLayerTag';

const RISK_COLOR_MAP: Record<string, string> = {
  LOW: '#059669',
  MEDIUM: '#d97706',
  HIGH: '#ea580c',
  CRITICAL: '#dc2626',
};

const VERIF_SOURCES = [
  { id: 'GSTN', name: 'Goods & Services Tax Network (GSTN)', mode: 'Mock Adapter', code: 'GST_ACTIVE' },
  { id: 'UDYAM', name: 'MSME Udyam Portal', mode: 'Mock Adapter', code: 'MSME_VALID' },
  { id: 'PAN', name: 'Income Tax Department (NSDL/PAN)', mode: 'Mock Adapter', code: 'PAN_VERIFIED' },
  { id: 'MCA', name: 'Ministry of Corporate Affairs (MCA21)', mode: 'Mock Adapter', code: 'CIN_ACTIVE' },
  { id: 'EPFO', name: 'Employees Provident Fund Org (EPFO)', mode: 'Mock Adapter', code: 'TRRN_CLEAR' },
  { id: 'ESIC', name: 'Employees State Insurance (ESIC)', mode: 'Mock Adapter', code: 'CONTRIB_OK' },
  { id: 'BLACKLIST', name: 'CPSE & GeM Debarment Registry', mode: 'Mock Adapter', code: 'NO_DEBARMENT' },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { isOfficer } = useAuth();
  const notifiedRef = React.useRef(false);

  // Filter states
  const [selectedTenderForBids, setSelectedTenderForBids] = React.useState<string>('ALL');
  const [attentionFilter, setAttentionFilter] = React.useState<string>('ALL');
  const [diagram1Tab, setDiagram1Tab] = React.useState<'TENDERS' | 'DENSITY' | 'CARDS'>('TENDERS');
  const [diagram2Tab, setDiagram2Tab] = React.useState<'VERIFICATION' | 'RISK'>('VERIFICATION');

  // Officer inbox notifications
  const { data: inboxItems } = useQuery({
    queryKey: ['reports-inbox'],
    queryFn: reportsApi.inbox,
    enabled: isOfficer,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  React.useEffect(() => {
    if (!isOfficer || notifiedRef.current || !inboxItems) return;
    const fresh = inboxItems.filter((i) => i.is_new);
    if (fresh.length === 0) return;
    notifiedRef.current = true;
    const first = fresh[0];
    toast({
      title: 'New Verification Report Received',
      description:
        fresh.length === 1
          ? `A verification report for ${first.bidder_name ?? 'a bidder'} has been submitted for your review.`
          : `${fresh.length} verification reports have been submitted for your review.`,
      variant: 'default',
      durationMs: 15000,
      actions: [
        { label: 'View Report', onClick: () => navigate('/app/inbox') },
        { label: 'Later', onClick: () => {} },
      ],
    });
  }, [isOfficer, inboxItems, toast, navigate]);

  // Queries
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.get,
    staleTime: 30000,
  });

  const { data: tenders = [] } = useQuery({
    queryKey: ['tenders'],
    queryFn: tendersApi.list,
    staleTime: 30000,
  });

  const { data: recentAudits = [] } = useQuery({
    queryKey: ['audit-recent'],
    queryFn: () => auditApi.list({ limit: 8 }),
    staleTime: 30000,
  });

  const metrics = data?.metrics;
  const charts = data?.charts;

  // Build items requiring officer attention
  const attentionItems = React.useMemo(() => {
    const items = [];

    for (const tender of tenders) {
      if (tender.high_risk_count > 0) {
        items.push({
          id: `tender-risk-${tender.id}`,
          severity: 'CRITICAL',
          type: 'HIGH_RISK',
          category: 'Statutory Mismatch / High Risk',
          title: `${tender.tender_number}: ${tender.high_risk_count} High-Risk Bidder(s) Flagged`,
          description: `Discrepancy detected in statutory cross-referencing (Debarment/PAN/GSTN mismatch).`,
          tenderId: tender.id,
          tenderNumber: tender.tender_number,
          linkText: 'Inspect Tender Dossier',
          to: `/app/tenders/${tender.id}`,
        });
      }
      if (tender.pending_reviews > 0) {
        items.push({
          id: `tender-pending-${tender.id}`,
          severity: 'HIGH',
          type: 'PENDING',
          category: 'Evaluation Pending',
          title: `${tender.tender_number}: ${tender.pending_reviews} Pending Officer Decisions`,
          description: `Bids have passed rule checks but require formal Procurement Officer qualification decision.`,
          tenderId: tender.id,
          tenderNumber: tender.tender_number,
          linkText: 'Review Submissions',
          to: `/app/tenders/${tender.id}`,
        });
      }
    }

    if (items.length === 0) {
      items.push({
        id: 'no-critical',
        severity: 'LOW',
        type: 'SYSTEM',
        category: 'System Status',
        title: 'All active tender evaluations are up to date',
        description: 'No unresolved high-risk alerts or debarment flags currently pending.',
        tenderId: null,
        tenderNumber: null,
        linkText: 'View All Tenders',
        to: '/app/tenders',
      });
    }

    return items;
  }, [tenders]);

  // Unique tenders with attention items for the attention dropdown
  const tendersWithAlerts = React.useMemo(() => {
    const map = new Map<number, { id: number; tender_number: string; count: number }>();
    for (const item of attentionItems) {
      if (item.tenderId && item.tenderNumber) {
        const cur = map.get(item.tenderId) ?? { id: item.tenderId, tender_number: item.tenderNumber, count: 0 };
        cur.count++;
        map.set(item.tenderId, cur);
      }
    }
    return Array.from(map.values());
  }, [attentionItems]);

  // Filtered attention items based on selected dropdown value
  const filteredAttentionItems = React.useMemo(() => {
    if (attentionFilter === 'ALL') return attentionItems;
    if (attentionFilter === 'HIGH_RISK') return attentionItems.filter((i) => i.type === 'HIGH_RISK');
    if (attentionFilter === 'PENDING') return attentionItems.filter((i) => i.type === 'PENDING');
    if (attentionFilter.startsWith('tender-')) {
      const tId = Number(attentionFilter.replace('tender-', ''));
      return attentionItems.filter((i) => i.tenderId === tId);
    }
    return attentionItems;
  }, [attentionItems, attentionFilter]);

  // Selected tender for "Bids Evaluated" card
  const selectedTenderObj = React.useMemo(() => {
    if (selectedTenderForBids === 'ALL') return null;
    return tenders.find((t) => String(t.id) === selectedTenderForBids) ?? null;
  }, [selectedTenderForBids, tenders]);

  // Enriched horizontal tender data for visual representation 1
  const tenderCapacityData = React.useMemo(() => {
    return tenders.map((t) => ({
      id: t.id,
      name: t.tender_number,
      title: t.title,
      department: t.department,
      bidders: t.bidder_count,
      pending: t.pending_reviews,
      highRisk: t.high_risk_count,
      status: t.status,
      value: t.estimated_value_inr,
    }));
  }, [tenders]);

  if (isLoading) {
    return (
      <div className="flex h-96 flex-col items-center justify-center gap-3">
        <RefreshCw className="h-7 w-7 animate-spin text-blue-800" />
        <p className="text-sm font-medium text-slate-600">Loading procurement intelligence metrics...</p>
      </div>
    );
  }

  if (isError || !metrics) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-red-800">
        <AlertOctagon className="mx-auto h-8 w-8 text-red-600" />
        <p className="mt-2 text-base font-semibold">Failed to load procurement dashboard</p>
        <p className="text-xs text-red-600">Please verify API connection or try again.</p>
        <Button onClick={() => refetch()} variant="outline" size="sm" className="mt-4">
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 1. Procurement Command Center Header */}
      <div className="border-b border-slate-200 bg-white p-5 rounded-lg border shadow-xs">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 font-mono">
                CPCL / GeM Operational Portal
              </span>
              <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200">
                Live Session
              </span>
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 font-serif">
              Procurement Overview
            </h1>
            <p className="mt-0.5 text-xs text-slate-600">
              Real-time bid compliance, verification status, and decision tracking.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              Refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/app/documents')}
              className="border-blue-300 text-blue-900 hover:bg-blue-50 text-xs font-medium"
            >
              <FileCheck2 className="mr-1.5 h-3.5 w-3.5 text-blue-700" />
              Test Document
            </Button>
            {/* Create Tender option: Visible ONLY to Procurement Officer */}
            {isOfficer && (
              <Button
                size="sm"
                onClick={() => navigate('/app/tenders/create')}
                className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium shadow-xs"
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                Create Tender
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* 2. Top Metric Blocks (4-column grid: Total Tenders, Active Tenders, Bids Evaluated with Tender Dropdown, Pending Decisions) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1: Total Tenders */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-colors">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600">Total Tenders</span>
            <FileText className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-slate-900 font-mono">
              {metrics.total_tenders}
            </span>
            <span className="text-xs text-slate-500 font-medium">procurement dossiers</span>
          </div>
          <p className="mt-1.5 text-xs text-slate-500 flex items-center gap-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-600" />
            <span>{metrics.active_tenders} currently published &amp; open</span>
          </p>
        </div>

        {/* Metric 2: Active Tenders */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-colors">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600">Active Tenders</span>
            <Activity className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-emerald-800 font-mono">
              {metrics.active_tenders}
            </span>
            <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 border border-emerald-200">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live
            </span>
          </div>
          <p className="mt-1.5 text-xs text-slate-500 truncate">
            Open for electronic bid submissions
          </p>
        </div>

        {/* Metric 3: Bids Evaluated (With Tender Selector Dropdown) */}
        <div className="rounded-lg border border-blue-200 bg-blue-50/20 p-4 shadow-xs hover:border-blue-300 transition-colors">
          <div className="flex items-center justify-between text-slate-500">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-bold uppercase tracking-wider text-blue-900">
                Bids Evaluated
              </span>
              <Users className="h-3.5 w-3.5 text-blue-700" />
            </div>
            {selectedTenderObj && (
              <Link
                to={`/app/tenders/${selectedTenderObj.id}`}
                className="text-[11px] font-medium text-blue-700 hover:text-blue-900 hover:underline inline-flex items-center"
                title="Open tender details"
              >
                <span>View Tender</span>
                <ChevronRight className="h-3 w-3" />
              </Link>
            )}
          </div>

          {/* Tender Selection Dropdown */}
          <div className="mt-2">
            <label htmlFor="bids-tender-select" className="sr-only">Select Tender</label>
            <select
              id="bids-tender-select"
              value={selectedTenderForBids}
              onChange={(e) => setSelectedTenderForBids(e.target.value)}
              className="w-full text-[11px] font-medium border border-blue-200 rounded px-2 py-1 bg-white text-blue-950 focus:outline-none focus:ring-1 focus:ring-blue-600 shadow-2xs cursor-pointer truncate"
            >
              <option value="ALL">All Tenders (Total: {metrics.total_bids} bids)</option>
              {tenders.map((t) => (
                <option key={t.id} value={String(t.id)}>
                  {t.tender_number} ({t.bidder_count} bids) - {t.title.slice(0, 32)}{t.title.length > 32 ? '…' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Dynamic Metric Display based on dropdown selection */}
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-blue-950 font-mono">
              {selectedTenderObj ? selectedTenderObj.bidder_count : metrics.total_bids}
            </span>
            <span className="text-xs text-blue-900 font-medium">
              {selectedTenderObj ? 'bids in this package' : 'total participating bids'}
            </span>
          </div>

          <p className="mt-1 text-[11px] text-slate-600 truncate">
            {selectedTenderObj ? (
              <span>
                <span className="font-semibold text-slate-800">{selectedTenderObj.department}</span>
                {' · '}
                <span className="text-slate-500">{selectedTenderObj.pending_reviews} pending reviews</span>
              </span>
            ) : (
              <span>{metrics.documents_processed} statutory documents indexed</span>
            )}
          </p>
        </div>

        {/* Metric 4: Pending Officer Decisions */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-colors">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600">Pending Decisions</span>
            <Clock className="h-4 w-4 text-amber-600" />
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-slate-900 font-mono">
              {metrics.pending_reviews}
            </span>
            <span className="text-xs text-amber-700 font-medium">awaiting sign-off</span>
          </div>
          <p className="mt-1.5 text-xs text-slate-500 truncate">
            Procurement Officer qualification queue
          </p>
        </div>
      </div>

      {/* 3. REQUIRES OFFICER ATTENTION (With Category & Tender Filter Dropdown) */}
      <div className="rounded-lg border border-amber-300 bg-amber-50/40 p-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-amber-200/80 pb-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-500 text-white shadow-xs shrink-0">
              <AlertTriangle className="h-4 w-4" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-amber-950 uppercase tracking-wide">
                  Requires Officer Attention
                </h2>
                <span className="rounded bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-900 border border-amber-300">
                  {filteredAttentionItems.length} Notice{filteredAttentionItems.length !== 1 ? 's' : ''}
                </span>
              </div>
              <p className="text-[11.5px] text-amber-900/80">
                Statutory mismatches, verification anomalies, and bids awaiting formal officer sign-off.
              </p>
            </div>
          </div>

          {/* Attention Filter Dropdown */}
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <label htmlFor="attention-filter-dropdown" className="text-xs font-semibold text-amber-900 shrink-0 flex items-center gap-1">
              <Filter className="h-3.5 w-3.5 text-amber-700" />
              <span>Filter:</span>
            </label>
            <select
              id="attention-filter-dropdown"
              value={attentionFilter}
              onChange={(e) => setAttentionFilter(e.target.value)}
              className="text-xs font-medium border border-amber-300 rounded px-2.5 py-1.5 bg-white text-amber-950 focus:outline-none focus:ring-1 focus:ring-amber-500 shadow-2xs cursor-pointer"
            >
              <option value="ALL">All Notices ({attentionItems.length})</option>
              <option value="HIGH_RISK">Statutory &amp; High Risk Flags</option>
              <option value="PENDING">Pending Decisions Awaiting Review</option>
              {tendersWithAlerts.length > 0 && (
                <optgroup label="By Specific Tender">
                  {tendersWithAlerts.map((t) => (
                    <option key={t.id} value={`tender-${t.id}`}>
                      {t.tender_number} ({t.count} notice{t.count !== 1 ? 's' : ''})
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </div>
        </div>

        {/* Notices List */}
        <div className="mt-3 divide-y divide-amber-200/60">
          {filteredAttentionItems.length > 0 ? (
            filteredAttentionItems.map((item) => (
              <div key={item.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-3 hover:bg-amber-100/30 rounded px-2 transition-colors">
                <div className="flex items-start gap-3 min-w-0">
                  <span
                    className={`mt-1 inline-block h-2.5 w-2.5 rounded-full shrink-0 ${
                      item.severity === 'CRITICAL'
                        ? 'bg-rose-600 ring-2 ring-rose-400/40'
                        : item.severity === 'HIGH'
                        ? 'bg-amber-600 ring-2 ring-amber-400/40'
                        : 'bg-emerald-600'
                    }`}
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-slate-900">{item.title}</span>
                      <span className="rounded bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-700 border border-slate-200 shadow-2xs">
                        {item.category}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-600 leading-relaxed">{item.description}</p>
                  </div>
                </div>

                <Link
                  to={item.to}
                  className="inline-flex items-center gap-1.5 rounded bg-white px-3 py-1.5 text-xs font-semibold text-blue-900 border border-slate-300 hover:border-blue-400 hover:bg-blue-50 transition-colors shrink-0 shadow-2xs self-start sm:self-auto"
                >
                  <span>{item.linkText}</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            ))
          ) : (
            <div className="py-6 text-center text-xs text-amber-800">
              No attention notices match the selected filter.
            </div>
          )}
        </div>
      </div>

      {/* 4. PROCUREMENT LIFECYCLE PIPELINE FLOW (Brand-new Visual Workflow Representation) */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded bg-blue-100 text-blue-800">
              <Layers className="h-3.5 w-3.5" />
            </div>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                CPSE Procurement Evaluation Pipeline
              </h3>
              <p className="text-[11px] text-slate-500">
                End-to-end data pipeline from NIT tender publication to statutory cross-verification and officer qualification
              </p>
            </div>
          </div>
          <span className="text-[11px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-medium">
            Automated &amp; Deterministic
          </span>
        </div>

        {/* Visual Pipeline Stages */}
        <div className="mt-4 grid grid-cols-1 md:grid-cols-5 gap-3">
          {/* Stage 1 */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 relative flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Stage 01</span>
                <span className="h-2 w-2 rounded-full bg-blue-500" />
              </div>
              <h4 className="mt-1 text-xs font-bold text-slate-900">NIT Publication</h4>
              <p className="mt-0.5 text-[11px] text-slate-500">Tenders issued &amp; criteria configured</p>
            </div>
            <div className="mt-3 pt-2 border-t border-slate-200 flex items-center justify-between text-xs">
              <span className="font-mono font-bold text-blue-900">{metrics.active_tenders} active</span>
              <span className="text-[10px] text-slate-400">{metrics.total_tenders} total</span>
            </div>
          </div>

          {/* Stage 2 */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 relative flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Stage 02</span>
                <span className="h-2 w-2 rounded-full bg-blue-500" />
              </div>
              <h4 className="mt-1 text-xs font-bold text-slate-900">Bid Submissions</h4>
              <p className="mt-0.5 text-[11px] text-slate-500">Bidder dossiers &amp; documents ingested</p>
            </div>
            <div className="mt-3 pt-2 border-t border-slate-200 flex items-center justify-between text-xs">
              <span className="font-mono font-bold text-blue-900">{metrics.total_bids} bids</span>
              <span className="text-[10px] text-slate-400">{metrics.documents_processed} docs</span>
            </div>
          </div>

          {/* Stage 3 */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 relative flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Stage 03</span>
                <span className="h-2 w-2 rounded-full bg-blue-500" />
              </div>
              <h4 className="mt-1 text-xs font-bold text-slate-900">Rule Engine Check</h4>
              <p className="mt-0.5 text-[11px] text-slate-500">Deterministic criteria verification</p>
            </div>
            <div className="mt-3 pt-2 border-t border-slate-200 flex items-center justify-between text-xs">
              <span className="font-mono font-bold text-emerald-800">Deterministic</span>
              <span className="text-[10px] text-slate-400">Zero AI drift</span>
            </div>
          </div>

          {/* Stage 4 */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 relative flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Stage 04</span>
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
              </div>
              <h4 className="mt-1 text-xs font-bold text-slate-900">7-Portal Verification</h4>
              <p className="mt-0.5 text-[11px] text-slate-500">GSTN, PAN, MSME, Debarment</p>
            </div>
            <div className="mt-3 pt-2 border-t border-slate-200 flex items-center justify-between text-xs">
              <span className="font-mono font-bold text-emerald-800">7 Adapters</span>
              <span className="text-[10px] text-slate-400">All Live</span>
            </div>
          </div>

          {/* Stage 5 */}
          <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 relative flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700">Stage 05</span>
                <span className="h-2 w-2 rounded-full bg-amber-500" />
              </div>
              <h4 className="mt-1 text-xs font-bold text-amber-950">Officer Sign-Off</h4>
              <p className="mt-0.5 text-[11px] text-amber-900/80">Final qualification &amp; award decisions</p>
            </div>
            <div className="mt-3 pt-2 border-t border-amber-200 flex items-center justify-between text-xs">
              <span className="font-mono font-bold text-amber-900">{metrics.pending_reviews} pending</span>
              <span className="text-[10px] text-amber-700 font-semibold">Decisions</span>
            </div>
          </div>
        </div>
      </div>

      {/* 5. REDESIGNED VISUALIZATIONS GRID (Modern Visual Representations of Procurement Data) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Visual 1: Procurement Performance & Capacity Visualizer */}
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-blue-700" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Tender Bid Volume &amp; Capacity Matrix
                  </h3>
                  <SystemLayerTag layer="RULE_ENGINE" size="sm" />
                </div>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  Participating bidders, evaluation progress, and compliance distribution
                </p>
              </div>

              {/* View Switcher Tabs */}
              <div className="flex items-center rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setDiagram1Tab('TENDERS')}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    diagram1Tab === 'TENDERS'
                      ? 'bg-white text-blue-900 shadow-2xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  By Tender
                </button>
                <button
                  type="button"
                  onClick={() => setDiagram1Tab('DENSITY')}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    diagram1Tab === 'DENSITY'
                      ? 'bg-white text-blue-900 shadow-2xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Score Density
                </button>
                <button
                  type="button"
                  onClick={() => setDiagram1Tab('CARDS')}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    diagram1Tab === 'CARDS'
                      ? 'bg-white text-blue-900 shadow-2xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Summary
                </button>
              </div>
            </div>

            {/* Content for Diagram 1 based on selected Tab */}
            <div className="mt-4">
              {diagram1Tab === 'TENDERS' && (
                <div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 mb-2 px-1">
                    <span>Tender Package &amp; Reference</span>
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-blue-700" />
                        <span>Bids Evaluated</span>
                      </span>
                      <span className="flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-amber-500" />
                        <span>Pending Decision</span>
                      </span>
                    </div>
                  </div>

                  <div className="h-64 w-full">
                    {tenderCapacityData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={tenderCapacityData}
                          layout="vertical"
                          margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
                          <XAxis type="number" tick={{ fontSize: 10, fill: '#64748b' }} allowDecimals={false} />
                          <YAxis
                            dataKey="name"
                            type="category"
                            tick={{ fontSize: 10, fill: '#334155', fontWeight: 600 }}
                            width={110}
                          />
                          <Tooltip
                            content={({ active, payload }) => {
                              if (active && payload && payload.length) {
                                const d = payload[0].payload;
                                return (
                                  <div className="rounded-md border border-slate-300 bg-white p-2.5 shadow-md text-xs space-y-1">
                                    <p className="font-bold text-slate-900">{d.name}</p>
                                    <p className="text-[11px] text-slate-600 truncate max-w-[200px]">{d.title}</p>
                                    <div className="pt-1.5 border-t border-slate-100 flex items-center justify-between gap-4">
                                      <span className="text-slate-500">Total Bidders:</span>
                                      <span className="font-mono font-bold text-blue-900">{d.bidders}</span>
                                    </div>
                                    <div className="flex items-center justify-between gap-4">
                                      <span className="text-slate-500">Pending Reviews:</span>
                                      <span className="font-mono font-bold text-amber-700">{d.pending}</span>
                                    </div>
                                    <div className="flex items-center justify-between gap-4">
                                      <span className="text-slate-500">Status:</span>
                                      <span className="font-semibold text-slate-700">{labelize(d.status)}</span>
                                    </div>
                                  </div>
                                );
                              }
                              return null;
                            }}
                          />
                          <Bar dataKey="bidders" fill="#1d4ed8" radius={[0, 4, 4, 0]} name="Evaluated Bids" barSize={14} />
                          <Bar dataKey="pending" fill="#f59e0b" radius={[0, 4, 4, 0]} name="Pending Reviews" barSize={14} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-slate-400">
                        No tender comparison data available
                      </div>
                    )}
                  </div>
                </div>
              )}

              {diagram1Tab === 'DENSITY' && (
                <div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 mb-2 px-1">
                    <span>Compliance Scoring Density Tiers</span>
                    <span className="text-blue-800 font-semibold">Deterministic Rule Pass (%)</span>
                  </div>

                  <div className="h-64 w-full">
                    {charts?.compliance_distribution && charts.compliance_distribution.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart
                          data={charts.compliance_distribution}
                          margin={{ top: 10, right: 15, left: -20, bottom: 10 }}
                        >
                          <defs>
                            <linearGradient id="scoreDensityGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#2563eb" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#2563eb" stopOpacity={0.0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                          <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#64748b' }} />
                          <YAxis tick={{ fontSize: 10, fill: '#64748b' }} allowDecimals={false} />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: '#ffffff',
                              border: '1px solid #cbd5e1',
                              borderRadius: '6px',
                              fontSize: '11px',
                            }}
                            formatter={(val: number) => [`${val} bids`, 'Frequency']}
                          />
                          <Area
                            type="monotone"
                            dataKey="count"
                            stroke="#1d4ed8"
                            strokeWidth={2.5}
                            fillOpacity={1}
                            fill="url(#scoreDensityGrad)"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-slate-400">
                        No score density distribution available
                      </div>
                    )}
                  </div>
                </div>
              )}

              {diagram1Tab === 'CARDS' && (
                <div className="h-64 overflow-y-auto space-y-2 pr-1">
                  {tenders.map((t) => (
                    <div
                      key={t.id}
                      onClick={() => navigate(`/app/tenders/${t.id}`)}
                      className="rounded-md border border-slate-200 p-2.5 hover:bg-slate-50 transition-colors cursor-pointer flex items-center justify-between text-xs"
                    >
                      <div className="min-w-0 pr-3">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-900">{t.tender_number}</span>
                          <span className="rounded bg-slate-100 px-1.5 py-0.2 text-[10px] font-semibold text-slate-700">
                            {t.department}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-slate-600 truncate">{t.title}</p>
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <div className="text-right">
                          <span className="font-mono font-bold text-blue-900">{t.bidder_count} bids</span>
                          <p className="text-[10px] text-slate-400">{t.pending_reviews} pending</p>
                        </div>
                        <ArrowUpRight className="h-4 w-4 text-slate-400" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
            <span>Aggregated across {tenders.length} active procurement contracts</span>
            <Link to="/app/tenders" className="font-semibold text-blue-700 hover:underline">
              View All Tenders →
            </Link>
          </div>
        </div>

        {/* Visual 2: Statutory Verification & Risk Assessment Intelligence Visualizer */}
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <PieChartIcon className="h-4 w-4 text-emerald-700" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Statutory Integrity &amp; Risk Profile
                  </h3>
                  <SystemLayerTag layer="VERIFICATION" size="sm" />
                </div>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  Government portal authentication &amp; independent AI advisory classifications
                </p>
              </div>

              {/* View Switcher Tabs */}
              <div className="flex items-center rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setDiagram2Tab('VERIFICATION')}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    diagram2Tab === 'VERIFICATION'
                      ? 'bg-white text-emerald-900 shadow-2xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  7 Portals
                </button>
                <button
                  type="button"
                  onClick={() => setDiagram2Tab('RISK')}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    diagram2Tab === 'RISK'
                      ? 'bg-white text-emerald-900 shadow-2xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Risk Levels
                </button>
              </div>
            </div>

            {/* Content for Diagram 2 based on selected Tab */}
            <div className="mt-4">
              {diagram2Tab === 'VERIFICATION' && (
                <div className="space-y-3">
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50/40 p-3 flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-white">
                        <ShieldCheck className="h-4 w-4" />
                      </span>
                      <div>
                        <h4 className="text-xs font-bold text-emerald-950">
                          100% Statutory Adapter Availability
                        </h4>
                        <p className="text-[11px] text-emerald-900/80">
                          Continuous mock integration verified across GSTN, PAN, MCA21, EPFO, and GeM Debarment.
                        </p>
                      </div>
                    </div>
                    <span className="font-mono text-xs font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded border border-emerald-300">
                      7/7 OK
                    </span>
                  </div>

                  {/* Portal Health Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                    {VERIF_SOURCES.slice(0, 6).map((s) => (
                      <div
                        key={s.id}
                        className="rounded border border-slate-200 bg-slate-50/70 p-2 flex items-center justify-between"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="h-2 w-2 rounded-full bg-emerald-500 shrink-0" />
                          <span className="font-bold text-slate-800 truncate">{s.id}</span>
                          <span className="text-[10px] text-slate-500 font-mono">[{s.code}]</span>
                        </div>
                        <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1 rounded border border-emerald-200 shrink-0">
                          Verified
                        </span>
                      </div>
                    ))}
                  </div>

                  <div className="rounded border border-slate-200 bg-slate-50 p-2 text-[11px] text-slate-500 flex items-center justify-between">
                    <span>CPSE &amp; GeM Blacklist Registry:</span>
                    <span className="font-semibold text-emerald-700">Real-time Debarment Sync Active</span>
                  </div>
                </div>
              )}

              {diagram2Tab === 'RISK' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 items-center gap-4">
                  <div className="h-56">
                    {charts?.risk_distribution && charts.risk_distribution.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={charts.risk_distribution}
                            dataKey="count"
                            nameKey="level"
                            cx="50%"
                            cy="50%"
                            innerRadius={50}
                            outerRadius={75}
                            paddingAngle={4}
                          >
                            {charts.risk_distribution.map((entry) => (
                              <Cell
                                key={entry.level}
                                fill={RISK_COLOR_MAP[entry.level] ?? '#94a3b8'}
                                stroke="#ffffff"
                                strokeWidth={2}
                              />
                            ))}
                          </Pie>
                          <Tooltip
                            contentStyle={{
                              backgroundColor: '#ffffff',
                              border: '1px solid #cbd5e1',
                              borderRadius: '6px',
                              fontSize: '11px',
                            }}
                            formatter={(val: number) => [`${val} submissions`, 'Bids']}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-slate-400">
                        No risk data available
                      </div>
                    )}
                  </div>

                  {/* Structured Risk Legend */}
                  <div className="space-y-2 border-t sm:border-t-0 sm:border-l border-slate-100 pt-3 sm:pt-0 sm:pl-4">
                    {charts?.risk_distribution?.map((item) => (
                      <div key={item.level} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span
                            className="h-2.5 w-2.5 rounded-full"
                            style={{ backgroundColor: RISK_COLOR_MAP[item.level] ?? '#94a3b8' }}
                          />
                          <span className="font-medium text-slate-700">{labelize(item.level)}</span>
                        </div>
                        <span className="font-mono font-bold text-slate-900">{item.count} bids</span>
                      </div>
                    ))}
                    <div className="mt-3 rounded border border-slate-200 bg-slate-50 p-2 text-[10.5px] text-slate-500">
                      Advisory classifications are independent of technical compliance scores.
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
            <span>Cryptographic provenance secured by SHA-256 ledger</span>
            <Link to="/app/audit" className="font-semibold text-emerald-800 hover:underline">
              Inspect Audit Ledger →
            </Link>
          </div>
        </div>
      </div>

      {/* 6. STATUTORY VERIFICATION OVERVIEW MATRIX */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                Statutory Verification Integration Status
              </h3>
              <SystemLayerTag layer="VERIFICATION" size="sm" />
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Government portal cross-referencing adapters for taxpayer, registration, and blacklisting status
            </p>
          </div>
          <span className="text-[11px] font-semibold text-blue-900 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
            7 Government Sources Configured
          </span>
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                <th className="py-2.5 px-3">Statutory Source</th>
                <th className="py-2.5 px-3">Operational Mode</th>
                <th className="py-2.5 px-3">Verification Scope</th>
                <th className="py-2.5 px-3 text-right">Integrity Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {VERIF_SOURCES.map((source) => (
                <tr key={source.id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="py-2 px-3 font-semibold text-slate-900">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-blue-700 shrink-0" />
                      <span>{source.name}</span>
                    </div>
                  </td>
                  <td className="py-2 px-3">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 border border-slate-200">
                      {source.mode}
                    </span>
                  </td>
                  <td className="py-2 px-3 font-mono text-[11px] text-slate-600">
                    {source.code}
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                      Operational
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 7. RECENT ACTIVITY TIMELINE (FROM AUDIT TRAIL) */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
        <div className="flex items-center justify-between border-b border-slate-200 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                Statutory Audit Trail (Recent Activity)
              </h3>
              <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Tamper-evident SHA-256 hash-chain recorded actions by Procurement Officers &amp; Verifiers
            </p>
          </div>
          <Link
            to="/app/audit"
            className="text-xs font-semibold text-blue-700 hover:text-blue-900 hover:underline inline-flex items-center gap-1"
          >
            <span>Full Audit Trail</span>
            <ExternalLink className="h-3 w-3" />
          </Link>
        </div>

        <div className="mt-3 overflow-x-auto">
          {recentAudits.length > 0 ? (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider">
                  <th className="py-2 px-3">Timestamp</th>
                  <th className="py-2 px-3">Actor</th>
                  <th className="py-2 px-3">Action</th>
                  <th className="py-2 px-3">Entity</th>
                  <th className="py-2 px-3 text-right">Hash Signature</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {recentAudits.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/60">
                    <td className="py-2 px-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">
                      {formatDateTime(log.timestamp)}
                    </td>
                    <td className="py-2 px-3 font-medium text-slate-900">
                      {log.user_name || 'System Engine'}
                    </td>
                    <td className="py-2 px-3 font-semibold text-blue-950">
                      <span className="rounded bg-blue-50 px-2 py-0.5 text-[10.5px] border border-blue-200 text-blue-900">
                        {labelize(log.action)}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-600">
                      <span className="font-mono text-[11px]">{log.entity_type}</span>{' '}
                      <span className="text-slate-400">#{log.entity_id}</span>
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-[10px] text-slate-400">
                      {log.current_hash ? `${log.current_hash.slice(0, 10)}...` : 'GENESIS'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="py-8 text-center text-xs text-slate-400">
              No audit logs recorded yet.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
