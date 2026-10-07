"""Bid Verification Summary, generated directly by the Procurement Officer.

Evidence-based summary with an audit-sourced lifecycle. Deliberately makes NO
database schema changes:

- The summary CONTENT is derived live from existing tables (documents,
  extracted fields, verification checks, compliance results, cross-document
  consistency, risk assessment, integrity signals, the stored AI
  recommendation, officer observations, decision status). Nothing is
  duplicated or invented.
- The summary LIFECYCLE (DRAFT -> GENERATED -> UPDATED) is derived from the
  existing hash-chained audit log using OFFICER_OBSERVATION_ADDED /
  VERIFICATION_REPORT_GENERATED / VERIFICATION_SUMMARY_REGENERATED events.
  The audit system itself is untouched.

Backward compatibility: histories from the retired verifier-handoff workflow
may contain VERIFICATION_REPORT_SENT / VERIFICATION_REPORT_RECEIVED /
VERIFICATION_REPORT_OPENED events; those map to GENERATED (read-only) and are
never written again. The legacy VERIFIER_OBSERVATION_ADDED event is still read
as an officer observation. The final procurement decision is recorded
separately and is not a summary-lifecycle state.

Product principle: the Procurement Officer reviews the evidence and decides;
the System calculates compliance/risk; AI explains/summarizes. The summary is
decision SUPPORT and never auto-approves/rejects.
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

OBSERVATION_ADDED = "OFFICER_OBSERVATION_ADDED"
# Legacy event from the retired verifier workflow; still read, never written.
LEGACY_OBSERVATION_ADDED = "VERIFIER_OBSERVATION_ADDED"
REPORT_GENERATED = "VERIFICATION_REPORT_GENERATED"
SUMMARY_REGENERATED = "VERIFICATION_SUMMARY_REGENERATED"
# Legacy events from the retired verifier-handoff workflow; mapped to
# GENERATED for read-only backward compatibility, never written again.
_LEGACY_SENT = "VERIFICATION_REPORT_SENT"
_LEGACY_RECEIVED = "VERIFICATION_REPORT_RECEIVED"
_LEGACY_OPENED = "VERIFICATION_REPORT_OPENED"

# Stage rank for status derivation: the furthest stage ever reached wins, so a
# later observation never regresses a GENERATED/UPDATED summary.
_STAGE_RANK = {
    OBSERVATION_ADDED: 0,
    LEGACY_OBSERVATION_ADDED: 0,
    REPORT_GENERATED: 1,
    _LEGACY_SENT: 1,
    _LEGACY_RECEIVED: 1,
    _LEGACY_OPENED: 1,
    SUMMARY_REGENERATED: 2,
}

_LIFECYCLE_STATUS = {
    OBSERVATION_ADDED: "DRAFT",
    LEGACY_OBSERVATION_ADDED: "DRAFT",
    REPORT_GENERATED: "GENERATED",
    _LEGACY_SENT: "GENERATED",
    _LEGACY_RECEIVED: "GENERATED",
    _LEGACY_OPENED: "GENERATED",
    SUMMARY_REGENERATED: "UPDATED",
}

# Cap the extracted-field list so one summary stays readable; the total is shown.
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


def _summary_events(db: Session, bid_id: int) -> list[AuditLog]:
    """All summary-lifecycle audit events for a bid, oldest first."""
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


def _consistency_section(db: Session, bid_id: int) -> dict | None:
    """Mismatch-only cross-document consistency summary (read-only)."""
    from app.services import consistency_service

    try:
        data = consistency_service.get_consistency(db, bid_id)
    except ValueError:
        return None
    if not data["checks"]:
        return None
    return {
        "checks_run": len(data["checks"]),
        "mismatches": data["mismatches"],
        "evaluated_at": data["evaluated_at"],
        "items": [
            {
                "check": c["check_label"],
                "field": c["field_name"],
                "document_1": (c["doc1"] or {}).get("name"),
                "value_1": c["value1"],
                "document_2": (c["doc2"] or {}).get("name"),
                "value_2": c["value2"],
                "result": c["result"],
                "reason": c["reason"],
                "severity": c["severity"],
            }
            for c in data["checks"]
            if c["result"] == "MISMATCH"
        ],
    }


def _integrity_section(db: Session, bid_id: int) -> dict | None:
    """Active integrity signals touching this bid (read-only)."""
    from app.services import integrity_service

    findings = integrity_service.active_signals_for_bid(db, bid_id)
    if not findings:
        return None
    return {
        "active_signals": len(findings),
        "items": [
            {
                "id": f.id,
                "signal_type": f.signal_type,
                "severity": f.severity,
                "title": f.title,
                "status": f.status,
                "is_demo_history": bool(f.is_demo_history),
            }
            for f in findings
        ],
    }


def summary_lifecycle(db: Session, bid_id: int) -> dict:
    """Derive the summary status, officer observations and timeline."""
    events = _summary_events(db, bid_id)
    status = "DRAFT"
    if events:
        furthest = max(events, key=lambda e: _STAGE_RANK[e.action])
        status = _LIFECYCLE_STATUS[furthest.action]

    observations = []
    for e in events:
        if e.action in (OBSERVATION_ADDED, LEGACY_OBSERVATION_ADDED):
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


def build_summary(db: Session, bid_id: int) -> dict:
    """Assemble the evidence-based verification summary from existing data only."""
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

    lifecycle = summary_lifecycle(db, bid_id)

    # generated_at is the timestamp of the latest generate/regenerate event —
    # never "now". A DRAFT summary has no generation event yet.
    _GENERATION_ACTIONS = {
        REPORT_GENERATED,
        SUMMARY_REGENERATED,
        _LEGACY_SENT,
        _LEGACY_RECEIVED,
        _LEGACY_OPENED,
    }
    generated_at = None
    for entry in lifecycle["timeline"]:
        if entry["action"] in _GENERATION_ACTIONS:
            generated_at = entry["at"]

    doc_issue_statuses = {"FAILED", "UNCLASSIFIED", "REVIEW_REQUIRED"}

    summary = {
        "bid_id": bid.id,
        "generated_at": generated_at,
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
        "officer_observations": lifecycle["observations"],
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
        # Cross-document consistency + integrity: read-only summaries of the
        # deterministic engines. Never generated here.
        "consistency": _consistency_section(db, bid_id),
        "integrity": _integrity_section(db, bid_id),
    }
    return summary


# ---------------------------------------------------------------------------
# Lifecycle transitions (each appends an audit event; guards enforce the flow)
# ---------------------------------------------------------------------------


def add_observation(db: Session, bid_id: int, user: User, observation: str) -> dict:
    """Procurement Officer adds a professional observation to the summary.

    Allowed while the summary is being prepared (DRAFT / GENERATED / UPDATED).
    """
    bid = _get_bid(db, bid_id)
    text = (observation or "").strip()
    if not text:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Observation text is required",
        )
    audit_service.append_audit(
        db,
        user_id=user.id,
        action=OBSERVATION_ADDED,
        entity_type=REPORT_ENTITY,
        entity_id=str(bid.id),
        metadata={"observation": text},
    )
    return summary_lifecycle(db, bid_id)


def generate_summary(db: Session, bid_id: int, user: User) -> dict:
    """Procurement Officer finalises the summary from the current evidence.

    Idempotent: a summary that already exists is returned as-is.
    """
    bid = _get_bid(db, bid_id)
    current = summary_lifecycle(db, bid_id)["status"]
    if current in ("GENERATED", "UPDATED"):
        return build_summary(db, bid_id)
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
    return build_summary(db, bid_id)


def regenerate_summary(db: Session, bid_id: int, user: User) -> dict:
    """Procurement Officer regenerates the summary after the evidence changed.

    Moves GENERATED -> UPDATED (or stays UPDATED). Requires a generated
    summary first.
    """
    bid = _get_bid(db, bid_id)
    current = summary_lifecycle(db, bid_id)["status"]
    if current == "DRAFT":
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generate the verification summary before regenerating it.",
        )
    audit_service.append_audit(
        db,
        user_id=user.id,
        action=SUMMARY_REGENERATED,
        entity_type=REPORT_ENTITY,
        entity_id=str(bid.id),
        metadata={"regenerated_at": _iso(_utcnow())},
    )
    return build_summary(db, bid_id)
