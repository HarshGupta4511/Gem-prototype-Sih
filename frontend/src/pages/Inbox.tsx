import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Inbox as InboxIcon, RefreshCw, ChevronRight, FileCheck2 } from 'lucide-react';
import { reportsApi, getErrorMessage } from '../lib/api';
import { useToast } from '../components/ui/toaster';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { PageHeader, BackLink, LoadingBlock } from '../components/common/ui-helpers';
import { labelize } from '../lib/utils';
import type { ReportStatus } from '../types';

const STATUS_STYLES: Record<ReportStatus, string> = {
  DRAFT: 'bg-slate-100 text-slate-700 border-slate-200',
  GENERATED: 'bg-blue-50 text-blue-800 border-blue-200',
  SENT_TO_OFFICER: 'bg-amber-50 text-amber-800 border-amber-200',
  UNDER_REVIEW: 'bg-indigo-50 text-indigo-800 border-indigo-200',
  DECISION_MADE: 'bg-emerald-50 text-emerald-800 border-emerald-200',
};

function formatDateTime(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function Inbox() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { data, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ['reports-inbox'],
    queryFn: reportsApi.inbox,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  React.useEffect(() => {
    if (error) toast('error', 'Could not load inbox', getErrorMessage(error));
  }, [error, toast]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <LoadingBlock rows={6} />
      </div>
    );
  }

  const items = data ?? [];
  const newCount = items.filter((i) => i.is_new).length;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Verification Reports"
        description="Review reports submitted by verifiers and record the final procurement decision."
        back={<BackLink to="/app/dashboard" label="Back to Dashboard" />}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isRefetching}
            className="border-slate-300 text-slate-700 hover:bg-slate-50 text-xs"
          >
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isRefetching ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        }
      />

      {newCount > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span className="font-semibold">{newCount} new report{newCount === 1 ? '' : 's'}</span>
          {' '}awaiting your review.
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-lg border border-slate-200 bg-white p-10 text-center">
          <FileCheck2 className="mx-auto h-10 w-10 text-slate-300" />
          <p className="mt-3 text-sm font-semibold text-slate-900">No verification reports yet</p>
          <p className="mt-1 text-sm text-slate-500">
            When a verifier sends a completed report, it will appear here for your review and decision.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xs">
          <ul className="divide-y divide-slate-100">
            {items.map((item) => (
              <li key={item.bid_id}>
                <button
                  onClick={() => navigate(`/app/bids/${item.bid_id}/report`)}
                  className="flex w-full items-center gap-4 px-4 py-4 text-left transition-colors hover:bg-slate-50"
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                    <FileCheck2 className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {item.bidder_name ?? `Bid #${item.bid_id}`}
                      </p>
                      {item.is_new && (
                        <Badge className="bg-amber-500 text-white border-amber-500 text-[10px]">
                          NEW
                        </Badge>
                      )}
                      <Badge variant="outline" className={STATUS_STYLES[item.status]}>
                        {labelize(item.status)}
                      </Badge>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      {item.tender_number} · {item.tender_title}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Submitted by {item.sent_by ?? 'Verifier'} · {formatDateTime(item.sent_at)}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
