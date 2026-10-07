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


def test_blacklist_high_despite_high_score():
    # Seed scenario D: debarred -> HIGH regardless of compliance score.
    # Serious risk is never suppressed by a high score.
    ctx = _ctx(verification={"BLACKLIST": {
        "data": {"blacklisted": False, "debarred": True,
                 "authority": "CPCL", "reason": "fraud", "period": "2024-2027"}}})
    out = risk_engine.assess(ctx, [], None)
    assert out["risk_level"] == "HIGH"
    assert any(s["code"] == "DEBARRED" and s["severity"] == "critical"
               for s in out["signals"])


def test_blacklisted_also_high():
    ctx = _ctx(verification={"BLACKLIST": {
        "data": {"blacklisted": True, "debarred": False,
                 "authority": "GeM", "reason": "x", "period": "y"}}})
    assert risk_engine.assess(ctx, [], None)["risk_level"] == "HIGH"


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
    # A medium-severity signal (unverified source) is moderate risk -> MEDIUM.
    out = risk_engine.assess(
        _ctx(), [_res("ESIC Registration", "REVIEW_REQUIRED",
                      rule_type="REGISTRATION_STATUS", vsrc="ESIC")], None)
    assert out["risk_level"] == "MEDIUM"
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


def test_integrity_review_required_forces_high():
    # A review-grade integrity pattern is a serious risk indicator even
    # with a perfect compliance record.
    sigs = [{"signal_type": "RECURRING_BIDDER_COHORT",
             "severity": "REVIEW_REQUIRED", "title": "cohort"}]
    out = risk_engine.assess(
        _ctx(), [_res("GST Registration", "PASS")], None,
        integrity_signals=sigs)
    assert out["risk_level"] == "HIGH"
    assert any(s["code"] == "INTEGRITY_REVIEW_REQUIRED" for s in out["signals"])


def test_integrity_elevated_is_medium():
    sigs = [{"signal_type": "REPEATED_PARTICIPATION",
             "severity": "ELEVATED", "title": "repeat"}]
    out = risk_engine.assess(
        _ctx(), [_res("GST Registration", "PASS")], None,
        integrity_signals=sigs)
    assert out["risk_level"] == "MEDIUM"


def test_mandatory_fail_forces_high():
    out = risk_engine.assess(
        _ctx(), [_res("GST Registration", "FAIL", rule_type="MINIMUM")], None)
    assert out["risk_level"] == "HIGH"


def test_ambiguous_compliance_is_at_least_medium():
    # A MISMATCH with no dedicated identity signal is still ambiguous.
    out = risk_engine.assess(
        _ctx(), [_res("Turnover", "MISMATCH", rule_type="MINIMUM")], None)
    assert out["risk_level"] == "MEDIUM"


def test_only_low_medium_high_levels():
    # The engine never emits CRITICAL or any other level, across a range
    # of inputs.
    cases = [
        (_ctx(), [], None, None),
        (_ctx(verification={"BLACKLIST": {
            "data": {"blacklisted": True, "authority": "GeM",
                     "reason": "x", "period": "y"}}}), [], None, None),
        (_ctx(), [_res("GST Registration", "MISMATCH", vsrc="GSTN",
                       rule_type="REGISTRATION_STATUS")], None, None),
        (_ctx(), [_res("GST Registration", "PASS")], None,
         [{"signal_type": "X", "severity": "REVIEW_REQUIRED", "title": "t"}]),
    ]
    for ctx, results, ver, sigs in cases:
        assert risk_engine.assess(ctx, results, ver,
                                  integrity_signals=sigs)["risk_level"] in (
            "LOW", "MEDIUM", "HIGH")
