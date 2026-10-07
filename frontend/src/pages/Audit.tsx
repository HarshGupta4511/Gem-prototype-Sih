import * as React from 'react';
import {
  CheckCircle2,
  Download,
  FileCheck,
  FileSpreadsheet,
  FileText,
  Filter,
  Layers,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  X,
  XCircle,
} from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { auditApi, getErrorMessage } from '../lib/api';
import { formatDateTime, labelize } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Input, Select } from '../components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { useToast } from '../components/ui/toaster';
import { EmptyState, LoadingBlock } from '../components/common/ui-helpers';
import { SystemLayerTag } from '../components/common/SystemLayerTag';
import type { AuditVerifyResult, AuditLog } from '../types';

export default function Audit() {
  const { toast } = useToast();
  // Single-role app: the Procurement Officer verifies the audit chain.
  const canVerifyChain = true;
  const queryClient = useQueryClient();
  const [search, setSearch] = React.useState('');
  const [actionFilter, setActionFilter] = React.useState('');
  const [entityTypeFilter, setEntityTypeFilter] = React.useState('');
  const [verifyResult, setVerifyResult] = React.useState<AuditVerifyResult | null>(null);
  const [selectedLog, setSelectedLog] = React.useState<AuditLog | null>(null);

  const { data: logs = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['audit'],
    queryFn: () => auditApi.list({ limit: 200 }),
  });

  const verifyMutation = useMutation({
    mutationFn: auditApi.verify,
    onSuccess: (res) => {
      setVerifyResult(res);
      void queryClient.invalidateQueries({ queryKey: ['audit'] });
      if (res.valid) {
        toast({
          title: 'Audit Chain Verified',
          description: `Cryptographic SHA-256 verification passed for all ${res.checked} ledger entries.`,
        });
      } else {
        toast({
          title: 'Integrity Anomaly Detected',
          description: res.broken_at ? `Mismatch detected at entry #${res.broken_at.id}.` : 'Chain anomaly.',
        });
      }
    },
    onError: (err) =>
      toast({ title: 'Verification Failed', description: getErrorMessage(err) }),
  });

  const distinctActions = React.useMemo(
    () => [...new Set(logs.map((l) => l.action))].sort(),
    [logs]
  );
  const distinctEntityTypes = React.useMemo(
    () => [...new Set(logs.map((l) => l.entity_type))].sort(),
    [logs]
  );

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return logs.filter((l) => {
      if (actionFilter && l.action !== actionFilter) return false;
      if (entityTypeFilter && l.entity_type !== entityTypeFilter) return false;
      if (q) {
        const hay = `${l.entity_id ?? ''} ${l.action} ${l.user_name ?? ''} ${l.target_label ?? ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [logs, search, actionFilter, entityTypeFilter]);

  const handleExportReport = () => {
    const content = JSON.stringify(logs, null, 2);
    const blob = new Blob([content], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `BIDWISE-Audit-Trail-Report-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: 'Report Generated', description: 'Statutory audit record exported as JSON.' });
  };

  return (
    <div className="space-y-6">
      {/* 1. Header */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-800 font-mono dark:text-blue-400">
                Statutory Ledger
              </span>
              <SystemLayerTag layer="HUMAN_DECISION" size="sm" />
            </div>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900 font-serif dark:text-slate-100">
              Audit Trail
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
              Tamper-evident record of all procurement verifications, rule scores, and officer decisions.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportReport}
              className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <Download className="mr-1.5 h-3.5 w-3.5" />
              Generate Report
            </Button>
            {canVerifyChain && (
              <Button
                size="sm"
                loading={verifyMutation.isPending}
                onClick={() => {
                  setVerifyResult(null);
                  verifyMutation.mutate();
                }}
                className="bg-blue-800 hover:bg-blue-900 text-white text-xs font-medium shadow-xs"
              >
                <ShieldCheck className="mr-1.5 h-3.5 w-3.5 text-blue-200" />
                Verify Audit Integrity
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* 2. Integrity Status Banner */}
      {verifyResult ? (
        <div
          className={`rounded-lg border p-4 shadow-xs ${
            verifyResult.valid
              ? 'border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-100'
              : 'border-rose-300 bg-rose-50 text-rose-950 dark:border-rose-800 dark:bg-rose-950/60 dark:text-rose-100'
          }`}
        >
          <div className="flex items-start gap-3">
            {verifyResult.valid ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5 shrink-0 dark:text-emerald-400" />
            ) : (
              <XCircle className="h-5 w-5 text-rose-600 mt-0.5 shrink-0 dark:text-rose-400" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-xs uppercase tracking-wider">
                  {verifyResult.valid
                    ? 'Audit Chain Verified — No Tampering Detected'
                    : 'Cryptographic Hash-Chain Integrity Compromised'}
                </span>
                <span className="font-mono text-[11px] font-semibold">
                  Algorithm: SHA-256
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed">
                {verifyResult.valid ? (
                  <span>
                    Successfully verified hash continuity across all{' '}
                    <strong>{verifyResult.checked} entries</strong>. Genesis state and backward pointer hashes remain intact.
                  </span>
                ) : (
                  <span>
                    Discrepancy at block entry #{verifyResult.broken_at?.id}. Expected hash does not match stored block signature.
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3.5 text-xs text-blue-900 flex items-center justify-between dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-100">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-blue-700 dark:text-blue-400" />
            <span>
              <strong>Cryptographic Guarantee:</strong> Every user action and engine evaluation is chained via SHA-256 back to the genesis block.
            </span>
          </div>
          <span className="font-mono text-[11px] text-blue-700 dark:text-blue-400">{logs.length} Blocks Indexed</span>
        </div>
      )}

      {/* 3. Filter Bar */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
            <Input
              placeholder="Search by actor, entity ID, or target…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 text-xs border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500"
            />
          </div>

          <Select
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="text-xs border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            <option value="">All Action Types ({distinctActions.length})</option>
            {distinctActions.map((a) => (
              <option key={a} value={a}>
                {labelize(a)}
              </option>
            ))}
          </Select>

          <Select
            value={entityTypeFilter}
            onChange={(e) => setEntityTypeFilter(e.target.value)}
            className="text-xs border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            <option value="">All Entity Types ({distinctEntityTypes.length})</option>
            {distinctEntityTypes.map((t) => (
              <option key={t} value={t}>
                {labelize(t)}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {/* 4. Audit Ledger Table */}
      <div className="rounded-lg border border-slate-200 bg-white shadow-xs overflow-hidden dark:border-slate-800 dark:bg-slate-900">
        {isLoading ? (
          <div className="p-6">
            <LoadingBlock rows={6} />
          </div>
        ) : isError ? (
          <EmptyState
            title="Could not load audit trail"
            description="Failed to fetch cryptographic ledger records."
            action={
              <Button onClick={() => refetch()} size="sm">
                Retry
              </Button>
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No matching audit entries"
            description="Try adjusting your search criteria or action filters."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-[10.5px] font-bold text-slate-600 uppercase tracking-wider dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-400">
                  <TableHead className="py-2.5 px-3">Timestamp (IST)</TableHead>
                  <TableHead className="py-2.5 px-3">Actor &amp; Role</TableHead>
                  <TableHead className="py-2.5 px-3">Action Recorded</TableHead>
                  <TableHead className="py-2.5 px-3">Target Entity</TableHead>
                  <TableHead className="py-2.5 px-3 font-mono">Current Hash (SHA-256)</TableHead>
                  <TableHead className="py-2.5 px-3 font-mono">Previous Hash</TableHead>
                  <TableHead className="py-2.5 px-3 text-right">Details</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {filtered.map((log) => (
                  <TableRow key={log.id} className="hover:bg-blue-50/40 transition-colors text-xs dark:hover:bg-blue-950/40">
                    <TableCell className="py-2.5 px-3 font-mono text-[11px] text-slate-600 whitespace-nowrap dark:text-slate-400">
                      {formatDateTime(log.timestamp)}
                    </TableCell>
                    <TableCell className="py-2.5 px-3">
                      <span className="font-semibold text-slate-900 block leading-tight dark:text-slate-100">
                        {log.user_name || 'System Automation'}
                      </span>
                      <span className="text-[10px] text-slate-400 dark:text-slate-500">
                        {log.user_id ? `User #${log.user_id}` : 'Deterministic Engine'}
                      </span>
                    </TableCell>
                    <TableCell className="py-2.5 px-3">
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-[10.5px] font-semibold text-slate-800 border border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700">
                        {labelize(log.action)}
                      </span>
                    </TableCell>
                    <TableCell className="py-2.5 px-3">
                      <span className="font-medium text-slate-800 dark:text-slate-200">{log.entity_type}</span>{' '}
                      <span className="font-mono text-slate-500 text-[11px] dark:text-slate-400">#{log.entity_id}</span>
                      {log.target_label && (
                        <span className="block text-[10.5px] text-slate-500 truncate max-w-xs dark:text-slate-400">
                          {log.target_label}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="py-2.5 px-3 font-mono text-[11px] text-blue-900 font-semibold dark:text-blue-400">
                      {log.current_hash ? `${log.current_hash.slice(0, 10)}...${log.current_hash.slice(-6)}` : 'GENESIS'}
                    </TableCell>
                    <TableCell className="py-2.5 px-3 font-mono text-[11px] text-slate-400 dark:text-slate-500">
                      {log.previous_hash ? `${log.previous_hash.slice(0, 8)}...` : 'GENESIS'}
                    </TableCell>
                    <TableCell className="py-2.5 px-3 text-right">
                      <button
                        type="button"
                        onClick={() => setSelectedLog(log)}
                        className="text-xs text-blue-800 hover:text-blue-950 hover:underline font-semibold dark:text-blue-400 dark:hover:text-blue-300"
                      >
                        Inspect
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Details Dialog */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-lg border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 pb-3 dark:border-slate-700">
              <div>
                <span className="text-[11px] font-bold uppercase tracking-wider text-blue-800 font-mono dark:text-blue-400">
                  Ledger Entry #{selectedLog.id}
                </span>
                <h3 className="text-sm font-bold text-slate-900 font-serif dark:text-slate-100">
                  {labelize(selectedLog.action)}
                </h3>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                className="rounded p-1 text-slate-400 hover:text-slate-700 dark:text-slate-500 dark:hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-3 space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400">Timestamp:</span>
                <span className="font-mono">{formatDateTime(selectedLog.timestamp)}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400">Actor:</span>
                <span className="font-medium">{selectedLog.user_name || 'System Engine'}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-100 dark:border-slate-800">
                <span className="text-slate-500 dark:text-slate-400">Target Entity:</span>
                <span className="font-mono">
                  {selectedLog.entity_type} #{selectedLog.entity_id}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block mb-1 dark:text-slate-400">Current Block Signature:</span>
                <p className="font-mono text-[10px] break-all bg-slate-100 p-2 rounded border border-slate-200 dark:bg-slate-800 dark:border-slate-700">
                  {selectedLog.current_hash}
                </p>
              </div>
              <div>
                <span className="text-slate-500 block mb-1 dark:text-slate-400">Previous Block Hash:</span>
                <p className="font-mono text-[10px] break-all bg-slate-100 p-2 rounded border border-slate-200 dark:bg-slate-800 dark:border-slate-700">
                  {selectedLog.previous_hash}
                </p>
              </div>
              {selectedLog.metadata && Object.keys(selectedLog.metadata).length > 0 && (
                <div>
                  <span className="text-slate-500 block mb-1 dark:text-slate-400">Event Payload Metadata:</span>
                  <pre className="font-mono text-[10px] bg-slate-900 text-slate-100 p-2.5 rounded max-h-36 overflow-y-auto">
                    {JSON.stringify(selectedLog.metadata, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 text-right dark:border-slate-800">
              <Button size="sm" onClick={() => setSelectedLog(null)} className="text-xs">
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
