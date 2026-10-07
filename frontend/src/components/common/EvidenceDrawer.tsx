import * as React from 'react';
import { ChevronDown, FileText, SearchCheck, ShieldCheck } from 'lucide-react';
import { Sheet, SheetContent } from '../ui/sheet';
import { StatusBadge } from './badges';
import { Separator } from '../ui/misc';
import { labelize, formatDateTime } from '../../lib/utils';
import {
  displayActualValue,
  displaySource,
  displayThreshold,
} from '../../lib/compliance-display';
import type { ComplianceResult, Document } from '../../types';

function Row({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 shrink-0 text-slate-400 dark:text-slate-500">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</div>
        <div className="mt-1 text-sm text-slate-800 dark:text-slate-200">{children}</div>
      </div>
    </div>
  );
}

type EvidenceShape = ComplianceResult['evidence'][number] & {
  bidder_value?: string | null;
  document_value?: string | null;
  document_type?: string | null;
  identifier?: string | null;
  source?: string | null;
};

function EvidenceItemCard({ e, documents }: { e: EvidenceShape; documents: Document[] }) {
  // Identity-match evidence: bidder declaration vs document value.
  if (e.bidder_value != null || e.document_value != null) {
    return (
      <li className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 px-3 py-2.5 text-sm space-y-1.5">
        <div className="font-medium text-slate-800 dark:text-slate-200">
          {e.document_type ? labelize(e.document_type) : 'Document comparison'}
          <span className="ml-1.5 font-normal text-slate-500 dark:text-slate-400 text-xs">· {labelize(e.field)}</span>
        </div>
        <div className="grid grid-cols-1 gap-1.5">
          <div>
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Submitted (bidder record): </span>
            <span className="text-[13px] font-medium text-slate-900 dark:text-slate-100">{e.bidder_value ?? '—'}</span>
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Document value: </span>
            <span className="text-[13px] font-medium text-slate-900 dark:text-slate-100">{e.document_value ?? '—'}</span>
          </div>
        </div>
      </li>
    );
  }

  // Verification-source evidence: statutory/mock portal check.
  const src = typeof e.source === 'string' && e.source.startsWith('verification:')
    ? e.source.slice('verification:'.length)
    : null;
  if (src) {
    return (
      <li className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 px-3 py-2.5 text-sm space-y-1.5">
        <div className="font-medium text-slate-800 dark:text-slate-200">
          Verified via {displaySource(src)} (mock data — not a live government registry)
        </div>
        {e.identifier && (
          <div>
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Identifier checked: </span>
            <span className="font-mono text-[13px] font-medium text-slate-900 dark:text-slate-100">{e.identifier}</span>
          </div>
        )}
        <div>
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Verified value: </span>
          <span className="text-[13px] font-medium text-slate-900 dark:text-slate-100">
            {displayActualValue(e.value, e.field ?? '')}
          </span>
        </div>
      </li>
    );
  }

  // Regular document evidence: extracted/submitted value from a file.
  const doc = e.document_id != null ? documents.find((d) => d.id === e.document_id) : undefined;
  return (
    <li className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 px-3 py-2.5 text-sm space-y-1.5">
      <div className="font-medium text-slate-800 dark:text-slate-200">
        {e.filename || 'Submitted document'}
        {e.page ? <span className="font-normal text-slate-500 dark:text-slate-400 text-xs"> · Page {e.page}</span> : null}
        {doc?.document_type && (
          <span className="ml-1.5 font-normal text-slate-500 dark:text-slate-400 text-xs">· {labelize(doc.document_type)}</span>
        )}
      </div>
      <div>
        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">Submitted {labelize(e.field)}: </span>
        <span className="text-[13px] font-medium text-slate-900 dark:text-slate-100">
          {displayActualValue(e.value, e.field ?? '')}
        </span>
      </div>
    </li>
  );
}

/**
 * Evidence panel — right-side drawer explaining WHY a compliance result was
 * produced: the finding, the document(s), submitted vs verified values.
 * Human-readable by default; raw rule expressions and raw JSON live behind
 * "View Technical Details".
 */
export function EvidenceDrawer({
  result,
  documents = [],
  onClose,
}: {
  result: ComplianceResult | null;
  documents?: Document[];
  onClose: () => void;
}) {
  const [showTechnical, setShowTechnical] = React.useState(false);
  React.useEffect(() => {
    setShowTechnical(false);
  }, [result?.id]);
  return (
    <Sheet open={!!result} onOpenChange={(o) => !o && onClose()}>
      <SheetContent title={result ? result.requirement?.requirement_name ?? 'Evidence' : 'Evidence'}>
        {result && (
          <div className="space-y-6">
            {/* RULE EVALUATION — compact, human-readable summary */}
            <div className="rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950 px-4 py-3">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-400 mb-3">
                Rule Evaluation
              </div>
              <dl className="space-y-2.5 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-xs font-semibold text-slate-500 dark:text-slate-400 shrink-0">Requirement</dt>
                  <dd className="text-right font-semibold text-slate-900 dark:text-slate-100">
                    {result.requirement?.requirement_name ?? `Requirement #${result.requirement_id}`}
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-xs font-semibold text-slate-500 dark:text-slate-400 shrink-0">Criteria</dt>
                  <dd className="text-right text-slate-800 dark:text-slate-200">
                    {displayThreshold(result.requirement?.threshold)}
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-xs font-semibold text-slate-500 dark:text-slate-400 shrink-0">Actual value</dt>
                  <dd className="text-right font-medium text-slate-900 dark:text-slate-100">
                    {displayActualValue(result.evidence?.[0]?.value, result.evidence?.[0]?.field ?? '')}
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-xs font-semibold text-slate-500 dark:text-slate-400 shrink-0">Rule result</dt>
                  <dd>
                    <StatusBadge status={result.status} />
                    {result.overridden && (
                      <span className="block text-right text-[10px] font-bold text-blue-700 dark:text-blue-400 mt-1">
                        OVERRIDDEN
                      </span>
                    )}
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <dt className="text-xs font-semibold text-slate-500 dark:text-slate-400 shrink-0">Evaluation</dt>
                  <dd className="text-right text-xs font-semibold text-slate-700 dark:text-slate-200">
                    Deterministic Rules Engine
                  </dd>
                </div>
              </dl>
            </div>

            <Row icon={<SearchCheck className="h-4 w-4" />} label="Finding">
              <p className="leading-relaxed">{result.explanation || 'No explanation recorded.'}</p>
            </Row>

            <Separator />

            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5" /> Evidence
              </div>
              {result.evidence.length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">No documentary evidence linked to this result.</p>
              ) : (
                <ul className="space-y-2">
                  {(result.evidence as EvidenceShape[]).map((e, i) => (
                    <EvidenceItemCard key={i} e={e} documents={documents} />
                  ))}
                </ul>
              )}
            </div>

            {/* Source + evaluated-at, human-readable */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Source</div>
                <div className="mt-1 text-slate-800 dark:text-slate-200">{displaySource(result.source)}</div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Evaluated At</div>
                <div className="mt-1 text-slate-800 dark:text-slate-200">{formatDateTime(result.created_at)}</div>
              </div>
            </div>

            {result.override_comment && (
              <div className="rounded-md border border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-950/60 px-3 py-2 text-sm">
                <div className="text-xs font-semibold uppercase tracking-wider text-purple-700 dark:text-purple-400">Officer override</div>
                <p className="mt-1 text-purple-900 dark:text-purple-300">{result.override_comment}</p>
              </div>
            )}

            {/* Technical payload, collapsed by default */}
            <div className="rounded-md border border-slate-200 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setShowTechnical((s) => !s)}
                className="flex w-full items-center justify-between px-3 py-2 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/70"
              >
                <span>View Technical Details</span>
                <ChevronDown className={`h-4 w-4 transition-transform ${showTechnical ? 'rotate-180' : ''}`} />
              </button>
              {showTechnical && (
                <div className="border-t border-slate-200 dark:border-slate-800 px-3 py-2 space-y-2">
                  {result.rule_applied && (
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Rule Applied</div>
                      <pre className="mt-1 overflow-x-auto rounded bg-slate-900 p-2 font-mono text-[11px] text-slate-100">
                        {result.rule_applied}
                      </pre>
                    </div>
                  )}
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Raw Evidence Payload</div>
                    <pre className="mt-1 max-h-56 overflow-auto rounded bg-slate-900 p-2 font-mono text-[11px] text-slate-100">
                      {JSON.stringify(result.evidence, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-md bg-slate-50 dark:bg-slate-900 px-3 py-2 text-xs text-slate-500 dark:text-slate-400 flex items-start gap-2">
              <ShieldCheck className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500 mt-0.5" />
              <span>
                Rule-based evaluation: this result was computed by the deterministic rules engine
                from the evidence above. The final qualification decision stays with the
                Procurement Officer.
              </span>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
