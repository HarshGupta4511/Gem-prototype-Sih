"""SQLAlchemy 2.0 models — every entity in CONTRACT.md §4.

Enum classes here carry the EXACT string values from §3 (plus the extra status
sets named in §4) so routers, engines, adapters and schemas share one source
of truth. Columns stay plain Strings (portable on SQLite); validation against
these values happens in Pydantic schemas.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enum string constants (exact values from CONTRACT.md §3, plus §4 additions)
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    PROCUREMENT_OFFICER = "PROCUREMENT_OFFICER"
    VERIFIER = "VERIFIER"
    AUDITOR = "AUDITOR"
    ADMIN = "ADMIN"


class TenderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    AWARDED = "AWARDED"


class RequirementStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MISSING = "MISSING"
    EXPIRED = "EXPIRED"
    MISMATCH = "MISMATCH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RequirementCategory(str, enum.Enum):
    STATUTORY = "STATUTORY"
    FINANCIAL = "FINANCIAL"
    EXPERIENCE = "EXPERIENCE"
    TECHNICAL = "TECHNICAL"
    REGISTRATION = "REGISTRATION"
    LOCAL_CONTENT = "LOCAL_CONTENT"
    OEM = "OEM"
    INTEGRITY = "INTEGRITY"
    DOCUMENT = "DOCUMENT"


class RuleType(str, enum.Enum):
    EXISTENCE = "EXISTENCE"
    EQUALITY = "EQUALITY"
    MATCH = "MATCH"
    MINIMUM = "MINIMUM"
    MAXIMUM = "MAXIMUM"
    DATE_VALIDITY = "DATE_VALIDITY"
    DATE_RANGE = "DATE_RANGE"
    CONTAINS = "CONTAINS"
    BOOLEAN = "BOOLEAN"
    REGISTRATION_STATUS = "REGISTRATION_STATUS"
    IDENTITY_MATCH = "IDENTITY_MATCH"
    DOCUMENT_REQUIRED = "DOCUMENT_REQUIRED"
    CUSTOM_RULE = "CUSTOM_RULE"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class VerificationStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    NOT_FOUND = "NOT_FOUND"
    EXPIRED = "EXPIRED"
    UNAVAILABLE = "UNAVAILABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class BidStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED"


class DocProcessingStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class DocumentType(str, enum.Enum):
    PAN_CERTIFICATE = "PAN_CERTIFICATE"
    GST_CERTIFICATE = "GST_CERTIFICATE"
    GST_RETURN = "GST_RETURN"
    UDYAM_CERTIFICATE = "UDYAM_CERTIFICATE"
    ITR = "ITR"
    TURNOVER_CERTIFICATE = "TURNOVER_CERTIFICATE"
    EXPERIENCE_CERTIFICATE = "EXPERIENCE_CERTIFICATE"
    OEM_AUTHORIZATION = "OEM_AUTHORIZATION"
    EPFO_CERTIFICATE = "EPFO_CERTIFICATE"
    ESIC_CERTIFICATE = "ESIC_CERTIFICATE"
    MII_DECLARATION = "MII_DECLARATION"
    STARTUP_INDIA_CERTIFICATE = "STARTUP_INDIA_CERTIFICATE"
    NSIC_CERTIFICATE = "NSIC_CERTIFICATE"
    DIGILOCKER_DOCUMENT = "DIGILOCKER_DOCUMENT"
    AUDITED_FINANCIAL_STATEMENT = "AUDITED_FINANCIAL_STATEMENT"
    BID_DOSSIER = "BID_DOSSIER"
    OTHER = "OTHER"
    # System could not confidently classify the document — never invent a
    # type; the officer corrects it manually only in this exception case.
    UNCLASSIFIED = "UNCLASSIFIED"


class ExtractionMethod(str, enum.Enum):
    REGEX = "REGEX"
    OCR = "OCR"
    LLM = "LLM"
    MANUAL = "MANUAL"


class OfficerDecision(str, enum.Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"


class Recommendation(str, enum.Enum):
    PROCEED = "PROCEED"
    PROCEED_WITH_CONDITIONS = "PROCEED_WITH_CONDITIONS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"


class AdapterSource(str, enum.Enum):
    GSTN = "GSTN"
    UDYAM = "UDYAM"
    PAN_IT = "PAN_IT"
    MCA21 = "MCA21"
    EPFO = "EPFO"
    ESIC = "ESIC"
    STARTUP_INDIA = "STARTUP_INDIA"
    NSIC = "NSIC"
    DIGILOCKER = "DIGILOCKER"
    BLACKLIST = "BLACKLIST"


class AuditAction(str, enum.Enum):
    LOGIN = "LOGIN"
    TENDER_CREATED = "TENDER_CREATED"
    BID_SUBMITTED = "BID_SUBMITTED"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_PROCESSED = "DOCUMENT_PROCESSED"
    CLASSIFICATION_CORRECTED = "CLASSIFICATION_CORRECTED"
    VERIFICATION_RUN = "VERIFICATION_RUN"
    COMPLIANCE_EVALUATED = "COMPLIANCE_EVALUATED"
    RISK_ASSESSED = "RISK_ASSESSED"
    RECOMMENDATION_GENERATED = "RECOMMENDATION_GENERATED"
    OFFICER_DECISION = "OFFICER_DECISION"
    OFFICER_DECISION_CHANGED = "OFFICER_DECISION_CHANGED"
    OVERRIDE_RECORDED = "OVERRIDE_RECORDED"
    CLARIFICATION_SENT = "CLARIFICATION_SENT"
    REPORT_GENERATED = "REPORT_GENERATED"
    AUDIT_VERIFIED = "AUDIT_VERIFIED"
    KNOWLEDGE_UPDATED = "KNOWLEDGE_UPDATED"
    INTEGRITY_ANALYSIS_RUN = "INTEGRITY_ANALYSIS_RUN"
    INTEGRITY_SIGNAL_DETECTED = "INTEGRITY_SIGNAL_DETECTED"
    INTEGRITY_SIGNAL_ACKNOWLEDGED = "INTEGRITY_SIGNAL_ACKNOWLEDGED"
    INTEGRITY_SIGNAL_REVIEWED = "INTEGRITY_SIGNAL_REVIEWED"
    INTEGRITY_SIGNAL_INVESTIGATED = "INTEGRITY_SIGNAL_INVESTIGATED"
    INTEGRITY_SIGNAL_CLOSED = "INTEGRITY_SIGNAL_CLOSED"
    INTEGRITY_NOTE_ADDED = "INTEGRITY_NOTE_ADDED"
    CONSISTENCY_CHECK_RUN = "CONSISTENCY_CHECK_RUN"
    CROSS_DOCUMENT_MISMATCH_DETECTED = "CROSS_DOCUMENT_MISMATCH_DETECTED"
    DEMO_HISTORY_SEEDED = "DEMO_HISTORY_SEEDED"


class ClarificationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    RESPONDED = "RESPONDED"


class EmbeddingStatus(str, enum.Enum):
    PENDING = "PENDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class OverrideTargetType(str, enum.Enum):
    COMPLIANCE_RESULT = "COMPLIANCE_RESULT"
    VERIFICATION = "VERIFICATION"


# ---------------------------------------------------------------------------
# Entities (§4)
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50))
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Tender(Base):
    __tablename__ = "tenders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    organization: Mapped[str] = mapped_column(String(255))
    department: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_value_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tender_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bid_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    emd_amount_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_period: Mapped[str | None] = mapped_column(String(255), nullable=True)
    place_of_delivery: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TenderStatus.DRAFT.value)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Clearly-labelled synthetic procurement history for the integrity demo.
    # Hidden from the normal tender list; included in integrity analysis.
    is_demo_history: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)

    requirements: Mapped[list["TenderRequirement"]] = relationship("TenderRequirement")
    bidders: Mapped[list["Bidder"]] = relationship("Bidder")
    bids: Mapped[list["BidSubmission"]] = relationship("BidSubmission")


class TenderRequirement(Base):
    __tablename__ = "tender_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"), index=True)
    requirement_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    rule_type: Mapped[str] = mapped_column(String(50))
    rule_config: Mapped[dict] = mapped_column(JSON, default=dict)
    threshold: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    policy_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tender: Mapped["Tender"] = relationship("Tender")


class Bidder(Base):
    __tablename__ = "bidders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"), index=True)
    legal_name: Mapped[str] = mapped_column(String(500))
    trade_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    udyam: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cin: Mapped[str | None] = mapped_column(String(30), nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bid_status: Mapped[str] = mapped_column(String(30), default=BidStatus.DRAFT.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tender: Mapped["Tender"] = relationship("Tender")
    bid: Mapped["BidSubmission | None"] = relationship(
        "BidSubmission", uselist=False, foreign_keys="BidSubmission.bidder_id"
    )


class BidSubmission(Base):
    __tablename__ = "bid_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int] = mapped_column(ForeignKey("tenders.id"), index=True)
    bidder_id: Mapped[int] = mapped_column(ForeignKey("bidders.id"), unique=True, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(String(30), default=BidStatus.SUBMITTED.value)
    compliance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_reasons: Mapped[list] = mapped_column(JSON, default=list)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_evidence: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    # Citable RAG policy context persisted at recommendation time. Additive,
    # nullable — never affects compliance score, risk, or officer decision.
    policy_context: Mapped[list | None] = mapped_column(JSON, nullable=True)
    officer_decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    officer_decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tender: Mapped["Tender"] = relationship("Tender")
    bidder: Mapped["Bidder"] = relationship("Bidder")
    documents: Mapped[list["Document"]] = relationship("Document")
    verification_checks: Mapped[list["VerificationCheck"]] = relationship("VerificationCheck")
    compliance_results: Mapped[list["ComplianceResult"]] = relationship("ComplianceResult")
    risk: Mapped["RiskAssessment | None"] = relationship(
        "RiskAssessment", uselist=False, foreign_keys="RiskAssessment.bid_id"
    )
    clarifications: Mapped[list["Clarification"]] = relationship("Clarification")
    overrides: Mapped[list["Override"]] = relationship("Override")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bid_submissions.id"), index=True)
    document_type: Mapped[str] = mapped_column(String(50))
    filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))
    file_hash: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(100))
    upload_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(20), default=DocProcessingStatus.UPLOADED.value
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    bid: Mapped["BidSubmission"] = relationship("BidSubmission")
    extracted_fields: Mapped[list["ExtractedField"]] = relationship("ExtractedField")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(100))
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    extraction_method: Mapped[str] = mapped_column(String(20))
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document: Mapped["Document"] = relationship("Document")


class VerificationCheck(Base):
    __tablename__ = "verification_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bid_submissions.id"), index=True)
    requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("tender_requirements.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(50))
    identifier: Mapped[str] = mapped_column(String(100))
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)

    bid: Mapped["BidSubmission"] = relationship("BidSubmission")


class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bid_submissions.id"), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("tender_requirements.id"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    weight: Mapped[float] = mapped_column(Float)
    weighted_contribution: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text)
    rule_applied: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    override_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    bid: Mapped["BidSubmission"] = relationship("BidSubmission")
    requirement: Mapped["TenderRequirement"] = relationship("TenderRequirement")


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bid_submissions.id"), unique=True, index=True)
    risk_level: Mapped[str] = mapped_column(String(20))
    risk_score: Mapped[float] = mapped_column(Float)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    bid: Mapped["BidSubmission"] = relationship("BidSubmission")


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500))
    doc_type: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_status: Mapped[str] = mapped_column(
        String(20), default=EmbeddingStatus.PENDING.value
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship("KnowledgeChunk")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("knowledge_docs.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    doc: Mapped["KnowledgeDoc"] = relationship("KnowledgeDoc")


class Clarification(Base):
    __tablename__ = "clarifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bid_submissions.id"), index=True)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ClarificationStatus.DRAFT.value)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    bid: Mapped["BidSubmission"] = relationship("BidSubmission")


class Override(Base):
    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bid_submissions.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[int] = mapped_column(Integer)
    original_status: Mapped[str] = mapped_column(String(30))
    officer_comment: Mapped[str] = mapped_column(Text)
    supporting_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    bid: Mapped["BidSubmission"] = relationship("BidSubmission")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    previous_hash: Mapped[str] = mapped_column(String(64))
    current_hash: Mapped[str] = mapped_column(String(64))
    # `metadata` is reserved on DeclarativeBase -> attribute `meta` maps to DB column `metadata`
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)

    user: Mapped["User | None"] = relationship("User")


# ---------------------------------------------------------------------------
# Procurement integrity (deterministic, evidence-backed signals — never
# findings of misconduct; the Procurement Officer reviews and decides)
# ---------------------------------------------------------------------------


class IntegritySeverity(str, enum.Enum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ELEVATED = "ELEVATED"
    INFORMATIONAL = "INFORMATIONAL"


class IntegritySignalType(str, enum.Enum):
    RECURRING_BIDDER_COHORT = "RECURRING_BIDDER_COHORT"
    REPEATED_PARTICIPATION = "REPEATED_PARTICIPATION"
    BID_ROTATION_PATTERN = "BID_ROTATION_PATTERN"
    BIDDER_RELATIONSHIP = "BIDDER_RELATIONSHIP"
    OFFICER_BIDDER_ASSOCIATION = "OFFICER_BIDDER_ASSOCIATION"
    CROSS_TENDER_CONCENTRATION = "CROSS_TENDER_CONCENTRATION"
    DOCUMENT_IDENTITY_RELATIONSHIP = "DOCUMENT_IDENTITY_RELATIONSHIP"


class IntegrityStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNDER_REVIEW = "UNDER_REVIEW"
    INVESTIGATING = "INVESTIGATING"
    CLOSED = "CLOSED"


class IntegrityFinding(Base):
    """A deterministic integrity *signal* (not a finding of misconduct).

    Detected from existing tender/bid/audit data by the integrity engine;
    every signal carries its supporting evidence and the rule logic that
    produced it. Officer actions transition ``status`` and are audited.
    """

    __tablename__ = "integrity_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tender_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenders.id"), nullable=True, index=True
    )
    bidder_id: Mapped[int | None] = mapped_column(
        ForeignKey("bidders.id"), nullable=True, index=True
    )
    signal_type: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    affected_bids: Mapped[list] = mapped_column(JSON, default=list)
    affected_tenders: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    rule_logic: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=IntegrityStatus.OPEN.value)
    # True when the signal is (partly) sourced from the clearly-labelled
    # synthetic DEMO procurement history — shown with a DEMO DATA banner.
    # Nullable for migration safety (pre-existing rows read as False); the
    # service always writes an explicit boolean for new findings.
    is_demo_history: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    officer_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    tender: Mapped["Tender | None"] = relationship("Tender")
    bidder: Mapped["Bidder | None"] = relationship("Bidder")


class ConsistencyCheck(Base):
    """One cross-document consistency check for a bid.

    Compares extracted fields across the bid's documents using normalized
    comparison (entity_resolution). Re-running replaces the bid's checks.
    """

    __tablename__ = "consistency_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bid_submissions.id"), index=True)
    check_name: Mapped[str] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(100))
    doc1_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    doc2_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    value1: Mapped[str | None] = mapped_column(Text, nullable=True)
    value2: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(String(30))  # MATCH / MISMATCH / REVIEW_REQUIRED
    reason: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(30))  # REVIEW_REQUIRED / INFORMATIONAL
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    bid: Mapped["BidSubmission"] = relationship("BidSubmission")
