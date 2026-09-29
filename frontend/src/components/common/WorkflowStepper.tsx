import * as React from 'react';
import { Check } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface WorkflowStep {
  key: string;
  label: string;
  hint: string;
  icon: React.ReactNode;
  done: boolean;
  /** tab value to jump to on click; omit for display-only steps */
  tab?: string;
}

/**
 * Guided evaluation workflow: Documents -> Verification -> Compliance ->
 * Risk -> Recommendation -> Decision. The first incomplete step
 * is highlighted as "next". Steps with a `tab` jump to that tab on click.
 */
export function WorkflowStepper({
  steps,
  onStepClick,
}: {
  steps: WorkflowStep[];
  onStepClick: (tab: string) => void;
}) {
  const currentIdx = steps.findIndex((s) => !s.done);
  const allDone = currentIdx === -1;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-700">Evaluation workflow</p>
        <p className="text-xs text-slate-500">
          {allDone
            ? 'All steps complete — ready for officer decision'
            : `Next: ${steps[currentIdx].label} — ${steps[currentIdx].hint}`}
        </p>
      </div>
      <ol className="flex min-w-[680px] items-start">
        {steps.map((step, i) => {
          const isCurrent = i === currentIdx;
          const clickable = !!step.tab;
          const circle = (
            <span
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold',
                step.done
                  ? 'border-emerald-600 bg-emerald-600 text-white'
                  : isCurrent
                    ? 'border-indigo-600 bg-indigo-50 text-indigo-700'
                    : 'border-slate-300 bg-white text-slate-400',
              )}
            >
              {step.done ? <Check className="h-4 w-4" /> : step.icon}
            </span>
          );
          return (
            <li key={step.key} className="flex flex-1 items-start last:flex-none">
              {clickable ? (
                <button
                  type="button"
                  onClick={() => onStepClick(step.tab as string)}
                  title={`Go to ${step.label}`}
                  className="group flex flex-col items-center gap-1 rounded-md px-1 py-1 text-center hover:bg-slate-50"
                >
                  {circle}
                  <span
                    className={cn(
                      'whitespace-nowrap text-xs font-medium',
                      step.done
                        ? 'text-emerald-700'
                        : isCurrent
                          ? 'text-indigo-700 group-hover:underline'
                          : 'text-slate-500 group-hover:underline',
                    )}
                  >
                    {i + 1}. {step.label}
                  </span>
                </button>
              ) : (
                <div className="flex flex-col items-center gap-1 px-1 py-1 text-center">
                  {circle}
                  <span
                    className={cn(
                      'whitespace-nowrap text-xs font-medium',
                      step.done ? 'text-emerald-700' : 'text-slate-500',
                    )}
                  >
                    {i + 1}. {step.label}
                  </span>
                </div>
              )}
              {i < steps.length - 1 && (
                <div
                  aria-hidden
                  className={cn(
                    'mx-1 mt-4 h-0.5 flex-1 rounded',
                    step.done ? 'bg-emerald-500' : 'bg-slate-200',
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
