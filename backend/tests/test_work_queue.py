"""Backend-driven officer work queue: six priorities from stored tables only.

Covers: high-risk bidder, statutory mismatch, missing mandatory
requirement, integrity signal, pending verifier report, pending officer
decision. Asserts the category set, priority ordering and that every item
is derived from real stored rows (no fabricated entries).
"""
from app.api.dashboard import _build_work_queue
from app.models.models import (
    BidStatus,
    Bidder,
    BidSubmission,
    ComplianceResult,
    ConsistencyCheck,
    IntegrityFinding,
    IntegritySeverity,
    IntegrityStatus,
    RiskLevel,
    Tender,
    TenderRequirement,
    User,
)
from app.services import audit_service, verifier_report_service

_CATS = [
    "HIGH_RISK_BIDDER",
    "STATUTORY_MISMATCH",
    "MISSING_MANDATORY_REQUIREMENT",
    "INTEGRITY_SIGNAL",
    "PENDING_VERIFIER_REPORT",
    "PENDING_OFFICER_DECISION",
]


def _make_bid(db, tender, name, **kw):
    bidder = Bidder(tender_id=tender.id, legal_name=name)
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id,
                        status=BidStatus.SUBMITTED.value, **kw)
    db.add(bid)
    db.flush()
    return bid


def test_work_queue_six_priorities_from_stored_data(db):
    tender = Tender(tender_number="T-Q-1", title="Queue", organization="CPCL",
                    department="Purchase")
    db.add(tender)
    db.flush()

    # 1. high-risk bidder
    b1 = _make_bid(db, tender, "Risky Ltd", risk_level=RiskLevel.CRITICAL.value,
                   compliance_score=40.0)

    # 2. statutory mismatch (consistency engine output row)
    b2 = _make_bid(db, tender, "Mismatch Ltd", risk_level=RiskLevel.LOW.value,
                   compliance_score=80.0)
    db.add(ConsistencyCheck(bid_id=b2.id, check_name="ENTITY_NAME_CONSISTENCY",
                            field_name="legal_name", result="MISMATCH",
                            reason="names differ", severity="REVIEW_REQUIRED",
                            evidence={"a": "1"}))

    # 3. missing mandatory requirement
    b3 = _make_bid(db, tender, "Missing Ltd", risk_level=RiskLevel.LOW.value,
                   compliance_score=60.0)
    req = TenderRequirement(tender_id=tender.id, requirement_name="GST Registration",
                            category="DOCUMENT", weight=10.0, mandatory=True,
                            rule_type="DOCUMENT_PRESENT")
    db.add(req)
    db.flush()
    db.add(ComplianceResult(bid_id=b3.id, requirement_id=req.id, status="FAIL",
                            weight=10.0, weighted_contribution=0.0,
                            explanation="missing", rule_applied="r",
                            source="test"))

    # 4. integrity signal (open finding)
    db.add(IntegrityFinding(
        signal_type="SHARED_CONTACT", severity=IntegritySeverity.REVIEW_REQUIRED.value,
        title="Shared contact across bids", description="same phone",
        affected_bids=[], affected_tenders=[], evidence=[], rule_logic="r",
        recommended_action="review", status=IntegrityStatus.OPEN.value))

    # 5. pending verifier report: sent, no decision
    verifier = User(name="Verifier", email="v-q@example.com", password_hash="x",
                    role="VERIFIER")
    db.add(verifier)
    db.flush()
    b5 = _make_bid(db, tender, "ReportWait Ltd", risk_level=RiskLevel.LOW.value,
                   compliance_score=75.0)
    verifier_report_service.generate_report(db, b5.id, verifier)
    verifier_report_service.send_report(db, b5.id, verifier)

    # 6. pending officer decision: evaluated, no decision, no report
    b6 = _make_bid(db, tender, "DecideMe Ltd", risk_level=RiskLevel.LOW.value,
                   compliance_score=88.0)

    # Decided bid must NOT appear anywhere.
    b7 = _make_bid(db, tender, "Done Ltd", risk_level=RiskLevel.CRITICAL.value,
                   compliance_score=30.0, officer_decision="APPROVE")
    db.commit()

    queue = _build_work_queue(db)
    cats = [i["category"] for i in queue]
    for c in _CATS:
        assert c in cats, f"missing category {c}: {cats}"

    # Priority ordering holds.
    prios = [i["priority"] for i in queue]
    assert prios == sorted(prios)

    # Every item carries its evidence and an action link.
    for i in queue:
        assert i["title"] and i["description"] and i["link"], i
        assert i["severity"] in ("REVIEW_REQUIRED", "ELEVATED", "INFORMATIONAL")

    # The decided bid is excluded everywhere.
    titles = " ".join(i["title"] for i in queue)
    assert "Done Ltd" not in titles

    # Integrity signal links to the integrity workbench, not a bid.
    sig = next(i for i in queue if i["category"] == "INTEGRITY_SIGNAL")
    assert sig["link"] == "/app/integrity"
    assert sig["bid_id"] is None

    # Pending report links to the report page.
    rep = next(i for i in queue if i["category"] == "PENDING_VERIFIER_REPORT")
    assert rep["link"] == f"/app/bids/{b5.id}/report"


def test_work_queue_empty_db_has_no_categories(db):
    queue = _build_work_queue(db)
    assert queue == []
