"""Cascade deletion tests for bids and tenders.

Deletion removes rows explicitly in dependency order (the models carry no
ORM/database cascades, and no schema change was needed). The append-only
audit trail is preserved: a ``*_DELETED`` event is appended *before* the
rows are removed, and existing audit events are never deleted.

Who may delete is decided by the API role gate (PROCUREMENT_OFFICER only);
these tests pin the service behavior. Gate coverage lives in
``test_role_authorization.py``.
"""
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core import config as config_mod
from app.models.models import (
    AuditLog,
    Bidder,
    BidSubmission,
    Clarification,
    ComplianceResult,
    Document,
    ExtractedField,
    Override,
    RiskAssessment,
    Tender,
    TenderRequirement,
    User,
    VerificationCheck,
)
from app.seed.demo_bidder_profiles import PROFILES
from app.services import delete_service
from app.services.compliance_service import evaluate_bid
from app.services.demo_seed_service import seed_demo_bidder_evidence
from app.services.recommendation_service import generate_recommendation
from app.services.verification_service import run_verification

REQUIREMENTS = [
    ("GST Registration Status", "REGISTRATION_STATUS",
     {"source": "GSTN", "identifier_field": "gstin", "require_status": "ACTIVE"},
     "GSTN", True, 40),
    ("Consolidated Bid Dossier", "DOCUMENT_REQUIRED",
     {"document_types": ["BID_DOSSIER"]}, None, True, 60),
]


def _make_tender(db, number="DEL-001"):
    t = Tender(tender_number=number, title="Delete cascade tender",
               organization="CPCL", department="Procurement", status="OPEN")
    db.add(t)
    db.flush()
    for name, rule_type, cfg, vs, mand, weight in REQUIREMENTS:
        db.add(TenderRequirement(tender_id=t.id, requirement_name=name,
                                 rule_type=rule_type, rule_config=cfg,
                                 verification_source=vs, mandatory=mand,
                                 weight=weight, category="demo"))
    db.commit()
    return t


def _make_bid(db, tender_id, legal_name):
    bidder = Bidder(tender_id=tender_id, legal_name=legal_name, bid_status="SUBMITTED")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=tender_id, bidder_id=bidder.id, status="SUBMITTED")
    db.add(bid)
    db.commit()
    return bid


def _full_bid(db, tender_id, profile_key):
    """Bid with the real pipeline outputs an officer would produce."""
    bid = _make_bid(db, tender_id, PROFILES[profile_key]["legal_name"])
    res = seed_demo_bidder_evidence(db, bid.id, profile_key)
    assert res["seeded"] is True
    doc = db.query(Document).filter_by(bid_id=bid.id).one()
    run_verification(db, bid.id)
    evaluate_bid(db, bid.id)
    generate_recommendation(db, bid.id)
    # One manual officer override + one clarification on this bid.
    db.add(Override(bid_id=bid.id, target_type="compliance_result", target_id=1,
                    original_status="PASS", officer_comment="recheck requested",
                    supporting_document_id=doc.id))
    db.add(Clarification(bid_id=bid.id, subject="EMD receipt",
                         body="Please re-upload the EMD receipt."))
    db.commit()
    return bid


@pytest.fixture()
def isolated_uploads(db, tmp_path, monkeypatch):
    """Keep dossier files out of the real upload dir during these tests."""
    monkeypatch.setattr(config_mod.settings, "UPLOAD_DIR", tmp_path / "uploads")
    return tmp_path / "uploads"


def _bid_counts(db, bid_id):
    doc_ids = [d.id for d in db.query(Document.id).filter_by(bid_id=bid_id).all()]
    return {
        "documents": db.query(Document).filter_by(bid_id=bid_id).count(),
        "fields": db.query(ExtractedField).filter(
            ExtractedField.document_id.in_(doc_ids)).count() if doc_ids else 0,
        "checks": db.query(VerificationCheck).filter_by(bid_id=bid_id).count(),
        "compliance": db.query(ComplianceResult).filter_by(bid_id=bid_id).count(),
        "risk": db.query(RiskAssessment).filter_by(bid_id=bid_id).count(),
        "overrides": db.query(Override).filter_by(bid_id=bid_id).count(),
        "clarifications": db.query(Clarification).filter_by(bid_id=bid_id).count(),
    }


def test_delete_bid_removes_everything_and_preserves_audit(db, isolated_uploads):
    tender = _make_tender(db)
    bid1 = _full_bid(db, tender.id, "apex")
    bid2 = _make_bid(db, tender.id, "Second Bidder Pvt Ltd")

    before = _bid_counts(db, bid1.id)
    assert before["documents"] == 1
    assert before["fields"] > 0
    assert before["checks"] > 0
    assert before["compliance"] > 0
    assert before["risk"] == 1
    assert before["overrides"] == 1
    assert before["clarifications"] == 1
    db.refresh(bid1)
    assert bid1.recommendation is not None

    dossier = db.query(Document).filter_by(bid_id=bid1.id).one()
    assert Path(dossier.file_path).exists()

    # Existing audit events for this bid (seed/verify/compliance wrote some).
    pre_events = db.query(AuditLog).filter(
        AuditLog.entity_type == "bid_submission",
        AuditLog.entity_id == str(bid1.id),
    ).count()

    res = delete_service.delete_bid(db, bid1.id)

    assert res["deleted"] is True
    assert res["bid_id"] == bid1.id
    assert db.get(BidSubmission, bid1.id) is None
    assert db.get(Bidder, bid1.bidder_id) is None
    assert _bid_counts(db, bid1.id) == {k: 0 for k in before}
    assert not Path(dossier.file_path).exists()

    # The other bid on the same tender is untouched.
    assert db.get(BidSubmission, bid2.id) is not None
    assert db.get(Bidder, bid2.bidder_id) is not None

    # Audit trail preserved + deletion event appended.
    events = db.query(AuditLog).filter(
        AuditLog.entity_type == "bid_submission",
        AuditLog.entity_id == str(bid1.id),
    ).all()
    assert len(events) == pre_events + 1
    assert events[-1].action == "BID_DELETED"
    assert events[-1].meta["tender_id"] == tender.id


def test_delete_tender_cascades_multiple_bids(db, isolated_uploads):
    tender = _make_tender(db)
    bid1 = _full_bid(db, tender.id, "vertex")
    bid2 = _make_bid(db, tender.id, "Second Bidder Pvt Ltd")
    other = _make_tender(db, number="DEL-002")
    other_bid = _make_bid(db, other.id, "Other Tender Bidder")

    tender_id, bid1_id = tender.id, bid1.id
    res = delete_service.delete_tender(db, tender.id)

    assert res["deleted"] is True
    assert res["tender_number"] == "DEL-001"
    assert res["bids"] == 2
    assert db.get(Tender, tender_id) is None
    assert db.query(TenderRequirement).filter_by(tender_id=tender_id).count() == 0
    assert db.query(BidSubmission).filter_by(tender_id=tender_id).count() == 0
    assert db.query(Bidder).filter_by(tender_id=tender_id).count() == 0
    assert _bid_counts(db, bid1_id) == {k: 0 for k in _bid_counts(db, bid1_id)}
    deleted_event = db.query(AuditLog).filter_by(
        action="TENDER_DELETED", entity_type="tender",
        entity_id=str(tender_id)).one_or_none()
    assert deleted_event is not None

    # An unrelated tender and its bid survive.
    assert db.get(Tender, other.id) is not None
    assert db.get(BidSubmission, other_bid.id) is not None


def test_delete_bid_not_found(db):
    with pytest.raises(ValueError):
        delete_service.delete_bid(db, 424242)


def test_delete_tender_not_found(db):
    with pytest.raises(ValueError):
        delete_service.delete_tender(db, 424242)


def _officer_user():
    return User(name="o", email="officer@test.local", password_hash="x",
                role="PROCUREMENT_OFFICER")


def test_bid_delete_endpoint_maps_missing_to_404(db):
    from app.api import bids as bids_mod
    with pytest.raises(HTTPException) as exc_info:
        bids_mod.delete_bid(bid_id=424242, db=db, user=_officer_user())
    assert exc_info.value.status_code == 404


def test_tender_delete_endpoint_maps_missing_to_404(db):
    from app.api import tenders as tenders_mod
    with pytest.raises(HTTPException) as exc_info:
        tenders_mod.delete_tender(tender_id=424242, db=db, user=_officer_user())
    assert exc_info.value.status_code == 404
