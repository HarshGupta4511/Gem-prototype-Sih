"""Dashboard endpoints (CONTRACT.md §5: Dashboard)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.database.session import engine
from app.models.models import (
    BidSubmission,
    DocProcessingStatus,
    Document,
    RiskLevel,
    Tender,
    TenderStatus,
    User,
    VerificationCheck,
    VerificationStatus,
)
from app.schemas.schemas import DashboardCharts, DashboardMetrics, DashboardOut
from app.services import extraction_service, llm_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_PENDING_STATUSES = ("SUBMITTED", "UNDER_REVIEW")
_HIGH_RISK = (RiskLevel.HIGH.value, RiskLevel.CRITICAL.value)
_ISSUE_STATUSES = (
    VerificationStatus.MISMATCH.value,
    VerificationStatus.NOT_FOUND.value,
    VerificationStatus.EXPIRED.value,
    VerificationStatus.UNAVAILABLE.value,
)
_COMPLIANCE_BUCKETS = [("0-50", 0.0, 50.0), ("50-70", 50.0, 70.0), ("70-85", 70.0, 85.0), ("85-100", 85.0, 100.0)]


class ProvidersOut(BaseModel):
    llm_provider: str
    ocr_available: bool
    db_dialect: str
    embedding_path: str
    mock_adapters: bool = True


def _pgvector_importable() -> bool:
    try:
        import pgvector  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


@router.get("", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Platform metrics and chart data per CONTRACT.md §5."""
    tenders = db.query(Tender).all()
    bids = db.query(BidSubmission).all()
    documents = db.query(Document).all()
    checks = db.query(VerificationCheck).all()

    scores = [b.compliance_score for b in bids if b.compliance_score is not None]
    metrics = DashboardMetrics(
        total_tenders=len(tenders),
        active_tenders=sum(1 for t in tenders if t.status == TenderStatus.OPEN.value),
        total_bids=len(bids),
        pending_reviews=sum(
            1
            for b in bids
            if b.status in _PENDING_STATUSES and b.officer_decision is None
        ),
        high_risk_bids=sum(1 for b in bids if b.risk_level in _HIGH_RISK),
        documents_processed=sum(
            1 for d in documents if d.processing_status == DocProcessingStatus.PROCESSED.value
        ),
        avg_compliance_score=round(sum(scores) / len(scores), 2) if scores else None,
        verification_issues=sum(1 for c in checks if c.verification_status in _ISSUE_STATUSES),
    )

    bucket_counts = {label: 0 for label, _, _ in _COMPLIANCE_BUCKETS}
    for score in scores:
        for label, lo, hi in _COMPLIANCE_BUCKETS:
            if lo <= score <= hi and (score < hi or hi == 100.0):
                bucket_counts[label] += 1
                break
    compliance_distribution = [
        {"range": label, "count": bucket_counts[label]} for label, _, _ in _COMPLIANCE_BUCKETS
    ]

    risk_counts: dict[str, int] = {level.value: 0 for level in RiskLevel}
    for b in bids:
        if b.risk_level in risk_counts:
            risk_counts[b.risk_level] += 1
    risk_distribution = [{"level": level, "count": count} for level, count in risk_counts.items()]

    status_counts: dict[str, int] = {st.value: 0 for st in VerificationStatus}
    for c in checks:
        if c.verification_status in status_counts:
            status_counts[c.verification_status] += 1
    verification_status = [
        {"status": st, "count": count} for st, count in status_counts.items()
    ]

    scores_by_tender: dict[int, list[float]] = {}
    for b in bids:
        if b.compliance_score is not None:
            scores_by_tender.setdefault(b.tender_id, []).append(b.compliance_score)
    tender_bidder_comparison = []
    for t in tenders:
        tscores = scores_by_tender.get(t.id, [])
        tender_bidder_comparison.append(
            {
                "tender": t.tender_number,
                "avg_score": round(sum(tscores) / len(tscores), 2) if tscores else None,
            }
        )

    proc_counts: dict[str, int] = {st.value: 0 for st in DocProcessingStatus}
    for d in documents:
        if d.processing_status in proc_counts:
            proc_counts[d.processing_status] += 1
    document_processing = [{"status": st, "count": count} for st, count in proc_counts.items()]

    charts = DashboardCharts(
        compliance_distribution=compliance_distribution,
        risk_distribution=risk_distribution,
        verification_status=verification_status,
        tender_bidder_comparison=tender_bidder_comparison,
        document_processing=document_processing,
    )
    return DashboardOut(metrics=metrics, charts=charts)


@router.get("/providers", response_model=ProvidersOut)
def providers(
    user: User = Depends(get_current_user),
):
    """Provider/environment status for the Settings page."""
    db_url = str(settings.DATABASE_URL or "")
    return ProvidersOut(
        llm_provider=llm_service.get_llm_provider().name,
        ocr_available=extraction_service.ocr_available(),
        db_dialect=engine.dialect.name,
        embedding_path=(
            "pgvector"
            if db_url.startswith("postgres") and _pgvector_importable()
            else "tfidf"
        ),
        mock_adapters=True,
    )
