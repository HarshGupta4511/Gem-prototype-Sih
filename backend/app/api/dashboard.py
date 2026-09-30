"""Dashboard endpoints (CONTRACT.md §5: Dashboard)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.database.session import engine
from app.models.models import (
    AuditLog,
    Bidder,
    BidSubmission,
    ComplianceResult,
    ConsistencyCheck,
    DocProcessingStatus,
    Document,
    IntegrityFinding,
    IntegritySeverity,
    IntegrityStatus,
    RiskLevel,
    Tender,
    TenderRequirement,
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
    # Integrity notices for the officer work queue: open (non-closed) signals
    # sourced from the real integrity_findings table — never frontend-only.
    open_signals = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.status != IntegrityStatus.CLOSED.value)
        .order_by(
            IntegrityFinding.severity
            != IntegritySeverity.REVIEW_REQUIRED.value,
            IntegrityFinding.id.desc(),
        )
        .limit(10)
        .all()
    )
    integrity_notices = [
        {
            "id": f.id,
            "title": f.title,
            "signal_type": f.signal_type,
            "severity": f.severity,
            "status": f.status,
            "is_demo_history": bool(f.is_demo_history),
        }
        for f in open_signals
    ]
    return DashboardOut(
        metrics=metrics,
        charts=charts,
        integrity_notices=integrity_notices,
        work_queue=_build_work_queue(db),
    )


# ---------------------------------------------------------------------------
# Officer work queue (backend-driven, six priorities)
# ---------------------------------------------------------------------------

# (priority, category key, human label) in display order.
_WORK_QUEUE_ORDER = (
    (1, "HIGH_RISK_BIDDER", "High-risk bidder"),
    (2, "STATUTORY_MISMATCH", "Statutory mismatch"),
    (3, "MISSING_MANDATORY_REQUIREMENT", "Missing mandatory requirement"),
    (4, "INTEGRITY_SIGNAL", "Integrity signal"),
    (5, "PENDING_SUMMARY", "Verification summary not generated"),
    (6, "PENDING_OFFICER_DECISION", "Pending officer decision"),
)

_QUEUE_LIMIT_PER_CATEGORY = 10
_QUEUE_LIMIT_TOTAL = 30

# Consistency checks that compare statutory identity/registration values.
_STATUTORY_CHECKS = {
    "ENTITY_NAME_CONSISTENCY",
    "GSTIN_PAN_CONSISTENCY",
    "IDENTIFIER_CONSISTENCY",
    "RETRIEVED_STATUTORY_COMPARISON",
    "DEBARMENT_DECLARATION_CONSISTENCY",
    "OEM_AUTHORIZATION_IDENTITY",
}

# Bidder-declared identity for queue display; raw ids never leak to the UI.
def _queue_bid_ref(bid, bidder_names, tender_numbers) -> dict:
    return {
        "bid_id": bid.id,
        "bidder_name": bidder_names.get(bid.bidder_id),
        "tender_number": tender_numbers.get(bid.tender_id),
        "tender_id": bid.tender_id,
        "link": f"/app/bids/{bid.id}",
    }


def _build_work_queue(db: Session) -> list[dict]:
    """Six-priority officer work queue, derived from stored tables only.

    Every item names the bid, the evidence behind it and where to act. The
    frontend renders this list directly — no frontend-only queue logic.
    """
    bids = {b.id: b for b in db.query(BidSubmission).all()}
    bidder_names = {b.id: b.legal_name for b in db.query(Bidder).all()}
    tender_numbers = {t.id: t.tender_number for t in db.query(Tender).all()}
    queue: list[dict] = []

    def add(priority: int, category: str, label: str, title: str,
            description: str, severity: str, ref: dict,
            finding_id: int | None = None) -> None:
        queue.append({
            "priority": priority,
            "category": category,
            "category_label": label,
            "title": title,
            "description": description,
            "severity": severity,
            "finding_id": finding_id,
            **ref,
        })

    # -- 1. High-risk bidder -------------------------------------------------
    n = 0
    for b in bids.values():
        if n >= _QUEUE_LIMIT_PER_CATEGORY:
            break
        if b.risk_level in _HIGH_RISK and b.officer_decision is None:
            add(1, "HIGH_RISK_BIDDER", "High-risk bidder",
                f"{bidder_names.get(b.bidder_id) or f'Bid #{b.id}'} — risk {b.risk_level}",
                "Risk engine rated this bid HIGH/CRITICAL. Review the risk "
                "signals and evidence before deciding.",
                "REVIEW_REQUIRED" if b.risk_level == RiskLevel.CRITICAL.value else "ELEVATED",
                _queue_bid_ref(b, bidder_names, tender_numbers))
            n += 1

    # -- 2. Statutory mismatch ----------------------------------------------
    mismatch_by_bid: dict[int, list] = {}
    for m in db.query(ConsistencyCheck).filter(
        ConsistencyCheck.result == "MISMATCH",
        ConsistencyCheck.check_name.in_(_STATUTORY_CHECKS),
    ).all():
        mismatch_by_bid.setdefault(m.bid_id, []).append(m)
    ver_issue_by_bid: dict[int, list] = {}
    for c in db.query(VerificationCheck).filter(
        VerificationCheck.verification_status.in_(_ISSUE_STATUSES)
    ).all():
        ver_issue_by_bid.setdefault(c.bid_id, []).append(c)
    n = 0
    for bid_id in sorted(set(mismatch_by_bid) | set(ver_issue_by_bid)):
        if n >= _QUEUE_LIMIT_PER_CATEGORY:
            break
        b = bids.get(bid_id)
        if b is None or b.officer_decision is not None:
            continue
        parts = []
        ms = mismatch_by_bid.get(bid_id, [])
        if ms:
            checks = sorted({m.check_name for m in ms})
            parts.append(f"{len(ms)} cross-document mismatch(es): "
                         + ", ".join(checks))
        vs = ver_issue_by_bid.get(bid_id, [])
        if vs:
            parts.append(f"{len(vs)} statutory verification issue(s): "
                         + ", ".join(sorted({c.source for c in vs})))
        add(2, "STATUTORY_MISMATCH", "Statutory mismatch",
            f"{bidder_names.get(b.bidder_id) or f'Bid #{bid_id}'} — statutory mismatch",
            "; ".join(parts) + ". Requires Procurement Officer review.",
            "REVIEW_REQUIRED",
            _queue_bid_ref(b, bidder_names, tender_numbers))
        n += 1

    # -- 3. Missing mandatory requirement ------------------------------------
    fail_rows = (
        db.query(ComplianceResult, TenderRequirement)
        .join(TenderRequirement,
              ComplianceResult.requirement_id == TenderRequirement.id)
        .filter(ComplianceResult.status == "FAIL",
                TenderRequirement.mandatory.is_(True))
        .all()
    )
    fail_by_bid: dict[int, list] = {}
    for res, req in fail_rows:
        fail_by_bid.setdefault(res.bid_id, []).append(req)
    n = 0
    for bid_id, reqs in sorted(fail_by_bid.items()):
        if n >= _QUEUE_LIMIT_PER_CATEGORY:
            break
        b = bids.get(bid_id)
        if b is None or b.officer_decision is not None:
            continue
        names = ", ".join(sorted({r.requirement_name for r in reqs if r.requirement_name})[:3])
        more = f" (+{len(reqs) - 3} more)" if len(reqs) > 3 else ""
        add(3, "MISSING_MANDATORY_REQUIREMENT", "Missing mandatory requirement",
            f"{bidder_names.get(b.bidder_id) or f'Bid #{bid_id}'} — "
            f"{len(reqs)} mandatory requirement(s) failing",
            f"Failing mandatory requirements: {names}{more}.",
            "REVIEW_REQUIRED",
            _queue_bid_ref(b, bidder_names, tender_numbers))
        n += 1

    # -- 4. Integrity signal --------------------------------------------------
    n = 0
    for f in (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.status != IntegrityStatus.CLOSED.value)
        .order_by(
            IntegrityFinding.severity
            != IntegritySeverity.REVIEW_REQUIRED.value,
            IntegrityFinding.id.desc(),
        )
        .limit(_QUEUE_LIMIT_PER_CATEGORY)
        .all()
    ):
        demo = " Sourced from clearly-labelled DEMO procurement history." \
            if f.is_demo_history else ""
        add(4, "INTEGRITY_SIGNAL", "Integrity signal", f.title,
            (f.description or "") + demo, f.severity,
            {
                # Signals are cross-bid by design; the queue links to the
                # integrity workbench, not to a single bid.
                "bid_id": None,
                "bidder_name": bidder_names.get(f.bidder_id),
                "tender_number": tender_numbers.get(f.tender_id),
                "tender_id": f.tender_id,
                "link": "/app/integrity",
            },
            finding_id=f.id)
        n += 1

    # -- 5. Verification summary not generated --------------------------------
    def _audit_bid_ids(action) -> set[int]:
        out = set()
        for (entity_id,) in db.query(AuditLog.entity_id).filter(
            AuditLog.entity_type == "bid_submission",
            AuditLog.action == action,
        ).all():
            try:
                out.add(int(entity_id))
            except (TypeError, ValueError):
                continue
        return out

    generated = _audit_bid_ids("VERIFICATION_REPORT_GENERATED")
    decided = _audit_bid_ids("OFFICER_DECISION") | _audit_bid_ids("OFFICER_DECISION_CHANGED")
    evaluated = {row[0] for row in db.query(ComplianceResult.bid_id).distinct().all()}
    n = 0
    for bid_id in sorted(evaluated - generated - decided):
        if n >= _QUEUE_LIMIT_PER_CATEGORY:
            break
        b = bids.get(bid_id)
        if b is None:
            continue
        add(5, "PENDING_SUMMARY", "Verification summary not generated",
            f"{bidder_names.get(b.bidder_id) or 'Bid #' + str(bid_id)} — compliance evaluated, no summary yet",
            "The bid has been evaluated but the Procurement Officer has not "
            "generated a verification summary. Generate it from the bid workspace.",
            "ELEVATED",
            {**_queue_bid_ref(b, bidder_names, tender_numbers),
             "link": f"/app/bids/{bid_id}/summary"})
        n += 1

    # -- 6. Pending officer decision -------------------------------------------
    covered = evaluated - decided  # already surfaced under priority 5
    n = 0
    for b in sorted(bids.values(), key=lambda x: x.id):
        if n >= _QUEUE_LIMIT_PER_CATEGORY:
            break
        if (b.id in covered or b.officer_decision is not None
                or b.compliance_score is None
                or b.status not in ("SUBMITTED", "UNDER_REVIEW", "ESCALATED",
                                    "CLARIFICATION_REQUESTED")):
            continue
        add(6, "PENDING_OFFICER_DECISION", "Pending officer decision",
            f"{bidder_names.get(b.bidder_id) or f'Bid #{b.id}'} — evaluation complete, decision pending",
            "Compliance evaluation is complete and no officer decision is "
            "recorded. The Procurement Officer is the final decision maker.",
            "ELEVATED",
            _queue_bid_ref(b, bidder_names, tender_numbers))
        n += 1

    queue.sort(key=lambda i: (i["priority"], i["title"]))
    return queue[:_QUEUE_LIMIT_TOTAL]


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
