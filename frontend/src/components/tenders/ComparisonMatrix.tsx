import { useMemo, useState } from 'react';
import { Info, Search, GitCompareArrows, X } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { EmptyState, ScoreRing } from '../common/ui-helpers';
import { RiskBadge, StatusBadge } from '../common/badges';
import { OFFICER_FINALITY } from '../common/honesty';
import { BidderCompareDrawer } from './BidderCompareDrawer';
import type { ComparisonData } from '../../types';

/** Side-by-side comparison allows 2–4 bidders at a time. */
const MAX_COMPARE = 4;

/**
 * Full bidder-comparison interface: requirement × bidder status matrix with
 * search, "hide rows where all bidders PASS", per-bidder score rings and
 * risk badges. Rendered inside Tender Detail → Compliance Matrix.
 */
export function ComparisonMatrix({ comparison }: { comparison: ComparisonData }) {
  const [search, setSearch] = useState('');
  const [hideAllPass, setHideAllPass] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const toggleSelect = (bidId: number) => {
    setSelected((prev) => {
      if (prev.includes(bidId)) return prev.filter((id) => id !== bidId);
      if (prev.length >= MAX_COMPARE) return prev;
      return [...prev, bidId];
    });
  };

  const canCompare = comparison.bidders.length >= 2;

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return comparison.matrix.filter((row) => {
      if (q && !row.requirement_name.toLowerCase().includes(q)) return false;
      if (hideAllPass) {
        const statuses = comparison.bidders.map((b) => row.results[String(b.bid_id)]);
        if (statuses.length > 0 && statuses.every((s) => s === 'PASS')) return false;
      }
      return true;
    });
  }, [comparison, search, hideAllPass]);

  if (comparison.bidders.length === 0) {
    return (
      <EmptyState
        title="No bidders to compare"
        description="Bids submitted against this tender will appear here for comparison."
      />
    );
  }

  if (comparison.matrix.length === 0) {
    return (
      <EmptyState
        title="No requirements to compare"
        description="Add requirements to this tender before running a comparison."
      />
    );
  }

  return (
    <>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-center gap-4 pt-5">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter requirements…"
              className="pl-9"
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
            <input
              type="checkbox"
              checked={hideAllPass}
              onChange={(e) => setHideAllPass(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 dark:border-slate-700 accent-indigo-800"
            />
            Hide rows where all bidders PASS
          </label>
          <p className="ml-auto text-xs text-slate-500 dark:text-slate-400">
            {rows.length} of {comparison.matrix.length} requirements · {comparison.bidders.length}{' '}
            bidders
          </p>
        </CardContent>
      </Card>

      {canCompare && (
        <Card className="mb-4 border-brand-200 dark:border-brand-800">
          <CardContent className="flex flex-wrap items-center gap-3 py-3">
            <span className="text-sm text-slate-600 dark:text-slate-300">
              {selected.length === 0
                ? `Select 2–${MAX_COMPARE} bidder columns below to compare them side-by-side.`
                : `${selected.length} bidder${selected.length === 1 ? '' : 's'} selected`}
            </span>
            {selected.length > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setSelected([])}
                className="ml-1"
              >
                <X className="mr-1 h-3.5 w-3.5" /> Clear
              </Button>
            )}
            <Button
              size="sm"
              className="ml-auto"
              disabled={selected.length < 2}
              onClick={() => setDrawerOpen(true)}
            >
              <GitCompareArrows className="mr-1.5 h-4 w-4" />
              Compare Selected ({selected.length})
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="pt-5">
          {rows.length === 0 ? (
            <EmptyState
              title="No rows match"
              description="Adjust the search term or the “hide all-PASS” filter."
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[240px]">Requirement</TableHead>
                    {comparison.bidders.map((b) => (
                      <TableHead key={b.bid_id} className="text-center">
                        <div className="flex flex-col items-center gap-1.5">
                          <span className="max-w-[160px] truncate font-semibold text-slate-800 dark:text-slate-200">
                            {b.legal_name}
                          </span>
                          <span className="flex items-center gap-2">
                            <ScoreRing score={b.compliance_score} size={56} />
                            <RiskBadge level={b.risk_level} />
                          </span>
                          {canCompare && (
                            <label
                              className="flex cursor-pointer items-center gap-1.5 text-xs font-normal text-slate-500 dark:text-slate-400"
                              title={
                                selected.includes(b.bid_id)
                                  ? 'Remove from comparison'
                                  : selected.length >= MAX_COMPARE
                                    ? `Up to ${MAX_COMPARE} bidders can be compared`
                                    : 'Add to comparison'
                              }
                            >
                              <input
                                type="checkbox"
                                checked={selected.includes(b.bid_id)}
                                disabled={
                                  !selected.includes(b.bid_id) &&
                                  selected.length >= MAX_COMPARE
                                }
                                onChange={() => toggleSelect(b.bid_id)}
                                className="h-3.5 w-3.5 rounded border-slate-300 dark:border-slate-700 accent-indigo-800"
                              />
                              Compare
                            </label>
                          )}
                        </div>
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.requirement_id}>
                      <TableCell className="font-medium text-slate-800 dark:text-slate-200">
                        {row.requirement_name}
                      </TableCell>
                      {comparison.bidders.map((b) => (
                        <TableCell key={b.bid_id} className="text-center">
                          <StatusBadge status={row.results[String(b.bid_id)] ?? null} />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mt-4 border-indigo-200 dark:border-indigo-800 bg-indigo-50/50 dark:bg-indigo-950/60">
        <CardHeader className="flex flex-row items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-brand-800 dark:text-brand-300" />
          <div>
            <CardTitle className="text-sm">How to read this comparison</CardTitle>
            <CardDescription className="text-sm">
              Comparison is informational and supports officer review. System-identified
              non-compliance is flagged for Procurement Officer review — the system does not
              disqualify bidders. {OFFICER_FINALITY}
            </CardDescription>
          </div>
        </CardHeader>
      </Card>

      <BidderCompareDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        bidIds={selected}
      />
    </>
  );
}
