"""Audit endpoints (CONTRACT.md §5: Audit)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models.models import (
    AuditLog,
    Bidder,
    BidSubmission,
    Clarification,
    Document,
    Tender,
    User,
)
from app.schemas.schemas import AuditOut, AuditVerifyResponse
from app.services import audit_service

router = APIRouter(prefix="/api/audit", tags=["audit"])

_VERIFIER = require_roles("AUDITOR", "ADMIN", "PROCUREMENT_OFFICER")

# Generic/housekeeping actions that would clutter a tender-level activity
# history. Kept out of the consolidated tender audit view.
_TENDER_AUDIT_EXCLUDED_ACTIONS = frozenset(
    {"LOGIN", "AUDIT_VERIFIED", "SEED", "KNOWLEDGE_UPDATED"}
)


def _audit_out(entry: AuditLog, user_name: str | None, target_label: str | None = None) -> AuditOut:
    return AuditOut(
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
        target_label=target_label,
    )


@router.get("", response_model=list[AuditOut])
def list_audit(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Audit trail, newest first, with the acting user's name."""
    query = (
        db.query(AuditLog, User.name.label("user_name"))
        .outerjoin(User, AuditLog.user_id == User.id)
        .order_by(AuditLog.id.desc())
    )
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    rows = query.limit(limit).all()
    return [_audit_out(entry, user_name) for entry, user_name in rows]


@router.get("/by-tender/{tender_id}", response_model=list[AuditOut])
def audit_by_tender(
    tender_id: int,
    limit: int = Query(default=200, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Consolidated activity history for one tender.

    Covers tender-level events plus every event on the tender's bids,
    documents and clarifications — newest first, with a human-readable
    ``target_label`` (bidder name / document filename / tender number).
    Generic housekeeping actions (login, chain verification, seeding) are
    excluded so the view stays a clean tender activity history.
    """
    tender = db.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")

    bids = db.query(BidSubmission).filter(BidSubmission.tender_id == tender_id).all()
    bid_ids = [b.id for b in bids]
    bidder_names = {
        b.id: (db.get(Bidder, b.bidder_id).legal_name if b.bidder_id else "")
        for b in bids
    }

    doc_labels: dict[str, str] = {}
    doc_bid_ids: dict[str, int] = {}
    if bid_ids:
        docs = db.query(Document).filter(Document.bid_id.in_(bid_ids)).all()
        for d in docs:
            name = bidder_names.get(d.bid_id, "")
            doc_labels[str(d.id)] = (
                f"{d.filename} ({name})" if name else d.filename
            )
            doc_bid_ids[str(d.id)] = d.bid_id

    clar_labels: dict[str, str] = {}
    if bid_ids:
        clars = db.query(Clarification).filter(Clarification.bid_id.in_(bid_ids)).all()
        for c in clars:
            subject = c.subject or "Clarification"
            name = bidder_names.get(c.bid_id, "")
            clar_labels[str(c.id)] = f"{subject} ({name})" if name else subject

    clauses = [
        (AuditLog.entity_type == "tender") & (AuditLog.entity_id == str(tender_id)),
    ]
    if bid_ids:
        bid_keys = [str(i) for i in bid_ids]
        clauses.append(
            (AuditLog.entity_type == "bid_submission") & (AuditLog.entity_id.in_(bid_keys))
        )
    if doc_labels:
        clauses.append(
            (AuditLog.entity_type == "document")
            & (AuditLog.entity_id.in_(list(doc_labels)))
        )
    if clar_labels:
        clauses.append(
            (AuditLog.entity_type == "clarification")
            & (AuditLog.entity_id.in_(list(clar_labels)))
        )

    rows = (
        db.query(AuditLog, User.name.label("user_name"))
        .outerjoin(User, AuditLog.user_id == User.id)
        .filter(or_(*clauses))
        .filter(~AuditLog.action.in_(_TENDER_AUDIT_EXCLUDED_ACTIONS))
        .order_by(AuditLog.id.desc())
        .limit(limit)
        .all()
    )

    out: list[AuditOut] = []
    for entry, user_name in rows:
        label: str | None = None
        if entry.entity_type == "tender":
            label = tender.tender_number
        elif entry.entity_type == "bid_submission":
            label = bidder_names.get(int(entry.entity_id)) or None
        elif entry.entity_type == "document":
            label = doc_labels.get(entry.entity_id)
        elif entry.entity_type == "clarification":
            label = clar_labels.get(entry.entity_id)
        out.append(_audit_out(entry, user_name, label))
    return out


@router.post("/verify", response_model=AuditVerifyResponse)
def verify_audit(
    db: Session = Depends(get_db),
    user: User = Depends(_VERIFIER),
):
    """Recompute the whole audit hash chain and report validity."""
    result = audit_service.verify_chain(db)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="AUDIT_VERIFIED",
        entity_type="audit",
        entity_id="chain",
        metadata={"valid": result.get("valid"), "checked": result.get("checked")},
    )
    return AuditVerifyResponse(
        valid=result.get("valid", False),
        checked=result.get("checked", 0),
        broken_at=result.get("broken_at"),
    )
