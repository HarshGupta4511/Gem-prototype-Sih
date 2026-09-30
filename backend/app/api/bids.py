"""Bid endpoints (CONTRACT.md §5: Bids)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_officer
from app.models.models import (
    AuditLog,
    BidSubmission,
    Bidder,
    Clarification,
    ComplianceResult,
    Document,
    Override,
    RiskAssessment,
    Tender,
    TenderRequirement,
    User,
    VerificationCheck,
)
from app.schemas.schemas import (
    AuditOut,
    BidCreate,
    BidCreateResponse,
    BidDetailOut,
    BidderOut,
    BidListItem,
    BidOut,
    ClarificationOut,
    ComplianceResultOut,
    DemoEvidenceSeedRequest,
    DocumentOut,
    OverrideOut,
    RecommendationOut,
    RequirementOut,
    RiskOut,
    VerificationCheckOut,
)
from app.services import audit_service

router = APIRouter(prefix="/api/bids", tags=["bids"])

_OFFICER = require_officer()
# Deletion is a procurement-officer-only destructive action.


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.post("", response_model=BidCreateResponse)
def create_bid(
    payload: BidCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Register a bidder and create its bid submission (status SUBMITTED)."""
    tender = db.get(Tender, payload.tender_id)
    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    bidder = Bidder(
        tender_id=payload.tender_id,
        legal_name=payload.legal_name,
        trade_name=payload.trade_name,
        pan=payload.pan,
        gstin=payload.gstin,
        udyam=payload.udyam,
        cin=payload.cin,
        registered_address=payload.registered_address,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        bid_status="SUBMITTED",
    )
    db.add(bidder)
    db.flush()
    bid = BidSubmission(
        tender_id=payload.tender_id,
        bidder_id=bidder.id,
        status="SUBMITTED",
        submitted_at=_utcnow(),
    )
    db.add(bid)
    db.commit()
    db.refresh(bid)
    db.refresh(bidder)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="BID_SUBMITTED",
        entity_type="bid_submission",
        entity_id=str(bid.id),
        metadata={"tender_id": payload.tender_id, "legal_name": bidder.legal_name},
    )
    return BidCreateResponse(
        bid=BidOut.model_validate(bid),
        bidder=BidderOut.model_validate(bidder),
    )


@router.get("", response_model=list[BidListItem])
def list_bids(
    tender_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List bid submissions, optionally filtered by tender."""
    query = db.query(BidSubmission).order_by(BidSubmission.id.desc())
    if tender_id is not None:
        query = query.filter(BidSubmission.tender_id == tender_id)
    bids = query.all()
    bidders = {b.id: b for b in db.query(Bidder).all()}
    return [
        BidListItem(
            bid_id=bid.id,
            legal_name=(bidders.get(bid.bidder_id).legal_name if bidders.get(bid.bidder_id) else ""),
            bid_status=bid.status,
            compliance_score=bid.compliance_score,
            risk_level=bid.risk_level,
            recommendation=bid.recommendation,
            officer_decision=bid.officer_decision,
            submitted_at=bid.submitted_at,
        )
        for bid in bids
    ]


def _bid_audit(db: Session, bid: BidSubmission, doc_ids: list[int]) -> list[AuditOut]:
    """Newest-first audit trail covering the bid, its documents and bidder."""
    entity_filters = [
        and_(AuditLog.entity_type == "bid_submission", AuditLog.entity_id == str(bid.id)),
        and_(AuditLog.entity_type == "bidder", AuditLog.entity_id == str(bid.bidder_id)),
    ]
    if doc_ids:
        entity_filters.append(
            and_(
                AuditLog.entity_type == "document",
                AuditLog.entity_id.in_([str(d) for d in doc_ids]),
            )
        )
    rows = (
        db.query(AuditLog, User.name.label("user_name"))
        .outerjoin(User, AuditLog.user_id == User.id)
        .filter(or_(*entity_filters))
        .order_by(AuditLog.id.desc())
        .limit(100)
        .all()
    )
    out = []
    for entry, user_name in rows:
        out.append(
            AuditOut(
                id=entry.id,
                user_id=entry.user_id,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                timestamp=entry.timestamp,
                previous_hash=entry.previous_hash,
                current_hash=entry.current_hash,
                metadata=entry.meta or {},
                user_name=user_name,
            )
        )
    return out


@router.get("/{bid_id}", response_model=BidDetailOut)
def get_bid(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full bid detail: bid, bidder, tender, documents, compliance, risk,
    verification checks, recommendation, overrides, clarifications, audit."""
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    bidder = db.get(Bidder, bid.bidder_id)
    tender = db.get(Tender, bid.tender_id)

    documents = (
        db.query(Document).filter(Document.bid_id == bid_id).order_by(Document.id).all()
    )
    doc_ids = [d.id for d in documents]

    comp_rows = (
        db.query(ComplianceResult, TenderRequirement)
        .outerjoin(TenderRequirement, ComplianceResult.requirement_id == TenderRequirement.id)
        .filter(ComplianceResult.bid_id == bid_id)
        .order_by(ComplianceResult.id)
        .all()
    )
    compliance_results = []
    for result, req in comp_rows:
        item = ComplianceResultOut.model_validate(result)
        item.requirement_name = req.requirement_name if req else None
        item.requirement = RequirementOut.model_validate(req) if req else None
        compliance_results.append(item)

    risk_row = db.query(RiskAssessment).filter(RiskAssessment.bid_id == bid_id).one_or_none()
    risk = RiskOut.model_validate(risk_row) if risk_row else None

    checks = (
        db.query(VerificationCheck)
        .filter(VerificationCheck.bid_id == bid_id)
        .order_by(VerificationCheck.verified_at.desc(), VerificationCheck.id.desc())
        .all()
    )

    recommendation = None
    if bid.recommendation:
        stored_evidence = bid.recommendation_evidence or []
        if isinstance(stored_evidence, dict):
            # Legacy shape (pre-fix seeds): normalize to the contract list shape.
            stored_evidence = [
                {"type": "requirement", "id": i}
                for i in stored_evidence.get("requirement_ids", [])
            ] + [
                {"type": "verification_check", "id": i}
                for i in stored_evidence.get("check_ids", [])
            ]
        recommendation = RecommendationOut(
            recommendation=bid.recommendation,
            reason=bid.recommendation_reason,
            evidence=stored_evidence,
            policy_context=bid.policy_context or [],
            provider="rules+policy-retrieval" if (bid.policy_context or []) else None,
        )

    overrides = (
        db.query(Override).filter(Override.bid_id == bid_id).order_by(Override.id.desc()).all()
    )
    clarifications = (
        db.query(Clarification)
        .filter(Clarification.bid_id == bid_id)
        .order_by(Clarification.id.desc())
        .all()
    )

    return BidDetailOut(
        bid=BidOut.model_validate(bid),
        bidder=BidderOut.model_validate(bidder),
        tender=(
            {"id": tender.id, "tender_number": tender.tender_number, "title": tender.title}
            if tender
            else {}
        ),
        documents=[DocumentOut.model_validate(d) for d in documents],
        compliance_results=compliance_results,
        risk=risk,
        verification_checks=[VerificationCheckOut.model_validate(c) for c in checks],
        recommendation=recommendation,
        overrides=[OverrideOut.model_validate(o) for o in overrides],
        clarifications=[ClarificationOut.model_validate(c) for c in clarifications],
        audit=_bid_audit(db, bid, doc_ids),
    )


@router.get("/{bid_id}/documents", response_model=list[DocumentOut], tags=["documents"])
def bid_documents(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all documents of a bid."""
    if db.get(BidSubmission, bid_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    documents = (
        db.query(Document).filter(Document.bid_id == bid_id).order_by(Document.id.desc()).all()
    )
    return [DocumentOut.model_validate(d) for d in documents]


@router.post("/{bid_id}/seed-demo-evidence")
def seed_demo_evidence(
    bid_id: int,
    payload: DemoEvidenceSeedRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Attach a fictional demo-bidder evidence dossier to an existing bid.

    Stores the dossier as a normal document and runs the REAL extraction
    pipeline (classification + regex/LLM extraction) — the same service that
    runs automatically on upload. Verification, compliance/risk and the AI
    recommendation are deliberately NOT pre-computed: the officer runs those
    from the existing Bid Detail buttons, so scores are derived live.
    Idempotent per (bid, profile): a repeat call creates no duplicate
    bidder or document rows.
    """
    from app.services import demo_seed_service

    try:
        return demo_seed_service.seed_demo_bidder_evidence(
            db, bid_id, payload.profile_key, user_id=user.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )


@router.delete("/{bid_id}")
def delete_bid(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Delete a bid submission and all its derived data (documents, extracted
    fields, verification checks, compliance results, risk, clarifications).

    Procurement Officer only. The append-only audit trail is preserved; a
    ``BID_DELETED`` event records the deletion.
    """
    from app.services import delete_service

    try:
        return delete_service.delete_bid(db, bid_id, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
