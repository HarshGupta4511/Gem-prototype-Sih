import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, Link } from 'react-router-dom';
import {
  Activity,
  AlertOctagon,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  FileCheck2,
  FileText,
  Filter,
  PieChart as PieChartIcon,
  Plus,
  RefreshCw,
  ShieldCheck,
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
import { dashboardApi, tendersApi, auditApi, verificationApi } from '../lib/api';
import { Button } from '../components/ui/button';
import { useMemo } from 'react';
import { formatDateTime, labelize } from '../lib/utils';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
import { useTheme } from '../context/ThemeContext';

const RISK_COLOR_MAP: Record<string, string> = {
  LOW: '#059669',
  MEDIUM: '#d97706',
  HIGH: '#ea580c',
  CRITICAL: '#dc2626',
};

export default function Dashboard() {
  const navigate = useNavigate();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  // Filter states
  const [selectedTenderForBids, setSelectedTenderForBids] = React.useState<string>('ALL');

  // Officer notifications live on the dedicated Notifications page; the
  // backend work queue remains available there. There is no report-inbox
  // notification flow anymore.

  // Queries
  const { data, isLoading, isError, isFetching: metricsFetching, refetch: refetchMetrics } = useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.get,
    staleTime: 30000,
  });

  const { data: tenders = [], isFetching: tendersFetching, refetch: refetchTenders } = useQuery({
    queryKey: ['tenders'],
    queryFn: tendersApi.list,
    staleTime: 30000,
  });

  const { data: recentAudits = [], isFetching: auditsFetching, refetch: refetchAudits } = useQuery({
    queryKey: ['audit-recent'],
    queryFn: () => auditApi.list({ limit: 8 }),
    staleTime: 30000,
  });

  // Verification adapters, read live from the backend registry so the
  // dashboard never shows an outdated hardcoded list. All are mock adapters.
  const { data: verifAdapters = [], isLoading: adaptersLoading } = useQuery({
    queryKey: ['verification-adapters'],
    queryFn: verificationApi.adapters,
    staleTime: 300000,
  });

  const metrics = data?.metrics;
  const charts = data?.charts;

  // Refresh reloads every data source rendered on this page.
  const refreshing = metricsFetching || tendersFetching || auditsFetching;
  const handleRefresh = () => {
    refetchMetrics();
    refetchTenders();
    refetchAudits();
  };

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
        <RefreshCw className="h-7 w-7 animate-spin text-blue-800 dark:text-blue-400" />
        <p className="text-sm font-medium text-slate-600 dark:text-slate-400">Loading procurement intelligence metrics...</p>
      </div>
    );
  }

  if (isError || !metrics) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-red-800 dark:border-red-900 dark:bg-red-950/60 dark:text-red-300">
        <AlertOctagon className="mx-auto h-8 w-8 text-red-600 dark:text-red-400" />
        <p className="mt-2 text-base font-semibold">Failed to load procurement dashboard</p>
        <p className="text-xs text-red-600 dark:text-red-400">Please verify API connection or try again.</p>
        <Button onClick={handleRefresh} variant="outline" size="sm" className="mt-4">
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 1. Procurement Command Center Header */}
      <div className="border-b border-slate-200 bg-white p-5 rounded-lg border shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 font-mono dark:text-blue-400">
                CPCL / GeM Operational Portal
              </span>
              <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-400 dark:border-emerald-800">
                Demo Session
              </span>
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 font-serif dark:text-slate-100">
              Procurement Overview
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
              Real-time bid compliance, verification status, and decision tracking.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800/70"
            >
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/app/documents')}
              className="border-blue-300 text-blue-900 hover:bg-blue-50 text-xs font-medium dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-950/60"
            >
              <FileCheck2 className="mr-1.5 h-3.5 w-3.5 text-blue-700 dark:text-blue-400" />
              Test Document
            </Button>
            {/* Create Tender — officer action (single-role app: always available) */}
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

      {/* 2. Top Metric Blocks (4-column grid: Total Tenders, Active Tenders, Bids Evaluated with Tender Dropdown, Pending Decisions) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1: Total Tenders */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-colors dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400">Total Tenders</span>
            <FileText className="h-4 w-4 text-slate-400 dark:text-slate-500" />
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-slate-900 font-mono dark:text-slate-100">
              {metrics.total_tenders}
            </span>
            <span className="text-xs text-slate-500 font-medium dark:text-slate-400">procurement dossiers</span>
          </div>
          <p className="mt-1.5 text-xs text-slate-500 flex items-center gap-1.5 dark:text-slate-400">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-600" />
            <span>{metrics.active_tenders} currently published &amp; open</span>
          </p>
        </div>

        {/* Metric 2: Active Tenders */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-colors dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400">Active Tenders</span>
            <Activity className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-emerald-800 font-mono dark:text-emerald-400">
              {metrics.active_tenders}
            </span>
            <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 border border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-400 dark:border-emerald-800">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live
            </span>
          </div>
          <p className="mt-1.5 text-xs text-slate-500 truncate dark:text-slate-400">
            Open for electronic bid submissions
          </p>
        </div>

        {/* Metric 3: Bids Evaluated (With Tender Selector Dropdown) */}
        <div className="rounded-lg border border-blue-200 bg-blue-50/20 p-4 shadow-xs hover:border-blue-300 transition-colors dark:border-blue-900 dark:bg-blue-950/30 dark:hover:border-blue-800">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-bold uppercase tracking-wider text-blue-900 dark:text-blue-300">
                Bids Evaluated
              </span>
              <Users className="h-3.5 w-3.5 text-blue-700 dark:text-blue-400" />
            </div>
            {selectedTenderObj && (
              <Link
                to={`/app/tenders/${selectedTenderObj.id}`}
                className="text-[11px] font-medium text-blue-700 hover:text-blue-900 hover:underline inline-flex items-center dark:text-blue-400 dark:hover:text-blue-300"
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
              className="w-full text-[11px] font-medium border border-blue-200 rounded px-2 py-1 bg-white text-blue-950 focus:outline-none focus:ring-1 focus:ring-blue-600 shadow-2xs cursor-pointer truncate dark:border-blue-800 dark:bg-slate-900 dark:text-blue-200"
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
            <span className="text-3xl font-bold tracking-tight text-blue-950 font-mono dark:text-blue-200">
              {selectedTenderObj ? selectedTenderObj.bidder_count : metrics.total_bids}
            </span>
            <span className="text-xs text-blue-900 font-medium dark:text-blue-300">
              {selectedTenderObj ? 'bids in this package' : 'total participating bids'}
            </span>
          </div>

          <p className="mt-1 text-[11px] text-slate-600 truncate dark:text-slate-400">
            {selectedTenderObj ? (
              <span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">{selectedTenderObj.department}</span>
                {' · '}
                <span className="text-slate-500 dark:text-slate-400">{selectedTenderObj.pending_reviews} pending reviews</span>
              </span>
            ) : (
              <span>{metrics.documents_processed} statutory documents indexed</span>
            )}
          </p>
        </div>

        {/* Metric 4: Pending Officer Decisions */}
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-colors dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700">
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400">Pending Decisions</span>
            <Clock className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          </div>
          <div className="mt-2.5 flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-slate-900 font-mono dark:text-slate-100">
              {metrics.pending_reviews}
            </span>
            <span className="text-xs text-amber-700 font-medium dark:text-amber-400">awaiting sign-off</span>
          </div>
          <p className="mt-1.5 text-xs text-slate-500 truncate dark:text-slate-400">
            Procurement Officer qualification queue
          </p>
        </div>
      </div>


      {/* 4. VISUALIZATIONS GRID (Tender Bid Volume & Bid Risk Profile) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Visual 1: Procurement Performance & Capacity Visualizer */}
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between dark:border-slate-800 dark:bg-slate-900">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
              <div>
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-blue-700 dark:text-blue-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                    Tender Bid Volume &amp; Capacity Matrix
                  </h3>
                  <SystemLayerTag layer="RULE_ENGINE" size="sm" />
                </div>
                <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                  Participating bidders and evaluation progress per tender package
                </p>
              </div>

            </div>

            {/* By Tender bid volume chart */}
            <div className="mt-4">
              <div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 mb-2 px-1 dark:text-slate-400">
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
                          <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#1e293b' : '#f1f5f9'} horizontal={false} />
                          <XAxis type="number" tick={{ fontSize: 10, fill: isDark ? '#cbd5e1' : '#64748b' }} allowDecimals={false} />
                          <YAxis
                            dataKey="name"
                            type="category"
                            tick={{ fontSize: 10, fill: isDark ? '#cbd5e1' : '#334155', fontWeight: 600 }}
                            width={110}
                          />
                          <Tooltip
                            content={({ active, payload }) => {
                              if (active && payload && payload.length) {
                                const d = payload[0].payload;
                                return (
                                  <div className="rounded-md border border-slate-300 bg-white p-2.5 shadow-md text-xs space-y-1 dark:border-slate-700 dark:bg-slate-900">
                                    <p className="font-bold text-slate-900 dark:text-slate-100">{d.name}</p>
                                    <p className="text-[11px] text-slate-600 truncate max-w-[200px] dark:text-slate-400">{d.title}</p>
                                    <div className="pt-1.5 border-t border-slate-100 flex items-center justify-between gap-4 dark:border-slate-800">
                                      <span className="text-slate-500 dark:text-slate-400">Total Bidders:</span>
                                      <span className="font-mono font-bold text-blue-900 dark:text-blue-300">{d.bidders}</span>
                                    </div>
                                    <div className="flex items-center justify-between gap-4">
                                      <span className="text-slate-500 dark:text-slate-400">Pending Reviews:</span>
                                      <span className="font-mono font-bold text-amber-700 dark:text-amber-400">{d.pending}</span>
                                    </div>
                                    <div className="flex items-center justify-between gap-4">
                                      <span className="text-slate-500 dark:text-slate-400">Status:</span>
                                      <span className="font-semibold text-slate-700 dark:text-slate-300">{labelize(d.status)}</span>
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
                      <div className="flex h-full items-center justify-center text-xs text-slate-400 dark:text-slate-500">
                        No tender comparison data available
                      </div>
                    )}
                  </div>
                </div>
            </div>
          </div>

          <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
            <span>Aggregated across {tenders.length} active procurement contracts</span>
            <Link to="/app/tenders" className="font-semibold text-blue-700 hover:underline dark:text-blue-400">
              View All Tenders →
            </Link>
          </div>
        </div>

        {/* Visual 2: Bid Risk Profile */}
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between dark:border-slate-800 dark:bg-slate-900">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
              <div>
                <div className="flex items-center gap-2">
                  <PieChartIcon className="h-4 w-4 text-emerald-700 dark:text-emerald-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                    Bid Risk Profile
                  </h3>
                  <SystemLayerTag layer="AI_ASSISTED" size="sm" />
                </div>
                <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                  Independent AI advisory risk classifications across evaluated bids
                </p>
              </div>
            </div>

            {/* Bid risk distribution chart */}
            <div className="mt-4">
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
                              // Dark mode: slate-800 surface so the tooltip stands
                              // out against the slate-900 card behind it.
                              backgroundColor: isDark ? '#1e293b' : '#ffffff',
                              border: isDark ? '1px solid #475569' : '1px solid #cbd5e1',
                              borderRadius: '6px',
                              fontSize: '11px',
                              color: isDark ? '#f1f5f9' : '#0f172a',
                            }}
                            // Recharts paints each tooltip item in the hovered
                            // segment's fill color by default (dark greens/reds
                            // that are unreadable on a dark surface). Override
                            // with theme text colors in dark mode only; light
                            // mode keeps its existing appearance.
                            labelStyle={
                              isDark
                                ? { color: '#f1f5f9', fontWeight: 600, margin: '0 0 4px' }
                                : undefined
                            }
                            itemStyle={isDark ? { color: '#e2e8f0' } : undefined}
                            formatter={(val: number) => [`${val} submissions`, 'Bids']}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-slate-400 dark:text-slate-500">
                        No risk data available
                      </div>
                    )}
                  </div>

                  {/* Structured Risk Legend */}
                  <div className="space-y-2 border-t sm:border-t-0 sm:border-l border-slate-100 pt-3 sm:pt-0 sm:pl-4 dark:border-slate-800">
                    {charts?.risk_distribution?.map((item) => (
                      <div key={item.level} className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span
                            className="h-2.5 w-2.5 rounded-full"
                            style={{ backgroundColor: RISK_COLOR_MAP[item.level] ?? '#94a3b8' }}
                          />
                          <span className="font-medium text-slate-700 dark:text-slate-300">{labelize(item.level)}</span>
                        </div>
                        <span className="font-mono font-bold text-slate-900 dark:text-slate-100">{item.count} bids</span>
                      </div>
                    ))}
                    <div className="mt-3 rounded border border-slate-200 bg-slate-50 p-2 text-[10.5px] text-slate-500 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-400">
                      Advisory classifications are independent of technical compliance scores.
                    </div>
                  </div>
                </div>
            </div>
          </div>

          <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500 dark:border-slate-800 dark:text-slate-400">
            <span>Cryptographic provenance secured by SHA-256 ledger</span>
            <Link to="/app/audit" className="font-semibold text-emerald-800 hover:underline dark:text-emerald-400">
              Inspect Audit Ledger →
            </Link>
          </div>
        </div>
      </div>

      {/* 5. STATUTORY VERIFICATION OVERVIEW MATRIX */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Statutory Verification Integration Status
              </h3>
              <SystemLayerTag layer="VERIFICATION" size="sm" />
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
              Government portal cross-referencing adapters for taxpayer, registration, and blacklisting status
            </p>
          </div>
          <span className="text-[11px] font-semibold text-blue-900 bg-blue-50 px-2 py-0.5 rounded border border-blue-200 dark:text-blue-300 dark:bg-blue-950/60 dark:border-blue-800">
            {verifAdapters.length} Government Sources Configured
          </span>
        </div>

        <div className="mt-3 overflow-x-auto">
          {adaptersLoading ? (
            <p className="py-6 text-center text-xs text-slate-500 dark:text-slate-400">
              Loading verification adapters…
            </p>
          ) : (
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-bold text-slate-600 uppercase tracking-wider dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-400">
                <th className="py-2.5 px-3">Statutory Source</th>
                <th className="py-2.5 px-3">Operational Mode</th>
                <th className="py-2.5 px-3">Adapter Code</th>
                <th className="py-2.5 px-3 text-right">Integrity Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700 dark:divide-slate-800 dark:text-slate-300">
              {verifAdapters.map((source) => (
                <tr key={source.source} className="hover:bg-slate-50/60 transition-colors dark:hover:bg-slate-800/70">
                  <td className="py-2 px-3 font-semibold text-slate-900 dark:text-slate-100">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4 text-blue-700 shrink-0 dark:text-blue-400" />
                      <span>{source.display_name}</span>
                    </div>
                  </td>
                  <td className="py-2 px-3">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700">
                      {source.mode}
                    </span>
                  </td>
                  <td className="py-2 px-3 font-mono text-[11px] text-slate-600 dark:text-slate-400">
                    {source.source}
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-400">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                      Mocked
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          )}
        </div>
      </div>

      {/* 6. RECENT ACTIVITY TIMELINE (FROM AUDIT TRAIL) */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-200 pb-3 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Statutory Audit Trail (Recent Activity)
              </h3>
              <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
              SHA-256 hash-chained audit ledger — run “Verify Chain” on the Audit Trail page to re-check integrity.
            </p>
          </div>
          <Link
            to="/app/audit"
            className="text-xs font-semibold text-blue-700 hover:text-blue-900 hover:underline inline-flex items-center gap-1 dark:text-blue-400 dark:hover:text-blue-300"
          >
            <span>Full Audit Trail</span>
            <ExternalLink className="h-3 w-3" />
          </Link>
        </div>

        <div className="mt-3 overflow-x-auto">
          {recentAudits.length > 0 ? (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-400">
                  <th className="py-2 px-3">Timestamp</th>
                  <th className="py-2 px-3">Actor</th>
                  <th className="py-2 px-3">Action</th>
                  <th className="py-2 px-3">Entity</th>
                  <th className="py-2 px-3 text-right">Hash Signature</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700 dark:divide-slate-800 dark:text-slate-300">
                {recentAudits.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/70">
                    <td className="py-2 px-3 font-mono text-[11px] text-slate-500 whitespace-nowrap dark:text-slate-400">
                      {formatDateTime(log.timestamp)}
                    </td>
                    <td className="py-2 px-3 font-medium text-slate-900 dark:text-slate-100">
                      {log.user_name || 'System Engine'}
                    </td>
                    <td className="py-2 px-3 font-semibold text-blue-950 dark:text-blue-200">
                      <span className="rounded bg-blue-50 px-2 py-0.5 text-[10.5px] border border-blue-200 text-blue-900 dark:bg-blue-950/60 dark:border-blue-800 dark:text-blue-300">
                        {labelize(log.action)}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-slate-600 dark:text-slate-400">
                      <span className="font-mono text-[11px]">{log.entity_type}</span>{' '}
                      <span className="text-slate-400 dark:text-slate-500">#{log.entity_id}</span>
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-[10px] text-slate-400 dark:text-slate-500">
                      {log.current_hash ? `${log.current_hash.slice(0, 10)}...` : 'GENESIS'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="py-8 text-center text-xs text-slate-400 dark:text-slate-500">
              No audit logs recorded yet.
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
