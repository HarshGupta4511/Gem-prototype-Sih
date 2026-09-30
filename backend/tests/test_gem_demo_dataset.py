"""GeM-style synthetic demo dataset (tender GEM-DEMO-2026-101).

Regression coverage for the dataset built from Harsh's reference PDFs:
three fictional bidders (A compliant / B mismatch / C multi-issue) under one
synthetic haemodialysis-consumables tender, each with a single bannered bid
dossier. Covers: requirement weight sanity, EMD + past-performance
extraction (regex and mock-LLM), the new dossier sections, rule-engine
behavior on the new requirements, the end-to-end seeded outcomes, per-tender
idempotency, and a guard that no real reference-PDF identifiers leak into the
synthetic data.
"""
import fitz

from app.models.models import (
    BidSubmission,
    ComplianceResult,
    Document,
    Tender,
)
from app.seed.demo_docs import _paragraphs, generate_dossier_pdf
from app.seed.gem_demo_seed import (
    BANNER,
    T4_NUMBER,
    _BIDDERS_T4,
    _t4_dossier,
    _tender4_requirements,
    seed_gem_demo_tender,
)
from app.seed.seed_data import _seed_users, run_seed
from app.engines.rules_engine import RulesEngine

ENGINE = RulesEngine()
from app.services.llm_service import MockLLMProvider
from app.services.regex_service import extract_all


# --- static sanity ----------------------------------------------------------

def test_t4_requirement_weights_sum_to_100():
    reqs = _tender4_requirements()
    assert len(reqs) == 10
    assert sum(r["weight"] for r in reqs) == 100
    assert all(r["mandatory"] for r in reqs if r["requirement_name"] !=
               "Make in India Local Content \u2265 50%")


def test_t4_dossier_templates_carry_extractable_labels():
    title, fields, _paras = _paragraphs(
        "EMD_PAYMENT",
        {"legal_name": "X", "emd_amount": "Rs 15,000",
         "emd_reference": "SBIN1", "emd_date": "12-09-2026",
         "emd_beneficiary": "Demo Hospital"})
    labels = [label for label, _ in fields]
    assert "EMD Amount" in labels and "Payment Reference" in labels

    title, fields, _paras = _paragraphs(
        "PAST_PERFORMANCE_CERTIFICATE",
        {"legal_name": "X", "past_performance": "34% of bid quantity",
         "past_performance_client": "Demo Hospital"})
    labels = [label for label, _ in fields]
    assert "Past Performance" in labels


def test_regex_extracts_emd_and_past_performance():
    fields = extract_all(
        "EMD Amount: Rs 15,000\nPayment Reference: SBIN202609120045\n"
        "Past Performance: 34% of bid quantity supplied in FY2024-25\n", 1)
    by_name = {f["field_name"]: f["normalized_value"] for f in fields}
    assert by_name["emd_amount_inr"] == "15000"
    assert by_name["past_performance_pct"] == "34.0"


def test_mock_llm_extracts_emd_and_past_performance():
    fields = MockLLMProvider().extract_fields(
        "BID_DOSSIER",
        "EMD Amount: Rs 15,000\n"
        "Past Performance: 22% of bid quantity supplied in FY2024-25\n",
        "dossier.pdf")
    assert fields["emd_amount_inr"] == 15000
    assert fields["past_performance_pct"] == 22.0


# --- rule engine on the new requirement types --------------------------------

def test_minimum_rule_on_emd():
    req = {"rule_type": "MINIMUM",
           "rule_config": {"value_source": "extracted.emd_amount_inr",
                           "operator": ">=", "value": 15000}}
    ok = ENGINE.evaluate(req, {"extracted": {"emd_amount_inr": 15000}})
    assert ok["status"] == "PASS"
    short = ENGINE.evaluate(req, {"extracted": {"emd_amount_inr": 14000}})
    assert short["status"] == "FAIL"
    missing = ENGINE.evaluate(req, {"extracted": {}})
    assert missing["status"] == "MISSING"


def test_boolean_rule_on_oem():
    req = {"rule_type": "BOOLEAN",
           "rule_config": {"value_source": "extracted.oem_authorization_valid",
                           "expected": True}}
    assert ENGINE.evaluate(
        req, {"extracted": {"oem_authorization_valid": True}})["status"] == "PASS"
    assert ENGINE.evaluate(
        req, {"extracted": {"oem_authorization_valid": False}})["status"] == "FAIL"
    assert ENGINE.evaluate(
        req, {"extracted": {}})["status"] == "MISSING"


def test_blacklist_custom_rule():
    req = {"rule_type": "CUSTOM_RULE",
           "rule_config": {"expression":
               "not (ctx['verification'].get('BLACKLIST') or {}).get('data', {}).get('blacklisted', False)"}}
    clean = ENGINE.evaluate(
        req, {"verification": {"BLACKLIST": {"data": {"blacklisted": False}}}})
    assert clean["status"] == "PASS"
    dirty = ENGINE.evaluate(
        req, {"verification": {"BLACKLIST": {"data": {"blacklisted": True}}}})
    assert dirty["status"] == "FAIL"


# --- seeded end-to-end outcomes -----------------------------------------------

def _seed_t4(db):
    users = _seed_users(db)
    result = seed_gem_demo_tender(db, users["officer@demo.cpcl.in"].id)
    assert result["skipped"] is False
    tender = db.query(Tender).filter(
        Tender.tender_number == T4_NUMBER).one()
    bids = db.query(BidSubmission).filter(
        BidSubmission.tender_id == tender.id).order_by(BidSubmission.id).all()
    assert len(bids) == 3
    return tender, {b.bidder.legal_name: b for b in bids}


def test_t4_seeds_three_bidders_with_one_dossier_each(db):
    tender, bids = _seed_t4(db)
    assert len(_BIDDERS_T4) == 3
    for name, bid in bids.items():
        docs = db.query(Document).filter(
            Document.bid_id == bid.id).all()
        assert len(docs) == 1, f"{name}: expected one dossier, got {len(docs)}"
        assert docs[0].document_type == "BID_DOSSIER"


def test_t4_banner_rendered_in_dossier_pdf():
    for spec in _BIDDERS_T4:
        doc = _t4_dossier(spec)
        assert len(doc) == 5  # banner slot
        _, _fn, legal_name, sections, banner = doc
        assert banner == BANNER
        pdf = generate_dossier_pdf(legal_name, sections, banner=banner)
        text = "\n".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))
        assert "SYNTHETIC DEMO DATA" in text


def test_t4_expected_compliance_outcomes(db):
    _tender, bids = _seed_t4(db)
    expected = {
        "Apex MediSupply Pvt Ltd": ("PROCEED", 100.0, "LOW"),
        "BrightCare Traders Pvt Ltd": ("REVIEW_REQUIRED", 70.0, "MEDIUM"),
        "CareWell Enterprises Pvt Ltd": ("NOT_RECOMMENDED", 0.0, "CRITICAL"),
    }
    for name, (rec, score, risk) in expected.items():
        bid = bids[name]
        assert bid.recommendation == rec, name
        assert bid.compliance_score == score, name
        assert bid.risk_level == risk, name


def test_t4_bidder_b_gst_name_mismatch_flagged(db):
    _tender, bids = _seed_t4(db)
    bid = bids["BrightCare Traders Pvt Ltd"]
    rows = db.query(ComplianceResult).filter(
        ComplianceResult.bid_id == bid.id).all()
    gst = next(r for r in rows
               if "GST Registration" in r.requirement.requirement_name)
    assert gst.status == "MISMATCH"
    assert bid.risk_reasons and "mismatch" in " ".join(bid.risk_reasons).lower()


def test_t4_bidder_c_blacklist_fail(db):
    _tender, bids = _seed_t4(db)
    bid = bids["CareWell Enterprises Pvt Ltd"]
    rows = db.query(ComplianceResult).filter(
        ComplianceResult.bid_id == bid.id).all()
    blk = next(r for r in rows
               if "Blacklisting" in r.requirement.requirement_name)
    assert blk.status == "FAIL"


def test_t4_seed_idempotent(db):
    users = _seed_users(db)
    admin_id = users["officer@demo.cpcl.in"].id
    first = seed_gem_demo_tender(db, admin_id)
    assert first["skipped"] is False
    second = seed_gem_demo_tender(db, admin_id)
    assert second["skipped"] is True
    tender = db.query(Tender).filter(
        Tender.tender_number == T4_NUMBER).one()
    assert db.query(BidSubmission).filter(
        BidSubmission.tender_id == tender.id).count() == 3


def test_run_seed_backfills_t4_on_legacy_database(db):
    """Regression: databases seeded before GEM-DEMO-2026-101 existed must get
    it on the next run_seed (the old startup guard seeded only empty DBs, so
    the new tender never appeared on existing installs)."""
    users = _seed_users(db)
    legacy = Tender(tender_number="CPCL-DEMO-2026-001", title="legacy tender",
                    organization="CPCL", department="Materials")
    db.add(legacy)
    db.commit()

    result = run_seed(db)

    assert result["skipped"] is True  # legacy block untouched
    assert result["gem_demo"]["skipped"] is False
    t4 = db.query(Tender).filter(Tender.tender_number == T4_NUMBER).one()
    assert db.query(BidSubmission).filter(
        BidSubmission.tender_id == t4.id).count() == 3
    assert db.query(Tender).filter(
        Tender.tender_number == "CPCL-DEMO-2026-001").count() == 1


def test_no_real_reference_identifiers_leak():
    forbidden = [
        "GEM/2025/B/6364645", "GEM/2026/B/7489269",
        "AAFCA1234E", "27AAFCA1234E1Z5",
        "BBMWB5678F", "27BBMWB5678F1Z5",
        "UDYAM-MH-19-0012345",
    ]
    haystack = " ".join(
        [str(_tender4_requirements())] +
        [str(_t4_dossier(spec)) for spec in _BIDDERS_T4])
    for ident in forbidden:
        assert ident not in haystack, f"real identifier leaked: {ident}"
