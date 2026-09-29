"""Tests for the risk engine (CONTRACT §8) — independent of the score."""
from app.engines import risk_engine


def _res(name, status, mandatory=True, rule_type="MINIMUM", vsrc=None,
         low_confidence=False):
    return {"requirement_name": name, "status": status, "mandatory": mandatory,
            "rule_type": rule_type, "verification_source": vsrc,
            "explanation": f"{status} on {name}", "confidence": 0.95,
            "low_confidence": low_confidence, "weight": 10}


def _ctx(**kw):
    base = {"verification": {}, "bidder": {}, "extracted": {}}
    base.update(kw)
    return base


def test_blacklist_critical_despite_high_score():
    # Seed scenario D: debarred -> CRITICAL regardless of compliance score.
    ctx = _ctx(verification={"BLACKLIST": {
        "data": {"blacklisted": False, "debarred": True,
                 "authority": "CPCL", "reason": "fraud", "period": "2024-2027"}}})
    out = risk_engine.assess(ctx, [], None)
    assert out["risk_level"] == "CRITICAL"
    assert any(s["code"] == "DEBARRED" and s["severity"] == "critical"
               for s in out["signals"])


def test_blacklisted_also_critical():
    ctx = _ctx(verification={"BLACKLIST": {
        "data": {"blacklisted": True, "debarred": False,
                 "authority": "GeM", "reason": "x", "period": "y"}}})
    assert risk_engine.assess(ctx, [], None)["risk_level"] == "CRITICAL"


def test_mismatch_weights_reach_high():
    results = [_res("GST Registration", "MISMATCH", vsrc="GSTN",
                    rule_type="REGISTRATION_STATUS"),
               _res("PAN Verification", "MISMATCH", vsrc="PAN_IT",
                    rule_type="REGISTRATION_STATUS")]
    out = risk_engine.assess(_ctx(), results, None)
    codes = {s["code"] for s in out["signals"]}
    assert {"GST_NAME_MISMATCH", "PAN_MISMATCH"} <= codes
    assert out["risk_level"] == "HIGH"  # 40 + 40 = 80 >= 50


def test_level_thresholds():
    # 15 -> LOW
    out = risk_engine.assess(
        _ctx(), [_res("ESIC Registration", "REVIEW_REQUIRED",
                      rule_type="REGISTRATION_STATUS", vsrc="ESIC")], None)
    assert out["risk_level"] == "LOW"
    # 15 + 10 = 25 -> MEDIUM
    out = risk_engine.assess(
        _ctx(), [_res("ESIC Registration", "REVIEW_REQUIRED",
                      rule_type="REGISTRATION_STATUS", vsrc="ESIC"),
                 _res("Turnover", "PASS", low_confidence=True)], None)
    assert out["risk_level"] == "MEDIUM"
    # 40 + 10 = 50 -> HIGH
    out = risk_engine.assess(
        _ctx(), [_res("GST Registration", "MISMATCH", vsrc="GSTN",
                      rule_type="REGISTRATION_STATUS"),
                 _res("Turnover", "PASS", low_confidence=True)], None)
    assert out["risk_level"] == "HIGH"


def test_missing_mandatory_doc_capped():
    # 3 x 30 = 90, capped at 60 -> HIGH (not 90).
    results = [_res(f"Doc req {i}", "MISSING", rule_type="DOCUMENT_REQUIRED")
               for i in range(3)]
    out = risk_engine.assess(_ctx(), results, None)
    assert out["risk_level"] == "HIGH"
    assert out["risk_score"] == 60.0


def test_no_signals_low():
    out = risk_engine.assess(_ctx(), [_res("GST Registration", "PASS")], None)
    assert out["risk_level"] == "LOW"
    assert out["risk_reasons"] == ["No risk signals detected."]


def test_unverified_source_medium_signal():
    out = risk_engine.assess(
        _ctx(), [_res("ESIC Registration", "REVIEW_REQUIRED",
                      rule_type="REGISTRATION_STATUS", vsrc="ESIC")], None)
    assert any(s["code"] == "UNVERIFIED_SOURCE" for s in out["signals"])
