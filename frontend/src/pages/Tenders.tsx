import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Building2,
  Calendar,
  Eye,
  Filter,
  Layers,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { tendersApi, getErrorMessage } from '../lib/api';
import { formatDate } from '../lib/utils';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/ui/toaster';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../components/ui/dialog';
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
  const { isOfficer } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [dialogOpen, setDialogOpen] = useState(false);
  // Bulk manage mode (Procurement Officer only): row selection + Delete Selected
  const [manageMode, setManageMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const { data = [], isLoading, isError, isFetching, refetch } = useQuery({
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

  const toggleManageMode = () => {
    setManageMode((m) => !m);
    setSelectedIds([]);
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === filtered.length) setSelectedIds([]);
    else setSelectedIds(filtered.map((t) => t.id));
  };

  const selectedTenders = useMemo(
    () => data.filter((t) => selectedIds.includes(t.id)),
    [data, selectedIds]
  );

  const confirmBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    setDeleting(true);
    const failed: string[] = [];
    for (const id of selectedIds) {
      try {
        await tendersApi.delete(id);
      } catch (err) {
        const t = data.find((x) => x.id === id);
        failed.push(`${t?.tender_number ?? id}: ${getErrorMessage(err)}`);
      }
    }
    setDeleting(false);
    setBulkDeleteOpen(false);
    setSelectedIds([]);
    setManageMode(false);
    queryClient.invalidateQueries({ queryKey: ['tenders'] });
    if (failed.length === 0) {
      toast({
        title: 'Tenders Deleted',
        description:
          'Selected tenders, their bidders and all derived records were deleted. The audit trail is preserved.',
      });
    } else {
      toast({
        title: 'Delete Partially Failed',
        description: failed[0],
      });
    }
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
              disabled={isFetching}
              className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
            >
              <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            {isOfficer && (
              <Button
                variant="outline"
                size="sm"
                onClick={toggleManageMode}
                className={`text-xs font-semibold ${
                  manageMode
                    ? 'border-blue-800 bg-blue-800 text-white hover:bg-blue-900'
                    : 'border-slate-300 text-slate-700 hover:bg-slate-50'
                }`}
              >
                Manage
              </Button>
            )}
            {isOfficer && !manageMode && (
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

        {/* Bulk actions bar (Manage mode, officer only) */}
        {isOfficer && manageMode && (
          <div className="mt-3 flex items-center justify-between rounded-md border border-blue-200 bg-blue-50/60 px-3 py-2">
            <span className="text-xs font-medium text-slate-700">
              {selectedIds.length === 0
                ? 'Select tenders using the checkboxes.'
                : `${selectedIds.length} tender${selectedIds.length > 1 ? 's' : ''} selected`}
            </span>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={toggleManageMode}
                className="border-slate-300 text-xs"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={selectedIds.length === 0}
                onClick={() => setBulkDeleteOpen(true)}
                className="bg-rose-700 hover:bg-rose-800 text-white text-xs font-medium disabled:opacity-40"
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                Delete Selected{selectedIds.length > 0 ? ` (${selectedIds.length})` : ''}
              </Button>
            </div>
          </div>
        )}
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
                isOfficer && data.length === 0 ? (
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
                  {isOfficer && manageMode && (
                    <TableHead className="py-3 px-4 w-10">
                      <input
                        type="checkbox"
                        checked={filtered.length > 0 && selectedIds.length === filtered.length}
                        onChange={toggleSelectAll}
                        className="h-4 w-4 rounded border-slate-300 accent-blue-800"
                        aria-label="Select all tenders"
                      />
                    </TableHead>
                  )}
                  <TableHead className="py-3 px-4 font-bold text-slate-700">Tender Reference</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700">Title &amp; Department</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700 text-right">Estimated Value</TableHead>
                  <TableHead className="py-3 px-4 font-bold text-slate-700 text-center">Bidders</TableHead>
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
                    {isOfficer && manageMode && (
                      <TableCell className="py-3 px-4">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(t.id)}
                          onChange={() => toggleSelect(t.id)}
                          className="h-4 w-4 rounded border-slate-300 accent-blue-800"
                          aria-label={`Select tender ${t.tender_number}`}
                        />
                      </TableCell>
                    )}
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
                            {t.tender_type || 'OPEN'}
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

                    {/* Risk Alerts */}
                    <TableCell className="py-3 px-4 text-center">
                      {t.high_risk_count > 0 ? (
                        <span className="inline-flex items-center gap-1 rounded bg-rose-50 px-2 py-0.5 text-[10.5px] font-bold text-rose-700 border border-rose-200">
                          <ShieldAlert className="h-3 w-3" />
                          {t.high_risk_count} High Risk
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-0.5 text-[10.5px] font-bold text-emerald-700 border border-emerald-200">
                          <ShieldCheck className="h-3 w-3" />
                          No Risk
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
                        View
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

      {/* Bulk delete confirmation (Procurement Officer only) */}
      <Dialog open={bulkDeleteOpen} onOpenChange={(open) => { if (!open) setBulkDeleteOpen(false); }}>
        <DialogContent className="max-w-md bg-white border border-slate-300">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-slate-900 font-serif">
              Delete {selectedTenders.length} Tender{selectedTenders.length > 1 ? 's' : ''}?
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-600">
              This permanently removes the following tenders, their requirements,
              all participating bidders, and every derived record (documents,
              verification checks, compliance results, risk assessments). The
              audit trail is preserved. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-40 overflow-y-auto rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
            <ul className="space-y-1">
              {selectedTenders.map((t) => (
                <li key={t.id} className="font-mono text-xs font-semibold text-slate-800">
                  #{t.tender_number}
                  <span className="ml-2 font-sans font-normal text-slate-500">{t.title}</span>
                </li>
              ))}
            </ul>
          </div>
          <DialogFooter className="flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
            <Button variant="outline" size="sm" onClick={() => setBulkDeleteOpen(false)} className="border-slate-300">
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={confirmBulkDelete}
              loading={deleting}
              className="bg-rose-700 hover:bg-rose-800 text-white font-medium text-xs"
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Delete Selected
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
