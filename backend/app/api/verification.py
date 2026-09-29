"""Verification endpoints (CONTRACT.md §5: Verification)."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models.models import BidSubmission, User, VerificationCheck, VerificationStatus
from app.schemas.schemas import (
    VerificationCheckOut,
    VerificationRunRequest,
    VerificationRunResponse,
)
from app.services import verification_service

router = APIRouter(prefix="/api/verification", tags=["verification"])

_RUNNER = require_roles("VERIFIER", "PROCUREMENT_OFFICER")


def _validate_check_status(value: str) -> str:
    try:
        return VerificationStatus(value).value
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification status '{value}'",
        ) from None


@router.get("", response_model=list[VerificationCheckOut])
def list_checks(
    bid_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all verification checks (newest first), filterable by bid and status."""
    query = db.query(VerificationCheck).order_by(
        VerificationCheck.verified_at.desc(), VerificationCheck.id.desc()
    )
    if bid_id is not None:
        query = query.filter(VerificationCheck.bid_id == bid_id)
    if status is not None:
        query = query.filter(VerificationCheck.verification_status == _validate_check_status(status))
    return [VerificationCheckOut.model_validate(c) for c in query.all()]


@router.post("/run", response_model=VerificationRunResponse)
def run_verification(
    payload: VerificationRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_RUNNER),
):
    """Run every applicable mock government adapter for a bid and store checks."""
    if db.get(BidSubmission, payload.bid_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    verification_service.run_verification(db, payload.bid_id, user_id=user.id)
    checks = verification_service.get_checks(db, payload.bid_id)
    return VerificationRunResponse(
        checks=[VerificationCheckOut.model_validate(c) for c in checks]
    )


@router.get("/{bid_id}", response_model=VerificationRunResponse)
def get_bid_checks(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Newest verification check per source for a bid."""
    if db.get(BidSubmission, bid_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    checks = verification_service.get_checks(db, bid_id)
    return VerificationRunResponse(
        checks=[VerificationCheckOut.model_validate(c) for c in checks]
    )
