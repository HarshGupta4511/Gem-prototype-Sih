"""Tests for the comparative per-tender AI recommendation.

Bidders are evaluated only within their own tender: strongest eligible →
APPROVE, disqualified → REJECT, everyone else → REVIEW_REQUIRED.
"""
import pytest

from app.models.models import (
    Bidder,
    BidSubmission,
    ComplianceResult,
    RiskAssessment,
    Tender,
    TenderRequirement,
)
from app.services.recommendation_service import generate_recommendation


def _tender(db, number):
    t = Tender(tender_number=number, title=f"Tender {number}",
               organization="CPCL", department="Materials")
    db.add(t)
    db.commit()
    db.refresh(t)
    req = TenderRequirement(tender_id=t.id, requirement_name="GST Registration",
                            category="STATUTORY", rule_type="DOCUMENT_REQUIRED",
                            weight=100.0, mandatory=True)
    db.add(req)
    db.commit()
    db.refresh(req)
    return t, req


def _bid(db, tender, req, name, score, risk_level, statuses,
         blacklisted=False):
    """Store a bid with compliance results + risk assessment.

    statuses: list of (status, mandatory) for the single requirement rows
    (extra rows reuse the same requirement for simplicity).
    """
    bidder = Bidder(tender_id=tender.id, legal_name=name)
    db.add(bidder)
    db.commit()
    db.refresh(bidder)
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id)
    bid.compliance_score = score
    bid.risk_level = risk_level
    db.add(bid)
    db.commit()
    db.refresh(bid)
    for status, mandatory in statuses:
        db.add(ComplianceResult(
            bid_id=bid.id, requirement_id=req.id, status=status,
            weight=100.0, weighted_contribution=0.0, evidence=[],
            explanation=f"{status} on GST", rule_applied="r", source="s",
            confidence=0.95,
        ))
    signals = []
    if blacklisted:
        signals = [{"code": "BLACKLISTED", "message": "listed",
                    "severity": "critical", "weight": 100}]
    db.add(RiskAssessment(bid_id=bid.id, risk_level=risk_level,
                          risk_score=10.0, signals=signals, explanation="e"))
    db.commit()
    db.refresh(bid)
    return bid


def _recs(db, tender):
    return {
        b.id: b.recommendation
        for b in db.query(BidSubmission)
        .filter(BidSubmission.tender_id == tender.id).all()
    }


def test_strongest_eligible_approved_rest_reviewed(db):
    t, req = _tender(db, "REC-T1")
    strong = _bid(db, t, req, "Strong Pvt Ltd", 90.0, "LOW", [("PASS", True)])
    mid = _bid(db, t, req, "Mid Pvt Ltd", 70.0, "MEDIUM", [("PASS", True)])
    weak = _bid(db, t, req, "Weak Pvt Ltd", 40.0, "MEDIUM",
                [("MISSING", False)])

    out = generate_recommendation(db, mid.id)
    assert out["recommendation"] == "REVIEW_REQUIRED"

    recs = _recs(db, t)
    assert recs[strong.id] == "APPROVE"
    assert recs[mid.id] == "REVIEW_REQUIRED"
    assert recs[weak.id] == "REVIEW_REQUIRED"
    assert "rank 1 of 3" in db.get(BidSubmission, strong.id).recommendation_reason


def test_blacklisted_and_mandatory_fail_rejected(db):
    t, req = _tender(db, "REC-T2")
    clean = _bid(db, t, req, "Clean Pvt Ltd", 85.0, "LOW", [("PASS", True)])
    listed = _bid(db, t, req, "Listed Pvt Ltd", 100.0, "HIGH",
                  [("PASS", True)], blacklisted=True)
    failed = _bid(db, t, req, "Failed Pvt Ltd", 60.0, "HIGH",
                  [("FAIL", True)])

    # High score must not save a blacklisted bidder.
    generate_recommendation(db, listed.id)
    recs = _recs(db, t)
    assert recs[listed.id] == "REJECT"
    assert recs[failed.id] == "REJECT"
    assert recs[clean.id] == "APPROVE"


def test_mandatory_missing_prevents_approve(db):
    t, req = _tender(db, "REC-T3")
    gap = _bid(db, t, req, "Gap Pvt Ltd", 95.0, "LOW", [("MISSING", True)])
    solid = _bid(db, t, req, "Solid Pvt Ltd", 80.0, "LOW", [("PASS", True)])

    generate_recommendation(db, gap.id)
    recs = _recs(db, t)
    assert recs[gap.id] == "REVIEW_REQUIRED"
    assert recs[solid.id] == "APPROVE"


def test_high_risk_prevents_approve(db):
    t, req = _tender(db, "REC-T4")
    risky = _bid(db, t, req, "Risky Pvt Ltd", 95.0, "HIGH", [("PASS", True)])
    steady = _bid(db, t, req, "Steady Pvt Ltd", 80.0, "LOW", [("PASS", True)])

    generate_recommendation(db, risky.id)
    recs = _recs(db, t)
    assert recs[risky.id] == "REVIEW_REQUIRED"
    assert recs[steady.id] == "APPROVE"


def test_tenders_evaluated_independently(db):
    t1, req1 = _tender(db, "REC-T5A")
    t2, req2 = _tender(db, "REC-T5B")
    # Weakest in tender 1 would lose there, but wins tender 2 alone.
    a1 = _bid(db, t1, req1, "A1", 90.0, "LOW", [("PASS", True)])
    a2 = _bid(db, t1, req1, "A2", 50.0, "MEDIUM", [("PASS", True)])
    b1 = _bid(db, t2, req2, "B1", 55.0, "LOW", [("PASS", True)])

    generate_recommendation(db, a2.id)
    recs1 = _recs(db, t1)
    assert recs1[a1.id] == "APPROVE"
    assert recs1[a2.id] == "REVIEW_REQUIRED"
    # Tender 2 untouched by tender 1's evaluation.
    assert _recs(db, t2)[b1.id] is None

    generate_recommendation(db, b1.id)
    assert _recs(db, t2)[b1.id] == "APPROVE"


def test_single_eligible_bidder_approved(db):
    t, req = _tender(db, "REC-T6")
    solo = _bid(db, t, req, "Solo Pvt Ltd", 75.0, "LOW", [("PASS", True)])
    out = generate_recommendation(db, solo.id)
    assert out["recommendation"] == "APPROVE"


def test_all_disqualified_no_approve(db):
    t, req = _tender(db, "REC-T7")
    b1 = _bid(db, t, req, "Bad1", 90.0, "HIGH", [("PASS", True)],
              blacklisted=True)
    b2 = _bid(db, t, req, "Bad2", 80.0, "HIGH", [("FAIL", True)])
    generate_recommendation(db, b1.id)
    recs = _recs(db, t)
    assert recs[b1.id] == "REJECT"
    assert recs[b2.id] == "REJECT"


def test_no_compliance_results_raises(db):
    t, req = _tender(db, "REC-T8")
    bidder = Bidder(tender_id=t.id, legal_name="Empty Pvt Ltd")
    db.add(bidder)
    db.commit()
    db.refresh(bidder)
    bid = BidSubmission(tender_id=t.id, bidder_id=bidder.id)
    db.add(bid)
    db.commit()
    db.refresh(bid)
    with pytest.raises(ValueError, match="No compliance results"):
        generate_recommendation(db, bid.id)
