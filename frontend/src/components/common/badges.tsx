import { Badge } from '../ui/badge';
import { cn } from '../../lib/utils';
import type {
  BidStatus,
  DocProcessingStatus,
  DocumentType,
  ExtractionMethod,
  OfficerDecision,
  Recommendation,
  RequirementStatus,
  RiskLevel,
  VerificationStatus,
} from '../../types';
import { labelize } from '../../lib/utils';

const statusVariant: Record<RequirementStatus, 'success' | 'destructive' | 'warning' | 'muted'> = {
  PASS: 'success',
  FAIL: 'destructive',
  MISSING: 'warning',
  EXPIRED: 'warning',
  MISMATCH: 'warning',
  REVIEW_REQUIRED: 'warning',
  NOT_APPLICABLE: 'muted',
};

export function StatusBadge({ status, className }: { status: RequirementStatus | null | undefined; className?: string }) {
  if (!status) return <Badge variant="muted" className={className}>—</Badge>;
  return (
    <Badge variant={statusVariant[status]} className={className}>
      {labelize(status)}
    </Badge>
  );
}

export function RiskBadge({ level, className }: { level: RiskLevel | null | undefined; className?: string }) {
  if (!level) return <Badge variant="muted" className={className}>—</Badge>;
  const cls: Record<RiskLevel, string> = {
    LOW: 'bg-emerald-100 text-emerald-800 border border-emerald-200',
    MEDIUM: 'bg-amber-100 text-amber-900 border border-amber-200',
    HIGH: 'bg-orange-100 text-orange-800 border border-orange-300',
    CRITICAL: 'bg-red-800 text-white border border-red-900',
  };
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold',
        cls[level],
        className,
      )}
    >
      {level} RISK
    </span>
  );
}

const verificationVariant: Record<VerificationStatus, 'success' | 'destructive' | 'warning' | 'info' | 'muted'> = {
  VERIFIED: 'success',
  MISMATCH: 'warning',
  NOT_FOUND: 'destructive',
  EXPIRED: 'warning',
  UNAVAILABLE: 'info',
  REVIEW_REQUIRED: 'warning',
};

export function VerificationBadge({ status, className }: { status: VerificationStatus | null | undefined; className?: string }) {
  if (!status) return <Badge variant="muted" className={className}>—</Badge>;
  return (
    <Badge variant={verificationVariant[status]} className={className}>
      {labelize(status)}
    </Badge>
  );
}

const bidStatusVariant: Record<BidStatus, 'success' | 'destructive' | 'warning' | 'info' | 'muted' | 'default'> = {
  DRAFT: 'muted',
  SUBMITTED: 'info',
  UNDER_REVIEW: 'warning',
  APPROVED: 'success',
  REJECTED: 'destructive',
  ESCALATED: 'warning',
  CLARIFICATION_REQUESTED: 'info',
};

export function BidStatusBadge({ status, className }: { status: BidStatus | null | undefined; className?: string }) {
  if (!status) return <Badge variant="muted" className={className}>—</Badge>;
  return (
    <Badge variant={bidStatusVariant[status]} className={className}>
      {labelize(status)}
    </Badge>
  );
}

export function RecommendationBadge({ rec, className }: { rec: Recommendation | null | undefined; className?: string }) {
  if (!rec) return <Badge variant="muted" className={className}>Not generated</Badge>;
  const variant: Record<Recommendation, 'success' | 'warning' | 'destructive' | 'info'> = {
    PROCEED: 'success',
    PROCEED_WITH_CONDITIONS: 'info',
    REVIEW_REQUIRED: 'warning',
    NOT_RECOMMENDED: 'destructive',
  };
  return (
    <Badge variant={variant[rec]} className={className}>
      {labelize(rec)}
    </Badge>
  );
}

export function DecisionBadge({ decision, className }: { decision: OfficerDecision | null | undefined; className?: string }) {
  if (!decision)
    return (
      <Badge variant="outline" className={className}>
        Pending decision
      </Badge>
    );
  const variant: Record<OfficerDecision, 'success' | 'destructive' | 'warning' | 'info'> = {
    APPROVE: 'success',
    REJECT: 'destructive',
    ESCALATE: 'warning',
    REQUEST_CLARIFICATION: 'info',
  };
  return (
    <Badge variant={variant[decision]} className={className}>
      {labelize(decision)}
    </Badge>
  );
}

const docStatusVariant: Record<DocProcessingStatus, 'info' | 'warning' | 'success' | 'destructive'> = {
  UPLOADED: 'info',
  PROCESSING: 'warning',
  PROCESSED: 'success',
  REVIEW_REQUIRED: 'warning',
  FAILED: 'destructive',
};

export function DocStatusBadge({ status, className }: { status: DocProcessingStatus; className?: string }) {
  return (
    <Badge variant={docStatusVariant[status]} className={className}>
      {labelize(status)}
    </Badge>
  );
}

const methodVariant: Record<ExtractionMethod, 'success' | 'info' | 'secondary' | 'muted'> = {
  REGEX: 'success',
  OCR: 'info',
  LLM: 'secondary',
  MANUAL: 'muted',
};

export function MethodBadge({ method, className }: { method: ExtractionMethod; className?: string }) {
  return (
    <Badge variant={methodVariant[method]} className={className}>
      {method}
    </Badge>
  );
}

export function DocTypeBadge({ docType, className }: { docType: DocumentType; className?: string }) {
  // UNCLASSIFIED means the system could not confidently identify the type —
  // never invent one; show "Type Not Detected" instead.
  const label = docType === 'UNCLASSIFIED' ? 'Type Not Detected' : labelize(docType);
  return (
    <Badge variant="outline" className={cn('font-mono text-[11px]', className)}>
      {label}
    </Badge>
  );
}
