import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  Filter,
  Plus,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
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
import { dashboardApi, tendersApi, auditApi, verificationApi, reportsApi } from '../lib/api';
import { Button } from '../components/ui/button';
import { useToast } from '../components/ui/toaster';
import { useAuth } from '../context/AuthContext';
import { formatDate, formatDateTime, labelize } from '../lib/utils';
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

  // Officer inbox: non-intrusive "new verification report" notification.
  // Shown once per session; opening the report marks it read.
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

    // Check tenders for high risk bidders or pending reviews
    for (const tender of tenders) {
      if (tender.high_risk_count > 0) {
        items.push({
          id: `tender-risk-${tender.id}`,
          severity: 'CRITICAL',
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

    // Default item if none
    if (items.length === 0) {
      items.push({
        id: 'no-critical',
        severity: 'LOW',
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
            <Button
              size="sm"
              onClick={() => navigate('/app/tenders/create')}
              className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium shadow-xs"
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Create Tender
            </Button>
          </div>
        </div>
      </div>

      {/* 2. Top Metric Blocks: Information-dense institutional design */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {/* Total Tenders */}
        <div className="rounded-md border border-slate-200 bg-white p-3.5 shadow-xs">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Total Tenders</span>
            <FileText className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-tight text-slate-900 font-mono">
              {metrics.total_tenders}
            </span>
            <span className="text-[11px] text-slate-500">records</span>
          </div>
          <p className="mt-1 text-[10.5px] text-slate-500 truncate">
            {metrics.active_tenders} currently published
          </p>
        </div>

        {/* Active Tenders */}
        <div className="rounded-md border border-slate-200 bg-white p-3.5 shadow-xs">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Active Tenders</span>
            <Activity className="h-4 w-4 text-blue-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-tight text-blue-900 font-mono">
              {metrics.active_tenders}
            </span>
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
          </div>
          <p className="mt-1 text-[10.5px] text-slate-500 truncate">Open for bid submissions</p>
        </div>

        {/* Total Bids Evaluated */}
        <div className="rounded-md border border-slate-200 bg-white p-3.5 shadow-xs">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Bids Evaluated</span>
            <Users className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-tight text-slate-900 font-mono">
              {metrics.total_bids}
            </span>
            <span className="text-[11px] text-slate-500">participating</span>
          </div>
          <p className="mt-1 text-[10.5px] text-slate-500 truncate">
            {metrics.documents_processed} documents indexed
          </p>
        </div>

        {/* Average Compliance Score */}
        <div className="rounded-md border border-slate-200 bg-white p-3.5 shadow-xs">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Avg Compliance</span>
            <Scale className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-tight text-emerald-800 font-mono">
              {Math.round(metrics.avg_compliance_score)}%
            </span>
            <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1 rounded border border-emerald-200">
              Rule pass
            </span>
          </div>
          <p className="mt-1 text-[10.5px] text-slate-500 truncate">Across qualified bids</p>
        </div>

        {/* High-Risk Bids */}
        <div className="rounded-md border border-slate-200 bg-white p-3.5 shadow-xs">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold uppercase tracking-wider">High Risk Bids</span>
            <ShieldAlert className="h-4 w-4 text-amber-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span
              className={`text-2xl font-bold tracking-tight font-mono ${
                metrics.high_risk_bids > 0 ? 'text-rose-700' : 'text-slate-900'
              }`}
            >
              {metrics.high_risk_bids}
            </span>
            {metrics.high_risk_bids > 0 && (
              <span className="text-[10px] font-semibold text-rose-700 bg-rose-50 px-1 rounded border border-rose-200">
                Action Req
              </span>
            )}
          </div>
          <p className="mt-1 text-[10.5px] text-slate-500 truncate">
            {metrics.verification_issues} statutory anomalies
          </p>
        </div>

        {/* Pending Officer Decisions */}
        <div className="rounded-md border border-slate-200 bg-white p-3.5 shadow-xs">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold uppercase tracking-wider">Pending Decisions</span>
            <Clock className="h-4 w-4 text-blue-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-tight text-slate-900 font-mono">
              {metrics.pending_reviews}
            </span>
            <span className="text-[11px] text-slate-500">awaiting</span>
          </div>
          <p className="mt-1 text-[10.5px] text-slate-500 truncate">Officer sign-off queue</p>
        </div>
      </div>

      {/* 3. CRITICAL SECTION: REQUIRES OFFICER ATTENTION */}
      <div className="rounded-lg border border-amber-300 bg-amber-50/40 p-4 shadow-xs">
        <div className="flex items-center justify-between border-b border-amber-200/80 pb-3">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-500 text-white shadow-xs">
              <AlertTriangle className="h-3.5 w-3.5" />
            </span>
            <div>
              <h2 className="text-sm font-bold text-amber-950 uppercase tracking-wide">
                Requires Officer Attention
              </h2>
              <p className="text-[11.5px] text-amber-900/80">
                Critical verification anomalies, statutory mismatches, and tenders awaiting final decision.
              </p>
            </div>
          </div>
          <span className="rounded bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-900 border border-amber-300">
            {attentionItems.length} Notice(s)
          </span>
        </div>

        <div className="mt-3 divide-y divide-amber-200/60">
          {attentionItems.map((item) => (
            <div key={item.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-2.5">
              <div className="flex items-start gap-2.5 min-w-0">
                <span
                  className={`mt-0.5 inline-block h-2 w-2 rounded-full shrink-0 ${
                    item.severity === 'CRITICAL'
                      ? 'bg-rose-600 ring-2 ring-rose-400/30'
                      : item.severity === 'HIGH'
                      ? 'bg-amber-600'
                      : 'bg-emerald-600'
                  }`}
                />
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-bold text-slate-900">{item.title}</span>
                    <span className="rounded bg-white px-1.5 py-0.2 text-[10px] font-semibold text-slate-600 border border-slate-200">
                      {item.category}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-600 leading-relaxed">{item.description}</p>
                </div>
              </div>

              <Link
                to={item.to}
                className="inline-flex items-center gap-1 rounded bg-white px-2.5 py-1 text-xs font-semibold text-blue-900 border border-slate-300 hover:border-blue-400 hover:bg-blue-50 transition-colors shrink-0 shadow-2xs"
              >
                <span>{item.linkText}</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          ))}
        </div>
      </div>

      {/* 4. MAIN VISUALIZATIONS GRID */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Viz 1: Compliance Scores by Tender */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between border-b border-slate-200 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                  Compliance Distribution by Tender
                </h3>
                <SystemLayerTag layer="RULE_ENGINE" size="sm" />
              </div>
              <p className="mt-0.5 text-[11px] text-slate-500">
                Average deterministic rule score (%) per active procurement package
              </p>
            </div>
            <span className="text-[11px] font-mono text-slate-400">Deterministic</span>
          </div>

          <div className="mt-4 h-64 w-full">
            {charts?.tender_bidder_comparison && charts.tender_bidder_comparison.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={charts.tender_bidder_comparison} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                  <XAxis
                    dataKey="tender"
                    tick={{ fontSize: 10, fill: '#64748b' }}
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                  />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#64748b' }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      fontSize: '11px',
                    }}
                    formatter={(val: number) => [`${val}%`, 'Avg Score']}
                  />
                  <Bar dataKey="avg_score" fill="#1e40af" radius={[3, 3, 0, 0]} maxBarSize={40} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">
                No tender comparison data available
              </div>
            )}
          </div>
        </div>

        {/* Viz 2: Risk Profile Overview */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
          <div className="flex items-center justify-between border-b border-slate-200 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                  Risk Classification Profile
                </h3>
                <SystemLayerTag layer="AI_ASSISTED" size="sm" />
              </div>
              <p className="mt-0.5 text-[11px] text-slate-500">
                Independent AI-assisted risk signals evaluated against bidder history
              </p>
            </div>
            <span className="text-[11px] font-mono text-slate-400">Advisory</span>
          </div>

          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 items-center gap-4">
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
                      innerRadius={45}
                      outerRadius={70}
                      paddingAngle={3}
                    >
                      {charts.risk_distribution.map((entry) => (
                        <Cell
                          key={entry.level}
                          fill={RISK_COLOR_MAP[entry.level] ?? '#94a3b8'}
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
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-slate-400">
                  No risk data available
                </div>
              )}
            </div>

            {/* Risk Legend Breakdown */}
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
                Score and risk are computed independently. A 100% compliant bidder can still carry Critical risk (e.g. debarment).
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 5. STATUTORY VERIFICATION OVERVIEW MATRIX */}
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

      {/* 6. RECENT ACTIVITY TIMELINE (FROM AUDIT TRAIL) */}
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
