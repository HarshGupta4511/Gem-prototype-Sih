"""20-step end-to-end test: scenario-driven demo evidence through the real pipeline.

Follows the officer's button flow (seed -> verify -> evaluate -> recommend)
for mismatch-focused scenarios with fixed seeds. Every outcome is computed
by the real engines — nothing is hardcoded in the app; the test only asserts
the direction each scenario is designed to produce.
"""
import json

import pytest

from app.models.models import (
    Bidder,
    BidSubmission,
    ComplianceResult,
    Document,
    ExtractedField,
    RiskAssessment,
    Tender,
    TenderRequirement,
    User,
    VerificationCheck,
)
from app.seed import demo_scenarios as ds
from app.services.compliance_service import evaluate_bid
from app.services.consistency_service import run_consistency_check
from app.services.demo_seed_service import seed_demo_bidder_evidence
from app.services.recommendation_service import generate_recommendation
from app.services.verification_service import run_verification


def _officer(db):
    u = db.query(User).filter_by(email="officer@demo.cpcl.in").first()
    if u is None:
        u = User(email="officer@demo.cpcl.in", name="Test Officer",
                 role="PROCUREMENT_OFFICER", password_hash="x")
        db.add(u)
        db.commit()
    return u


def _catalogue_entries():
    data = json.loads(open(
        "/home/hatch/workspace/cpcl-bidverify-live/frontend/src/lib/"
        "requirement-catalogue.json").read())
    return [e for e in data["entries"] if e.get("in_default_template")]


def _make_tender(db):
    entries = _catalogue_entries()
    assert len(entries) == 10
    assert round(sum(e["default_weight"] for e in entries), 2) == 100.0
    t = Tender(tender_number="SCN-E2E-001", title="Scenario E2E",
               organization="CPCL", department="Procurement", status="OPEN")
    db.add(t)
    db.flush()
    for e in entries:
        db.add(TenderRequirement(
            tender_id=t.id,
            requirement_name=e["requirement_name"],
            category=e.get("category", "STATUTORY"),
            rule_type=e["rule_type"],
            rule_config=e.get("rule_config") or {},
            verification_source=e.get("verification_source"),
            threshold=e.get("threshold"),
            description=e.get("description"),
            weight=e["default_weight"],
            mandatory=bool(e.get("default_mandatory", True)),
        ))
    db.commit()
    return t.id


def _make_bid(db, tender_id, legal_name):
    bidder = Bidder(tender_id=tender_id, legal_name=legal_name,
                    bid_status="SUBMITTED")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=tender_id, bidder_id=bidder.id,
                        status="SUBMITTED")
    db.add(bid)
    db.commit()
    return bid


def _run_pipeline(db, bid_id):
    run_verification(db, bid_id)
    run_consistency_check(db, bid_id)
    evaluate_bid(db, bid_id)
    generate_recommendation(db, bid_id)
    db.refresh(db.get(BidSubmission, bid_id))


def _statuses(db, bid_id):
    return sorted({r.status for r in
                   db.query(ComplianceResult).filter_by(bid_id=bid_id).all()})


def test_20_step_scenario_end_to_end(db, tmp_path):
    _officer(db)

    # -- Steps 1-2: tender from the 10-requirement catalogue -----------------
    # 1. The catalogue template carries exactly 10 requirements.
    entries = _catalogue_entries()
    assert len(entries) == 10
    # 2. Default weights sum to exactly 100 (publish gate precondition).
    assert round(sum(e["default_weight"] for e in entries), 2) == 100.0
    tender_id = _make_tender(db)
    reqs = db.query(TenderRequirement).filter_by(tender_id=tender_id).all()
    assert len(reqs) == 10

    # -- Steps 3-7: clean scenario -----------------------------------------
    # 3. Register a bidder and seed the clean scenario with a fixed seed.
    bid = _make_bid(db, tender_id, "Scenario Clean Pvt. Ltd.")
    res = seed_demo_bidder_evidence(db, bid.id, "apex",
                                    scenario_id="clean", seed=42)
    assert res["seeded"] is True
    assert res["scenario_id"] == "clean"
    assert res["seed"] == 42
    docs = db.query(Document).filter_by(bid_id=bid.id).all()
    # 4. All documents processed through the real pipeline.
    assert all(d.processing_status == "PROCESSED" for d in docs)
    n_docs = len(docs)
    assert n_docs >= 10
    # 5. Re-seeding with the same seed is idempotent (no duplicates).
    res2 = seed_demo_bidder_evidence(db, bid.id, "apex",
                                     scenario_id="clean", seed=42)
    assert db.query(Document).filter_by(bid_id=bid.id).count() == n_docs
    # 6. Every generated PDF is literally marked as a sample.
    import fitz
    for d in docs:
        text = "\n".join(
            p.get_text() for p in
            fitz.open(stream=open(d.file_path, "rb").read(), filetype="pdf"))
        assert "SAMPLE" in text and "FOR DEMONSTRATION ONLY" in text
    # 7. Clean scenario -> APPROVE / LOW via the real engines.
    _run_pipeline(db, bid.id)
    b = db.get(BidSubmission, bid.id)
    assert b.compliance_score is not None and b.recommendation == "APPROVE"
    assert b.risk_level == "LOW"

    # -- Steps 8-10: GST name mismatch --------------------------------------
    # 8. Seed the GST name-mismatch scenario.
    bid2 = _make_bid(db, tender_id, "Scenario GST Pvt. Ltd.")
    seed_demo_bidder_evidence(db, bid2.id, "apex",
                              scenario_id="gst_name_mismatch", seed=42)
    _run_pipeline(db, bid2.id)
    # 9. A GSTN verification MISMATCH is recorded (document vs registry).
    gst_checks = [c for c in db.query(VerificationCheck)
                  .filter_by(bid_id=bid2.id).all() if c.source == "GSTN"]
    assert gst_checks and any(c.verification_status == "MISMATCH"
                              for c in gst_checks)
    # 10. The mismatch surfaces in compliance statuses.
    assert "MISMATCH" in _statuses(db, bid2.id)

    # -- Steps 11-12: PAN name mismatch ------------------------------------
    # 11. Seed the PAN name-mismatch scenario.
    bid3 = _make_bid(db, tender_id, "Scenario PAN Pvt. Ltd.")
    seed_demo_bidder_evidence(db, bid3.id, "apex",
                              scenario_id="pan_name_mismatch", seed=42)
    _run_pipeline(db, bid3.id)
    # 12. PAN_IT verification reports MISMATCH.
    pan_checks = [c for c in db.query(VerificationCheck)
                  .filter_by(bid_id=bid3.id).all() if c.source == "PAN_IT"]
    assert pan_checks and any(c.verification_status == "MISMATCH"
                              for c in pan_checks)

    # -- Step 13: ITR financial-year mismatch -------------------------------
    bid4 = _make_bid(db, tender_id, "Scenario ITR Pvt. Ltd.")
    seed_demo_bidder_evidence(db, bid4.id, "apex",
                              scenario_id="itr_fy_mismatch", seed=42)
    _run_pipeline(db, bid4.id)
    itr_rows = [r for r in db.query(ComplianceResult)
                .filter_by(bid_id=bid4.id).all()
                if "Income Tax Return" in (db.get(
                    TenderRequirement, r.requirement_id).requirement_name)]
    assert itr_rows and all(r.status == "FAIL" for r in itr_rows)

    # -- Step 14: turnover shortfall ----------------------------------------
    bid5 = _make_bid(db, tender_id, "Scenario Turnover Pvt. Ltd.")
    seed_demo_bidder_evidence(db, bid5.id, "apex",
                              scenario_id="turnover_shortfall", seed=42)
    _run_pipeline(db, bid5.id)
    bs_rows = [r for r in db.query(ComplianceResult)
               .filter_by(bid_id=bid5.id).all()
               if "Balance Sheet" in (db.get(
                   TenderRequirement, r.requirement_id).requirement_name)]
    assert bs_rows and all(r.status == "FAIL" for r in bs_rows)

    # -- Step 15: expired ISO certificate -----------------------------------
    bid6 = _make_bid(db, tender_id, "Scenario ISO Pvt. Ltd.")
    seed_demo_bidder_evidence(db, bid6.id, "apex",
                              scenario_id="iso_expired", seed=42)
    _run_pipeline(db, bid6.id)
    assert "FAIL" in _statuses(db, bid6.id) or "EXPIRED" in _statuses(db, bid6.id)

    # -- Step 16: EMD wrong amount ------------------------------------------
    bid7 = _make_bid(db, tender_id, "Scenario EMD Pvt. Ltd.")
    seed_demo_bidder_evidence(db, bid7.id, "apex",
                              scenario_id="emd_wrong_amount", seed=42)
    _run_pipeline(db, bid7.id)
    emd_rows = [r for r in db.query(ComplianceResult)
                .filter_by(bid_id=bid7.id).all()
                if "EMD" in (db.get(
                    TenderRequirement, r.requirement_id).requirement_name)]
    assert emd_rows and all(r.status == "FAIL" for r in emd_rows)

    # -- Step 17: debarred scenario ------------------------------------------
    bid8 = _make_bid(db, tender_id, "Scenario Debarred Pvt. Ltd.")
    seed_demo_bidder_evidence(db, bid8.id, "primetech",
                              scenario_id="debarred", seed=42)
    _run_pipeline(db, bid8.id)
    b8 = db.get(BidSubmission, bid8.id)
    assert b8.risk_level == "HIGH"
    assert b8.recommendation == "REJECT"

    # -- Step 18: missing evidence -------------------------------------------
    bid9 = _make_bid(db, tender_id, "Scenario Missing Pvt. Ltd.")
    seed_demo_bidder_evidence(db, bid9.id, "vertex",
                              scenario_id="missing_evidence", seed=42)
    _run_pipeline(db, bid9.id)
    assert "MISSING" in _statuses(db, bid9.id)

    # -- Step 19: seed sensitivity -------------------------------------------
    # A different seed produces different fictional identifiers.
    p1 = ds.plan_scenario("apex", "clean", 42, "Seed Test Pvt. Ltd.")
    p2 = ds.plan_scenario("apex", "clean", 43, "Seed Test Pvt. Ltd.")
    assert p1.identifiers != p2.identifiers

    # -- Step 20: audit trail carries scenario metadata -----------------------
    from app.models.models import AuditLog
    events = db.query(AuditLog).filter(
        AuditLog.entity_type == "bid_submission").all()
    seeded = [e for e in events if e.action == "DEMO_EVIDENCE_SEEDED"]
    assert seeded, "seed events must be audited"
    assert any((e.meta or {}).get("scenario_id") == "gst_name_mismatch"
               for e in seeded)
