"""Unit tests for the mismatch-focused demo scenario generator.

Covers: scenario catalogue validity, seeded reproducibility (same triple ->
same dataset), seed sensitivity, fixture idempotency, and honest bounds
(identifiers are fictional-format, never real).
"""
import json
import re

import pytest

from app.seed import demo_scenarios as ds

MOCK = ds.MOCK_DATA_DIR


def test_scenario_catalogue_is_valid():
    assert len(ds.SCENARIO_IDS) >= 10
    for sid, meta in ds.SCENARIOS.items():
        assert meta["title"], sid
        assert meta["description"], sid


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        ds.plan_scenario("apex", "nope", 1, "Apex Flow Systems Pvt. Ltd.")


def test_plan_is_reproducible():
    a = ds.plan_scenario("apex", "gst_name_mismatch", 42, "Apex Flow Systems Pvt. Ltd.")
    b = ds.plan_scenario("apex", "gst_name_mismatch", 42, "Apex Flow Systems Pvt. Ltd.")
    assert a.identifiers == b.identifiers
    assert a.doc_mutations == b.doc_mutations
    assert a.fixture_mutations == b.fixture_mutations


def test_plan_is_seed_sensitive():
    a = ds.plan_scenario("apex", "clean", 42, "Apex Flow Systems Pvt. Ltd.")
    b = ds.plan_scenario("apex", "clean", 43, "Apex Flow Systems Pvt. Ltd.")
    assert a.identifiers != b.identifiers


def test_plan_is_scenario_sensitive():
    a = ds.plan_scenario("apex", "clean", 42, "Apex Flow Systems Pvt. Ltd.")
    b = ds.plan_scenario("apex", "debarred", 42, "Apex Flow Systems Pvt. Ltd.")
    # Mutations differ per scenario; the (identity, scenario, seed) triple
    # stays reproducible either way.
    assert b.blacklist_record is not None
    assert a.blacklist_record is None
    b2 = ds.plan_scenario("apex", "debarred", 42, "Apex Flow Systems Pvt. Ltd.")
    assert b2.blacklist_record == b.blacklist_record
    assert b2.identifiers == b.identifiers


def test_identifiers_are_fictional_format():
    p = ds.plan_scenario("nova", "clean", 7, "Nova Engineering Works Pvt. Ltd.")
    ids = p.identifiers
    assert re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", ids["pan"])
    assert re.fullmatch(r"27[A-Z]{5}[0-9]{4}[A-Z]1Z5", ids["gstin"])
    assert ids["udyam"].startswith("UDYAM-MH-")
    assert re.fullmatch(r"U[0-9]{5}MH[0-9]{4}PTC[0-9]{6}", ids["cin"])


def test_none_seed_picks_fresh_seed():
    a = ds.plan_scenario("apex", "clean", None, "Apex Flow Systems Pvt. Ltd.")
    b = ds.plan_scenario("apex", "clean", None, "Apex Flow Systems Pvt. Ltd.")
    assert isinstance(a.seed, int)
    # Replaying the returned seed reproduces the dataset.
    c = ds.plan_scenario("apex", "clean", a.seed, "Apex Flow Systems Pvt. Ltd.")
    assert c.identifiers == a.identifiers


def test_fixtures_are_idempotent_and_additive(tmp_path):
    p = ds.plan_scenario("apex", "gst_status_conflict", 99, "Apex Flow Systems Pvt. Ltd.")
    before = json.loads((MOCK / "gstn.json").read_text())
    n_before = len(before)
    added1 = ds.ensure_scenario_fixtures(p)
    added2 = ds.ensure_scenario_fixtures(p)
    after = json.loads((MOCK / "gstn.json").read_text())
    assert added2 == 0, "second run must add nothing"
    assert len(after) >= n_before  # additive only
    # The conflict mutation landed on the scenario's own record.
    rec = after[p.identifiers["gstin"]]
    assert rec["status"] == "INACTIVE"
    assert rec["legal_name"] == "Apex Flow Systems Pvt. Ltd."
    # Pre-existing records untouched.
    assert before["27AAFCA1234E1Z5"] == after["27AAFCA1234E1Z5"]


def test_debarred_appends_blacklist_record_once():
    p = ds.plan_scenario("primetech", "debarred", 5, "PrimeTech Industrial Systems Pvt. Ltd.")
    ds.ensure_scenario_fixtures(p)
    data = json.loads((MOCK / "blacklist.json").read_text())
    matches = [r for r in data if r.get("company_name") == "PrimeTech Industrial Systems Pvt. Ltd."]
    assert len(matches) == 1
    assert matches[0]["blacklisted"] is True
    ds.ensure_scenario_fixtures(p)
    data2 = json.loads((MOCK / "blacklist.json").read_text())
    assert len([r for r in data2 if r.get("company_name") == "PrimeTech Industrial Systems Pvt. Ltd."]) == 1


def test_missing_evidence_omits_templates():
    p = ds.plan_scenario("vertex", "missing_evidence", 3, "Vertex Industrial Solutions Pvt. Ltd.")
    assert "GST_CERTIFICATE" in p.omit_templates
    assert "BALANCE_SHEET" not in p.omit_templates
    assert "EXPERIENCE_CERTIFICATE" not in p.omit_templates


def test_classic_mapping_covers_legacy_profiles():
    for key in ("apex", "vertex", "nova", "primetech"):
        assert ds.CLASSIC_SCENARIO[key] in ds.SCENARIOS
