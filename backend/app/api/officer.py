"""Officer workflow endpoints (CONTRACT.md §5: Officer workflow)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_officer
from app.models.models import (
    BidSubmission,
    Clarification,
    ClarificationStatus,
    ComplianceResult,
    Document,
    Override,
    OverrideTargetType,
    User,
    VerificationCheck,
)
from app.schemas.schemas import (
    BidOut,
    ClarificationCreate,
    ClarificationOut,
    DecisionRequest,
    OverrideCreate,
    OverrideOut,
)
from app.services import audit_service

router = APIRouter(prefix="/api/officer", tags=["officer"])

_OFFICER = require_officer()

DECISION_TO_STATUS = {
    "APPROVE": "APPROVED",
    "REJECT": "REJECTED",
    "ESCALATE": "ESCALATED",
    "REQUEST_CLARIFICATION": "CLARIFICATION_REQUESTED",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_bid(db: Session, bid_id: int) -> BidSubmission:
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    return bid


@router.post("/decision", response_model=BidOut)
def officer_decision(
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Record the officer's decision on a bid and move its status accordingly.

    The original decision always remains in the audit history. Replacing a
    recorded decision requires an explicit confirmation flag, a new decision
    and a written reason — and is logged as OFFICER_DECISION_CHANGED.
    """
    decision = payload.decision.value
    bid = _get_bid(db, payload.bid_id)
    previous_decision = bid.officer_decision
    is_change = previous_decision is not None
    if is_change and not payload.confirm_change:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Changing a recorded decision requires explicit confirmation (confirm_change=True)",
        )
    if is_change and not (payload.reason or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reason is required when changing a recorded decision",
        )
    if decision in ("REJECT", "ESCALATE", "REQUEST_CLARIFICATION") and not (payload.reason or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A reason is required for REJECT, ESCALATE and REQUEST_CLARIFICATION",
        )
    bid.officer_decision = decision
    bid.officer_decision_reason = payload.reason
    bid.decided_by = user.id
    bid.decided_at = _utcnow()
    bid.status = DECISION_TO_STATUS[decision]
    db.commit()
    db.refresh(bid)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action=(
            "OFFICER_DECISION_CHANGED" if is_change else "OFFICER_DECISION"
        ),
        entity_type="bid_submission",
        entity_id=str(bid.id),
        metadata={"decision": decision, "reason": payload.reason, "previous_decision": previous_decision},
    )
    return BidOut.model_validate(bid)


@router.post("/override", response_model=OverrideOut)
def record_override(
    payload: OverrideCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Record an officer override against a compliance result or verification check.

    The original finding is never deleted: compliance results keep their first
    original_status and are flagged overridden=true.
    """
    target_type = payload.target_type.value
    if payload.supporting_document_id is not None and db.get(
        Document, payload.supporting_document_id
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supporting document not found",
        )

    if target_type == OverrideTargetType.COMPLIANCE_RESULT.value:
        result = db.get(ComplianceResult, payload.target_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Compliance result not found",
            )
        # Keep the FIRST original status; the finding itself is never deleted.
        if result.original_status is None:
            result.original_status = result.status
        result.overridden = True
        result.override_comment = payload.officer_comment
        override = Override(
            bid_id=result.bid_id,
            target_type=target_type,
            target_id=payload.target_id,
            original_status=result.original_status,
            officer_comment=payload.officer_comment,
            supporting_document_id=payload.supporting_document_id,
            created_by=user.id,
        )
    else:  # VERIFICATION
        check = db.get(VerificationCheck, payload.target_id)
        if check is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification check not found",
            )
        override = Override(
            bid_id=check.bid_id,
            target_type=target_type,
            target_id=payload.target_id,
            original_status=check.verification_status,
            officer_comment=payload.officer_comment,
            supporting_document_id=payload.supporting_document_id,
            created_by=user.id,
        )
    db.add(override)
    db.commit()
    db.refresh(override)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="OVERRIDE_RECORDED",
        entity_type="override",
        entity_id=str(override.id),
        metadata={
            "target_type": target_type,
            "target_id": payload.target_id,
            "bid_id": override.bid_id,
        },
    )
    return OverrideOut.model_validate(override)


@router.post("/clarification", response_model=ClarificationOut)
def create_clarification(
    payload: ClarificationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Create a DRAFT clarification (officer edits before sending)."""
    _get_bid(db, payload.bid_id)
    clarification = Clarification(
        bid_id=payload.bid_id,
        subject=payload.subject,
        body=payload.body,
        status=ClarificationStatus.DRAFT.value,
        created_by=user.id,
    )
    db.add(clarification)
    db.commit()
    db.refresh(clarification)
    return ClarificationOut.model_validate(clarification)


@router.post("/clarification/{clarification_id}/send", response_model=ClarificationOut)
def send_clarification(
    clarification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Mark a clarification SENT (no real email in demo; records intent)."""
    clarification = db.get(Clarification, clarification_id)
    if clarification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clarification not found",
        )
    clarification.status = ClarificationStatus.SENT.value
    clarification.sent_at = _utcnow()
    db.commit()
    db.refresh(clarification)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="CLARIFICATION_SENT",
        entity_type="clarification",
        entity_id=str(clarification.id),
        metadata={"bid_id": clarification.bid_id, "subject": clarification.subject},
    )
    return ClarificationOut.model_validate(clarification)


@router.get("/clarifications", response_model=list[ClarificationOut])
def list_clarifications(
    bid_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List clarifications, optionally filtered by bid."""
    query = db.query(Clarification).order_by(Clarification.id.desc())
    if bid_id is not None:
        query = query.filter(Clarification.bid_id == bid_id)
    return [ClarificationOut.model_validate(c) for c in query.all()]
