import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Inbox as InboxIcon, RefreshCw, ArrowRight, X, Trash2 } from 'lucide-react';
import { dashboardApi } from '../lib/api';
import { useToast } from '../components/ui/toaster';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { PageHeader, LoadingBlock } from '../components/common/ui-helpers';
import { cn, labelize } from '../lib/utils';
import {
  dismissAllNotifications,
  dismissNotification,
  notificationKey,
  useDismissedNotifications,
} from '../lib/dismissedNotifications';

// Single-role model: Notifications is the Procurement Officer's attention
// queue — the backend-driven work queue. No report-inbox receive/acknowledge.
const KIND_META: Record<string, { classes: string }> = {
  HIGH_RISK_BIDDER: { classes: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-400 dark:border-red-900' },
  STATUTORY_MISMATCH: { classes: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-400 dark:border-red-900' },
  MISSING_MANDATORY_REQUIREMENT: { classes: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-400 dark:border-amber-900' },
  INTEGRITY_SIGNAL: { classes: 'bg-violet-50 text-violet-800 border-violet-200 dark:bg-violet-950/60 dark:text-violet-400 dark:border-violet-900' },
  PENDING_SUMMARY: { classes: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-400 dark:border-amber-900' },
  PENDING_OFFICER_DECISION: { classes: 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-950/60 dark:text-blue-400 dark:border-blue-900' },
  DOCUMENT: { classes: 'bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700' },
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

  // Dismissed items are filtered out of the backend-driven work queue. The
  // dismissal set lives in localStorage, so cleared notifications do not come
  // back on refresh.
  const dismissed = useDismissedNotifications();
  const items = (dashboard?.work_queue ?? []).filter(
    (item) => !dismissed.has(notificationKey(item)),
  );

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

  const handleClearAll = () => {
    dismissAllNotifications(items.map(notificationKey));
    toast('success', 'All notifications cleared');
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Notifications"
        description="Items that need the Procurement Officer's attention — high-risk bids, statutory mismatches, missing mandatory evidence, integrity signals, and pending decisions."
        actions={
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleClearAll}
              disabled={items.length === 0}
              className="border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-200"
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Clear All
            </Button>
            <Button size="sm" variant="outline" onClick={handleRefresh} disabled={refreshing} className="border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-200">
              <RefreshCw className={cn('mr-1.5 h-3.5 w-3.5', refreshing && 'animate-spin')} />
              Refresh
            </Button>
          </div>
        }
      />

      {isLoading ? (
        <LoadingBlock rows={6} />
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white py-16 text-center dark:border-slate-700 dark:bg-slate-900">
          <InboxIcon className="h-10 w-10 text-slate-300 dark:text-slate-600" />
          <p className="mt-3 text-sm font-semibold text-slate-700 dark:text-slate-200">No pending items</p>
          <p className="mt-1 max-w-sm text-xs text-slate-500 dark:text-slate-400">
            Everything is clear. New items appear here as soon as the work queue flags
            something that needs your attention.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {items.length} item{items.length === 1 ? '' : 's'} needing attention
          </p>
          <ul className="space-y-2.5">
            {items.map((item, i) => {
              const meta = KIND_META[item.category] ?? KIND_META.DOCUMENT;
              const key = notificationKey(item);
              return (
                <li key={`${item.category}-${item.bid_id ?? item.tender_id ?? i}`} className="relative">
                  <Link
                    to={item.link ?? '/app/dashboard'}
                    className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 pr-11 shadow-xs transition-colors hover:border-brand-300 hover:bg-brand-50/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-600 dark:hover:bg-slate-800/70"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.title}</p>
                      <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">{item.description}</p>
                    </div>
                    <Badge variant="outline" className={cn('text-[11px]', meta.classes)}>
                      {item.category_label ?? labelize(item.category)}
                    </Badge>
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-[11px]',
                        item.severity === 'HIGH' || item.severity === 'CRITICAL'
                          ? 'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-400 dark:border-red-900'
                          : 'bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700'
                      )}
                    >
                      {labelize(item.severity)}
                    </Badge>
                    <ArrowRight className="h-4 w-4 text-slate-400 dark:text-slate-500" />
                  </Link>
                  <button
                    type="button"
                    onClick={() => dismissNotification(key)}
                    aria-label="Dismiss notification"
                    title="Dismiss"
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
