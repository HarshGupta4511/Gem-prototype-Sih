"""Tests for the variety demo dataset seeder.

Covers: idempotent load (6 tenders x 7 bidders, weights = 100), real
engine-computed outcome diversity (scores, risk levels, recommendations),
spot-checked engineered scenarios, integrity detectors firing from the
dataset, and surgical reset isolation (unrelated records survive).
"""
import os

import app.models.models  # noqa: F401  (register models on Base)
from app.models.models import (Bidder, BidSubmission, ComplianceResult,
                               Document, ExtractedField, IntegrityFinding,
                               RiskAssessment, Tender, TenderRequirement)
from app.seed.variety_demo_seed import (
    VARIETY_TENDER_NUMBERS,
    load_variety_demo_dataset,
    reset_variety_demo_dataset,
    variety_demo_dataset_status,
)
from app.services.integrity_service import run_integrity_analysis


def _variety_tenders(db):
    return (db.query(Tender)
            .filter(Tender.tender_number.in_(VARIETY_TENDER_NUMBERS))
            .order_by(Tender.tender_number).all())


def _bid_of(db, tender_no, legal_name):
    t = db.query(Tender).filter_by(tender_number=tender_no).one()
    return (db.query(BidSubmission)
            .join(Bidder, BidSubmission.bidder_id == Bidder.id)
            .filter(Bidder.tender_id == t.id,
                    Bidder.legal_name == legal_name).one())


def test_load_creates_six_tenders_seven_bidders_each(db):
    res = load_variety_demo_dataset(db)
    assert res["loaded"] is True
    assert res["tenders"] == 6
    assert res["bidders"] == 42
    assert res["bids"] == 42
    assert res["documents"] > 300

    tenders = _variety_tenders(db)
    assert len(tenders) == 6
    for t in tenders:
        assert db.query(Bidder).filter_by(tender_id=t.id).count() == 7
        # Every tender's requirement weights total exactly 100.
        total = sum(r.weight for r in
                    db.query(TenderRequirement).filter_by(tender_id=t.id).all())
        assert abs(total - 100.0) < 1e-6
    # 15 distinct fictional companies.
    names = {b.legal_name for b in db.query(Bidder).join(
        Tender, Bidder.tender_id == Tender.id).filter(
        Tender.tender_number.in_(VARIETY_TENDER_NUMBERS)).all()}
    assert 12 <= len(names) <= 15
    # Every bid got real compliance results from the real engine.
    for b in db.query(BidSubmission).join(
            Tender, BidSubmission.tender_id == Tender.id).filter(
            Tender.tender_number.in_(VARIETY_TENDER_NUMBERS)).all():
        assert db.query(ComplianceResult).filter_by(bid_id=b.id).count() > 0
        assert b.compliance_score is not None
    # Estimated values + criteria text on every tender/requirement.
    expected_est = {"VAR-DEMO-2026-01": 85_000_000, "VAR-DEMO-2026-02": 120_000_000,
                    "VAR-DEMO-2026-03": 67_500_000, "VAR-DEMO-2026-04": 185_000_000,
                    "VAR-DEMO-2026-05": 92_500_000, "VAR-DEMO-2026-06": 150_000_000}
    for t in tenders:
        assert t.estimated_value_inr == expected_est[t.tender_number]
    assert (db.query(TenderRequirement)
            .join(Tender, TenderRequirement.tender_id == Tender.id)
            .filter(Tender.tender_number.in_(VARIETY_TENDER_NUMBERS))
            .filter((TenderRequirement.threshold.is_(None))
                    | (TenderRequirement.threshold == "")).count() == 0)


def test_outcome_diversity_from_real_engines(db):
    load_variety_demo_dataset(db)
    bids = (db.query(BidSubmission).join(
        Tender, BidSubmission.tender_id == Tender.id).filter(
        Tender.tender_number.in_(VARIETY_TENDER_NUMBERS)).all())
    scores = [b.compliance_score for b in bids]
    assert max(scores) - min(scores) > 20
    assert {b.risk_level for b in bids} >= {"LOW", "MEDIUM", "HIGH"}
    assert {b.recommendation for b in bids} >= {"APPROVE", "REVIEW_REQUIRED",
                                               "REJECT"}
    statuses = {c.status for c in db.query(ComplianceResult).join(
        BidSubmission, ComplianceResult.bid_id == BidSubmission.id).join(
        Tender, BidSubmission.tender_id == Tender.id).filter(
        Tender.tender_number.in_(VARIETY_TENDER_NUMBERS)).all()}
    assert "PASS" in statuses and "FAIL" in statuses
    assert "MISSING" in statuses or "MISMATCH" in statuses


def test_engineered_scenarios(db):
    load_variety_demo_dataset(db)
    # T1-A: clean bidder -> APPROVE / LOW.
    mer = _bid_of(db, "VAR-DEMO-2026-01", "Meridian Systems")
    assert mer.recommendation == "APPROVE"
    assert mer.risk_level == "LOW"
    # T6-F: blacklisted bidder -> REJECT / HIGH.
    brah = _bid_of(db, "VAR-DEMO-2026-06", "Brahmani Traders")
    assert brah.recommendation == "REJECT"
    assert brah.risk_level == "HIGH"
    # T2-D: ITR filed for the wrong financial year -> ITR requirement fails.
    tap = _bid_of(db, "VAR-DEMO-2026-02", "Tapi Engineering Works")
    itr = (db.query(ComplianceResult).filter_by(bid_id=tap.id)
           .join(TenderRequirement,
                 ComplianceResult.requirement_id == TenderRequirement.id)
           .filter(TenderRequirement.rule_type == "MATCH").one())
    assert itr.status in ("FAIL", "REVIEW_REQUIRED", "MISSING")
    # T4-B: ISO certificate present and valid -> PASS (the old
    # missing-document scenario is gone; T5-G's certificate does not state
    # an expiry date -> REVIEW_REQUIRED since the document is present).
    kav = _bid_of(db, "VAR-DEMO-2026-04", "Kaveri Pumps Ltd.")
    iso = (db.query(ComplianceResult).filter_by(bid_id=kav.id)
           .join(TenderRequirement,
                 ComplianceResult.requirement_id == TenderRequirement.id)
           .filter(TenderRequirement.rule_type == "DATE_VALIDITY").one())
    assert iso.status == "PASS"
    assert (db.query(Document).filter_by(
        bid_id=kav.id, document_type="ISO_9001_CERTIFICATE",
        processing_status="PROCESSED").count() == 1)


def test_integrity_detectors_fire(db):
    load_variety_demo_dataset(db)
    run_integrity_analysis(db)
    findings = db.query(IntegrityFinding).all()
    types = {f.signal_type for f in findings}
    # Simplified mode: only repeated participation.
    assert types == {"REPEATED_PARTICIPATION"}, types
    assert len(findings) > 0
    # One bidder = one signal.
    titles = [f.title for f in findings]
    assert len(titles) == len(set(titles))
    # Spot-check: Kestrel in 4 tenders.
    kestrel = [f for f in findings if "Kestrel" in f.title]
    assert len(kestrel) == 1
    assert "4 tenders" in kestrel[0].evidence[0]["detail"]


def test_metadata_refresh_backfills_legacy_rows(db):
    load_variety_demo_dataset(db)
    tenders = _variety_tenders(db)
    for t in tenders:
        t.estimated_value_inr = None
    db.query(TenderRequirement).filter(
        TenderRequirement.tender_id.in_([t.id for t in tenders])
    ).update({TenderRequirement.threshold: None}, synchronize_session=False)
    # Simulate legacy rows lacking document_type in DATE_VALIDITY configs.
    for req in db.query(TenderRequirement).filter(
            TenderRequirement.rule_type == "DATE_VALIDITY").all():
        cfg = dict(req.rule_config or {})
        cfg.pop("document_type", None)
        req.rule_config = cfg
    db.commit()

    res = load_variety_demo_dataset(db)
    assert res["already_loaded"] is True
    assert res["metadata_refreshed"]["tenders"] == 6
    assert res["metadata_refreshed"]["requirements"] > 0
    assert res["metadata_refreshed"]["rule_configs"] > 0
    for t in _variety_tenders(db):
        assert t.estimated_value_inr is not None
    for req in db.query(TenderRequirement).filter(
            TenderRequirement.rule_type == "DATE_VALIDITY").all():
        assert (req.rule_config or {}).get("document_type") == "ISO_9001_CERTIFICATE"
    # Second refresh is a no-op.
    again = load_variety_demo_dataset(db)
    assert again["metadata_refreshed"] == {"tenders": 0, "requirements": 0,
                                           "rule_configs": 0}


def test_iso_scenarios(db):
    load_variety_demo_dataset(db)

    def iso_status(tender_no, legal):
        b = _bid_of(db, tender_no, legal)
        return (db.query(ComplianceResult).filter_by(bid_id=b.id)
                .join(TenderRequirement,
                      ComplianceResult.requirement_id == TenderRequirement.id)
                .filter(TenderRequirement.rule_type == "DATE_VALIDITY")
                .one().status)

    # Former missing-evidence bidder now has a present, valid ISO.
    assert iso_status("VAR-DEMO-2026-04", "Kaveri Pumps Ltd.") == "PASS"
    # Expired-certificate scenarios (engine-computed, never hardcoded).
    assert iso_status("VAR-DEMO-2026-01",
                      "Mahanadi Equipments Pvt. Ltd.") == "EXPIRED"
    assert iso_status("VAR-DEMO-2026-01", "Aarohan Industries") == "EXPIRED"
    assert iso_status("VAR-DEMO-2026-03", "Kestrel Enterprises") == "EXPIRED"
    assert iso_status("VAR-DEMO-2026-04", "Brightline Tools Co.") == "EXPIRED"
    assert iso_status("VAR-DEMO-2026-06", "Crestline Valves Ltd.") == "EXPIRED"
    # Near-expiry but still valid at evaluation -> PASS (boundary case).
    assert iso_status("VAR-DEMO-2026-03", "Tapi Engineering Works") == "PASS"
    # Certificate does not state an expiry date -> REVIEW_REQUIRED via the
    # engine (the PDF itself is present and processed; the date is unclear).
    assert iso_status("VAR-DEMO-2026-05", "Tapi Engineering Works") == "REVIEW_REQUIRED"
    tapi = _bid_of(db, "VAR-DEMO-2026-05", "Tapi Engineering Works")
    assert db.query(Document).filter_by(
        bid_id=tapi.id, document_type="ISO_9001_CERTIFICATE",
        processing_status="PROCESSED").count() == 1
    # Identity-mismatch certificates: validity PASS, but the ISO document
    # names a different company than the registered bidder.
    for tender_no, legal, iso_name in [
            ("VAR-DEMO-2026-05", "Aarohan Industries",
             "Aarohan Industrial Works"),
            ("VAR-DEMO-2026-06", "Narmada Systems Pvt. Ltd.",
             "Narmada Systems and Controls")]:
        assert iso_status(tender_no, legal) == "PASS"
        b = _bid_of(db, tender_no, legal)
        doc = db.query(Document).filter_by(
            bid_id=b.id, document_type="ISO_9001_CERTIFICATE",
            processing_status="PROCESSED").one()
        got = db.query(ExtractedField).filter_by(
            document_id=doc.id, field_name="legal_name").one().field_value
        assert got == iso_name
    # Everyone else in ISO tenders has a real processed ISO PDF.
    iso_tenders = ["VAR-DEMO-2026-01", "VAR-DEMO-2026-03", "VAR-DEMO-2026-04",
                   "VAR-DEMO-2026-05", "VAR-DEMO-2026-06"]
    bids = (db.query(BidSubmission)
            .join(Tender, BidSubmission.tender_id == Tender.id)
            .filter(Tender.tender_number.in_(iso_tenders)).all())
    lacking = []
    for b in bids:
        docs = db.query(Document).filter_by(
            bid_id=b.id, document_type="ISO_9001_CERTIFICATE").all()
        if not any(d.processing_status == "PROCESSED" for d in docs):
            bidder = db.query(Bidder).filter_by(id=b.bidder_id).one()
            lacking.append(bidder.legal_name)
    assert lacking == []


def test_reset_after_consistency_checks(db):
    """Regression: reset must not trip on consistency_checks doc FKs."""
    from app.models.models import ConsistencyCheck
    from app.services.consistency_service import run_consistency_check

    load_variety_demo_dataset(db)
    bid = _bid_of(db, "VAR-DEMO-2026-02", "Godavari Forge Pvt. Ltd.")
    run_consistency_check(db, bid.id)
    assert db.query(ConsistencyCheck).filter_by(bid_id=bid.id).count() > 0

    result = reset_variety_demo_dataset(db)
    assert result["reset"] is True
    assert result["tenders"] == 6
    assert db.query(ConsistencyCheck).filter_by(bid_id=bid.id).count() == 0
    assert variety_demo_dataset_status(db)["loaded"] is False


def test_load_is_idempotent(db):
    first = load_variety_demo_dataset(db)
    assert first["loaded"] is True
    before = {
        "tenders": db.query(Tender).count(),
        "bids": db.query(BidSubmission).count(),
        "docs": db.query(Document).count(),
    }
    second = load_variety_demo_dataset(db)
    assert second["already_loaded"] is True
    assert {
        "tenders": db.query(Tender).count(),
        "bids": db.query(BidSubmission).count(),
        "docs": db.query(Document).count(),
    } == before
    assert variety_demo_dataset_status(db)["loaded"] is True


def test_reset_is_surgical(db):
    keep = Tender(
        tender_number="REAL-KEEP-VAR-001",
        title="A real tender that must survive",
        organization="CPCL",
        department="Procurement",
        status="OPEN",
    )
    db.add(keep)
    db.commit()

    load_variety_demo_dataset(db)
    run_integrity_analysis(db)
    assert db.query(Tender).filter_by(
        tender_number="REAL-KEEP-VAR-001").count() == 1

    result = reset_variety_demo_dataset(db)
    assert result["reset"] is True
    assert result["tenders"] == 6
    for number in VARIETY_TENDER_NUMBERS:
        assert db.query(Tender).filter_by(tender_number=number).count() == 0
    assert db.query(BidSubmission).join(
        Tender, BidSubmission.tender_id == Tender.id).filter(
        Tender.tender_number.in_(VARIETY_TENDER_NUMBERS)).count() == 0
    assert db.query(Document).join(
        BidSubmission, Document.bid_id == BidSubmission.id).join(
        Tender, BidSubmission.tender_id == Tender.id).filter(
        Tender.tender_number.in_(VARIETY_TENDER_NUMBERS)).count() == 0
    # Unrelated records survive; variety integrity findings are gone.
    assert db.query(Tender).filter_by(
        tender_number="REAL-KEEP-VAR-001").count() == 1
    assert db.query(IntegrityFinding).filter(
        IntegrityFinding.signal_type == "DOCUMENT_IDENTITY_RELATIONSHIP",
        IntegrityFinding.status != "CLOSED").count() == 0
    assert variety_demo_dataset_status(db)["loaded"] is False

    # Reload works cleanly after reset.
    again = load_variety_demo_dataset(db)
    assert again["loaded"] is True
    assert again["bids"] == 42
