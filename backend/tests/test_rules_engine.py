"""Tests for the rules engine — the ONLY decider of PASS/FAIL (CONTRACT §6).

All 13 rule types are exercised against hand-built contexts (no seed data).
"""
from app.engines.rules_engine import RulesEngine

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


# ------------------------------------------------------------------ EXISTENCE
def test_existence_pass_and_missing():
    req = _req("EXISTENCE", {"value_source": "extracted.gstin"})
    assert ENGINE.evaluate(req, _ctx(extracted={"gstin": "27AAFCA1234E1Z5"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx())["status"] == "MISSING"


# ---------------------------------------------------------- DOCUMENT_REQUIRED
def test_document_required():
    req = _req("DOCUMENT_REQUIRED", {"document_types": ["OEM_AUTHORIZATION"]})
    assert ENGINE.evaluate(req, _ctx(documents=["OEM_AUTHORIZATION"]))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(documents=["PAN_CERTIFICATE"]))["status"] == "MISSING"


# ------------------------------------------------------------------ EQUALITY
def test_equality_case_insensitive():
    req = _req("EQUALITY", {"value_source": "extracted.trade_name", "expected": "apex"})
    assert ENGINE.evaluate(req, _ctx(extracted={"trade_name": "Apex"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"trade_name": "Other"}))["status"] == "FAIL"


# --------------------------------------------------------------------- MATCH
def test_match_regex():
    req = _req("MATCH", {"value_source": "extracted.pan",
                         "pattern": r"^[A-Z]{5}[0-9]{4}[A-Z]$"})
    assert ENGINE.evaluate(req, _ctx(extracted={"pan": "AAFCA1234E"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"pan": "BAD"}))["status"] == "FAIL"


# ------------------------------------------------------------ MINIMUM/MAXIMUM
def test_minimum():
    req = _req("MINIMUM", {"value_source": "extracted.turnover_inr",
                           "operator": ">=", "value": 100000000})
    assert ENGINE.evaluate(req, _ctx(extracted={"turnover_inr": "124000000"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"turnover_inr": "82000000"}))["status"] == "FAIL"
    assert ENGINE.evaluate(req, _ctx())["status"] == "MISSING"


def test_maximum():
    req = _req("MAXIMUM", {"value_source": "extracted.deviation_pct",
                           "operator": "<=", "value": 50})
    assert ENGINE.evaluate(req, _ctx(extracted={"deviation_pct": "40"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"deviation_pct": "60"}))["status"] == "FAIL"


# ------------------------------------------------------------- DATE_VALIDITY
def test_date_validity():
    req = _req("DATE_VALIDITY", {"value_source": "extracted.valid_until",
                                 "must_be_after": "today"})
    assert ENGINE.evaluate(req, _ctx(extracted={"valid_until": "2027-12-31"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"valid_until": "2024-03-31"}))["status"] == "EXPIRED"
    assert ENGINE.evaluate(req, _ctx())["status"] == "MISSING"


# ---------------------------------------------------------------- DATE_RANGE
def test_date_range():
    req = _req("DATE_RANGE", {"value_source": "extracted.incorporation_date",
                              "min": "2000-01-01", "max": "2026-01-01"})
    assert ENGINE.evaluate(req, _ctx(extracted={"incorporation_date": "2015-03-12"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"incorporation_date": "1990-01-01"}))["status"] == "FAIL"


# ------------------------------------------------------------------ CONTAINS
def test_contains():
    req = _req("CONTAINS", {"value_source": "extracted.address", "substring": "Mumbai"})
    assert ENGINE.evaluate(req, _ctx(extracted={"address": "Andheri, Mumbai"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"address": "Pune"}))["status"] == "FAIL"


# ------------------------------------------------------------------ BOOLEAN
def test_boolean():
    req = _req("BOOLEAN", {"value_source": "extracted.oem_authorization_valid",
                           "expected": True})
    assert ENGINE.evaluate(req, _ctx(extracted={"oem_authorization_valid": "True"}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"oem_authorization_valid": "False"}))["status"] == "FAIL"


# ------------------------------------------------------- REGISTRATION_STATUS
def _reg_req(**overrides):
    config = {"source": "ESIC", "identifier_field": "esic_code",
              "require_status": "ACTIVE"}
    config.update(overrides)
    return _req("REGISTRATION_STATUS", config)


def _ver(status, data_status="ACTIVE"):
    return {"ESIC": {"status": status,
                     "data": {"status": data_status, "identifier": "X"},
                     "confidence": 0.9, "check_id": 7}}


def test_registration_status_verified_active():
    assert ENGINE.evaluate(_reg_req(), _ctx(verification=_ver("VERIFIED")))["status"] == "PASS"


def test_registration_status_unavailable_never_pass_fail():
    # UNAVAILABLE -> REVIEW_REQUIRED (never a silent PASS/FAIL).
    out = ENGINE.evaluate(_reg_req(), _ctx(verification=_ver("UNAVAILABLE")))
    assert out["status"] == "REVIEW_REQUIRED"


def test_registration_status_not_found_defaults_fail():
    out = ENGINE.evaluate(_reg_req(), _ctx(verification=_ver("NOT_FOUND")))
    assert out["status"] == "FAIL"


def test_registration_status_not_found_override():
    out = ENGINE.evaluate(_reg_req(not_found_status="REVIEW_REQUIRED"),
                          _ctx(verification=_ver("NOT_FOUND")))
    assert out["status"] == "REVIEW_REQUIRED"


def test_registration_status_mismatch_and_expired():
    assert ENGINE.evaluate(_reg_req(), _ctx(verification=_ver("MISMATCH")))["status"] == "MISMATCH"
    assert ENGINE.evaluate(_reg_req(), _ctx(verification=_ver("EXPIRED")))["status"] == "EXPIRED"


# ------------------------------------------------------------ IDENTITY_MATCH
def test_identity_match_pass():
    req = _req("IDENTITY_MATCH", {"fields": ["legal_name"]})
    ctx = _ctx(bidder={"legal_name": "Apex Flow Systems Pvt Ltd"},
               extracted_by_doc={"PAN_CERTIFICATE":
                                 {"legal_name": "Apex Flow Systems Private Limited"}})
    assert ENGINE.evaluate(req, ctx)["status"] == "PASS"


def test_identity_match_mismatch():
    req = _req("IDENTITY_MATCH", {"fields": ["legal_name"]})
    ctx = _ctx(bidder={"legal_name": "Crestline Pumps Pvt Ltd"},
               extracted_by_doc={"GST_CERTIFICATE":
                                 {"legal_name": "Crestline Trading Co"}})
    assert ENGINE.evaluate(req, ctx)["status"] == "MISMATCH"


# --------------------------------------------------------------- CUSTOM_RULE
def test_custom_rule_bool_outcomes():
    assert ENGINE.evaluate(_req("CUSTOM_RULE", {"expression": "True"}),
                           _ctx())["status"] == "PASS"
    assert ENGINE.evaluate(_req("CUSTOM_RULE", {"expression": "False"}),
                           _ctx())["status"] == "FAIL"


def test_custom_rule_status_string():
    out = ENGINE.evaluate(_req("CUSTOM_RULE", {"expression": "'REVIEW_REQUIRED'"}),
                          _ctx())
    assert out["status"] == "REVIEW_REQUIRED"


def test_custom_rule_error_becomes_review():
    out = ENGINE.evaluate(_req("CUSTOM_RULE", {"expression": "1/0"}), _ctx())
    assert out["status"] == "REVIEW_REQUIRED"


def test_custom_rule_over_context():
    expr = "ctx['extracted'].get('turnover_inr', 0) >= 100"
    req = _req("CUSTOM_RULE", {"expression": expr})
    assert ENGINE.evaluate(req, _ctx(extracted={"turnover_inr": 150}))["status"] == "PASS"
    assert ENGINE.evaluate(req, _ctx(extracted={"turnover_inr": 50}))["status"] == "FAIL"


# ---------------------------------------------------------- confidence rule
def test_low_confidence_pass_downgraded():
    req = _req("MINIMUM", {"value_source": "extracted.turnover_inr",
                           "operator": ">=", "value": 100000000})
    ctx = _ctx(
        extracted={"turnover_inr": "124000000"},
        evidence_index={"turnover_inr": [
            {"field": "turnover_inr", "value": "124000000",
             "confidence": 0.62, "document_id": 1, "filename": "t.pdf"}]},
    )
    out = ENGINE.evaluate(req, ctx)
    assert out["status"] == "REVIEW_REQUIRED"
    assert out["low_confidence"] is True
    assert "Low extraction confidence" in out["explanation"]


def test_fail_stands_despite_low_confidence():
    # FAIL/MISSING are never "silent AI decisions" -> they stand as computed.
    req = _req("MINIMUM", {"value_source": "extracted.turnover_inr",
                           "operator": ">=", "value": 100000000})
    ctx = _ctx(
        extracted={"turnover_inr": "82000000"},
        evidence_index={"turnover_inr": [
            {"field": "turnover_inr", "value": "82000000",
             "confidence": 0.5, "document_id": 1}]},
    )
    assert ENGINE.evaluate(req, ctx)["status"] == "FAIL"
