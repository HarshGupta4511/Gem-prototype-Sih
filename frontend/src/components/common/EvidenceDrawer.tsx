import { FileText, Scale, Database, ShieldCheck } from 'lucide-react';
import { Sheet, SheetContent } from '../ui/sheet';
import { StatusBadge, MethodBadge } from './badges';
import { Separator } from '../ui/misc';
import { labelize } from '../../lib/utils';
import type { ComplianceResult } from '../../types';

function Row({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="mt-0.5 shrink-0 text-slate-400">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</div>
        <div className="mt-1 text-sm text-slate-800">{children}</div>
      </div>
    </div>
  );
}

/**
 * Evidence Explorer — right-side drawer showing everything behind one
 * compliance result: claim, evidence, rule, source, timestamp.
 */
export function EvidenceDrawer({
  result,
  onClose,
}: {
  result: ComplianceResult | null;
  onClose: () => void;
}) {
  return (
    <Sheet open={!!result} onOpenChange={(o) => !o && onClose()}>
      <SheetContent title={result ? result.requirement?.requirement_name ?? 'Evidence' : 'Evidence'}>
        {result && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={result.status} />
              {result.overridden && (
                <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-800 border border-purple-200">
                  Officer overridden (was {labelize(result.original_status)})
                </span>
              )}
              <span className="ml-auto text-xs text-slate-500">
                Weight <strong className="text-slate-800">{result.weight}</strong> · Contribution{' '}
                <strong className="text-slate-800">{result.weighted_contribution.toFixed(1)}</strong>
              </span>
            </div>

            <Row icon={<FileText className="h-4 w-4" />} label="Claim / explanation">
              <p className="leading-relaxed">{result.explanation}</p>
            </Row>

            <Separator />

            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Evidence</div>
              {result.evidence.length === 0 ? (
                <p className="text-sm text-slate-500">No documentary evidence linked to this result.</p>
              ) : (
                <ul className="space-y-2">
                  {result.evidence.map((e, i) => (
                    <li key={i} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                      <div className="font-medium text-slate-800">
                        {e.filename}
                        {e.page ? <span className="text-slate-500"> · Page {e.page}</span> : null}
                      </div>
                      <div className="mt-0.5 text-slate-600">
                        <span className="font-mono text-xs text-slate-500">{e.field}:</span>{' '}
                        <span className="font-mono text-[13px] font-medium text-slate-900">{e.value}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <Row icon={<Scale className="h-4 w-4" />} label="Rule applied (deterministic rules engine)">
              <code className="block rounded-md bg-slate-900 px-3 py-2 font-mono text-xs text-slate-100">{result.rule_applied}</code>
            </Row>

            <Row icon={<Database className="h-4 w-4" />} label="Source">
              {result.source}
            </Row>

            <Row icon={<ShieldCheck className="h-4 w-4" />} label="Evaluated at">
              {new Date(result.created_at).toLocaleString('en-IN')}
            </Row>

            {result.override_comment && (
              <div className="rounded-md border border-purple-200 bg-purple-50 px-3 py-2 text-sm">
                <div className="text-xs font-semibold uppercase tracking-wider text-purple-700">Officer override</div>
                <p className="mt-1 text-purple-900">{result.override_comment}</p>
              </div>
            )}

            <div className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-500">
              Every compliance result is computed by the deterministic rules engine from document evidence and
              verification sources. It never represents a final qualification decision — that authority stays with
              the Procurement Officer.
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
