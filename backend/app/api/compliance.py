"""Compliance & risk endpoints (CONTRACT.md §5: Compliance & risk)."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models.models import (
    BidSubmission,
    Bidder,
    ComplianceResult,
    RiskAssessment,
    RiskLevel,
    Tender,
    TenderRequirement,
    User,
)
from app.schemas.schemas import (
    ComplianceEvaluateRequest,
    ComplianceEvaluateResponse,
    ComplianceGetResponse,
    ComplianceResultOut,
    RequirementOut,
    RiskOut,
)
from app.services import compliance_service

router = APIRouter(prefix="/api", tags=["compliance"])

_EVALUATOR = require_roles("VERIFIER", "PROCUREMENT_OFFICER")


class ComplianceOverviewItem(BaseModel):
    bid_id: int
    legal_name: str
    tender_number: str
    compliance_score: float | None = None
    evaluated_at: datetime | None = None


class RiskOverviewItem(BaseModel):
    bid_id: int
    legal_name: str
    tender_number: str
    risk_level: RiskLevel | None = None
    risk_score: float | None = None
    top_signals: list[str] = []


def _orm_result_out(result: ComplianceResult, req: TenderRequirement | None) -> ComplianceResultOut:
    out = ComplianceResultOut.model_validate(result)
    out.requirement_name = req.requirement_name if req else None
    out.requirement = RequirementOut.model_validate(req) if req else None
    return out


@router.get("/compliance", response_model=list[ComplianceOverviewItem])
def compliance_overview(
    tender_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Overview of recent compliance evaluations (newest first)."""
    eval_subq = (
        db.query(
            ComplianceResult.bid_id.label("bid_id"),
            func.max(ComplianceResult.created_at).label("evaluated_at"),
        )
        .group_by(ComplianceResult.bid_id)
        .subquery()
    )
    query = (
        db.query(BidSubmission, Bidder.legal_name, Tender.tender_number, eval_subq.c.evaluated_at)
        .join(Bidder, BidSubmission.bidder_id == Bidder.id)
        .join(Tender, BidSubmission.tender_id == Tender.id)
        .outerjoin(eval_subq, eval_subq.c.bid_id == BidSubmission.id)
        .order_by(eval_subq.c.evaluated_at.desc().nulls_last(), BidSubmission.id.desc())
    )
    if tender_id is not None:
        query = query.filter(BidSubmission.tender_id == tender_id)
    return [
        ComplianceOverviewItem(
            bid_id=bid.id,
            legal_name=legal_name,
            tender_number=tender_number,
            compliance_score=bid.compliance_score,
            evaluated_at=evaluated_at,
        )
        for bid, legal_name, tender_number, evaluated_at in query.all()
    ]


@router.post("/compliance/evaluate", response_model=ComplianceEvaluateResponse)
def evaluate(
    payload: ComplianceEvaluateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_EVALUATOR),
):
    """Run the rules engine, then the risk engine; persist results and scores."""
    if db.get(BidSubmission, payload.bid_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    outcome = compliance_service.evaluate_bid(db, payload.bid_id, user_id=user.id)
    rows = (
        db.query(ComplianceResult, TenderRequirement)
        .outerjoin(TenderRequirement, ComplianceResult.requirement_id == TenderRequirement.id)
        .filter(ComplianceResult.bid_id == payload.bid_id)
        .order_by(ComplianceResult.id)
        .all()
    )
    risk_row = (
        db.query(RiskAssessment).filter(RiskAssessment.bid_id == payload.bid_id).one_or_none()
    )
    return ComplianceEvaluateResponse(
        results=[_orm_result_out(r, req) for r, req in rows],
        compliance_score=outcome.get("compliance_score", 0.0),
        risk=RiskOut.model_validate(risk_row),
    )


@router.get("/compliance/{bid_id}", response_model=ComplianceGetResponse)
def get_compliance(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stored compliance results for a bid, with the last evaluation time."""
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    if bid.compliance_score is None and db.query(
        ComplianceResult
    ).filter(ComplianceResult.bid_id == bid_id).count() == 0:
        return ComplianceGetResponse(results=[], compliance_score=None, evaluated_at=None)
    rows = (
        db.query(ComplianceResult, TenderRequirement)
        .outerjoin(TenderRequirement, ComplianceResult.requirement_id == TenderRequirement.id)
        .filter(ComplianceResult.bid_id == bid_id)
        .order_by(ComplianceResult.id)
        .all()
    )
    evaluated_at = (
        db.query(func.max(ComplianceResult.created_at))
        .filter(ComplianceResult.bid_id == bid_id)
        .scalar()
    )
    return ComplianceGetResponse(
        results=[_orm_result_out(r, req) for r, req in rows],
        compliance_score=bid.compliance_score,
        evaluated_at=evaluated_at,
    )


@router.get("/risk", response_model=list[RiskOverviewItem])
def risk_overview(
    tender_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Overview of assessed bid risks (newest first); skips unassessed bids."""
    query = (
        db.query(RiskAssessment, Bidder.legal_name, Tender.tender_number)
        .join(BidSubmission, RiskAssessment.bid_id == BidSubmission.id)
        .join(Bidder, BidSubmission.bidder_id == Bidder.id)
        .join(Tender, BidSubmission.tender_id == Tender.id)
        .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())
    )
    if tender_id is not None:
        query = query.filter(BidSubmission.tender_id == tender_id)
    items = []
    for assessment, legal_name, tender_number in query.all():
        signals = assessment.signals or []
        top_signals = [str(s.get("code")) for s in signals[:3] if isinstance(s, dict) and s.get("code")]
        items.append(
            RiskOverviewItem(
                bid_id=assessment.bid_id,
                legal_name=legal_name,
                tender_number=tender_number,
                risk_level=assessment.risk_level,
                risk_score=assessment.risk_score,
                top_signals=top_signals,
            )
        )
    return items


@router.get("/risk/{bid_id}", response_model=RiskOut)
def get_risk(
    bid_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persisted risk assessment for a bid."""
    if db.get(BidSubmission, bid_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bid not found")
    row = db.query(RiskAssessment).filter(RiskAssessment.bid_id == bid_id).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No risk assessment for this bid",
        )
    return RiskOut.model_validate(row)
