"""End-to-end test for Stage-3 demo-bidder evidence seeding.

The seed endpoint attaches each profile's fictional dossier and runs ONLY
the real document pipeline (classification + extraction) — exactly what
happens automatically on upload. Verification, compliance+risk and the AI
recommendation are deliberately NOT pre-computed: the officer triggers those
from the existing Bid Detail buttons, so scores are derived live.

The test therefore simulates the officer flow per profile
(run_verification -> evaluate_bid -> generate_recommendation, the same
services the buttons call) and asserts the four profiles produce
meaningfully different, honest outcomes:

- apex:      mostly compliant (PROCEED, high score, LOW risk)
- vertex:    missing evidence (REVIEW_REQUIRED, MISSING statuses)
- nova:      portal name conflict (MISMATCH, REVIEW_REQUIRED)
- primetech: blacklist signal (CRITICAL risk, NOT_RECOMMENDED, high score —
  compliance and risk stay separate)

Re-seeding the same profile must not duplicate bidders or documents.
"""
from app.models.models import (
    Bidder,
    BidSubmission,
    ComplianceResult,
    Document,
    ExtractedField,
    RiskAssessment,
    Tender,
    TenderRequirement,
    VerificationCheck,
)
from app.seed.demo_bidder_profiles import PROFILES
from app.services.compliance_service import evaluate_bid
from app.services.demo_seed_service import seed_demo_bidder_evidence
from app.services.recommendation_service import generate_recommendation
from app.services.verification_service import run_verification

REQUIREMENTS = [
    ("GST Registration Status", "REGISTRATION_STATUS",
     {"source": "GSTN", "identifier_field": "gstin", "require_status": "ACTIVE"},
     "GSTN", True, 10),
    ("PAN Statutory Verification", "REGISTRATION_STATUS",
     {"source": "PAN_IT", "identifier_field": "pan", "require_status": "ACTIVE"},
     "PAN_IT", True, 5),
    ("Average Annual Turnover", "MINIMUM",
     {"value_source": "extracted.turnover_inr", "operator": ">=", "value": 25000000},
     None, True, 15),
    ("Relevant Technical Experience", "MINIMUM",
     {"value_source": "extracted.experience_years", "operator": ">=", "value": 3},
     None, True, 15),
    ("Past Contract Performance", "MINIMUM",
     {"value_source": "extracted.past_performance_pct", "operator": ">=", "value": 40},
     None, True, 10),
    ("OEM Authorization Undertaking", "BOOLEAN",
     {"value_source": "extracted.oem_authorization_valid", "expected": True},
     None, True, 15),
    ("Make In India (MII) Local Content", "MINIMUM",
     {"value_source": "extracted.local_content_pct", "operator": ">=", "value": 50},
     None, False, 10),
    ("Earnest Money Deposit (EMD)", "MINIMUM",
     {"value_source": "extracted.emd_amount_inr", "operator": ">=", "value": 500000},
     None, True, 10),
    ("Consolidated Bid Dossier", "DOCUMENT_REQUIRED",
     {"document_types": ["BID_DOSSIER"]}, None, True, 10),
]


def _make_tender(db):
    t = Tender(tender_number="DEMO-E2E-001", title="Demo E2E", organization="CPCL",
               department="Procurement", status="OPEN")
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


def _officer_flow(db, bid_id):
    """Simulate the officer's Bid Detail button clicks with real services."""
    run_verification(db, bid_id)
    evaluate_bid(db, bid_id)
    generate_recommendation(db, bid_id)


def _statuses(db, bid_id):
    return sorted({r.status for r in
                   db.query(ComplianceResult).filter_by(bid_id=bid_id).all()})


def test_demo_seed_stops_at_extraction(db, tmp_path):
    """Scores must NOT be pre-computed — only the document + extracted fields."""
    tender = _make_tender(db)
    bid = _make_bid(db, tender.id, PROFILES["apex"]["legal_name"])

    res = seed_demo_bidder_evidence(db, bid.id, "apex")
    assert res["seeded"] is True

    doc = db.query(Document).filter_by(bid_id=bid.id).one()
    assert doc.processing_status == "PROCESSED"
    assert db.query(ExtractedField).filter_by(document_id=doc.id).count() > 0

    # Nothing derived yet: the officer hasn't clicked anything.
    db.refresh(bid)
    assert db.query(VerificationCheck).filter_by(bid_id=bid.id).count() == 0
    assert db.query(ComplianceResult).filter_by(bid_id=bid.id).count() == 0
    assert db.query(RiskAssessment).filter_by(bid_id=bid.id).count() == 0
    assert bid.compliance_score is None
    assert bid.recommendation is None


def test_demo_profiles_produce_distinct_real_outcomes(db, tmp_path):
    tender = _make_tender(db)
    bids = {}
    for key, profile in PROFILES.items():
        bid = _make_bid(db, tender.id, profile["legal_name"])
        res = seed_demo_bidder_evidence(db, bid.id, key)
        assert res["seeded"] is True, key
        bids[key] = bid

    # Officer evaluates each bid through the real buttons' services.
    for key, bid in bids.items():
        _officer_flow(db, bid.id)

    apex, vertex, nova, prime = (bids["apex"], bids["vertex"],
                                bids["nova"], bids["primetech"])
    for bid in bids.values():
        db.refresh(bid)
        assert bid.recommendation, "recommendation stored"
        assert bid.compliance_score is not None

    # Apex: mostly compliant — high score, PROCEED, LOW risk, no missing/mismatch.
    assert apex.compliance_score >= 85
    assert apex.recommendation == "PROCEED"
    assert apex.risk_level == "LOW"
    assert "MISSING" not in _statuses(db, apex.id)
    assert "MISMATCH" not in _statuses(db, apex.id)

    # Vertex: missing evidence — MISSING statuses, REVIEW_REQUIRED.
    assert "MISSING" in _statuses(db, vertex.id)
    assert vertex.recommendation == "REVIEW_REQUIRED"
    assert vertex.compliance_score < apex.compliance_score

    # Nova: portal name conflict — MISMATCH on registration checks.
    assert "MISMATCH" in _statuses(db, nova.id)
    assert nova.recommendation == "REVIEW_REQUIRED"
    mismatch_checks = [c for c in db.query(VerificationCheck)
                       .filter_by(bid_id=nova.id).all()
                       if c.verification_status == "MISMATCH"]
    assert mismatch_checks, "expected MISMATCH verification checks for nova"

    # PrimeTech: compliance stays high but the blacklist drives CRITICAL risk
    # and NOT_RECOMMENDED — score and risk are separate concepts.
    assert prime.compliance_score >= 85
    assert prime.risk_level == "CRITICAL"
    assert prime.recommendation == "NOT_RECOMMENDED"
    risk = db.query(RiskAssessment).filter_by(bid_id=prime.id).one()
    assert any(s.get("code") in ("BLACKLISTED", "DEBARRED") for s in (risk.signals or []))


def test_demo_seed_is_idempotent(db, tmp_path):
    tender = _make_tender(db)
    bid = _make_bid(db, tender.id, PROFILES["apex"]["legal_name"])

    first = seed_demo_bidder_evidence(db, bid.id, "apex")
    assert first["seeded"] is True
    doc_count = db.query(Document).filter_by(bid_id=bid.id).count()

    second = seed_demo_bidder_evidence(db, bid.id, "apex")
    assert second["seeded"] is False
    assert db.query(Document).filter_by(bid_id=bid.id).count() == doc_count
    # Still exactly one bidder row for the tender + this bid.
    assert db.query(Bidder).filter_by(tender_id=tender.id).count() == 1


def test_demo_seed_rejects_unknown_profile(db, tmp_path):
    tender = _make_tender(db)
    bid = _make_bid(db, tender.id, "Some Bidder")
    try:
        seed_demo_bidder_evidence(db, bid.id, "unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown profile")


def test_seed_endpoint_matches_frontend_flow(db, tmp_path):
    """Regression test for the exact HTTP flow the Create-Tender publish
    loop performs: POST /bids -> POST /bids/{id}/seed-demo-evidence.

    Calls the endpoint function directly (same arguments FastAPI would
    inject) and asserts the response shape the frontend consumes plus the
    resulting bid detail state (1 processed dossier document).
    """
    import app.api.bids as bids_mod
    from app.schemas.schemas import DemoEvidenceSeedRequest
    from app.models.models import User

    tender = _make_tender(db)
    bid = _make_bid(db, tender.id, PROFILES["apex"]["legal_name"])
    officer = User(name="o", email="officer@test.local", password_hash="x",
                   role="PROCUREMENT_OFFICER")

    res = bids_mod.seed_demo_evidence(
        bid_id=bid.id,
        payload=DemoEvidenceSeedRequest(profile_key="apex"),
        db=db,
        user=officer,
    )
    assert res["seeded"] is True
    assert res["bid_id"] == bid.id
    assert res["document_id"] is not None
    assert res["processing_status"] == "PROCESSED"
    assert res["fields_extracted"] > 0

    doc = db.query(Document).filter_by(bid_id=bid.id).one()
    assert doc.processing_status == "PROCESSED"
    assert doc.document_type == "BID_DOSSIER"


def test_seed_endpoint_unknown_profile_is_404(db):
    import pytest as _pytest
    import app.api.bids as bids_mod
    from fastapi import HTTPException as _HTTPException
    from app.schemas.schemas import DemoEvidenceSeedRequest
    from app.models.models import User

    tender = _make_tender(db)
    bid = _make_bid(db, tender.id, "Some Bidder")
    officer = User(name="o", email="officer@test.local", password_hash="x",
                   role="PROCUREMENT_OFFICER")
    with _pytest.raises(_HTTPException) as exc_info:
        bids_mod.seed_demo_evidence(
            bid_id=bid.id,
            payload=DemoEvidenceSeedRequest(profile_key="bogus"),
            db=db,
            user=officer,
        )
    assert exc_info.value.status_code == 404
