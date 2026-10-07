import * as React from 'react';
import { cn } from '../../lib/utils';

export const Separator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement> & { orientation?: 'horizontal' | 'vertical' }>(
  ({ className, orientation = 'horizontal', ...props }, ref) => (
    <div
      ref={ref}
      role="separator"
      className={cn(
        'shrink-0 bg-slate-200 dark:bg-slate-700',
        orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px',
        className,
      )}
      {...props}
    />
  ),
);
Separator.displayName = 'Separator';

export const Skeleton = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('animate-pulse rounded-md bg-slate-200 dark:bg-slate-700', className)} {...props} />
  ),
);
Skeleton.displayName = 'Skeleton';

export const Progress = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { value: number; barClassName?: string }
>(({ className, value, barClassName, ...props }, ref) => (
  <div ref={ref} role="progressbar" className={cn('relative h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700', className)} {...props}>
    <div
      className={cn('h-full rounded-full bg-brand-700 transition-all', barClassName)}
      style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
    />
  </div>
));
Progress.displayName = 'Progress';
