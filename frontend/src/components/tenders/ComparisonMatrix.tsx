import { useMemo, useState } from 'react';
import { Info, Search } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
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
import type { ComparisonData } from '../../types';

/**
 * Full bidder-comparison interface: requirement × bidder status matrix with
 * search, "hide rows where all bidders PASS", per-bidder score rings and
 * risk badges. Rendered inside Tender Detail → Compliance Matrix.
 */
export function ComparisonMatrix({ comparison }: { comparison: ComparisonData }) {
  const [search, setSearch] = useState('');
  const [hideAllPass, setHideAllPass] = useState(false);

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
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter requirements…"
              className="pl-9"
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={hideAllPass}
              onChange={(e) => setHideAllPass(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 accent-indigo-800"
            />
            Hide rows where all bidders PASS
          </label>
          <p className="ml-auto text-xs text-slate-500">
            {rows.length} of {comparison.matrix.length} requirements · {comparison.bidders.length}{' '}
            bidders
          </p>
        </CardContent>
      </Card>

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
                          <span className="max-w-[160px] truncate font-semibold text-slate-800">
                            {b.legal_name}
                          </span>
                          <span className="flex items-center gap-2">
                            <ScoreRing score={b.compliance_score} size={56} />
                            <RiskBadge level={b.risk_level} />
                          </span>
                        </div>
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.requirement_id}>
                      <TableCell className="font-medium text-slate-800">
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

      <Card className="mt-4 border-indigo-200 bg-indigo-50/50">
        <CardHeader className="flex flex-row items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-brand-800" />
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
    </>
  );
}
