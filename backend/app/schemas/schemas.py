"""Pydantic v2 request/response schemas for every API in CONTRACT.md §5.

Enum-typed fields reuse the exact string enums from app.models.models (§3).
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import (
    AdapterSource,
    BidStatus,
    ClarificationStatus,
    DocProcessingStatus,
    DocumentType,
    EmbeddingStatus,
    ExtractionMethod,
    OfficerDecision,
    OverrideTargetType,
    Recommendation,
    RequirementCategory,
    RequirementStatus,
    RiskLevel,
    RuleType,
    TenderStatus,
    UserRole,
    VerificationStatus,
)

_orm = ConfigDict(from_attributes=True)


# --- Auth ---


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = _orm

    id: int
    name: str
    email: str
    role: UserRole
    department: str | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- Tenders ---


TenderType = Literal["GOODS", "SERVICES", "WORKS"]
BidType = Literal["SINGLE_PACKET", "TWO_PACKET"]


class RequirementCreate(BaseModel):
    requirement_name: str
    category: RequirementCategory
    description: str | None = None
    mandatory: bool = True
    rule_type: RuleType
    rule_config: dict = Field(default_factory=dict)
    threshold: str | None = None
    expected_value: str | None = None
    verification_source: AdapterSource | None = None
    weight: float = 1.0
    policy_reference: str | None = None


class RequirementsBulkCreate(BaseModel):
    requirements: list[RequirementCreate]


class TenderCreate(BaseModel):
    tender_number: str
    title: str
    organization: str
    department: str
    description: str | None = None
    issue_date: date | None = None
    closing_date: date | None = None
    estimated_value_inr: int | None = None
    tender_type: TenderType | None = None
    bid_type: BidType | None = None
    emd_amount_inr: int | None = None
    delivery_period: str | None = None
    place_of_delivery: str | None = None
    # Optional wizard payload: when present the tender and its requirements are
    # created atomically. Weights must be non-negative and sum to exactly 100.
    requirements: list[RequirementCreate] | None = None


class TenderOut(BaseModel):
    model_config = _orm

    id: int
    tender_number: str
    title: str
    organization: str
    department: str
    description: str | None = None
    issue_date: date | None = None
    closing_date: date | None = None
    estimated_value_inr: int | None = None
    tender_type: TenderType | None = None
    bid_type: BidType | None = None
    emd_amount_inr: int | None = None
    delivery_period: str | None = None
    place_of_delivery: str | None = None
    status: TenderStatus
    created_by: int | None = None
    created_at: datetime


class TenderListItem(TenderOut):
    bidder_count: int = 0
    pending_reviews: int = 0
    avg_compliance: float | None = None
    high_risk_count: int = 0


class RequirementOut(BaseModel):
    model_config = _orm

    id: int
    tender_id: int
    requirement_name: str
    category: RequirementCategory
    description: str | None = None
    mandatory: bool
    rule_type: RuleType
    rule_config: dict = Field(default_factory=dict)
    threshold: str | None = None
    expected_value: str | None = None
    verification_source: AdapterSource | None = None
    weight: float
    policy_reference: str | None = None
    created_at: datetime


class TenderBidderRow(BaseModel):
    """One bidder row in the tender detail response (§5)."""

    bid_id: int
    legal_name: str
    trade_name: str | None = None
    pan: str | None = None
    gstin: str | None = None
    udyam: str | None = None
    cin: str | None = None
    bid_status: BidStatus
    compliance_score: float | None = None
    risk_level: RiskLevel | None = None
    recommendation: Recommendation | None = None
    officer_decision: OfficerDecision | None = None
    submitted_at: datetime | None = None


class TenderDetailOut(BaseModel):
    tender: TenderOut
    requirements: list[RequirementOut] = []
    bidders: list[TenderBidderRow] = []
    stats: dict = Field(default_factory=dict)


class TenderAnalyzeRequest(BaseModel):
    tender_text: str


class TenderAnalyzeResponse(BaseModel):
    requirements: list[RequirementCreate]


class SuggestRequirementsRequest(BaseModel):
    """Tender context for AI requirement suggestions (nothing persisted)."""

    title: str
    description: str | None = None
    department: str | None = None
    organization: str | None = None
    tender_type: str | None = None
    bid_type: str | None = None
    estimated_value_inr: float | None = None
    delivery_period: str | None = None
    place_of_delivery: str | None = None


class SuggestedRequirement(BaseModel):
    """One AI-suggested requirement — ADVISORY, officer reviews before use."""

    requirement_name: str
    threshold: str | None = None
    mandatory: bool = True
    weight: float = 0
    description: str | None = None


class SuggestRequirementsResponse(BaseModel):
    requirements: list[SuggestedRequirement]
    provider: str


class ComparisonBidderRow(BaseModel):
    bid_id: int
    legal_name: str
    compliance_score: float | None = None
    risk_level: RiskLevel | None = None


class ComparisonRequirementRow(BaseModel):
    id: int
    requirement_name: str


class ComparisonMatrixRow(BaseModel):
    requirement_id: int
    requirement_name: str
    results: dict[int, RequirementStatus] = Field(default_factory=dict)


class ComparisonOut(BaseModel):
    requirements: list[ComparisonRequirementRow] = []
    bidders: list[ComparisonBidderRow] = []
    matrix: list[ComparisonMatrixRow] = []


# --- Bids ---


class BidderOut(BaseModel):
    model_config = _orm

    id: int
    tender_id: int
    legal_name: str
    trade_name: str | None = None
    pan: str | None = None
    gstin: str | None = None
    udyam: str | None = None
    cin: str | None = None
    registered_address: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    bid_status: BidStatus
    created_at: datetime


class BidCreate(BaseModel):
    tender_id: int
    legal_name: str
    trade_name: str | None = None
    pan: str | None = None
    gstin: str | None = None
    udyam: str | None = None
    cin: str | None = None
    registered_address: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class BidOut(BaseModel):
    model_config = _orm

    id: int
    tender_id: int
    bidder_id: int
    submitted_at: datetime
    status: BidStatus
    compliance_score: float | None = None
    risk_level: RiskLevel | None = None
    risk_reasons: list = Field(default_factory=list)
    risk_score: float | None = None
    recommendation: Recommendation | None = None
    recommendation_reason: str | None = None
    recommendation_evidence: dict | list | None = None
    officer_decision: OfficerDecision | None = None
    officer_decision_reason: str | None = None
    decided_by: int | None = None
    decided_at: datetime | None = None


class BidCreateResponse(BaseModel):
    bid: BidOut
    bidder: BidderOut


class DemoEvidenceSeedRequest(BaseModel):
    """Attach a fictional demo-bidder evidence dossier to an existing bid.

    ``profile_key`` is one of ``apex`` | ``vertex`` | ``nova`` | ``primetech``.
    """

    profile_key: str


class BidListItem(BaseModel):
    bid_id: int
    legal_name: str
    bid_status: BidStatus
    compliance_score: float | None = None
    risk_level: RiskLevel | None = None
    recommendation: Recommendation | None = None
    officer_decision: OfficerDecision | None = None
    submitted_at: datetime | None = None


class BidDetailOut(BaseModel):
    bid: BidOut
    bidder: BidderOut
    tender: dict = Field(default_factory=dict)
    documents: list["DocumentOut"] = []
    compliance_results: list["ComplianceResultOut"] = []
    risk: "RiskOut | None" = None
    verification_checks: list["VerificationCheckOut"] = []
    recommendation: "RecommendationOut | None" = None
    overrides: list["OverrideOut"] = []
    clarifications: list["ClarificationOut"] = []
    audit: list["AuditOut"] = []


# --- Documents ---


class DocumentOut(BaseModel):
    model_config = _orm

    id: int
    bid_id: int
    document_type: DocumentType
    filename: str
    file_path: str
    file_hash: str
    file_size: int
    mime_type: str
    upload_time: datetime
    uploaded_by: int | None = None
    processing_status: DocProcessingStatus
    extraction_confidence: float | None = None
    page_count: int | None = None
    ocr_used: bool = False
    error: str | None = None


class DocumentTypeUpdate(BaseModel):
    document_type: DocumentType


class ExtractedFieldOut(BaseModel):
    model_config = _orm

    id: int
    document_id: int
    field_name: str
    field_value: str | None = None
    normalized_value: str | None = None
    confidence: float
    extraction_method: ExtractionMethod
    page_number: int | None = None


class DocumentDetailOut(BaseModel):
    document: DocumentOut
    extracted_fields: list[ExtractedFieldOut] = []


class DocumentProcessResponse(BaseModel):
    document: DocumentOut
    extracted_fields: list[ExtractedFieldOut] = []
    classification: DocumentType | None = None


# --- Verification ---


class VerificationCheckOut(BaseModel):
    model_config = _orm

    id: int
    bid_id: int
    requirement_id: int | None = None
    source: AdapterSource
    identifier: str
    request_payload: dict | None = None
    response_payload: dict | None = None
    verification_status: VerificationStatus
    verified_at: datetime
    confidence: float | None = None
    is_mock: bool = True
    evidence_reference: str | None = None


class VerificationRunRequest(BaseModel):
    bid_id: int


class VerificationRunResponse(BaseModel):
    checks: list[VerificationCheckOut]


# --- Compliance & risk ---


class ComplianceResultOut(BaseModel):
    model_config = _orm

    id: int
    bid_id: int
    requirement_id: int
    requirement_name: str | None = None  # convenience, filled by the router
    requirement: RequirementOut | None = None  # nested tender requirement (name, threshold, mandatory), filled by the router
    status: RequirementStatus
    weight: float
    weighted_contribution: float = 0.0
    evidence: list = Field(default_factory=list)
    explanation: str
    rule_applied: str
    source: str
    confidence: float | None = None
    overridden: bool = False
    override_comment: str | None = None
    original_status: RequirementStatus | None = None
    created_at: datetime


class ComplianceEvaluateRequest(BaseModel):
    bid_id: int


class ComplianceEvaluateResponse(BaseModel):
    results: list[ComplianceResultOut]
    compliance_score: float
    risk: "RiskOut"


class ComplianceGetResponse(BaseModel):
    results: list[ComplianceResultOut]
    compliance_score: float | None = None
    evaluated_at: datetime | None = None


class RiskOut(BaseModel):
    model_config = _orm

    id: int
    bid_id: int
    risk_level: RiskLevel
    risk_score: float
    signals: list = Field(default_factory=list)
    explanation: str
    created_at: datetime


# --- Recommendation ---


class RecommendationOut(BaseModel):
    recommendation: Recommendation
    reason: str | None = None
    evidence: list = Field(default_factory=list)
    policy_context: list = Field(default_factory=list)
    provider: str | None = None


# --- Officer workflow ---


class DecisionRequest(BaseModel):
    bid_id: int
    decision: OfficerDecision
    reason: str | None = None


class OverrideCreate(BaseModel):
    target_type: OverrideTargetType
    target_id: int
    officer_comment: str
    supporting_document_id: int | None = None


class OverrideOut(BaseModel):
    model_config = _orm

    id: int
    bid_id: int
    target_type: OverrideTargetType
    target_id: int
    original_status: str
    officer_comment: str
    supporting_document_id: int | None = None
    created_by: int | None = None
    created_at: datetime


class ClarificationCreate(BaseModel):
    bid_id: int
    subject: str
    body: str


class ClarificationOut(BaseModel):
    model_config = _orm

    id: int
    bid_id: int
    subject: str
    body: str
    status: ClarificationStatus
    created_by: int | None = None
    created_at: datetime
    sent_at: datetime | None = None


# --- Knowledge base / RAG ---


class KnowledgeCreate(BaseModel):
    title: str
    doc_type: str
    version: str
    content: str


class KnowledgeOut(BaseModel):
    model_config = _orm

    id: int
    title: str
    doc_type: str
    version: str
    content: str
    uploaded_at: datetime
    chunk_count: int = 0
    embedding_status: EmbeddingStatus


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)


class RagResultItem(BaseModel):
    doc_title: str
    chunk: str
    score: float


class RagSearchResponse(BaseModel):
    results: list[RagResultItem] = []
    embedding_path: str


# --- Audit ---


class AuditOut(BaseModel):
    """NOTE: the model attribute is `meta` (DB column `metadata`, reserved on
    DeclarativeBase). Pass `metadata=entry.meta` explicitly when building this
    schema from an AuditLog row — `model_validate` alone leaves it empty."""

    model_config = _orm

    id: int
    user_id: int | None = None
    action: str
    entity_type: str
    entity_id: str
    timestamp: datetime
    previous_hash: str
    current_hash: str
    metadata: dict = Field(default_factory=dict)
    user_name: str | None = None
    # Human-readable label for the event's target (bidder name, document
    # filename, ...). Populated only by the by-tender endpoint.
    target_label: str | None = None


class AuditVerifyResponse(BaseModel):
    valid: bool
    checked: int
    broken_at: dict | None = None


# --- Dashboard ---


class DashboardMetrics(BaseModel):
    total_tenders: int = 0
    active_tenders: int = 0
    total_bids: int = 0
    pending_reviews: int = 0
    high_risk_bids: int = 0
    documents_processed: int = 0
    avg_compliance_score: float | None = None
    verification_issues: int = 0


class DashboardCharts(BaseModel):
    compliance_distribution: list[dict] = Field(default_factory=list)
    risk_distribution: list[dict] = Field(default_factory=list)
    verification_status: list[dict] = Field(default_factory=list)
    tender_bidder_comparison: list[dict] = Field(default_factory=list)
    document_processing: list[dict] = Field(default_factory=list)


class DashboardOut(BaseModel):
    metrics: DashboardMetrics
    charts: DashboardCharts


# --- Seed ---


class SeedResponse(BaseModel):
    tenders: int
    bidders: int
    documents: int
