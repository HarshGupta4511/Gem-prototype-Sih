// ============================================================================
// CPCL BidVerify — shared TypeScript types mirroring CONTRACT.md §§3–4
// ============================================================================

export type RequirementStatus =
  | 'PASS'
  | 'FAIL'
  | 'MISSING'
  | 'EXPIRED'
  | 'MISMATCH'
  | 'REVIEW_REQUIRED'
  | 'NOT_APPLICABLE';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type VerificationStatus =
  | 'VERIFIED'
  | 'MISMATCH'
  | 'NOT_FOUND'
  | 'EXPIRED'
  | 'UNAVAILABLE'
  | 'REVIEW_REQUIRED';

export type BidStatus =
  | 'DRAFT'
  | 'SUBMITTED'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'REJECTED'
  | 'ESCALATED'
  | 'CLARIFICATION_REQUESTED';

export type DocProcessingStatus = 'UPLOADED' | 'PROCESSING' | 'PROCESSED' | 'REVIEW_REQUIRED' | 'FAILED';

export type DocumentType =
  | 'BID_DOSSIER'
  | 'PAN_CERTIFICATE'
  | 'GST_CERTIFICATE'
  | 'GST_RETURN'
  | 'UDYAM_CERTIFICATE'
  | 'ITR'
  | 'TURNOVER_CERTIFICATE'
  | 'EXPERIENCE_CERTIFICATE'
  | 'OEM_AUTHORIZATION'
  | 'EPFO_CERTIFICATE'
  | 'ESIC_CERTIFICATE'
  | 'MII_DECLARATION'
  | 'STARTUP_INDIA_CERTIFICATE'
  | 'NSIC_CERTIFICATE'
  | 'DIGILOCKER_DOCUMENT'
  | 'AUDITED_FINANCIAL_STATEMENT'
  | 'OTHER'
  | 'UNCLASSIFIED';

export type ExtractionMethod = 'REGEX' | 'OCR' | 'LLM' | 'MANUAL';

export type RuleType =
  | 'EXISTENCE'
  | 'EQUALITY'
  | 'MATCH'
  | 'MINIMUM'
  | 'MAXIMUM'
  | 'DATE_VALIDITY'
  | 'DATE_RANGE'
  | 'CONTAINS'
  | 'BOOLEAN'
  | 'REGISTRATION_STATUS'
  | 'IDENTITY_MATCH'
  | 'DOCUMENT_REQUIRED'
  | 'CUSTOM_RULE';

export type OfficerDecision = 'APPROVE' | 'REJECT' | 'ESCALATE' | 'REQUEST_CLARIFICATION';

export type AdapterSource =
  | 'GSTN'
  | 'UDYAM'
  | 'PAN_IT'
  | 'MCA21'
  | 'EPFO'
  | 'ESIC'
  | 'STARTUP_INDIA'
  | 'NSIC'
  | 'DIGILOCKER'
  | 'BLACKLIST';

export type Recommendation =
  | 'PROCEED'
  | 'PROCEED_WITH_CONDITIONS'
  | 'REVIEW_REQUIRED'
  | 'NOT_RECOMMENDED';

export type Role = 'PROCUREMENT_OFFICER' | 'VERIFIER' | 'AUDITOR' | 'ADMIN';

export type RequirementCategory =
  | 'STATUTORY'
  | 'FINANCIAL'
  | 'EXPERIENCE'
  | 'TECHNICAL'
  | 'REGISTRATION'
  | 'LOCAL_CONTENT'
  | 'OEM'
  | 'INTEGRITY'
  | 'DOCUMENT';

export type TenderStatus = 'DRAFT' | 'OPEN' | 'CLOSED' | 'AWARDED';

export type TenderType = 'GOODS' | 'SERVICES' | 'WORKS';

export type BidType = 'SINGLE_PACKET' | 'TWO_PACKET';

export type EmbeddingStatus = 'PENDING' | 'INDEXED' | 'FAILED';

export type ClarificationStatus = 'DRAFT' | 'SENT' | 'RESPONDED';

// ---------------------------------------------------------------- entities

export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  department: string;
  created_at: string;
}

export interface Tender {
  id: number;
  tender_number: string;
  title: string;
  organization: string;
  department: string;
  description: string;
  issue_date: string;
  closing_date: string;
  estimated_value_inr: number;
  tender_type: TenderType | null;
  bid_type: BidType | null;
  emd_amount_inr: number | null;
  delivery_period: string | null;
  place_of_delivery: string | null;
  status: TenderStatus;
  created_at: string;
}

export interface TenderRequirement {
  id: number;
  tender_id: number;
  requirement_name: string;
  category: RequirementCategory;
  description: string;
  mandatory: boolean;
  rule_type: RuleType;
  rule_config: Record<string, unknown>;
  threshold: string | null;
  expected_value: string | null;
  verification_source: AdapterSource | null;
  weight: number;
  policy_reference: string | null;
  created_at: string;
}

export interface Bidder {
  id: number;
  tender_id: number;
  legal_name: string;
  trade_name: string | null;
  pan: string | null;
  gstin: string | null;
  udyam: string | null;
  cin: string | null;
  registered_address: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  bid_status: BidStatus;
  created_at: string;
}

export interface RiskSignal {
  code: string;
  message: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  weight?: number;
}

export interface RiskAssessment {
  id: number;
  bid_id: number;
  risk_level: RiskLevel;
  risk_score: number;
  signals: RiskSignal[];
  explanation: string;
  created_at: string;
}

export interface BidSubmission {
  id: number;
  tender_id: number;
  bidder_id: number;
  submitted_at: string;
  status: BidStatus;
  compliance_score: number | null;
  risk_level: RiskLevel | null;
  risk_reasons: string[] | null;
  risk_score: number | null;
  recommendation: Recommendation | null;
  recommendation_reason: string | null;
  recommendation_evidence: unknown;
  officer_decision: OfficerDecision | null;
  officer_decision_reason: string | null;
  decided_by: number | null;
  decided_at: string | null;
}

export interface BidSummary {
  bid_id: number;
  legal_name: string;
  bid_status: BidStatus;
  compliance_score: number | null;
  risk_level: RiskLevel | null;
  recommendation: Recommendation | null;
  officer_decision: OfficerDecision | null;
  submitted_at: string;
}

export interface Document {
  id: number;
  bid_id: number;
  document_type: DocumentType;
  filename: string;
  file_hash: string;
  file_size: number;
  mime_type: string;
  upload_time: string;
  processing_status: DocProcessingStatus;
  extraction_confidence: number | null;
  page_count: number | null;
  ocr_used: boolean;
  error: string | null;
}

export interface ExtractedField {
  id: number;
  document_id: number;
  field_name: string;
  field_value: string;
  normalized_value: string;
  confidence: number;
  extraction_method: ExtractionMethod;
  page_number: number | null;
}

export interface VerificationCheck {
  id: number;
  bid_id: number;
  requirement_id: number | null;
  source: AdapterSource;
  identifier: string;
  request_payload: Record<string, unknown> | null;
  response_payload: Record<string, unknown> | null;
  verification_status: VerificationStatus;
  verified_at: string;
  confidence: number;
  is_mock: boolean;
  evidence_reference: string | null;
}

export interface EvidenceItem {
  document_id: number | null;
  filename: string;
  page: number | null;
  field: string;
  value: string;
}

export interface ComplianceResult {
  id: number;
  bid_id: number;
  requirement_id: number;
  requirement?: TenderRequirement;
  status: RequirementStatus;
  weight: number;
  weighted_contribution: number;
  evidence: EvidenceItem[];
  explanation: string;
  rule_applied: string;
  source: string;
  confidence: number;
  overridden: boolean;
  override_comment: string | null;
  original_status: RequirementStatus | null;
  created_at: string;
}

export interface Clarification {
  id: number;
  bid_id: number;
  subject: string;
  body: string;
  status: ClarificationStatus;
  created_at: string;
  sent_at: string | null;
}

export interface OverrideRecord {
  id: number;
  bid_id: number;
  target_type: 'COMPLIANCE_RESULT' | 'VERIFICATION';
  target_id: number;
  original_status: string;
  officer_comment: string;
  supporting_document_id: number | null;
  created_by: number;
  created_at: string;
}

export interface AuditLog {
  id: number;
  user_id: number | null;
  user_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  timestamp: string;
  previous_hash: string;
  current_hash: string;
  metadata: Record<string, unknown> | null;
  target_label?: string | null;
}

// A citable authoritative policy record produced by policy retrieval for a
// compliance finding. Each record traces UI -> chunk -> source document ->
// official URL -> exact rule/section/clause.
export interface PolicyCitation {
  title: string;
  authority: string;
  source_url: string;
  document_type: string;
  version: string;
  publication_date: string;
  effective_date: string;
  section: string;
  why_relevant: string;
  excerpt: string;
  score: number;
}

export interface RecommendationResult {
  recommendation: Recommendation;
  reason: string;
  evidence: unknown[];
  policy_context: PolicyCitation[];
  provider: string;
}

// ------------------------------------------------------- composite responses

export interface DashboardMetrics {
  total_tenders: number;
  active_tenders: number;
  total_bids: number;
  pending_reviews: number;
  high_risk_bids: number;
  documents_processed: number;
  avg_compliance_score: number;
  verification_issues: number;
}

export interface DashboardData {
  metrics: DashboardMetrics;
  charts: {
    compliance_distribution: { range: string; count: number }[];
    risk_distribution: { level: string; count: number }[];
    verification_status: { status: string; count: number }[];
    tender_bidder_comparison: { tender: string; avg_score: number }[];
    document_processing: { status: string; count: number }[];
  };
}

export interface TenderListItem extends Tender {
  bidder_count: number;
  pending_reviews: number;
  avg_compliance: number | null;
  high_risk_count: number;
}

export interface TenderBidderRow {
  bid_id: number;
  legal_name: string;
  trade_name: string | null;
  pan: string | null;
  gstin: string | null;
  bid_status: BidStatus;
  compliance_score: number | null;
  risk_level: RiskLevel | null;
  recommendation: Recommendation | null;
  officer_decision: OfficerDecision | null;
  submitted_at: string;
}

export interface TenderDetail {
  tender: Tender;
  requirements: TenderRequirement[];
  bidders: TenderBidderRow[];
  stats: {
    bidder_count: number;
    avg_compliance: number | null;
    high_risk_count: number;
    pending_reviews: number;
  };
}

export interface ComparisonData {
  requirements: { id: number; requirement_name: string }[];
  bidders: { bid_id: number; legal_name: string; compliance_score: number | null; risk_level: RiskLevel | null }[];
  matrix: { requirement_id: number; requirement_name: string; results: Record<string, RequirementStatus> }[];
}

export interface BidDetail {
  bid: BidSubmission;
  bidder: Bidder;
  tender: { id: number; tender_number: string; title: string };
  documents: Document[];
  compliance_results: ComplianceResult[];
  risk: RiskAssessment | null;
  verification_checks: VerificationCheck[];
  recommendation: {
    recommendation: Recommendation | null;
    reason: string | null;
    evidence: unknown;
  };
  overrides: OverrideRecord[];
  clarifications: Clarification[];
  audit: AuditLog[];
}

export interface AuditVerifyResult {
  valid: boolean;
  checked: number;
  broken_at: { id: number; expected: string; actual: string } | null;
}

export interface ProviderStatus {
  llm_provider: string;
  ocr_available: boolean;
  db_dialect: string;
  embedding_path: string;
}

// ------------------------------------------------------------ request shapes

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface RequirementDraft {
  requirement_name: string;
  category: RequirementCategory;
  description?: string | null;
  mandatory: boolean;
  rule_type: RuleType;
  rule_config?: Record<string, unknown>;
  threshold?: string | null;
  expected_value?: string | null;
  verification_source?: AdapterSource | null;
  weight: number;
  policy_reference?: string | null;
}

export interface CreateTenderRequest {
  tender_number: string;
  title: string;
  organization: string;
  department: string;
  description: string;
  /** Accepted for backwards compatibility; the backend always uses the server creation date. */
  issue_date?: string;
  closing_date: string;
  estimated_value_inr: number;
  tender_type?: TenderType | null;
  bid_type?: BidType | null;
  emd_amount_inr?: number | null;
  delivery_period?: string | null;
  place_of_delivery?: string | null;
  requirements?: RequirementDraft[];
}

/** One AI-suggested requirement — advisory; the officer reviews before use. */
export interface SuggestedRequirement {
  requirement_name: string;
  threshold?: string | null;
  mandatory: boolean;
  weight: number;
  description?: string | null;
}

export interface SuggestRequirementsRequest {
  title: string;
  description?: string | null;
  department?: string | null;
  organization?: string | null;
  tender_type?: string | null;
  bid_type?: string | null;
  estimated_value_inr?: number | null;
  delivery_period?: string | null;
  place_of_delivery?: string | null;
}

export interface CreateBidRequest {
  tender_id: number;
  legal_name: string;
  trade_name?: string;
  pan?: string;
  gstin?: string;
  udyam?: string;
  cin?: string;
  registered_address?: string;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
}

export interface OfficerDecisionRequest {
  bid_id: number;
  decision: OfficerDecision;
  reason?: string;
}

export interface OverrideRequest {
  target_type: 'COMPLIANCE_RESULT' | 'VERIFICATION';
  target_id: number;
  officer_comment: string;
  supporting_document_id?: number;
}

export type ReportStatus =
  | 'DRAFT'
  | 'GENERATED'
  | 'SENT_TO_OFFICER'
  | 'UNDER_REVIEW'
  | 'DECISION_MADE';

export interface ReportObservation {
  text: string;
  added_by: string | null;
  added_at: string | null;
}

export interface ReportTimelineEvent {
  action: string;
  status_after: ReportStatus;
  actor: string | null;
  at: string | null;
}

export interface VerificationReportData {
  bid_id: number;
  generated_at: string | null;
  compliance_score: number | null;
  bid_info: {
    tender_number: string | null;
    tender_title: string | null;
    bidder_name: string | null;
    submission_date: string | null;
  };
  documents: {
    submitted_count: number;
    processed_count: number;
    items: {
      id: number;
      file_name: string;
      document_type: string;
      status: string;
      extracted_field_count: number;
    }[];
    issues: {
      id: number;
      file_name: string;
      document_type: string;
      status: string;
    }[];
  };
  extracted_fields: {
    total: number;
    items: {
      field_name: string;
      field_value: string | null;
      document_name: string | null;
      document_type: string | null;
      extraction_method: string;
    }[];
  };
  verification: {
    source: string;
    identifier: string;
    status: string;
    observation: string | null;
    is_mock: boolean;
    verified_at: string | null;
  }[];
  compliance: {
    requirement: string;
    result: string;
    evidence: unknown[];
    observation: string;
  }[];
  risk: {
    level: string;
    score: number | null;
    factors: string[];
    explanation: string | null;
  } | null;
  ai_summary: {
    recommendation: string;
    reason: string | null;
    evidence: unknown[];
  } | null;
  observations: ReportObservation[];
  status: ReportStatus;
  timeline: ReportTimelineEvent[];
  decision: {
    decision: string;
    reason: string | null;
    decided_by: string | null;
    decided_at: string | null;
  } | null;
}

export interface ReportInboxItem {
  bid_id: number;
  bidder_name: string | null;
  tender_number: string | null;
  tender_title: string | null;
  sent_by: string | null;
  sent_at: string | null;
  is_new: boolean;
  status: ReportStatus;
}
