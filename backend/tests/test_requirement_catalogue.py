"""Contract tests: the frontend requirement catalogue vs the backend engine.

``frontend/src/lib/requirement-catalogue.json`` is the single authoritative
source of requirement templates consumed by both the Create Tender wizard and
the TenderWizard dialog. These tests prevent frontend/backend configuration
drift:

1. Every catalogue entry's ``rule_config`` satisfies the deterministic rules
   engine's structural contract (required keys per rule type, valid
   value_source prefixes, known verification sources, safe expressions).
2. The demo default template's weights total exactly 100.
3. Every default-template requirement evaluates through the REAL
   ``RulesEngine`` without crashing (smoke test on an empty context).
4. The catalogue's BLACKLIST expression never fabricates a clean chit.
5. ``infer_requirement_metadata`` (backend keyword inference used by
   analyze-draft / manual rows / LLM suggestions) produces the same
   rule_type + rule_config shapes as the catalogue for equivalent names.
"""
import json
from pathlib import Path

import pytest

from app.engines.rules_engine import RulesEngine

ENGINE = RulesEngine()

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_PATH = REPO_ROOT / "frontend" / "src" / "lib" / "requirement-catalogue.json"

KNOWN_RULE_TYPES = {
    "EXISTENCE", "DOCUMENT_REQUIRED", "EQUALITY", "MATCH", "MINIMUM",
    "MAXIMUM", "DATE_VALIDITY", "DATE_RANGE", "CONTAINS", "BOOLEAN",
    "REGISTRATION_STATUS", "IDENTITY_MATCH", "CUSTOM_RULE",
}
KNOWN_STATUSES = {
    "PASS", "FAIL", "MISSING", "REVIEW_REQUIRED", "EXPIRED", "MISMATCH",
}
KNOWN_SOURCES = {
    "GSTN", "PAN_IT", "UDYAM", "MCA21", "EPFO", "ESIC", "STARTUP_INDIA",
    "NSIC", "DIGILOCKER", "BLACKLIST",
}
KNOWN_CATEGORIES = {
    "STATUTORY", "FINANCIAL", "EXPERIENCE", "TECHNICAL", "REGISTRATION",
    "LOCAL_CONTENT", "OEM", "INTEGRITY", "DOCUMENT",
}
REQUIRED_CONFIG_KEYS = {
    "EXISTENCE": ["value_source"],
    "DOCUMENT_REQUIRED": ["document_types"],
    "EQUALITY": ["value_source", "expected"],
    "MATCH": ["value_source", "pattern"],
    "MINIMUM": ["value_source", "operator", "value"],
    "MAXIMUM": ["value_source", "operator", "value"],
    "DATE_VALIDITY": ["value_source"],
    "DATE_RANGE": ["value_source"],
    "CONTAINS": ["value_source", "substring"],
    "BOOLEAN": ["value_source", "expected"],
    "REGISTRATION_STATUS": ["source", "identifier_field", "require_status"],
    "IDENTITY_MATCH": [],
    "CUSTOM_RULE": ["expression"],
}
VALUE_SOURCE_PREFIXES = ("extracted.", "bidder.", "verification.")


@pytest.fixture(scope="module")
def catalogue():
    assert CATALOGUE_PATH.exists(), f"catalogue not found at {CATALOGUE_PATH}"
    data = json.loads(CATALOGUE_PATH.read_text())
    assert data["entries"], "catalogue has no entries"
    return data


def _req(entry, idx=1):
    return {"id": idx, "requirement_name": entry["requirement_name"],
            "rule_type": entry["rule_type"],
            "rule_config": entry["rule_config"],
            "weight": entry.get("default_weight", 0),
            "mandatory": entry.get("default_mandatory", True),
            "verification_source": entry.get("verification_source")}


def _ctx(**kw):
    base = {"bidder": {}, "extracted": {}, "extracted_confidence": {},
            "extracted_by_doc": {}, "evidence_index": {}, "documents": [],
            "document_index": {}, "verification": {}, "today": "2026-09-26"}
    base.update(kw)
    return base


# ------------------------------------------------- structural contract
def test_every_entry_structurally_valid(catalogue):
    problems = []
    for e in catalogue["entries"]:
        key = e.get("key", "?")
        rt = e.get("rule_type")
        if rt not in KNOWN_RULE_TYPES:
            problems.append(f"{key}: unknown rule_type {rt!r}")
            continue
        cfg = e.get("rule_config") or {}
        for k in REQUIRED_CONFIG_KEYS[rt]:
            if cfg.get(k) in (None, "", []):
                problems.append(f"{key}: {rt} missing rule_config.{k}")
        vs = cfg.get("value_source")
        if isinstance(vs, str) and vs and not vs.startswith(VALUE_SOURCE_PREFIXES):
            problems.append(f"{key}: bad value_source prefix {vs!r}")
        src = e.get("verification_source")
        if src is not None and src not in KNOWN_SOURCES:
            problems.append(f"{key}: unknown verification_source {src!r}")
        if e.get("category") not in KNOWN_CATEGORIES:
            problems.append(f"{key}: unknown category {e.get('category')!r}")
        if e.get("applicability") not in ("REQUIRED", "CONDITIONAL", "OPTIONAL"):
            problems.append(f"{key}: bad applicability {e.get('applicability')!r}")
        if not isinstance(e.get("default_weight"), (int, float)) or e["default_weight"] < 0:
            problems.append(f"{key}: bad default_weight {e.get('default_weight')!r}")
        dt = cfg.get("document_types")
        if dt is not None and (not isinstance(dt, list) or not dt):
            problems.append(f"{key}: document_types must be a non-empty list")
        expr = cfg.get("expression")
        if isinstance(expr, str):
            for bad in ("import ", "exec(", "eval(", "open(", "__"):
                if bad in expr:
                    problems.append(f"{key}: expression contains {bad!r}")
    assert not problems, "catalogue contract violations:\n" + "\n".join(problems)


def test_default_template_weights_total_100(catalogue):
    total = sum(e["default_weight"] for e in catalogue["entries"]
                if e.get("in_default_template"))
    assert round(total, 2) == 100.0, f"default template weights total {total}, want 100"
    assert any(e.get("in_default_template") for e in catalogue["entries"])


def test_default_template_has_sane_mandatory_mix(catalogue):
    default = [e for e in catalogue["entries"] if e.get("in_default_template")]
    assert any(e["default_mandatory"] for e in default), "no mandatory requirements"
    assert any(not e["default_mandatory"] for e in default), "no non-mandatory requirements"


# ------------------------------------------------- engine smoke test
def test_every_default_requirement_evaluates_without_crash(catalogue):
    """Each default-template requirement runs through the REAL engine on an
    empty context and yields a known status (no crash, no unknown status)."""
    default = [e for e in catalogue["entries"] if e.get("in_default_template")]
    assert default
    bad = []
    for i, e in enumerate(default):
        try:
            result = ENGINE.evaluate(_req(e, i), _ctx())
        except Exception as exc:  # noqa: BLE001 — the point is "never crashes"
            bad.append(f"{e['key']}: raised {exc!r}")
            continue
        if result["status"] not in KNOWN_STATUSES:
            bad.append(f"{e['key']}: unknown status {result['status']!r}")
    assert not bad, "engine smoke failures:\n" + "\n".join(bad)


# ------------------------------------------------- blacklist honesty
def test_catalogue_blacklist_expression_never_fabricates(catalogue):
    entry = next(e for e in catalogue["entries"] if e["key"] == "non_debarment")
    assert entry["rule_type"] == "CUSTOM_RULE"
    req = _req(entry)
    assert ENGINE.evaluate(req, _ctx())["status"] == "REVIEW_REQUIRED"
    flagged = _ctx(verification={"BLACKLIST": {"status": "VERIFIED",
                                              "data": {"blacklisted": True}}})
    assert ENGINE.evaluate(req, flagged)["status"] == "FAIL"
    clean = _ctx(verification={"BLACKLIST": {"status": "VERIFIED",
                                             "data": {"blacklisted": False}}})
    assert ENGINE.evaluate(req, clean)["status"] == "PASS"


# ------------------------------------------------- inference parity
@pytest.mark.parametrize("name,threshold,expected_key", [
    ("GST Registration", None, "gst_registration"),
    ("PAN Verification", None, "pan_verification"),
    ("Udyam Registration", None, "udyam_registration"),
    ("EPFO Registration", None, "epfo_registration"),
    ("ESIC Registration", None, "esic_registration"),
    ("Balance Sheet FY 2023-24", "Rs 1.5 crore", "balance_sheet"),
    ("Work Experience Certificate", None, "work_experience"),
    ("ISO 9001 Certificate", None, "iso_9001"),
    ("Income Tax Return FY 2023-24", None, "itr_document"),
    ("Earnest Money Deposit Receipt", "Rs 5,00,000", "emd_receipt"),
    ("Company Incorporation CIN", None, "mca21_certificate"),
    ("NSIC Registration", None, "nsic_registration"),
    ("Blacklisting / Debarment Check", None, "non_debarment"),
    ("Startup India", None, "startup_india"),
    ("Average Annual Turnover", "Rs 1.5 crore", "turnover"),
    ("Make in India Local Content", "50%", "mii_local_content"),
])
def test_inference_matches_catalogue_shapes(catalogue, name, threshold, expected_key):
    """Backend keyword inference must produce the same rule_type and the same
    rule_config keys as the catalogue entry for the equivalent requirement."""
    from app.services.tender_intel_service import infer_requirement_metadata

    entry = next(e for e in catalogue["entries"] if e["key"] == expected_key)
    inferred = infer_requirement_metadata(name, threshold)
    assert inferred["rule_type"] == entry["rule_type"], (
        f"{name!r}: inference={inferred['rule_type']} catalogue={entry['rule_type']}")
    for k in REQUIRED_CONFIG_KEYS[entry["rule_type"]]:
        assert k in inferred["rule_config"], (
            f"{name!r}: inference rule_config missing {k!r}")
    # identifier/source agreement for registration rules
    if entry["rule_type"] == "REGISTRATION_STATUS":
        assert inferred["rule_config"]["source"] == entry["rule_config"]["source"]
        assert (inferred["rule_config"]["identifier_field"]
                == entry["rule_config"]["identifier_field"])


def test_inference_blacklist_is_honest():
    from app.services.tender_intel_service import infer_requirement_metadata

    req = _req({"requirement_name": "x",
                "rule_type": "CUSTOM_RULE",
                "rule_config": infer_requirement_metadata(
                    "Blacklisting / Debarment Check")["rule_config"]})
    assert ENGINE.evaluate(req, _ctx())["status"] == "REVIEW_REQUIRED"
