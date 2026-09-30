"""Verifier -> Procurement Officer verification-report endpoints.

Role rules (existing auth mechanism, no duplicate permission system):
- Generate / send report, add observations: VERIFIER only.
- Mark report received / opened: PROCUREMENT_OFFICER only.
- View report: PROCUREMENT_OFFICER, VERIFIER, AUDITOR (read-only), ADMIN.
- Officer inbox: PROCUREMENT_OFFICER only.

The report is evidence-based: content is derived live from existing tables and
the lifecycle from the hash-chained audit log. No schema changes.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models.models import User
from app.services import verifier_report_service

router = APIRouter(prefix="/api/verifier-reports", tags=["verifier-reports"])

_VERIFIER = require_roles("VERIFIER")
_OFFICER = require_roles("PROCUREMENT_OFFICER")
_VIEWER = require_roles("PROCUREMENT_OFFICER", "VERIFIER", "AUDITOR", "ADMIN")


class ObservationRequest(BaseModel):
    observation: str = Field(..., min_length=1, max_length=2000)


@router.get("/inbox")
def report_inbox(
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Procurement Officer inbox: verification reports sent for review."""
    return verifier_report_service.inbox(db)


@router.get("/bids/{bid_id}/report")
def get_report(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_VIEWER),
):
    """Full evidence-based verification report for a bid."""
    return verifier_report_service.build_report(db, bid_id)


@router.get("/bids/{bid_id}/lifecycle")
def get_lifecycle(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_VIEWER),
):
    """Report status, observations and timeline for a bid."""
    verifier_report_service._get_bid(db, bid_id)
    return verifier_report_service.report_lifecycle(db, bid_id)


@router.post("/bids/{bid_id}/observations")
def add_observation(
    bid_id: int,
    payload: ObservationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_VERIFIER),
):
    """Verifier adds a professional observation to the report draft."""
    return verifier_report_service.add_observation(db, bid_id, user, payload.observation)


@router.post("/bids/{bid_id}/generate")
def generate_report(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_VERIFIER),
):
    """Verifier finalises the report from the current evidence."""
    return verifier_report_service.generate_report(db, bid_id, user)


@router.post("/bids/{bid_id}/send")
def send_report(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_VERIFIER),
):
    """Verifier hands the report to the Procurement Officer."""
    return verifier_report_service.send_report(db, bid_id, user)


@router.post("/bids/{bid_id}/opened")
def mark_opened(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Record that the Procurement Officer opened the report."""
    return verifier_report_service.mark_opened(db, bid_id, user)


@router.post("/bids/{bid_id}/received")
def mark_received(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Procurement Officer acknowledges receipt of the report (SENT -> RECEIVED)."""
    return verifier_report_service.receive_report(db, bid_id, user)
