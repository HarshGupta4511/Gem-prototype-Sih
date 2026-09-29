import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Building2,
  Calendar,
  ChevronRight,
  Eye,
  Filter,
  Layers,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react';
import { tendersApi } from '../lib/api';
import { formatDate } from '../lib/utils';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { EmptyState, LoadingBlock } from '../components/common/ui-helpers';
import TenderWizard from '../components/tenders/TenderWizard';
import { SystemLayerTag } from '../components/common/SystemLayerTag';

function formatCurrencyINR(val?: number | null) {
  if (!val) return '—';
  if (val >= 10000000) {
    return `₹${(val / 10000000).toFixed(2)} Cr`;
  }
  if (val >= 100000) {
    return `₹${(val / 100000).toFixed(2)} Lakh`;
  }
  return `₹${val.toLocaleString('en-IN')}`;
}

export default function Tenders() {
  const { canDecide } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['tenders'],
    queryFn: tendersApi.list,
  });

  const filtered = useMemo(() => {
    let result = data;
    const q = search.trim().toLowerCase();
    if (q) {
      result = result.filter(
        (t) =>
          t.title.toLowerCase().includes(q) ||
          t.tender_number.toLowerCase().includes(q) ||
          t.department.toLowerCase().includes(q)
      );
    }
    if (statusFilter !== 'ALL') {
      result = result.filter((t) => t.status === statusFilter);
    }
    return result;
  }, [data, search, statusFilter]);

  const handleCreated = () => {
    queryClient.invalidateQueries({ queryKey: ['tenders'] });
  };

  return (
    <div className="space-y-5">
      {/* Header section */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 font-mono">
                Procurement Registry
              </span>
              <SystemLayerTag layer="RULE_ENGINE" size="sm" />
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 font-serif">
              Tenders
            </h1>
            <p className="mt-0.5 text-xs text-slate-600">
              Manage procurement tenders and evaluate participating bidders against statutory &amp; technical requirements.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
            >
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
              Refresh
            </Button>
            {canDecide && (
              <Button
                size="sm"
                onClick={() => navigate('/app/tenders/create')}
                className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-semibold shadow-xs"
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                Create Tender
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Search and Filter Panel */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="relative flex-1 max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by tender reference, package title, or department…"
              className="pl-9 text-xs border-slate-300 focus:border-blue-600"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500">
              <Filter className="h-3.5 w-3.5" />
              <span>Status:</span>
            </div>
            {['ALL', 'OPEN', 'DRAFT', 'CLOSED'].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`rounded px-2.5 py-1 text-xs font-medium border transition-colors ${
                  statusFilter === st
                    ? 'bg-blue-900 text-white border-blue-900 shadow-2xs'
                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                }`}
              >
                {st === 'ALL' ? 'All Tenders' : st}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Official Registry Table */}
      <div className="rounded-lg border border-slate-200 bg-white shadow-xs overflow-hidden">
        {isLoading ? (
          <div className="p-6">
            <LoadingBlock rows={6} />
          </div>
        ) : isError ? (
          <div className="p-8 text-center">
            <EmptyState
              title="Could not load tenders registry"
              description="The procurement registry could not be fetched. Check server status and try again."
              action={
                <Button onClick={() => refetch()} size="sm" variant="outline">
                  Retry
                </Button>
              }
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center">
            <EmptyState
              title={data.length > 0 ? 'No matching tenders found' : 'No tenders created yet'}
              description={
                data.length > 0
                  ? 'Adjust your search query or status filter.'
                  : 'Publish your first tender to start bidder evaluation.'
              }
              action={
                canDecide && data.length === 0 ? (
                  <Button onClick={() => setDialogOpen(true)} size="sm">
                    <Plus className="mr-1.5 h-4 w-4" />
                    Create First Tender
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                  <TableHead className="py-3 px-4 font-bold text-slate-700">Tender Reference</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700">Title &amp; Department</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700 text-right">Estimated Value</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700 text-center">Bidders</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700 text-center">Avg Compliance</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700 text-center">Risk Alerts</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700">Closing Date</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700">Status</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700 text-right">Action</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {filtered.map((t) => (
                  <TableRow
                    key={t.id}
                    className="hover:bg-blue-50/40 transition-colors border-b border-slate-100 group"
                  >
                    {/* Tender Number */}
                    <TableCell className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-blue-600 shrink-0" />
                        <div>
                          <span
                            onClick={() => navigate(`/app/tenders/${t.id}`)}
                            className="font-mono text-xs font-bold text-blue-900 hover:text-blue-700 hover:underline cursor-pointer"
                          >
                            {t.tender_number}
                          </span>
                          <span className="block text-[10px] text-slate-500 font-mono">
                            {t.tender_type || 'OPEN'} • {t.bid_type || 'TWO_PACKET'}
                          </span>
                        </div>
                      </div>
                    </TableCell>

                    {/* Title & Department */}
                    <TableCell className="py-3 px-4 max-w-sm">
                      <p className="truncate text-xs font-semibold text-slate-900 group-hover:text-blue-950">
                        {t.title}
                      </p>
                      <p className="truncate text-[10.5px] text-slate-500 flex items-center gap-1 mt-0.5">
                        <Building2 className="h-3 w-3 text-slate-400 shrink-0" />
                        <span>{t.department}</span>
                      </p>
                    </TableCell>

                    {/* Estimated Value */}
                    <TableCell className="py-3 px-4 text-right font-mono text-xs font-semibold text-slate-800">
                      {formatCurrencyINR(t.estimated_value_inr)}
                    </TableCell>

                    {/* Bidders */}
                    <TableCell className="py-3 px-4 text-center">
                      <span className="inline-flex items-center gap-1 font-mono text-xs font-medium text-slate-700 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                        <Layers className="h-3 w-3 text-slate-500" />
                        {t.bidder_count}
                      </span>
                    </TableCell>

                    {/* Avg Compliance */}
                    <TableCell className="py-3 px-4 text-center">
                      {t.avg_compliance !== null && t.avg_compliance !== undefined ? (
                        <div className="inline-flex items-center gap-1">
                          <span
                            className={`font-mono text-xs font-bold ${
                              t.avg_compliance >= 80
                                ? 'text-emerald-700'
                                : t.avg_compliance >= 60
                                ? 'text-amber-700'
                                : 'text-rose-700'
                            }`}
                          >
                            {Math.round(t.avg_compliance)}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-[11px] text-slate-400">—</span>
                      )}
                    </TableCell>

                    {/* Risk Alerts */}
                    <TableCell className="py-3 px-4 text-center">
                      {t.high_risk_count > 0 ? (
                        <span className="inline-flex items-center gap-1 rounded bg-rose-50 px-2 py-0.5 text-[10.5px] font-bold text-rose-700 border border-rose-200">
                          <ShieldAlert className="h-3 w-3" />
                          {t.high_risk_count} High Risk
                        </span>
                      ) : (
                        <span className="text-[11px] text-emerald-700 font-medium flex items-center justify-center gap-1">
                          <ShieldCheck className="h-3 w-3 text-emerald-600" /> Clear
                        </span>
                      )}
                    </TableCell>

                    {/* Closing Date */}
                    <TableCell className="py-3 px-4 whitespace-nowrap text-xs text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="h-3 w-3 text-slate-400" />
                        <span className="font-mono text-[11px]">{formatDate(t.closing_date)}</span>
                      </div>
                    </TableCell>

                    {/* Status */}
                    <TableCell className="py-3 px-4">
                      <span
                        className={`inline-block rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide border ${
                          t.status === 'OPEN'
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                            : t.status === 'DRAFT'
                            ? 'bg-slate-100 text-slate-700 border-slate-300'
                            : 'bg-slate-100 text-slate-500 border-slate-200'
                        }`}
                      >
                        {t.status}
                      </span>
                    </TableCell>

                    {/* Action */}
                    <TableCell className="py-3 px-4 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => navigate(`/app/tenders/${t.id}`)}
                        className="border-slate-300 text-blue-900 hover:bg-blue-50 text-xs font-medium py-1 px-2.5 h-7 shadow-2xs"
                      >
                        <Eye className="mr-1 h-3 w-3 text-blue-700" />
                        Open Dossier
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Wizard modal */}
      <TenderWizard open={dialogOpen} onOpenChange={setDialogOpen} onCreated={handleCreated} />
    </div>
  );
}
