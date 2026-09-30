"""E2E: decision-change workflow preserves full audit history.

Flow: APPROVE a bid, then change to REJECT with a reason.
Asserts:
- two OFFICER_DECISION audit events exist (history never overwritten),
- the second event carries previous_decision=APPROVE,
- the latest decision (REJECT) is the current one on the bid.
"""
import app.api.officer as officer_mod
from app.models.models import (
    Bidder,
    BidStatus,
    BidSubmission,
    OfficerDecision,
    Tender,
    User,
    AuditLog,
)
from app.schemas.schemas import DecisionRequest


def _setup(db):
    user = User(
        name="Officer",
        email="officer-change@example.com",
        password_hash="x",
        role="PROCUREMENT_OFFICER",
    )
    db.add(user)
    tender = Tender(
        tender_number="T-CHG-1",
        title="Decision change test",
        organization="CPCL",
        department="Purchase",
    )
    db.add(tender)
    db.flush()
    bidder = Bidder(tender_id=tender.id, legal_name="ChangeMe Ltd", pan="CCCCC3333C")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(
        tender_id=tender.id,
        bidder_id=bidder.id,
        status=BidStatus.SUBMITTED.value,
    )
    db.add(bid)
    db.commit()
    return bid, user


def test_decision_change_preserves_audit_history(db):
    bid, user = _setup(db)

    officer_mod.officer_decision(
        DecisionRequest(bid_id=bid.id, decision=OfficerDecision.APPROVE, reason="Looks good"),
        db=db,
        user=user,
    )
    officer_mod.officer_decision(
        DecisionRequest(
            bid_id=bid.id,
            decision=OfficerDecision.REJECT,
            reason="Required clarification was not provided",
            confirm_change=True,
        ),
        db=db,
        user=user,
    )

    events = (
        db.query(AuditLog)
        .filter(
            AuditLog.action.in_(("OFFICER_DECISION", "OFFICER_DECISION_CHANGED")),
            AuditLog.entity_type == "bid_submission",
            AuditLog.entity_id == str(bid.id),
        )
        .order_by(AuditLog.id)
        .all()
    )
    assert len(events) == 2, f"expected 2 decision events, got {len(events)}"
    assert events[0].action == "OFFICER_DECISION"
    assert events[1].action == "OFFICER_DECISION_CHANGED"
    first, second = (e.meta or {} for e in events)
    assert first["decision"] == "APPROVE"
    assert first["previous_decision"] is None
    assert second["decision"] == "REJECT"
    assert second["previous_decision"] == "APPROVE"
    assert second["reason"] == "Required clarification was not provided"

    db.refresh(bid)
    assert bid.officer_decision == OfficerDecision.REJECT.value
    assert bid.status == BidStatus.REJECTED.value
