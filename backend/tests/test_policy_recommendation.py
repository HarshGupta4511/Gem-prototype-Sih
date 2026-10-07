"""End-to-end: deterministic finding -> retrieval -> citation -> explanation.

Covers the eight required scenarios:
1. GST mismatch            -> no citation (no configured authoritative source)
2. PAN mismatch            -> no citation
3. Udyam requirement       -> Udyam/MSME citation, version-aware
4. Make in India / local content -> DPIIT Order citations
5. Blacklisting/debarment  -> GFR Rule 151 + DoE guidelines citations
6. OEM authorization       -> no citation
7. Missing document        -> no citation
8. Minimum turnover        -> no citation

Also proves the non-regression contract: compliance statuses, compliance
score, risk score/level are unchanged by retrieval, and citations persist
on the bid so reopening Bid Detail shows the same records.
"""
import uuid

from app.models.models import (
    Bidder,
    BidSubmission,
    ComplianceResult,
    RiskAssessment,
    Tender,
    TenderRequirement,
)
from app.schemas.schemas import RecommendationOut
from app.seed.seed_data import _seed_knowledge
from app.services.recommendation_service import MIN_RELEVANCE, generate_recommendation

MII_TITLE = (
    "Public Procurement (Preference to Make in India), Order 2017 — "
    "Revision dated 19.07.2024"
)
GFR_TITLE = "General Financial Rules, 2017 — Procurement Provisions"
UDYAM_TITLE = "Udyam Registration — MSME Classification (Ministry of MSME)"
DEBAR_TITLE = "Debarment of Firms from Bidding — DoE Guidelines"

CITABLE_KEYS = {
    "title", "authority", "source_url", "document_type", "version",
    "publication_date", "effective_date", "section", "why_relevant",
    "excerpt", "score",
}


def _make_bid(db, findings, signals=None):
    """Build tender + requirement + compliance rows for synthetic findings.

    findings: list of dicts with keys: name, description, threshold,
    expected_value, mandatory, weight, status, explanation, source.
    """
    tender = Tender(
        tender_number=f"RAG-{uuid.uuid4().hex[:8]}",
        title="RAG scenario tender",
        organization="CPCL",
        department="Procurement",
        status="OPEN",
    )
    db.add(tender)
    db.flush()
    bidder = Bidder(tender_id=tender.id, legal_name="Scenario Bidder Pvt Ltd",
                    bid_status="SUBMITTED")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(
        tender_id=tender.id, bidder_id=bidder.id, status="SUBMITTED",
        compliance_score=62.5, risk_score=40.0, risk_level="MEDIUM",
    )
    db.add(bid)
    db.flush()
    for f in findings:
        req = TenderRequirement(
            tender_id=tender.id, requirement_name=f["name"], category="test",
            description=f.get("description", ""), threshold=f.get("threshold"),
            expected_value=f.get("expected_value"),
            mandatory=f.get("mandatory", True), rule_type="TEST",
            rule_config={}, verification_source=f.get("source"),
            weight=f.get("weight", 10),
        )
        db.add(req)
        db.flush()
        db.add(ComplianceResult(
            bid_id=bid.id, requirement_id=req.id, status=f["status"],
            weight=req.weight, weighted_contribution=0.0,
            evidence=[], explanation=f.get("explanation", ""),
            rule_applied="test-rule", source=f.get("source", "document"),
        ))
    if signals:
        db.add(RiskAssessment(bid_id=bid.id, risk_level="CRITICAL",
                              risk_score=95.0, signals=signals, explanation=""))
    db.commit()
    return bid.id


def _recommend(db, findings, signals=None):
    _seed_knowledge(db)
    bid_id = _make_bid(db, findings, signals)
    before = db.get(BidSubmission, bid_id)
    snapshot = (
        before.compliance_score, before.risk_score, before.risk_level,
        [(r.id, r.status) for r in
         db.query(ComplianceResult).filter_by(bid_id=bid_id).all()],
    )
    result = generate_recommendation(db, bid_id)
    return bid_id, result, snapshot


def _assert_engines_untouched(db, bid_id, snapshot):
    score, risk_score, risk_level, statuses = snapshot
    bid = db.get(BidSubmission, bid_id)
    assert bid.compliance_score == score
    assert bid.risk_score == risk_score
    assert bid.risk_level == risk_level
    current = [(r.id, r.status) for r in
               db.query(ComplianceResult).filter_by(bid_id=bid_id).all()]
    assert current == statuses, "retrieval must never change compliance statuses"


def _assert_citable(citations):
    for c in citations:
        missing = CITABLE_KEYS - set(c.keys())
        assert not missing, f"citation missing keys: {missing}"
        assert c["title"] and c["authority"] and c["section"]
        assert c["excerpt"], "citation excerpt must be non-empty"
        assert c["source_url"].startswith("https://"), c["source_url"]
        assert c["score"] >= MIN_RELEVANCE


# 1. GST mismatch -> no citation -------------------------------------------
def test_gst_mismatch_no_citation(db):
    bid_id, result, snap = _recommend(db, [{
        "name": "GST Registration Status",
        "description": "Bidder GSTIN must be active on the GST portal.",
        "threshold": "Active", "expected_value": "ACTIVE",
        "status": "MISMATCH",
        "explanation": "MISMATCH — GSTIN 27XXXXX1234X1Z5 in bid does not match GST portal record.",
        "source": "GSTN",
    }])
    assert result["policy_context"] == []
    assert result["provider"] == "rules+policy-retrieval"
    _assert_engines_untouched(db, bid_id, snap)


# 2. PAN mismatch -> no citation -------------------------------------------
def test_pan_mismatch_no_citation(db):
    bid_id, result, snap = _recommend(db, [{
        "name": "PAN Statutory Verification",
        "description": "Bidder PAN must verify on the Income Tax portal.",
        "threshold": "Active", "expected_value": "ACTIVE",
        "status": "MISMATCH",
        "explanation": "MISMATCH — PAN ABCDE1234F in bid document does not match portal record.",
        "source": "PAN_IT",
    }])
    assert result["policy_context"] == []
    _assert_engines_untouched(db, bid_id, snap)


# 3. Udyam requirement -> Udyam citation -----------------------------------
def test_udyam_missing_citation(db):
    bid_id, result, snap = _recommend(db, [{
        "name": "Udyam Registration (MSME)",
        "description": "Bidder must hold valid Udyam registration for MSE benefits.",
        "threshold": "Valid Udyam", "expected_value": "REGISTERED",
        "status": "MISSING",
        "explanation": "MISSING — Udyam registration certificate not submitted by bidder.",
        "source": "document",
    }])
    cites = result["policy_context"]
    assert cites, "expected Udyam citation"
    assert {c["title"] for c in cites} == {UDYAM_TITLE}
    assert "udyamregistration.gov.in" in cites[0]["source_url"]
    _assert_citable(cites)
    _assert_engines_untouched(db, bid_id, snap)


# 4. Make in India -> DPIIT Order citations --------------------------------
def test_mii_mismatch_citation(db):
    bid_id, result, snap = _recommend(db, [{
        "name": "Make In India (MII) Local Content",
        "description": "Minimum local content 50% with self-certification; Class-I local supplier.",
        "threshold": "Minimum 50%", "expected_value": ">=50",
        "status": "MISMATCH",
        "explanation": "MISMATCH — declared local content 30% below required minimum 50%.",
        "source": "document",
    }])
    cites = result["policy_context"]
    assert cites, "expected MII citations"
    assert {c["title"] for c in cites} == {MII_TITLE}
    sections = [c["section"] for c in cites]
    assert any(s.startswith("Para 5") for s in sections), sections
    assert "dpiit.gov.in" in cites[0]["source_url"]
    assert "19.07.2024" in cites[0]["version"]
    _assert_citable(cites)
    _assert_engines_untouched(db, bid_id, snap)


# 5. Blacklisting/debarment -> GFR Rule 151 + DoE guidelines ---------------
def test_debarment_fail_citation(db):
    signals = [{
        "code": "BLACKLISTED", "severity": "critical",
        "message": "BLACKLISTED: bidder found on blacklist as per BLACKLIST verification.",
    }]
    bid_id, result, snap = _recommend(db, [{
        "name": "Bidder must not be blacklisted or debarred",
        "description": "Bidder must not appear on any blacklist or debarment list.",
        "threshold": "Not blacklisted / debarred", "expected_value": "PASS",
        "status": "FAIL",
        "explanation": "FAIL — bidder appears on blacklist verification data.",
        "source": "BLACKLIST",
    }], signals=signals)
    cites = result["policy_context"]
    assert cites, "expected debarment citations"
    assert {c["title"] for c in cites} <= {GFR_TITLE, DEBAR_TITLE}
    assert any("Rule 151" in c["section"] for c in cites), [c["section"] for c in cites]
    assert all("Department of Expenditure" in c["authority"] for c in cites)
    assert result["recommendation"] == "REJECT"
    _assert_citable(cites)
    _assert_engines_untouched(db, bid_id, snap)


# 6. OEM authorization -> no citation --------------------------------------
def test_oem_mismatch_no_citation(db):
    bid_id, result, snap = _recommend(db, [{
        "name": "OEM Authorization Undertaking",
        "description": "Bidder must submit valid OEM authorization for quoted product.",
        "threshold": "Valid", "expected_value": "True",
        "status": "MISMATCH",
        "explanation": "MISMATCH — OEM authorization letter not valid for quoted product.",
        "source": "document",
    }])
    assert result["policy_context"] == []
    _assert_engines_untouched(db, bid_id, snap)


# 7. Missing document -> no citation ---------------------------------------
def test_missing_document_no_citation(db):
    bid_id, result, snap = _recommend(db, [{
        "name": "Experience Certificate",
        "description": "Bidder must upload experience certificate.",
        "threshold": "Uploaded", "expected_value": "PRESENT",
        "status": "MISSING",
        "explanation": "MISSING — required experience certificate document not uploaded.",
        "source": "document",
    }])
    assert result["policy_context"] == []
    _assert_engines_untouched(db, bid_id, snap)


# 8. Minimum turnover -> no citation ---------------------------------------
def test_turnover_review_no_citation(db):
    bid_id, result, snap = _recommend(db, [{
        "name": "Average Annual Turnover",
        "description": "Bidder must meet minimum average annual turnover.",
        "threshold": "Rs 5 crore", "expected_value": ">=50000000",
        "status": "REVIEW_REQUIRED",
        "explanation": "REVIEW_REQUIRED — average annual turnover Rs 4.2 crore below minimum Rs 5 crore.",
        "source": "document",
    }])
    assert result["policy_context"] == []
    _assert_engines_untouched(db, bid_id, snap)


# Persistence: reopening Bid Detail shows the same citations ----------------
def test_policy_context_persisted_and_returned_on_reopen(db):
    _seed_knowledge(db)
    bid_id = _make_bid(db, [{
        "name": "Make In India (MII) Local Content",
        "description": "Minimum local content 50% with self-certification.",
        "threshold": "Minimum 50%", "expected_value": ">=50",
        "status": "MISMATCH",
        "explanation": "MISMATCH — declared local content 30% below required minimum 50%.",
        "source": "document",
    }])
    result = generate_recommendation(db, bid_id)
    assert result["policy_context"], "expected citations at generation time"

    # Simulate reopening Bid Detail in a fresh read (as bids.py does).
    db.expire_all()
    bid = db.get(BidSubmission, bid_id)
    assert bid.policy_context == result["policy_context"]

    out = RecommendationOut(
        recommendation=bid.recommendation,
        reason=bid.recommendation_reason,
        evidence=bid.recommendation_evidence or [],
        policy_context=bid.policy_context or [],
        provider="rules+policy-retrieval" if (bid.policy_context or []) else None,
    )
    assert out.policy_context == result["policy_context"]
    assert out.provider == "rules+policy-retrieval"
    _assert_citable(out.policy_context)


# All-PASS bid: single eligible bidder -> APPROVE, no citations ----------
def test_all_pass_no_citations(db):
    bid_id, result, snap = _recommend(db, [{
        "name": "GST Registration Status",
        "description": "Bidder GSTIN must be active.",
        "threshold": "Active", "expected_value": "ACTIVE",
        "status": "PASS",
        "explanation": "PASS — GSTIN active on portal.",
        "source": "GSTN",
    }])
    assert result["recommendation"] == "APPROVE"
    assert result["policy_context"] == []
    _assert_engines_untouched(db, bid_id, snap)
