"""Regression test: GET /tenders/:id must surface the officer's persisted
decision on each bidder row (not always null), and must return the stats
keys the Tender Detail UI actually reads.

Bug: ``get_tender`` built ``TenderBidderRow`` without ``officer_decision``,
so an approved bidder still rendered "Pending decision". It also returned
stats keys (``bid_count``/``risk_breakdown``) the frontend never reads,
which broke the summary card layout.
"""
from app.api.tenders import get_tender
from app.models.models import (
    Bidder,
    BidStatus,
    BidSubmission,
    OfficerDecision,
    RiskLevel,
    Tender,
    User,
)


def _make_tender_with_bids(db):
    user = User(
        name="Officer",
        email="officer@example.com",
        password_hash="x",
        role="PROCUREMENT_OFFICER",
    )
    db.add(user)
    tender = Tender(
        tender_number="T-DEC-1",
        title="Decision plumbing test",
        organization="CPCL",
        department="Purchase",
    )
    db.add(tender)
    db.flush()

    decided_bidder = Bidder(tender_id=tender.id, legal_name="Decided Ltd", pan="AAAAA1111A")
    undecided_bidder = Bidder(tender_id=tender.id, legal_name="Undecided Ltd", pan="BBBBB2222B")
    db.add_all([decided_bidder, undecided_bidder])
    db.flush()

    decided_bid = BidSubmission(
        tender_id=tender.id,
        bidder_id=decided_bidder.id,
        status=BidStatus.APPROVED.value,
        compliance_score=90.0,
        risk_level=RiskLevel.LOW.value,
        officer_decision=OfficerDecision.APPROVE.value,
        officer_decision_reason="All good",
    )
    undecided_bid = BidSubmission(
        tender_id=tender.id,
        bidder_id=undecided_bidder.id,
        status=BidStatus.SUBMITTED.value,
        compliance_score=40.0,
        risk_level=RiskLevel.HIGH.value,
        officer_decision=None,
    )
    db.add_all([decided_bid, undecided_bid])
    db.commit()
    return tender, user


def test_tender_detail_surfaces_officer_decision(db):
    tender, user = _make_tender_with_bids(db)

    out = get_tender(tender_id=tender.id, db=db, user=user)
    by_name = {r.legal_name: r for r in out.bidders}

    assert by_name["Decided Ltd"].officer_decision == OfficerDecision.APPROVE
    assert by_name["Undecided Ltd"].officer_decision is None


def test_tender_detail_stats_match_frontend_keys(db):
    tender, user = _make_tender_with_bids(db)

    out = get_tender(tender_id=tender.id, db=db, user=user)

    assert out.stats["bidder_count"] == 2
    assert out.stats["avg_compliance"] == 65.0
    assert out.stats["high_risk_count"] == 1
    assert out.stats["pending_reviews"] == 1
    # stale keys the UI never reads must not come back
    assert "bid_count" not in out.stats
    assert "risk_breakdown" not in out.stats
