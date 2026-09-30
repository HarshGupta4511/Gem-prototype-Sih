"""Regression test: GET /api/bids/{id} must include the nested tender requirement
(name, threshold, mandatory) on every compliance result.

Bug: the router only populated the flat ``requirement_name`` convenience field,
but the frontend contract reads the nested ``requirement`` object — so the
Bid Detail compliance table rendered "Requirement #N" and "No specific
threshold" for every row even though the tender requirements existed.

The fix populates ``ComplianceResultOut.requirement`` (additive, response-only)
and uses an outer join so orphaned results are still returned.
"""
from app.api.bids import get_bid
from app.models.models import (
    Bidder,
    BidSubmission,
    ComplianceResult,
    Tender,
    TenderRequirement,
)


def _make_bid_with_results(db):
    t = Tender(tender_number="REQ-NEST-001", title="Requirement nesting",
               organization="CPCL", department="Procurement", status="OPEN")
    db.add(t)
    db.flush()
    req = TenderRequirement(
        tender_id=t.id,
        requirement_name="GST Registration",
        category="STATUTORY",
        description="Active GSTIN required",
        mandatory=True,
        rule_type="REGISTRATION_STATUS",
        rule_config={},
        threshold="Active GSTIN",
        weight=15,
    )
    db.add(req)
    db.flush()
    bidder = Bidder(tender_id=t.id, legal_name="Test Bidder Pvt Ltd")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=t.id, bidder_id=bidder.id)
    db.add(bid)
    db.flush()
    # One healthy result + one orphaned (requirement deleted afterwards)
    db.add(ComplianceResult(
        bid_id=bid.id, requirement_id=req.id, status="PASS",
        weight=15, weighted_contribution=15,
        evidence=[{"field": "gstin", "value": "ACTIVE"}],
        explanation="ok", rule_applied="x == y", source="GSTN",
    ))
    db.add(ComplianceResult(
        bid_id=bid.id, requirement_id=999999, status="MISSING",
        weight=10, weighted_contribution=0,
        evidence=[],
        explanation="orphan", rule_applied="x == y", source="MANUAL",
    ))
    db.commit()
    return bid.id


def test_bid_detail_includes_nested_requirement(db):
    bid_id = _make_bid_with_results(db)
    detail = get_bid(bid_id, db, None)

    assert len(detail.compliance_results) == 2

    healthy = detail.compliance_results[0]
    assert healthy.requirement is not None
    assert healthy.requirement.requirement_name == "GST Registration"
    assert healthy.requirement.threshold == "Active GSTIN"
    assert healthy.requirement.mandatory is True
    # flat convenience field still populated (backward compatible)
    assert healthy.requirement_name == "GST Registration"

    orphan = detail.compliance_results[1]
    assert orphan.requirement is None
    assert orphan.requirement_name is None
