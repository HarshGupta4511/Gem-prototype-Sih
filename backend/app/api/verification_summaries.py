"""Bid Verification Summary endpoints (single-role model).

The Procurement Officer generates and reviews the summary directly; there is
no verifier handoff, no send/receive workflow. All endpoints require an
authenticated Procurement Officer.

- GET  /api/verification-summaries/bids/{bid_id}            full summary
- GET  /api/verification-summaries/bids/{bid_id}/lifecycle  status/timeline
- POST /api/verification-summaries/bids/{bid_id}/observations  add a note
- POST /api/verification-summaries/bids/{bid_id}/generate     generate
- POST /api/verification-summaries/bids/{bid_id}/regenerate   regenerate

The summary is evidence-based: content is derived live from existing tables
and the lifecycle (DRAFT -> GENERATED -> UPDATED) from the hash-chained audit
log. No schema changes.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_officer
from app.models.models import User
from app.services import verification_summary_service

router = APIRouter(prefix="/api/verification-summaries", tags=["verification-summaries"])

_OFFICER = require_officer()


class ObservationRequest(BaseModel):
    observation: str = Field(..., min_length=1, max_length=2000)


@router.get("/bids/{bid_id}")
def get_summary(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Full evidence-based verification summary for a bid."""
    return verification_summary_service.build_summary(db, bid_id)


@router.get("/bids/{bid_id}/lifecycle")
def get_lifecycle(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Summary status, officer observations and timeline for a bid."""
    return verification_summary_service.summary_lifecycle(db, bid_id)


@router.post("/bids/{bid_id}/observations")
def add_observation(
    bid_id: int,
    payload: ObservationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Procurement Officer adds a professional observation to the summary."""
    return verification_summary_service.add_observation(
        db, bid_id, user, payload.observation
    )


@router.post("/bids/{bid_id}/generate")
def generate_summary(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Procurement Officer finalises the summary from the current evidence."""
    return verification_summary_service.generate_summary(db, bid_id, user)


@router.post("/bids/{bid_id}/regenerate")
def regenerate_summary(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Procurement Officer regenerates the summary after evidence changed."""
    return verification_summary_service.regenerate_summary(db, bid_id, user)
