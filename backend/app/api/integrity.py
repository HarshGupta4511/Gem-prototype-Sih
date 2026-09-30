"""Procurement-integrity endpoints.

Role rules (existing auth mechanism, no duplicate permission system):
- Run analysis: PROCUREMENT_OFFICER, VERIFIER.
- View findings / overview / bid signals: PROCUREMENT_OFFICER, VERIFIER, AUDITOR.
- Officer actions (acknowledge / review / investigate / close / note):
  PROCUREMENT_OFFICER only.
- ADMIN has no procurement role here (system administration only).

Every signal is evidence-backed and deterministic; the officer reviews and
decides. Nothing here makes qualification decisions.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models.models import IntegrityFinding, IntegrityStatus, User
from app.services import integrity_service

router = APIRouter(prefix="/api/integrity", tags=["integrity"])

_RUNNER = require_roles("PROCUREMENT_OFFICER", "VERIFIER")
_VIEWER = require_roles("PROCUREMENT_OFFICER", "VERIFIER", "AUDITOR")
_OFFICER = require_roles("PROCUREMENT_OFFICER")


class AnalyzeRequest(BaseModel):
    tender_id: int | None = Field(default=None, description="Scope hint (analysis is global)")


class OfficerActionRequest(BaseModel):
    action: str = Field(
        ..., description="acknowledge | mark_review | investigate | close | add_note"
    )
    note: str | None = Field(default=None, max_length=2000)


def _finding_out(f: IntegrityFinding) -> dict:
    return {
        "id": f.id,
        "tender_id": f.tender_id,
        "bidder_id": f.bidder_id,
        "signal_type": f.signal_type,
        "severity": f.severity,
        "title": f.title,
        "description": f.description,
        "affected_bids": f.affected_bids or [],
        "affected_tenders": f.affected_tenders or [],
        "evidence": f.evidence or [],
        "rule_logic": f.rule_logic,
        "recommended_action": f.recommended_action,
        "status": f.status,
        "is_demo_history": bool(f.is_demo_history),
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "evaluated_at": f.evaluated_at.isoformat() if f.evaluated_at else None,
        "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
        "reviewed_by": f.reviewed_by,
        "officer_note": f.officer_note,
    }


@router.post("/analyze")
def analyze(
    payload: AnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_RUNNER),
):
    """Run deterministic integrity analysis over tender/bid/audit data."""
    return integrity_service.run_integrity_analysis(db, user_id=user.id)


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(_VIEWER),
):
    """Integrity overview counts for the dashboard screen."""
    return integrity_service.overview(db)


@router.get("/findings")
def list_findings(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    tender_id: int | None = Query(default=None),
    bid_id: int | None = Query(default=None),
    include_closed: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(_VIEWER),
):
    """List integrity findings with optional filters."""
    q = db.query(IntegrityFinding)
    if status:
        q = q.filter(IntegrityFinding.status == status.upper())
    elif not include_closed:
        q = q.filter(IntegrityFinding.status != IntegrityStatus.CLOSED.value)
    if severity:
        q = q.filter(IntegrityFinding.severity == severity.upper())
    if signal_type:
        q = q.filter(IntegrityFinding.signal_type == signal_type.upper())
    if tender_id:
        q = q.filter(IntegrityFinding.tender_id == tender_id)
    findings = q.order_by(IntegrityFinding.id.desc()).all()
    if bid_id:
        findings = [
            f for f in findings
            if bid_id in (f.affected_bids or [])
        ]
    return [_finding_out(f) for f in findings]


@router.get("/findings/{finding_id}")
def get_finding(
    finding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_VIEWER),
):
    finding = db.get(IntegrityFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Integrity finding not found")
    return _finding_out(finding)


@router.post("/findings/{finding_id}/actions")
def officer_action(
    finding_id: int,
    payload: OfficerActionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Officer action on a signal: acknowledge / mark_review / investigate /
    close / add_note. Every action is audit-logged."""
    try:
        finding = integrity_service.apply_officer_action(
            db, finding_id, payload.action, user, payload.note
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _finding_out(finding)


@router.get("/bid/{bid_id}/signals")
def bid_signals(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_VIEWER),
):
    """Active (non-closed) integrity signals touching a bid."""
    findings = integrity_service.active_signals_for_bid(db, bid_id)
    return [_finding_out(f) for f in findings]
