import * as React from 'react';
import { cn } from '../../lib/utils';

type BadgeVariant =
  | 'default'
  | 'secondary'
  | 'outline'
  | 'success'
  | 'destructive'
  | 'warning'
  | 'info'
  | 'muted';

const variantClasses: Record<BadgeVariant, string> = {
  default: 'bg-brand-800 text-white',
  secondary: 'bg-slate-100 text-slate-700',
  outline: 'border border-slate-300 text-slate-600 bg-white',
  success: 'bg-emerald-100 text-emerald-800 border border-emerald-200',
  destructive: 'bg-red-100 text-red-800 border border-red-200',
  warning: 'bg-amber-100 text-amber-900 border border-amber-200',
  info: 'bg-sky-100 text-sky-800 border border-sky-200',
  muted: 'bg-slate-100 text-slate-500 border border-slate-200',
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium',
        variantClasses[variant],
        className,
      )}
      {...props}
    />
  ),
);
Badge.displayName = 'Badge';
