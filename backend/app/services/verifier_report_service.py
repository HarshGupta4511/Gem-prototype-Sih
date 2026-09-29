"""Verifier -> Procurement Officer verification report.

Evidence-based handoff with an audit-sourced lifecycle. Deliberately makes NO
database schema changes:

- The report CONTENT is derived live from existing tables (documents,
  extracted fields, verification checks, compliance results, risk assessment,
  the stored AI recommendation). Nothing is duplicated or invented.
- The report LIFECYCLE (DRAFT -> GENERATED -> SENT_TO_OFFICER -> UNDER_REVIEW
  -> DECISION_MADE) is derived from the existing hash-chained audit log using
  VERIFIER_OBSERVATION_ADDED / VERIFICATION_REPORT_* events. The audit system
  itself is untouched.

Product principle: the Verifier reviews evidence and reports; the System
calculates compliance/risk; AI explains/summarizes; the Procurement Officer
decides. The report is decision SUPPORT and never auto-approves/rejects.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import (
    AuditLog,
    Bidder,
    BidSubmission,
    ComplianceResult,
    Document,
    ExtractedField,
    RiskAssessment,
    Tender,
    TenderRequirement,
    User,
    VerificationCheck,
)
from app.services import audit_service

# Must match the entity_type used by the existing officer/decision audit events.
REPORT_ENTITY = "bid_submission"

OBSERVATION_ADDED = "VERIFIER_OBSERVATION_ADDED"
REPORT_GENERATED = "VERIFICATION_REPORT_GENERATED"
REPORT_SENT = "VERIFICATION_REPORT_SENT"
REPORT_OPENED = "VERIFICATION_REPORT_OPENED"
OFFICER_DECISION = "OFFICER_DECISION"

# Stage rank for status derivation: the furthest stage ever reached wins, so a
# later observation never regresses a GENERATED/SENT report back to DRAFT.
_STAGE_RANK = {
    OBSERVATION_ADDED: 0,
    REPORT_GENERATED: 1,
    REPORT_SENT: 2,
    REPORT_OPENED: 3,
    OFFICER_DECISION: 4,
}

_LIFECYCLE_STATUS = {
    OBSERVATION_ADDED: "DRAFT",
    REPORT_GENERATED: "GENERATED",
    REPORT_SENT: "SENT_TO_OFFICER",
    REPORT_OPENED: "UNDER_REVIEW",
    OFFICER_DECISION: "DECISION_MADE",
}

# Cap the extracted-field list so one report stays readable; the total is shown.
MAX_EXTRACTED_FIELDS = 40


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


def _get_bid(db: Session, bid_id: int) -> BidSubmission:
    from fastapi import HTTPException, status

    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    return bid


def _report_events(db: Session, bid_id: int) -> list[AuditLog]:
    """All report-lifecycle audit events for a bid, oldest first."""
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == REPORT_ENTITY,
            AuditLog.entity_id == str(bid_id),
            AuditLog.action.in_(tuple(_STAGE_RANK.keys())),
        )
        .order_by(AuditLog.id.asc())
        .all()
    )


def _actor_name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user.name if user is not None else None


def report_lifecycle(db: Session, bid_id: int) -> dict:
    """Derive the report status, observations and timeline from the audit log."""
    events = _report_events(db, bid_id)
    status = "DRAFT"
    if events:
        furthest = max(events, key=lambda e: _STAGE_RANK[e.action])
        status = _LIFECYCLE_STATUS[furthest.action]

    observations = []
    for e in events:
        if e.action == OBSERVATION_ADDED:
            text = (e.meta or {}).get("observation", "")
            if text:
                observations.append(
                    {
                        "text": text,
                        "added_by": _actor_name(db, e.user_id),
                        "added_at": _iso(e.timestamp),
                    }
                )

    timeline = [
        {
            "action": e.action,
            "status_after": _LIFECYCLE_STATUS[e.action],
            "actor": _actor_name(db, e.user_id),
            "at": _iso(e.timestamp),
        }
        for e in events
    ]
    return {"status": status, "observations": observations, "timeline": timeline}


def build_report(db: Session, bid_id: int) -> dict:
    """Assemble the evidence-based verification report from existing data only."""
    bid = _get_bid(db, bid_id)
    bidder = db.get(Bidder, bid.bidder_id)
    tender = db.get(Tender, bid.tender_id)

    documents = (
        db.query(Document).filter(Document.bid_id == bid_id).order_by(Document.id).all()
    )
    doc_ids = [d.id for d in documents]

    fields: list[ExtractedField] = []
    if doc_ids:
        fields = (
            db.query(ExtractedField)
            .filter(ExtractedField.document_id.in_(doc_ids))
            .order_by(ExtractedField.id)
            .all()
        )
    doc_by_id = {d.id: d for d in documents}
    field_count_by_doc: dict[int, int] = {}
    for f in fields:
        field_count_by_doc[f.document_id] = field_count_by_doc.get(f.document_id, 0) + 1

    checks = (
        db.query(VerificationCheck)
        .filter(VerificationCheck.bid_id == bid_id)
        .order_by(VerificationCheck.id)
        .all()
    )

    comp_rows = (
        db.query(ComplianceResult, TenderRequirement.requirement_name)
        .join(TenderRequirement, ComplianceResult.requirement_id == TenderRequirement.id)
        .filter(ComplianceResult.bid_id == bid_id)
        .order_by(ComplianceResult.id)
        .all()
    )

    risk = db.query(RiskAssessment).filter(RiskAssessment.bid_id == bid_id).one_or_none()

    lifecycle = report_lifecycle(db, bid_id)

    doc_issue_statuses = {"FAILED", "UNCLASSIFIED", "REVIEW_REQUIRED"}

    report = {
        "bid_id": bid.id,
        "generated_at": _iso(_utcnow()),
        "compliance_score": bid.compliance_score,
        "bid_info": {
            "tender_number": tender.tender_number if tender else None,
            "tender_title": tender.title if tender else None,
            "bidder_name": bidder.legal_name if bidder else None,
            "submission_date": _iso(getattr(bid, "submitted_at", None)),
        },
        "documents": {
            "submitted_count": len(documents),
            "processed_count": sum(
                1 for d in documents if d.processing_status == "PROCESSED"
            ),
            "items": [
                {
                    "id": d.id,
                    "file_name": d.filename,
                    "document_type": d.document_type,
                    "status": d.processing_status,
                    "extracted_field_count": field_count_by_doc.get(d.id, 0),
                }
                for d in documents
            ],
            "issues": [
                {
                    "id": d.id,
                    "file_name": d.filename,
                    "document_type": d.document_type,
                    "status": d.processing_status,
                }
                for d in documents
                if d.processing_status in doc_issue_statuses
            ],
        },
        "extracted_fields": {
            "total": len(fields),
            "items": [
                {
                    "field_name": f.field_name,
                    "field_value": f.field_value,
                    "document_name": (
                        doc_by_id[f.document_id].filename
                        if f.document_id in doc_by_id
                        else None
                    ),
                    "document_type": (
                        doc_by_id[f.document_id].document_type
                        if f.document_id in doc_by_id
                        else None
                    ),
                    "extraction_method": f.extraction_method,
                }
                for f in fields[:MAX_EXTRACTED_FIELDS]
            ],
        },
        "verification": [
            {
                "source": c.source,
                "identifier": c.identifier,
                "status": c.verification_status,
                "observation": c.evidence_reference,
                "is_mock": bool(c.is_mock),
                "verified_at": _iso(c.verified_at),
            }
            for c in checks
        ],
        "compliance": [
            {
                "requirement": name,
                "result": r.status,
                "evidence": r.evidence or [],
                "observation": r.explanation,
            }
            for r, name in comp_rows
        ],
        "risk": (
            {
                "level": risk.risk_level,
                "score": risk.risk_score,
                "factors": risk.signals or [],
                "explanation": risk.explanation,
            }
            if risk is not None
            else None
        ),
        # AI section: strictly the already-stored AI recommendation, clearly
        # labelled. Never generated or invented here.
        "ai_summary": (
            {
                "recommendation": bid.recommendation,
                "reason": bid.recommendation_reason,
                "evidence": bid.recommendation_evidence or [],
            }
            if bid.recommendation
            else None
        ),
        "observations": lifecycle["observations"],
        "status": lifecycle["status"],
        "timeline": lifecycle["timeline"],
        "decision": (
            {
                "decision": bid.officer_decision,
                "reason": bid.officer_decision_reason,
                "decided_by": _actor_name(db, bid.decided_by),
                "decided_at": _iso(bid.decided_at),
            }
            if bid.officer_decision
            else None
        ),
    }
    return report


# ---------------------------------------------------------------------------
# Lifecycle transitions (each appends an audit event; guards enforce the flow)
# ---------------------------------------------------------------------------


def add_observation(db: Session, bid_id: int, user: User, observation: str) -> dict:
    """Verifier adds a professional observation. Allowed while the report is
    still being prepared (DRAFT / GENERATED)."""
    bid = _get_bid(db, bid_id)
    text = (observation or "").strip()
    if not text:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Observation text is required",
        )
    current = report_lifecycle(db, bid_id)["status"]
    if current not in ("DRAFT", "GENERATED"):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report is already {current}; observations are locked after sending.",
        )
    audit_service.append_audit(
        db,
        user_id=user.id,
        action=OBSERVATION_ADDED,
        entity_type=REPORT_ENTITY,
        entity_id=str(bid.id),
        metadata={"observation": text},
    )
    return report_lifecycle(db, bid_id)


def generate_report(db: Session, bid_id: int, user: User) -> dict:
    """Verifier finalises the report draft from the current evidence."""
    bid = _get_bid(db, bid_id)
    current = report_lifecycle(db, bid_id)["status"]
    if current == "GENERATED":
        # Idempotent: the draft already exists.
        return build_report(db, bid_id)
    if current not in ("DRAFT",):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report is already {current}; it cannot be regenerated.",
        )
    audit_service.append_audit(
        db,
        user_id=user.id,
        action=REPORT_GENERATED,
        entity_type=REPORT_ENTITY,
        entity_id=str(bid.id),
        metadata={
            "documents": db.query(Document).filter(Document.bid_id == bid.id).count(),
            "verification_checks": db.query(VerificationCheck)
            .filter(VerificationCheck.bid_id == bid.id)
            .count(),
            "compliance_results": db.query(ComplianceResult)
            .filter(ComplianceResult.bid_id == bid.id)
            .count(),
        },
    )
    return build_report(db, bid_id)


def send_report(db: Session, bid_id: int, user: User) -> dict:
    """Verifier hands the report to the Procurement Officer for decision."""
    bid = _get_bid(db, bid_id)
    current = report_lifecycle(db, bid_id)["status"]
    if current == "SENT_TO_OFFICER":
        return build_report(db, bid_id)
    if current != "GENERATED":
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generate the verification report before sending it.",
        )
    audit_service.append_audit(
        db,
        user_id=user.id,
        action=REPORT_SENT,
        entity_type=REPORT_ENTITY,
        entity_id=str(bid.id),
        metadata={
            "sender_id": user.id,
            "sender_name": user.name,
            "sender_role": user.role,
            "recipient_role": "PROCUREMENT_OFFICER",
            "sent_at": _iso(_utcnow()),
        },
    )
    return build_report(db, bid_id)


def mark_opened(db: Session, bid_id: int, user: User) -> dict:
    """Record that the Procurement Officer opened the report (RECEIVED ->
    UNDER_REVIEW). Idempotent."""
    bid = _get_bid(db, bid_id)
    current = report_lifecycle(db, bid_id)["status"]
    if current == "SENT_TO_OFFICER":
        audit_service.append_audit(
            db,
            user_id=user.id,
            action=REPORT_OPENED,
            entity_type=REPORT_ENTITY,
            entity_id=str(bid.id),
            metadata={"opened_by": user.id, "opened_by_name": user.name},
        )
    return report_lifecycle(db, bid_id)


def inbox(db: Session) -> list[dict]:
    """Reports sent to the Procurement Officer, newest first.

    A report is NEW when it was sent but the officer has not opened it yet.
    Derived purely from audit events.
    """
    sent_events = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == REPORT_ENTITY,
            AuditLog.action == REPORT_SENT,
        )
        .order_by(AuditLog.id.desc())
        .all()
    )
    items: list[dict] = []
    for e in sent_events:
        try:
            bid_id = int(e.entity_id)
        except (TypeError, ValueError):
            continue
        bid = db.get(BidSubmission, bid_id)
        if bid is None:
            continue
        bidder = db.get(Bidder, bid.bidder_id)
        tender = db.get(Tender, bid.tender_id)

        # Opened after this specific send event?
        opened = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == REPORT_ENTITY,
                AuditLog.entity_id == str(bid_id),
                AuditLog.action == REPORT_OPENED,
                AuditLog.id > e.id,
            )
            .first()
        )
        # A later decision also clears the "new" flag.
        decided = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == REPORT_ENTITY,
                AuditLog.entity_id == str(bid_id),
                AuditLog.action == OFFICER_DECISION,
                AuditLog.id > e.id,
            )
            .first()
        )
        meta = e.meta or {}
        items.append(
            {
                "bid_id": bid_id,
                "bidder_name": bidder.legal_name if bidder else None,
                "tender_number": tender.tender_number if tender else None,
                "tender_title": tender.title if tender else None,
                "sent_by": meta.get("sender_name") or _actor_name(db, e.user_id),
                "sent_at": _iso(e.timestamp),
                "is_new": opened is None and decided is None,
                "status": report_lifecycle(db, bid_id)["status"],
            }
        )
    return items
