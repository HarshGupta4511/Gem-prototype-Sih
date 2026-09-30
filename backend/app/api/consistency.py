"""Cross-document consistency endpoints.

- Run checks: PROCUREMENT_OFFICER, VERIFIER.
- View results: PROCUREMENT_OFFICER, VERIFIER, AUDITOR.
- ADMIN has no procurement role here.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models.models import User
from app.services import consistency_service

router = APIRouter(prefix="/api/consistency", tags=["consistency"])

_RUNNER = require_roles("PROCUREMENT_OFFICER", "VERIFIER")
_VIEWER = require_roles("PROCUREMENT_OFFICER", "VERIFIER", "AUDITOR")


@router.post("/bids/{bid_id}/run")
def run_checks(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_RUNNER),
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
    user: User = Depends(_VIEWER),
):
    """Stored cross-document consistency checks for a bid."""
    try:
        return consistency_service.get_consistency(db, bid_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
