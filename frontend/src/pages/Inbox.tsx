import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Inbox as InboxIcon, RefreshCw, ArrowRight } from 'lucide-react';
import { dashboardApi } from '../lib/api';
import { useToast } from '../components/ui/toaster';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { PageHeader, LoadingBlock } from '../components/common/ui-helpers';
import { cn, labelize } from '../lib/utils';

// Single-role model: Notifications is the Procurement Officer's attention
// queue — the backend-driven work queue. No report-inbox receive/acknowledge.
const KIND_META: Record<string, { classes: string }> = {
  HIGH_RISK_BIDDER: { classes: 'bg-red-50 text-red-800 border-red-200' },
  STATUTORY_MISMATCH: { classes: 'bg-red-50 text-red-800 border-red-200' },
  MISSING_MANDATORY_REQUIREMENT: { classes: 'bg-amber-50 text-amber-800 border-amber-200' },
  INTEGRITY_SIGNAL: { classes: 'bg-violet-50 text-violet-800 border-violet-200' },
  PENDING_SUMMARY: { classes: 'bg-amber-50 text-amber-800 border-amber-200' },
  PENDING_OFFICER_DECISION: { classes: 'bg-blue-50 text-blue-800 border-blue-200' },
  DOCUMENT: { classes: 'bg-slate-100 text-slate-700 border-slate-300' },
};

export default function Inbox() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [refreshing, setRefreshing] = React.useState(false);

  const { data: dashboard, isLoading, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.get,
    staleTime: 30_000,
  });

  const items = dashboard?.work_queue ?? [];

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await qc.invalidateQueries({ queryKey: ['dashboard'] });
      await refetch();
    } catch {
      toast('error', 'Refresh failed');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Notifications"
        description="Items that need the Procurement Officer's attention — high-risk bids, statutory mismatches, missing mandatory evidence, integrity signals, and pending decisions."
        actions={
          <Button size="sm" variant="outline" onClick={handleRefresh} disabled={refreshing} className="border-slate-300 text-slate-700">
            <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', refreshing && 'animate-spin')} />
            Refresh
          </Button>
        }
      />

      {isLoading ? (
        <LoadingBlock rows={6} />
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white py-16 text-center">
          <InboxIcon className="h-10 w-10 text-slate-300" />
          <p className="mt-3 text-sm font-semibold text-slate-700">No pending items</p>
          <p className="mt-1 max-w-sm text-xs text-slate-500">
            Everything is clear. New items appear here as soon as the work queue flags
            something that needs your attention.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            {items.length} item{items.length === 1 ? '' : 's'} needing attention
          </p>
          <ul className="space-y-2.5">
            {items.map((item, i) => {
              const meta = KIND_META[item.category] ?? KIND_META.DOCUMENT;
              return (
                <li key={`${item.category}-${item.bid_id ?? item.tender_id ?? i}`}>
                  <Link
                    to={item.link ?? '/app/dashboard'}
                    className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-xs transition-colors hover:border-brand-300 hover:bg-brand-50/40"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                      <p className="mt-0.5 text-xs text-slate-500 line-clamp-2">{item.description}</p>
                    </div>
                    <Badge variant="outline" className={cn('text-[11px]', meta.classes)}>
                      {item.category_label ?? labelize(item.category)}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-[11px]',
                        item.severity === 'HIGH' || item.severity === 'CRITICAL'
                          ? 'bg-red-50 text-red-800 border-red-200'
                          : 'bg-slate-100 text-slate-700 border-slate-300'
                      )}
                    >
                      {labelize(item.severity)}
                    </Badge>
                    <ArrowRight className="h-4 w-4 text-slate-400" />
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
