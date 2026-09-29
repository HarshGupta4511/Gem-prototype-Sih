"""Data-consistency tests for the tender-creation flow alignment.

Covers:
- ``_create_tender`` stamps the Step-1 wizard fields on seeded demo tenders
  (tender_type, bid_type, emd_amount_inr, delivery_period, place_of_delivery).
- ``_backfill_tender_wizard_fields`` fills NULL wizard fields on demo
  tenders that predate the wizard (existing databases), without touching
  officer-created tenders or overwriting already-set values.
- ``GET /api/audit/by-tender`` returns a consolidated, enriched tender
  activity history: bid/document events attributed to bidders, generic
  housekeeping actions (LOGIN/SEED/...) excluded.
"""
from datetime import date

import pytest

from app.api.audit import audit_by_tender
from app.main import _backfill_tender_wizard_fields
from app.models.models import (
    Bidder,
    BidSubmission,
    Document,
    Tender,
    User,
)
from app.seed.seed_data import _create_tender, DEMO_TENDER_WIZARD_FIELDS
from app.services.audit_service import append_audit


def _user(db) -> User:
    user = User(name="Officer", email="officer@t.test", password_hash="x",
                role="PROCUREMENT_OFFICER")
    db.add(user)
    db.commit()
    return user


def _tender(db, number: str, **kwargs) -> Tender:
    tender = Tender(tender_number=number, title=f"Tender {number}",
                    organization="CPCL", department="Purchase",
                    issue_date=date(2026, 8, 1), closing_date=date(2026, 9, 30),
                    estimated_value_inr=1000000, status="OPEN", **kwargs)
    db.add(tender)
    db.commit()
    db.refresh(tender)
    return tender


# ------------------------------------------------- seed wizard fields

def test_create_tender_stamps_wizard_fields_for_demo_tenders(db):
    """Fresh seeds of the demo tenders carry the Step-1 wizard fields."""
    user = _user(db)
    tender = _create_tender(
        db, number="CPCL-DEMO-2026-001", title="T1", department="Materials",
        issue=date(2026, 8, 1), closing=date(2026, 9, 30), value=45000000,
        requirements=[], created_by=user.id,
    )
    assert tender.tender_type == "GOODS"
    assert tender.bid_type == "TWO_PACKET"
    assert tender.emd_amount_inr == 900000
    assert tender.delivery_period == "12 months"
    assert tender.place_of_delivery == "Chennai"


def test_create_tender_stamps_gem_demo_fields(db):
    user = _user(db)
    tender = _create_tender(
        db, number="GEM-DEMO-2026-101", title="T4", department="Demo",
        issue=date(2026, 9, 1), closing=date(2026, 10, 31), value=12500000,
        requirements=[], created_by=user.id,
    )
    assert tender.tender_type == "GOODS"
    assert tender.bid_type == "TWO_PACKET"
    assert tender.emd_amount_inr == 15000
    assert tender.place_of_delivery == "Multiple consignee locations"


def test_create_tender_explicit_kwargs_win_over_defaults(db):
    """An explicitly supplied field is never overwritten by the demo default."""
    user = _user(db)
    tender = _create_tender(
        db, number="CPCL-DEMO-2026-001", title="T1", department="Materials",
        issue=date(2026, 8, 1), closing=date(2026, 9, 30), value=45000000,
        requirements=[], created_by=user.id, tender_type="WORKS",
    )
    assert tender.tender_type == "WORKS"


def test_demo_field_map_covers_all_demo_tenders():
    assert set(DEMO_TENDER_WIZARD_FIELDS) == {
        "CPCL-DEMO-2026-001",
        "CPCL-DEMO-2026-002",
        "CPCL-DEMO-2026-003",
        "GEM-DEMO-2026-101",
    }
    for fields in DEMO_TENDER_WIZARD_FIELDS.values():
        assert fields["tender_type"] in {"GOODS", "SERVICES", "WORKS"}
        assert fields["bid_type"] in {"SINGLE_PACKET", "TWO_PACKET"}


# ------------------------------------------------- startup backfill

def test_backfill_fills_null_fields_on_demo_tender(db):
    tender = _tender(db, "CPCL-DEMO-2026-001")  # all wizard fields NULL
    _backfill_tender_wizard_fields(db)
    db.refresh(tender)
    assert tender.tender_type == "GOODS"
    assert tender.bid_type == "TWO_PACKET"
    assert tender.emd_amount_inr == 900000
    assert tender.delivery_period == "12 months"
    assert tender.place_of_delivery == "Chennai"


def test_backfill_does_not_touch_officer_tender(db):
    """Tenders not in the demo map keep their NULLs — never invented."""
    tender = _tender(db, "OFFICER-2026-042")
    _backfill_tender_wizard_fields(db)
    db.refresh(tender)
    assert tender.tender_type is None
    assert tender.bid_type is None
    assert tender.emd_amount_inr is None


def test_backfill_preserves_existing_values(db):
    """Already-set fields are not overwritten by the backfill."""
    tender = _tender(db, "CPCL-DEMO-2026-002", tender_type="WORKS")
    _backfill_tender_wizard_fields(db)
    db.refresh(tender)
    assert tender.tender_type == "WORKS"  # preserved
    assert tender.bid_type == "TWO_PACKET"  # NULL was filled


def test_backfill_is_idempotent(db):
    _tender(db, "GEM-DEMO-2026-101")
    _backfill_tender_wizard_fields(db)
    _backfill_tender_wizard_fields(db)
    tender = db.query(Tender).filter(
        Tender.tender_number == "GEM-DEMO-2026-101").one()
    assert tender.emd_amount_inr == 15000


# ------------------------------------------------- audit by-tender

def _seed_audit_scenario(db):
    user = _user(db)
    tender = _tender(db, "CPCL-DEMO-2026-001")
    bidder = Bidder(tender_id=tender.id, legal_name="Audit Test Pvt Ltd",
                    pan="AAAAA1111A", bid_status="SUBMITTED")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id,
                        status="SUBMITTED")
    db.add(bid)
    db.flush()
    doc = Document(bid_id=bid.id, filename="dossier.pdf", file_path="/tmp/dossier.pdf",
                   file_hash="abc123", file_size=1024, mime_type="application/pdf",
                   document_type="BID_DOSSIER", processing_status="PROCESSED")
    db.add(doc)
    db.commit()

    append_audit(db, user_id=user.id, action="TENDER_CREATED",
                 entity_type="tender", entity_id=str(tender.id))
    append_audit(db, user_id=user.id, action="BID_SUBMITTED",
                 entity_type="bid_submission", entity_id=str(bid.id),
                 metadata={"legal_name": bidder.legal_name})
    append_audit(db, user_id=user.id, action="DOCUMENT_PROCESSED",
                 entity_type="document", entity_id=str(doc.id),
                 metadata={"fields": 12})
    append_audit(db, user_id=user.id, action="COMPLIANCE_EVALUATED",
                 entity_type="bid_submission", entity_id=str(bid.id),
                 metadata={"compliance_score": 82.5})
    # Generic housekeeping — must be excluded from the tender view.
    append_audit(db, user_id=user.id, action="LOGIN",
                 entity_type="user", entity_id=str(user.id))
    append_audit(db, user_id=None, action="SEED",
                 entity_type="tender", entity_id=str(tender.id))
    return tender, user


def test_by_tender_excludes_housekeeping_events(db):
    tender, user = _seed_audit_scenario(db)
    rows = audit_by_tender(tender.id, limit=200, db=db, user=user)
    actions = [r.action for r in rows]
    assert "LOGIN" not in actions
    assert "SEED" not in actions
    assert "TENDER_CREATED" in actions
    assert "BID_SUBMITTED" in actions
    assert "DOCUMENT_PROCESSED" in actions
    assert "COMPLIANCE_EVALUATED" in actions


def test_by_tender_labels_targets(db):
    tender, user = _seed_audit_scenario(db)
    rows = audit_by_tender(tender.id, limit=200, db=db, user=user)
    by_action = {r.action: r for r in rows}
    assert by_action["TENDER_CREATED"].target_label == "CPCL-DEMO-2026-001"
    assert by_action["BID_SUBMITTED"].target_label == "Audit Test Pvt Ltd"
    assert by_action["COMPLIANCE_EVALUATED"].target_label == "Audit Test Pvt Ltd"
    assert "dossier.pdf" in (by_action["DOCUMENT_PROCESSED"].target_label or "")
    assert "Audit Test Pvt Ltd" in (by_action["DOCUMENT_PROCESSED"].target_label or "")
    # Workflow metadata survives for the Result column.
    assert by_action["COMPLIANCE_EVALUATED"].metadata["compliance_score"] == 82.5


def test_by_tender_newest_first_and_scoped(db):
    tender, user = _seed_audit_scenario(db)
    other = _tender(db, "CPCL-DEMO-2026-002")
    append_audit(db, user_id=user.id, action="TENDER_CREATED",
                 entity_type="tender", entity_id=str(other.id))
    rows = audit_by_tender(tender.id, limit=200, db=db, user=user)
    assert all(r.entity_id == str(tender.id) or r.entity_type != "tender"
               for r in rows)
    ids = [r.id for r in rows]
    assert ids == sorted(ids, reverse=True)


def test_by_tender_404_for_unknown_tender(db):
    from fastapi import HTTPException
    user = _user(db)
    with pytest.raises(HTTPException) as exc:
        audit_by_tender(999999, limit=200, db=db, user=user)
    assert exc.value.status_code == 404
