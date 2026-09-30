"""Cross-document consistency endpoints.

Single-role model: the Procurement Officer runs the checks and reviews the
results directly.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_officer
from app.models.models import User
from app.services import consistency_service

router = APIRouter(prefix="/api/consistency", tags=["consistency"])

_OFFICER = require_officer()


@router.post("/bids/{bid_id}/run")
def run_checks(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Run cross-document consistency checks for a bid (replaces prior runs)."""
    try:
        return consistency_service.run_consistency_check(db, bid_id, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bids/{bid_id}")
def get_checks(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Stored cross-document consistency checks for a bid."""
    try:
        return consistency_service.get_consistency(db, bid_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
