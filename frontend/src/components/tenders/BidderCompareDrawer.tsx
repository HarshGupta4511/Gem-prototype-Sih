import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { AlertTriangle, FileText, GitCompareArrows, Sparkles } from 'lucide-react';
import { Sheet, SheetContent } from '../ui/sheet';
import { Button } from '../ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';
import { LoadingBlock, ScoreRing } from '../common/ui-helpers';
import {
  DecisionBadge,
  RecommendationBadge,
  RiskBadge,
  StatusBadge,
} from '../common/badges';
import { bidsApi, documentsApi, integrityApi } from '../../lib/api';
import { displayThreshold } from '../../lib/compliance-display';
import { formatINR } from '../../lib/utils';
import { OFFICER_FINALITY } from '../common/honesty';
import type {
  BidDetail,
  ComplianceResult,
  IntegrityFinding,
  RequirementStatus,
} from '../../types';

/* ------------------------------------------------------------------ types */

interface SemanticEntityValue {
  normalized_value: string;
  raw_value: string;
  sources: { document_id: number; document_type: string | null; filename: string | null }[];
}

interface SemanticEntity {
  field_name: string;
  display_label: string;
  values: SemanticEntityValue[];
  has_conflict: boolean;
  is_empty: boolean;
}

interface SemanticView {
  bid_id: number;
  entities: SemanticEntity[];
}

export interface BidCompareData {
  bidId: number;
  legalName: string;
  detail: BidDetail;
  semantic: SemanticView;
  integrity: IntegrityFinding[];
}

/* ---------------------------------------------------------------- helpers */

const FIELD_CANDIDATES: Record<string, string[]> = {
  turnover: ['turnover_inr'],
  experience: ['experience_years'],
  emd: ['emd_amount_inr'],
  itr: ['itr_financial_year', 'itr_fy'],
  iso: ['iso_valid_until'],
  pan: ['pan'],
  gstin: ['gstin'],
  udyam: ['udyam_number'],
  cin: ['cin'],
  epfo: ['epfo_code'],
};

function entityOf(sem: SemanticView, ...names: string[]): SemanticEntity | null {
  const wanted = new Set(names);
  return sem.entities.find((e) => wanted.has(e.field_name) && !e.is_empty) ?? null;
}

function valueOf(sem: SemanticView, ...names: string[]): string | null {
  const e = entityOf(sem, ...names);
  return e?.values[0]?.normalized_value ?? null;
}

function numOf(sem: SemanticView, ...names: string[]): number | null {
  const v = valueOf(sem, ...names);
  if (!v) return null;
  const n = parseFloat(v.replace(/[^0-9.]/g, ''));
  return Number.isFinite(n) ? n : null;
}

function resultFor(
  detail: BidDetail,
  ...keywords: string[]
): ComplianceResult | null {
  const kw = keywords.map((k) => k.toLowerCase());
  return (
    detail.compliance_results.find((r) =>
      kw.some((k) => r.requirement?.requirement_name.toLowerCase().includes(k)),
    ) ?? null
  );
}

function verificationFor(
  detail: BidDetail,
  ...sourceKeys: string[]
): { status: string; identifier: string } | null {
  const keys = sourceKeys.map((k) => k.toLowerCase());
  const c = detail.verification_checks.find((v) =>
    keys.some((k) => v.source.toLowerCase().includes(k)),
  );
  return c ? { status: c.verification_status, identifier: c.identifier } : null;
}

function fmtYears(n: number | null): string {
  return n == null ? '—' : `${n} year${n === 1 ? '' : 's'}`;
}

function fmtMoney(n: number | null): string {
  return n == null ? '—' : formatINR(n);
}

/** Map a requirement name to the canonical extracted field(s) holding its value. */
function requirementFields(requirementName: string): string[] {
  const name = requirementName.toLowerCase();
  if (/experience/.test(name)) return FIELD_CANDIDATES.experience;
  if (/turnover|balance/.test(name)) return FIELD_CANDIDATES.turnover;
  if (/emd/.test(name)) return FIELD_CANDIDATES.emd;
  if (/itr|income tax/.test(name)) return FIELD_CANDIDATES.itr;
  if (/iso/.test(name)) return FIELD_CANDIDATES.iso;
  if (/gst/.test(name)) return FIELD_CANDIDATES.gstin;
  if (/\bpan\b/.test(name)) return FIELD_CANDIDATES.pan;
  if (/udyam|msme/.test(name)) return FIELD_CANDIDATES.udyam;
  if (/mca|\bcin\b|incorporat/.test(name)) return FIELD_CANDIDATES.cin;
  if (/epfo|provident/.test(name)) return FIELD_CANDIDATES.epfo;
  return [];
}

/* ------------------------------------------------------- smart highlights */

function buildHighlights(data: BidCompareData[]): string[] {
  const out: string[] = [];
  const n = data.length;

  const mandFails = data.map(
    (d) =>
      d.detail.compliance_results.filter(
        (r) =>
          r.requirement?.mandatory &&
          (r.status === 'FAIL' || r.status === 'MISSING'),
      ).length,
  );
  if (mandFails.every((f) => f === 0)) {
    out.push(`All ${n} bidders satisfy every mandatory requirement.`);
  } else {
    data.forEach((d, i) => {
      if (mandFails[i] > 0)
        out.push(
          `${d.legalName} has ${mandFails[i]} mandatory requirement failure${mandFails[i] === 1 ? '' : 's'}.`,
        );
    });
  }

  const exps = data
    .map((d) => ({ name: d.legalName, years: numOf(d.semantic, ...FIELD_CANDIDATES.experience) }))
    .filter((e) => e.years != null) as { name: string; years: number }[];
  if (exps.length >= 2) {
    const sorted = [...exps].sort((a, b) => b.years - a.years);
    const diff = Math.round((sorted[0].years - sorted[sorted.length - 1].years) * 10) / 10;
    if (diff > 0)
      out.push(
        `${sorted[0].name} reports ${diff} more year${diff === 1 ? '' : 's'} of relevant experience than ${sorted[sorted.length - 1].name}.`,
      );
  }

  const emds = data.map((d) => numOf(d.semantic, ...FIELD_CANDIDATES.emd));
  if (emds.every((e) => e != null) && new Set(emds).size === 1)
    out.push(`All bidders submitted ${formatINR(emds[0] as number)} EMD.`);
  else if (emds.every((e) => e != null)) {
    const nums = emds as number[];
    out.push(`EMD submitted ranges from ${formatINR(Math.min(...nums))} to ${formatINR(Math.max(...nums))}.`);
  }

  data.forEach((d) => {
    if (d.integrity.length === 0)
      out.push(`${d.legalName} has no detected integrity signals.`);
    else
      out.push(
        `${d.legalName} has ${d.integrity.length} integrity signal${d.integrity.length === 1 ? '' : 's'} flagged for officer review.`,
      );
  });

  const scores = data
    .map((d) => d.detail.bid.compliance_score)
    .filter((s): s is number => s != null);
  if (scores.length >= 2)
    out.push(
      `Compliance scores range from ${Math.min(...scores)} to ${Math.max(...scores)}.`,
    );

  return out;
}

/* ------------------------------------------------------------ data fetch */

async function fetchBidCompare(bidId: number): Promise<BidCompareData> {
  const [detail, semantic, integrity] = await Promise.all([
    bidsApi.get(bidId),
    documentsApi.semanticView(bidId),
    integrityApi.bidSignals(bidId),
  ]);
  return {
    bidId,
    legalName: detail.bidder.legal_name,
    detail,
    semantic: semantic as SemanticView,
    integrity,
  };
}

/* ------------------------------------------------------------ row layout */

interface CompareRow {
  label: string;
  hint?: string;
  cells: (d: BidCompareData) => React.ReactNode;
}

function SectionTable({
  title,
  rows,
  data,
}: {
  title: string;
  rows: CompareRow[];
  data: BidCompareData[];
}) {
  return (
    <section className="mb-6">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {title}
      </h3>
      <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-[190px] bg-slate-50 dark:bg-slate-900/60" />
              {data.map((d) => (
                <TableHead key={d.bidId} className="min-w-[210px] bg-slate-50 dark:bg-slate-900/60">
                  <Link
                    to={`/app/bids/${d.bidId}`}
                    className="font-semibold text-brand-800 hover:underline dark:text-brand-300"
                  >
                    {d.legalName}
                  </Link>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.label}>
                <TableCell className="align-top font-medium text-slate-700 dark:text-slate-300">
                  {row.label}
                  {row.hint && (
                    <div className="mt-0.5 text-xs font-normal text-slate-500 dark:text-slate-400">
                      {row.hint}
                    </div>
                  )}
                </TableCell>
                {data.map((d) => (
                  <TableCell key={d.bidId} className="align-top">
                    {row.cells(d)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}

/* ------------------------------------------------- statutory status cell */

function StatCell({
  data,
  label,
  value,
  sourceKeys,
}: {
  data: BidCompareData;
  label: string;
  value: string | null;
  sourceKeys: string[];
}) {
  const v = verificationFor(data.detail, ...sourceKeys);
  const bad = v && (v.status === 'MISMATCH' || v.status === 'FAIL');
  return (
    <div>
      <div
        className={
          bad
            ? 'font-mono text-sm font-semibold text-red-700 dark:text-red-400'
            : 'font-mono text-sm text-slate-800 dark:text-slate-200'
        }
      >
        {value ?? v?.identifier ?? '—'}
      </div>
      {v && (
        <div className="mt-1">
          <StatusBadge status={v.status as RequirementStatus} />
          {bad && (
            <div className="mt-1 flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
              <AlertTriangle className="h-3 w-3" /> Verification issue — see {label} checks
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- drawer */

export function BidderCompareDrawer({
  open,
  onClose,
  bidIds,
}: {
  open: boolean;
  onClose: () => void;
  bidIds: number[];
}) {
  const query = useQuery({
    queryKey: ['bidder-compare', [...bidIds].sort((a, b) => a - b)],
    queryFn: () => Promise.all(bidIds.map(fetchBidCompare)),
    enabled: open && bidIds.length >= 2,
    staleTime: 60_000,
  });

  const data = useMemo(() => query.data ?? [], [query.data]);
  const highlights = useMemo(() => (data.length >= 2 ? buildHighlights(data) : []), [data]);

  const requirementRows: { name: string; threshold: string | null }[] = useMemo(() => {
    if (data.length === 0) return [];
    return data[0].detail.compliance_results.map((r) => ({
      name: r.requirement?.requirement_name ?? `Requirement ${r.requirement_id}`,
      threshold: r.requirement?.threshold ?? null,
    }));
  }, [data]);

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent
        className="max-w-6xl"
        title={
          <span className="flex items-center gap-2 text-base font-semibold">
            <GitCompareArrows className="h-5 w-5 text-brand-800 dark:text-brand-300" />
            Side-by-Side Bidder Comparison
          </span>
        }
      >
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {query.isLoading && <LoadingBlock rows={8} />}
          {query.isError && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
              Could not load comparison data. Please try again.
              <div className="mt-2">
                <Button size="sm" variant="outline" onClick={() => query.refetch()}>
                  Retry
                </Button>
              </div>
            </div>
          )}
          {data.length >= 2 && (
            <>
              {/* Smart highlights */}
              <section className="mb-6 rounded-lg border border-indigo-200 bg-indigo-50/60 p-4 dark:border-indigo-900 dark:bg-indigo-950/50">
                <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-indigo-900 dark:text-indigo-200">
                  <Sparkles className="h-4 w-4" /> Key differences
                </h3>
                <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-300">
                  {highlights.map((h, i) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                  Factual differences computed from bidder data. No bidder is ranked or
                  declared a winner — {OFFICER_FINALITY}
                </p>
              </section>

              {/* A. Overall evaluation */}
              <SectionTable
                title="A. Overall evaluation"
                data={data}
                rows={[
                  {
                    label: 'Compliance score',
                    cells: (d) => (
                      <ScoreRing score={d.detail.bid.compliance_score} size={56} />
                    ),
                  },
                  {
                    label: 'Risk level',
                    cells: (d) => <RiskBadge level={d.detail.bid.risk_level} />,
                  },
                  {
                    label: 'AI recommendation',
                    cells: (d) => (
                      <RecommendationBadge rec={d.detail.bid.recommendation} />
                    ),
                  },
                  {
                    label: 'Officer decision',
                    cells: (d) => (
                      <DecisionBadge decision={d.detail.bid.officer_decision} />
                    ),
                  },
                  {
                    label: 'Mandatory failures',
                    cells: (d) => {
                      const fails = d.detail.compliance_results.filter(
                        (r) =>
                          r.requirement?.mandatory &&
                          (r.status === 'FAIL' || r.status === 'MISSING'),
                      );
                      return fails.length === 0 ? (
                        <span className="text-sm text-emerald-700 dark:text-emerald-400">None</span>
                      ) : (
                        <span className="text-sm font-semibold text-red-700 dark:text-red-400">
                          {fails.length} —{' '}
                          {fails.map((f) => f.requirement?.requirement_name).join(', ')}
                        </span>
                      );
                    },
                  },
                  {
                    label: 'Pending reviews',
                    cells: (d) => {
                      const n = d.detail.compliance_results.filter(
                        (r) => r.status === 'REVIEW_REQUIRED',
                      ).length;
                      return <span className="text-sm">{n === 0 ? 'None' : n}</span>;
                    },
                  },
                ]}
              />

              {/* B. Financial & experience */}
              <SectionTable
                title="B. Financial & experience"
                data={data}
                rows={[
                  {
                    label: 'Turnover',
                    hint: 'Required threshold shown below the value',
                    cells: (d) => (
                      <div>
                        <div className="text-sm font-semibold">
                          {fmtMoney(numOf(d.semantic, ...FIELD_CANDIDATES.turnover))}
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          Required: {displayThreshold(resultFor(d.detail, 'turnover', 'balance sheet')?.requirement?.threshold)}
                        </div>
                      </div>
                    ),
                  },
                  {
                    label: 'Work experience',
                    cells: (d) => (
                      <div>
                        <div className="text-sm font-semibold">
                          {fmtYears(numOf(d.semantic, ...FIELD_CANDIDATES.experience))}
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          Required: {displayThreshold(resultFor(d.detail, 'experience')?.requirement?.threshold)}
                        </div>
                      </div>
                    ),
                  },
                  {
                    label: 'EMD submitted',
                    cells: (d) => (
                      <div>
                        <div className="text-sm font-semibold">
                          {fmtMoney(numOf(d.semantic, ...FIELD_CANDIDATES.emd))}
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          Required: {displayThreshold(resultFor(d.detail, 'emd')?.requirement?.threshold)}
                        </div>
                      </div>
                    ),
                  },
                  {
                    label: 'ITR financial year',
                    cells: (d) => (
                      <div>
                        <div className="font-mono text-sm">
                          {valueOf(d.semantic, ...FIELD_CANDIDATES.itr) ?? '—'}
                        </div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          Expected: {displayThreshold(resultFor(d.detail, 'itr', 'income tax')?.requirement?.threshold)}
                        </div>
                      </div>
                    ),
                  },
                ]}
              />

              {/* C. Statutory information */}
              <SectionTable
                title="C. Statutory information"
                data={data}
                rows={[
                  {
                    label: 'PAN',
                    cells: (d) => (
                      <StatCell
                        data={d}
                        label="PAN"
                        value={d.detail.bidder.pan ?? valueOf(d.semantic, ...FIELD_CANDIDATES.pan)}
                        sourceKeys={['pan']}
                      />
                    ),
                  },
                  {
                    label: 'GSTIN',
                    cells: (d) => (
                      <StatCell
                        data={d}
                        label="GST"
                        value={d.detail.bidder.gstin ?? valueOf(d.semantic, ...FIELD_CANDIDATES.gstin)}
                        sourceKeys={['gst']}
                      />
                    ),
                  },
                  {
                    label: 'Udyam',
                    cells: (d) => (
                      <StatCell
                        data={d}
                        label="Udyam"
                        value={valueOf(d.semantic, ...FIELD_CANDIDATES.udyam)}
                        sourceKeys={['udyam']}
                      />
                    ),
                  },
                  {
                    label: 'CIN',
                    cells: (d) => (
                      <StatCell
                        data={d}
                        label="MCA21"
                        value={valueOf(d.semantic, ...FIELD_CANDIDATES.cin)}
                        sourceKeys={['mca', 'cin']}
                      />
                    ),
                  },
                  {
                    label: 'EPFO',
                    cells: (d) => (
                      <StatCell
                        data={d}
                        label="EPFO"
                        value={valueOf(d.semantic, ...FIELD_CANDIDATES.epfo)}
                        sourceKeys={['epfo']}
                      />
                    ),
                  },
                  {
                    label: 'ISO valid until',
                    cells: (d) => {
                      const v = valueOf(d.semantic, ...FIELD_CANDIDATES.iso);
                      const r = resultFor(d.detail, 'iso');
                      return (
                        <div>
                          <div className="font-mono text-sm">{v ?? '—'}</div>
                          {r && (
                            <div className="mt-1">
                              <StatusBadge status={r.status} />
                            </div>
                          )}
                        </div>
                      );
                    },
                  },
                ]}
              />

              {/* D. Requirement comparison */}
              <section className="mb-6">
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  D. Requirement comparison
                </h3>
                <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="min-w-[220px] bg-slate-50 dark:bg-slate-900/60">
                          Requirement
                        </TableHead>
                        {data.map((d) => (
                          <TableHead
                            key={d.bidId}
                            className="min-w-[210px] bg-slate-50 dark:bg-slate-900/60"
                          >
                            <span className="font-semibold text-slate-800 dark:text-slate-200">
                              {d.legalName}
                            </span>
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {requirementRows.map((row) => (
                        <TableRow key={row.name}>
                          <TableCell className="align-top">
                            <div className="font-medium text-slate-800 dark:text-slate-200">
                              {row.name}
                            </div>
                            <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                              Required: {displayThreshold(row.threshold)}
                            </div>
                          </TableCell>
                          {data.map((d) => {
                            const res =
                              d.detail.compliance_results.find(
                                (r) => r.requirement?.requirement_name === row.name,
                              ) ?? null;
                            const fields = requirementFields(row.name);
                            const actual =
                              fields.length > 0 ? valueOf(d.semantic, ...fields) : null;
                            return (
                              <TableCell key={d.bidId} className="align-top">
                                {res ? (
                                  <div>
                                    <StatusBadge status={res.status} />
                                    {actual && (
                                      <div className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-200">
                                        {actual}
                                      </div>
                                    )}
                                    {!actual && res.explanation && (
                                      <div
                                        className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400"
                                        title={res.explanation}
                                      >
                                        {res.explanation}
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-sm text-slate-400">—</span>
                                )}
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </section>

              {/* E. Documents & evidence */}
              <section className="mb-6">
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  E. Documents &amp; evidence
                </h3>
                <div
                  className="grid gap-4"
                  style={{ gridTemplateColumns: `repeat(${data.length}, minmax(0, 1fr))` }}
                >
                  {data.map((d) => (
                    <div
                      key={d.bidId}
                      className="rounded-lg border border-slate-200 dark:border-slate-800"
                    >
                      <div className="border-b border-slate-200 px-3 py-2 dark:border-slate-800">
                        <Link
                          to={`/app/bids/${d.bidId}`}
                          className="text-sm font-semibold text-brand-800 hover:underline dark:text-brand-300"
                        >
                          {d.legalName}
                        </Link>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          {d.detail.documents.length} document
                          {d.detail.documents.length === 1 ? '' : 's'}
                        </div>
                      </div>
                      <ul className="divide-y divide-slate-100 px-3 dark:divide-slate-800">
                        {d.detail.documents.map((doc) => {
                          const keyVals = d.semantic.entities
                            .filter(
                              (e) =>
                                !e.is_empty &&
                                e.values.some((v) =>
                                  v.sources.some((s) => s.document_id === doc.id),
                                ),
                            )
                            .slice(0, 2);
                          return (
                            <li key={doc.id} className="py-2">
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="truncate text-xs font-medium text-slate-700 dark:text-slate-300">
                                    {doc.document_type}
                                  </div>
                                  <div className="truncate text-xs text-slate-500 dark:text-slate-400">
                                    {doc.filename}
                                  </div>
                                </div>
                                <Link
                                  to={`/app/documents/${doc.id}`}
                                  className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-brand-800 hover:underline dark:text-brand-300"
                                >
                                  <FileText className="h-3 w-3" /> View
                                </Link>
                              </div>
                              <div className="mt-1">
                                <StatusBadge
                                  status={
                                    (doc.processing_status === 'PROCESSED'
                                      ? 'PASS'
                                      : doc.processing_status === 'FAILED'
                                        ? 'FAIL'
                                        : 'REVIEW_REQUIRED') as RequirementStatus
                                  }
                                />
                              </div>
                              {keyVals.length > 0 && (
                                <div className="mt-1 space-y-0.5">
                                  {keyVals.map((e) => (
                                    <div
                                      key={e.field_name}
                                      className="truncate text-xs text-slate-600 dark:text-slate-400"
                                      title={`${e.display_label}: ${e.values[0].normalized_value}`}
                                    >
                                      <span className="font-medium">{e.display_label}:</span>{' '}
                                      {e.values[0].normalized_value}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </div>
              </section>

              {/* F. Risk & integrity */}
              <SectionTable
                title="F. Risk & integrity"
                data={data}
                rows={[
                  {
                    label: 'Risk level',
                    cells: (d) => <RiskBadge level={d.detail.bid.risk_level} />,
                  },
                  {
                    label: 'Risk factors',
                    cells: (d) => {
                      const signals = d.detail.risk?.signals ?? [];
                      return signals.length === 0 ? (
                        <span className="text-sm text-slate-500 dark:text-slate-400">None</span>
                      ) : (
                        <ul className="list-disc space-y-1 pl-4 text-sm">
                          {signals.map((s) => (
                            <li key={s.code}>{s.message}</li>
                          ))}
                        </ul>
                      );
                    },
                  },
                  {
                    label: 'Integrity signals',
                    cells: (d) =>
                      d.integrity.length === 0 ? (
                        <span className="text-sm text-slate-500 dark:text-slate-400">
                          No integrity signals detected.
                        </span>
                      ) : (
                        <ul className="space-y-1.5">
                          {d.integrity.map((f) => (
                            <li key={f.id} className="text-sm">
                              <StatusBadge
                                status={(f.severity === 'ELEVATED' ? 'REVIEW_REQUIRED' : 'REVIEW_REQUIRED') as RequirementStatus}
                              />{' '}
                              <span className="font-medium">{f.title}</span>
                            </li>
                          ))}
                        </ul>
                      ),
                  },
                  {
                    label: 'Evidence-based explanation',
                    cells: (d) => (
                      <p className="text-sm text-slate-600 dark:text-slate-400">
                        {d.detail.risk?.explanation ?? '—'}
                      </p>
                    ),
                  },
                ]}
              />
              <p className="mb-2 flex items-start gap-2 text-xs text-slate-500 dark:text-slate-400">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Integrity signals are prompts for officer review — they are not findings of
                misconduct and never decide an outcome on their own.
              </p>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
