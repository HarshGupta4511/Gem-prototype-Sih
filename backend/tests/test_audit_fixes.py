"""Regression tests for the 2026-10-04 end-to-end audit fixes.

Covers: MockLLM boolean negation handling, the BLACKLIST custom rule
no-fabrication fix, per-source adapter failure isolation in
run_verification, and REVIEW_REQUIRED (not MISSING) for value rules that
read from an UNAVAILABLE verification source.
"""
from app.engines.rules_engine import RulesEngine
from app.models.models import Bidder, BidSubmission, Tender, VerificationCheck

ENGINE = RulesEngine()


def _req(rule_type, config, weight=10.0, mandatory=True, name="Req"):
    return {"id": 1, "requirement_name": name, "rule_type": rule_type,
            "rule_config": config, "weight": weight, "mandatory": mandatory,
            "verification_source": config.get("source")}


def _ctx(**kw):
    base = {"bidder": {}, "extracted": {}, "extracted_confidence": {},
            "extracted_by_doc": {}, "evidence_index": {}, "documents": [],
            "document_index": {}, "verification": {}, "today": "2026-09-26"}
    base.update(kw)
    return base


# ------------------------------------------------- MockLLM boolean negation
def test_mock_llm_bool_denied_authorization_is_false():
    """'OEM Authorization: Invalid' must not extract as authorized.

    The old substring check matched 'valid' inside 'Invalid' → True,
    which fed the mandatory OEM BOOLEAN rule a false PASS.
    """
    from app.services.llm_service import MockLLMProvider

    text = "OEM Authorization: Invalid\n"
    got = MockLLMProvider().extract_fields("OEM_AUTHORIZATION", text, "x.pdf")
    assert got["oem_authorization_valid"] is False


def test_mock_llm_bool_variants():
    from app.services.llm_service import MockLLMProvider

    def val(raw):
        t = f"OEM Authorization: {raw}\n"
        return MockLLMProvider().extract_fields("OEM_AUTHORIZATION", t, "x.pdf").get(
            "oem_authorization_valid")

    assert val("Yes, authorized") is True
    assert val("Valid") is True
    assert val("Not valid") is False
    assert val("Not authorized") is False
    assert val("Denied") is False
    assert val("Pending review") is None


# --------------------------------------- BLACKLIST custom rule honesty
def _blacklist_req():
    # mirrors the expression built by tender_intel_service for blacklist/debar
    return _req("CUSTOM_RULE", {
        "expression": "('REVIEW_REQUIRED' if ctx.get('verification', {}).get('BLACKLIST') is None "
                      "else ('FAIL' if ctx['verification']['BLACKLIST'].get('data', {})"
                      ".get('blacklisted', False) else 'PASS'))",
    }, name="Blacklist")


def test_blacklist_rule_no_check_is_review_required_not_pass():
    """A bidder that was never blacklist-checked must not PASS the rule."""
    assert ENGINE.evaluate(_blacklist_req(), _ctx())["status"] == "REVIEW_REQUIRED"


def test_blacklist_rule_flagged_is_fail_and_clean_is_pass():
    flagged = _ctx(verification={"BLACKLIST": {"status": "VERIFIED",
                                              "data": {"blacklisted": True}}})
    clean = _ctx(verification={"BLACKLIST": {"status": "VERIFIED",
                                             "data": {"blacklisted": False}}})
    assert ENGINE.evaluate(_blacklist_req(), flagged)["status"] == "FAIL"
    assert ENGINE.evaluate(_blacklist_req(), clean)["status"] == "PASS"


# --------------------------------- adapter failure isolation (UNAVAILABLE)
def test_verification_run_isolates_adapter_failure(db):
    """One exploding adapter → UNAVAILABLE row for that source, others persist."""
    from app.services import verification_service
    from app.adapters import registry as reg

    tender = Tender(tender_number="AUD-001", title="Audit", organization="CPCL",
                    department="P", status="OPEN")
    db.add(tender)
    db.flush()
    bidder = Bidder(tender_id=tender.id, legal_name="Audit Bidder Pvt. Ltd.",
                    gstin="27AAFCA1234E1Z5")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id, status="SUBMITTED")
    db.add(bid)
    db.commit()

    real_get = reg.get_adapter

    class _Boom:
        def verify(self, identifier):
            raise RuntimeError("simulated adapter outage")

    def _patched(source):
        return _Boom() if source == "GSTN" else real_get(source)

    import unittest.mock as mock
    with mock.patch.object(verification_service, "get_adapter", _patched):
        verification_service.run_verification(db, bid.id)
    db.commit()

    rows = {c.source: c for c in
            db.query(VerificationCheck).filter_by(bid_id=bid.id).all()}
    assert rows["GSTN"].verification_status == "UNAVAILABLE"
    assert "simulated adapter outage" in (rows["GSTN"].response_payload or {}).get("error", "")
    # the rest of the run still persisted (BLACKLIST always resolves a name)
    assert rows["BLACKLIST"].verification_status == "VERIFIED"
    assert all(r.is_mock for r in rows.values())


# ------------------------- value rules must not collapse outage → MISSING
def test_value_rule_on_unavailable_source_is_review_required():
    """EXISTENCE over verification.PAN_IT.itr_filed_upto with an UNAVAILABLE
    PAN_IT check must yield REVIEW_REQUIRED, not MISSING."""
    req = _req("EXISTENCE", {"value_source": "verification.PAN_IT.itr_filed_upto"})
    ctx = _ctx(verification={"PAN_IT": {"status": "UNAVAILABLE", "data": {},
                                        "confidence": 0.0, "check_id": 7}})
    result = ENGINE.evaluate(req, ctx)
    assert result["status"] == "REVIEW_REQUIRED"
    assert "UNAVAILABLE" in result["explanation"]


def test_value_rule_still_missing_when_no_check_ran():
    """No check at all → still MISSING (unchanged behavior)."""
    req = _req("EXISTENCE", {"value_source": "verification.PAN_IT.itr_filed_upto"})
    assert ENGINE.evaluate(req, _ctx())["status"] == "MISSING"
