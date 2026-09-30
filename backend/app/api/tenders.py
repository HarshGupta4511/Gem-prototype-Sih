"""Tender endpoints (CONTRACT.md §5: Tenders)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_roles
from app.models.models import (
    BidStatus,
    BidSubmission,
    Bidder,
    RiskLevel,
    Tender,
    TenderRequirement,
    User,
)
from app.schemas.schemas import (
    ComparisonBidderRow,
    ComparisonMatrixRow,
    ComparisonOut,
    ComparisonRequirementRow,
    RequirementCreate,
    RequirementOut,
    RequirementsBulkCreate,
    SuggestRequirementsRequest,
    SuggestRequirementsResponse,
    SuggestedRequirement,
    TenderAnalyzeRequest,
    TenderAnalyzeResponse,
    TenderBidderRow,
    TenderCreate,
    TenderDetailOut,
    TenderListItem,
    TenderOut,
)
from app.services import audit_service, tender_intel_service

router = APIRouter(prefix="/api/tenders", tags=["tenders"])

_OFFICER = require_roles("PROCUREMENT_OFFICER")


def _apply_requirement_inference(req) -> dict:
    """Resolve the internal fields stored for a wizard-supplied requirement.

    The Step-2 UI no longer collects ``rule_type`` / ``verification_source`` /
    ``rule_config`` (implementation-level fields). When a requirement arrives
    WITHOUT a rule_config (e.g. typed manually by the officer), those internal
    fields are inferred deterministically from the requirement name so the
    compliance engine keeps working unchanged. Requirements that already carry
    a rule_config (analyze-draft output, standard template) are stored as-is.
    """
    if req.rule_config:
        return {
            "rule_type": req.rule_type.value,
            "category": req.category.value,
            "rule_config": req.rule_config,
            "verification_source": (
                req.verification_source.value if req.verification_source else None
            ),
        }
    inferred = tender_intel_service.infer_requirement_metadata(req.requirement_name, req.threshold)
    return {
        "rule_type": inferred["rule_type"],
        "category": inferred["category"],
        "rule_config": inferred["rule_config"],
        "verification_source": inferred["verification_source"],
    }


def _validate_wizard_weights(requirements: list[RequirementCreate]) -> None:
    """Enforce the tender-wizard weight rules: non-negative weights summing to 100."""
    for req in requirements:
        if req.weight < 0 or req.weight != req.weight:  # NaN check
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Weight for '{req.requirement_name}' must be a non-negative number",
            )
    total = round(sum(req.weight for req in requirements), 2)
    if total != 100.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Total requirement weight must equal 100 (got {total})",
        )


@router.post("", response_model=TenderOut)
def create_tender(
    payload: TenderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Create a tender; tender_number must be unique.

    When ``payload.requirements`` is supplied (tender wizard), the requirements
    are validated (weights non-negative, total exactly 100) and created in the
    same transaction — nothing is persisted unless both succeed.

    The issue date is ALWAYS the server-side creation date: any client-supplied
    ``issue_date`` is ignored. The closing date must be after the issue date.
    """
    if db.query(Tender).filter(Tender.tender_number == payload.tender_number).one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tender number '{payload.tender_number}' already exists",
        )
    if payload.requirements:
        _validate_wizard_weights(payload.requirements)
    issue_date = date.today()  # server-side source of truth; never trust the client
    if payload.closing_date is not None and payload.closing_date <= issue_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Closing date must be after the tender issue date.",
        )
    tender = Tender(
        tender_number=payload.tender_number,
        title=payload.title,
        organization=payload.organization,
        department=payload.department,
        description=payload.description,
        issue_date=issue_date,
        closing_date=payload.closing_date,
        estimated_value_inr=payload.estimated_value_inr,
        tender_type=payload.tender_type,
        bid_type=payload.bid_type,
        emd_amount_inr=payload.emd_amount_inr,
        delivery_period=payload.delivery_period,
        place_of_delivery=payload.place_of_delivery,
        created_by=user.id,
    )
    db.add(tender)
    db.flush()  # assign tender.id for the requirement rows below
    if payload.requirements:
        for req in payload.requirements:
            internal = _apply_requirement_inference(req)
            db.add(
                TenderRequirement(
                    tender_id=tender.id,
                    requirement_name=req.requirement_name,
                    category=internal["category"],
                    description=req.description,
                    mandatory=req.mandatory,
                    rule_type=internal["rule_type"],
                    rule_config=internal["rule_config"],
                    threshold=req.threshold,
                    expected_value=req.expected_value,
                    verification_source=internal["verification_source"],
                    weight=req.weight,
                    policy_reference=req.policy_reference,
                )
            )
    db.commit()
    db.refresh(tender)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="TENDER_CREATED",
        entity_type="tender",
        entity_id=str(tender.id),
        metadata={
            "tender_number": tender.tender_number,
            "title": tender.title,
            "requirements_created": len(payload.requirements or []),
        },
    )
    return TenderOut.model_validate(tender)


@router.get("", response_model=list[TenderListItem])
def list_tenders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List tenders with per-tender bid aggregates."""
    tenders = db.query(Tender).order_by(Tender.id.desc()).all()
    bids = db.query(BidSubmission).all()
    by_tender: dict[int, list[BidSubmission]] = {}
    for bid in bids:
        by_tender.setdefault(bid.tender_id, []).append(bid)

    items = []
    for tender in tenders:
        tbids = by_tender.get(tender.id, [])
        scores = [b.compliance_score for b in tbids if b.compliance_score is not None]
        items.append(
            TenderListItem(
                **TenderOut.model_validate(tender).model_dump(),
                bidder_count=len(tbids),
                pending_reviews=sum(
                    1
                    for b in tbids
                    if b.status in (BidStatus.SUBMITTED.value, BidStatus.UNDER_REVIEW.value)
                    and b.officer_decision is None
                ),
                avg_compliance=round(sum(scores) / len(scores), 2) if scores else None,
                high_risk_count=sum(
                    1
                    for b in tbids
                    if b.risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)
                ),
            )
        )
    return items


@router.get("/{tender_id}", response_model=TenderDetailOut)
def get_tender(
    tender_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Tender detail: requirements, bidder rows and aggregate stats."""
    tender = db.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    requirements = (
        db.query(TenderRequirement)
        .filter(TenderRequirement.tender_id == tender_id)
        .order_by(TenderRequirement.id)
        .all()
    )
    bids = (
        db.query(BidSubmission)
        .filter(BidSubmission.tender_id == tender_id)
        .order_by(BidSubmission.id)
        .all()
    )
    bidders = {b.id: b for b in db.query(Bidder).filter(Bidder.tender_id == tender_id).all()}

    rows = []
    for bid in bids:
        bidder = bidders.get(bid.bidder_id)
        if bidder is None:
            continue
        rows.append(
            TenderBidderRow(
                bid_id=bid.id,
                legal_name=bidder.legal_name,
                trade_name=bidder.trade_name,
                pan=bidder.pan,
                gstin=bidder.gstin,
                udyam=bidder.udyam,
                cin=bidder.cin,
                bid_status=bid.status,
                compliance_score=bid.compliance_score,
                risk_level=bid.risk_level,
                recommendation=bid.recommendation,
                officer_decision=bid.officer_decision,
                submitted_at=bid.submitted_at,
            )
        )

    scores = [b.compliance_score for b in bids if b.compliance_score is not None]

    return TenderDetailOut(
        tender=TenderOut.model_validate(tender),
        requirements=[RequirementOut.model_validate(r) for r in requirements],
        bidders=rows,
        stats={
            "bidder_count": len(bids),
            "avg_compliance": round(sum(scores) / len(scores), 2) if scores else None,
            "high_risk_count": sum(
                1
                for b in bids
                if b.risk_level in (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)
            ),
            "pending_reviews": sum(
                1
                for b in bids
                if b.status in (BidStatus.SUBMITTED.value, BidStatus.UNDER_REVIEW.value)
                and b.officer_decision is None
            ),
        },
    )


@router.post("/{tender_id}/requirements", response_model=list[RequirementOut])
def set_requirements(
    tender_id: int,
    payload: RequirementsBulkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Replace the tender's requirements with the supplied list."""
    tender = db.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    # Same 100%-total rule as the creation wizard: requirement weights must be
    # non-negative and sum to exactly 100, enforced server-side.
    _validate_wizard_weights(payload.requirements)
    db.query(TenderRequirement).filter(TenderRequirement.tender_id == tender_id).delete()
    created: list[TenderRequirement] = []
    for req in payload.requirements:
        internal = _apply_requirement_inference(req)
        row = TenderRequirement(
            tender_id=tender_id,
            requirement_name=req.requirement_name,
            category=internal["category"],
            description=req.description,
            mandatory=req.mandatory,
            rule_type=internal["rule_type"],
            rule_config=internal["rule_config"],
            threshold=req.threshold,
            expected_value=req.expected_value,
            verification_source=internal["verification_source"],
            weight=req.weight,
            policy_reference=req.policy_reference,
        )
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="TENDER_CREATED",
        entity_type="tender",
        entity_id=str(tender_id),
        metadata={"requirements_replaced": len(created)},
    )
    return [RequirementOut.model_validate(r) for r in created]


@router.post("/{tender_id}/analyze", response_model=TenderAnalyzeResponse)
def analyze_tender(
    tender_id: int,
    payload: TenderAnalyzeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Parse free-form tender text into structured requirement drafts."""
    tender = db.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    analysis = tender_intel_service.analyze_tender_text(payload.tender_text)
    return TenderAnalyzeResponse(
        requirements=[RequirementCreate(**d) for d in analysis.get("requirements", [])]
    )


@router.post("/analyze-draft", response_model=TenderAnalyzeResponse)
def analyze_draft(
    payload: TenderAnalyzeRequest,
    user: User = Depends(_OFFICER),
):
    """Parse free-form tender text into requirement drafts without a tender.

    Used by the New Tender wizard (Step 2): the tender does not exist yet, so
    drafts are generated from the Step-1 description and returned for officer
    review. Nothing is persisted here.
    """
    analysis = tender_intel_service.analyze_tender_text(payload.tender_text)
    return TenderAnalyzeResponse(
        requirements=[RequirementCreate(**d) for d in analysis.get("requirements", [])]
    )


@router.post("/suggest-requirements", response_model=SuggestRequirementsResponse)
def suggest_requirements(
    payload: SuggestRequirementsRequest,
    user: User = Depends(_OFFICER),
):
    """AI-suggested tender requirements for the New Tender wizard (Step 2).

    Uses the configured LLM provider (Gemini/OpenAI). Suggestions are ADVISORY:
    the officer reviews, edits and confirms every requirement before the tender
    is created. Compliance PASS/FAIL stays with the deterministic rules engine.

    Returns 503 when no real LLM provider is configured (the deterministic
    /analyze-draft endpoint remains available for quota-free drafting).
    """
    from app.services.llm_service import LLMError, get_llm_provider

    provider = get_llm_provider()
    try:
        suggestions = provider.suggest_requirements(payload.model_dump())
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    return SuggestRequirementsResponse(
        requirements=[SuggestedRequirement(**s) for s in suggestions],
        provider=provider.name,
    )


@router.get("/{tender_id}/comparison", response_model=ComparisonOut)
def comparison(
    tender_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Requirement × bidder compliance matrix for a tender."""
    from app.models.models import ComplianceResult  # noqa: PLC0415

    tender = db.get(Tender, tender_id)
    if tender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not found")
    requirements = (
        db.query(TenderRequirement)
        .filter(TenderRequirement.tender_id == tender_id)
        .order_by(TenderRequirement.id)
        .all()
    )
    bids = (
        db.query(BidSubmission)
        .filter(BidSubmission.tender_id == tender_id)
        .order_by(BidSubmission.id)
        .all()
    )
    bidders = {b.id: b for b in db.query(Bidder).filter(Bidder.tender_id == tender_id).all()}
    status_map: dict[tuple[int, int], str] = {}
    if bids:
        bid_ids = [b.id for b in bids]
        for r in db.query(ComplianceResult).filter(ComplianceResult.bid_id.in_(bid_ids)).all():
            status_map[(r.requirement_id, r.bid_id)] = r.status

    matrix = [
        ComparisonMatrixRow(
            requirement_id=req.id,
            requirement_name=req.requirement_name,
            results={
                bid.id: status_map.get((req.id, bid.id), "NOT_APPLICABLE") for bid in bids
            },
        )
        for req in requirements
    ]
    return ComparisonOut(
        requirements=[
            ComparisonRequirementRow(id=req.id, requirement_name=req.requirement_name)
            for req in requirements
        ],
        bidders=[
            ComparisonBidderRow(
                bid_id=bid.id,
                legal_name=(bidders[bid.bidder_id].legal_name if bid.bidder_id in bidders else ""),
                compliance_score=bid.compliance_score,
                risk_level=bid.risk_level,
            )
            for bid in bids
        ],
        matrix=matrix,
    )


@router.delete("/{tender_id}")
def delete_tender(
    tender_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Delete a tender and every bid/derived record under it.

    Procurement Officer only. The append-only audit trail is preserved; a
    ``TENDER_DELETED`` event records the deletion.
    """
    from app.services import delete_service

    try:
        return delete_service.delete_tender(db, tender_id, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
