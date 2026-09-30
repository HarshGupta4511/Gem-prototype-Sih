"""Tests for the 3-step New Tender wizard flow.

Covers: atomic tender+requirements creation, the new Step-1 procurement fields,
weight validation (non-negative, total exactly 100), the analyze-draft endpoint
(Step 2, no tender id needed), the additive column migration for pre-wizard
databases, and proof that the compliance engine scores with the FINAL saved
weights (not the auto-generated ones).
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, text

import app.api.tenders as tenders_mod
from app.engines.rules_engine import RulesEngine
from app.models.models import Tender, TenderRequirement, User
from app.schemas.schemas import TenderAnalyzeRequest, TenderCreate
from app.services.scoring_service import compute_score

ENGINE = RulesEngine()


def _officer() -> User:
    return User(name="Officer", email="officer@test.local", password_hash="x",
                role="PROCUREMENT_OFFICER")


def _req(name, weight, rule_type="EXISTENCE", category="DOCUMENT", **kw):
    d = {
        "requirement_name": name,
        "category": category,
        "mandatory": True,
        "rule_type": rule_type,
        "rule_config": {"value_source": "extracted.gstin"},
        "threshold": "present",
        "weight": weight,
    }
    d.update(kw)
    return d


def _payload(**kw):
    d = {
        "tender_number": "WIZ/2026/001",
        "title": "Wizard Test Tender",
        "organization": "CPCL",
        "department": "Materials",
        "description": "Supply of valves. Bidder must have GST registration and PAN.",
        "issue_date": "2026-09-01",
        "closing_date": "2026-10-01",
        "estimated_value_inr": 5000000,
        "tender_type": "GOODS",
        "bid_type": "TWO_PACKET",
        "emd_amount_inr": 50000,
        "delivery_period": "60 days",
        "place_of_delivery": "Chennai",
    }
    d.update(kw)
    return TenderCreate(**d)


# ------------------------------------------------- atomic create + new fields
def test_wizard_creates_tender_and_requirements_atomically(db):
    payload = _payload(requirements=[
        _req("GST Registration", 60.0, rule_type="EXISTENCE",
             rule_config={"value_source": "extracted.gstin"}),
        _req("PAN Verification", 40.0, rule_type="EXISTENCE",
             rule_config={"value_source": "extracted.pan"}),
    ])
    out = tenders_mod.create_tender(payload=payload, db=db, user=_officer())

    tender = db.query(Tender).filter(Tender.tender_number == "WIZ/2026/001").one()
    assert out.id == tender.id
    assert tender.tender_type == "GOODS"
    assert tender.bid_type == "TWO_PACKET"
    assert tender.emd_amount_inr == 50000
    assert tender.delivery_period == "60 days"
    assert tender.place_of_delivery == "Chennai"

    rows = (db.query(TenderRequirement)
            .filter(TenderRequirement.tender_id == tender.id)
            .order_by(TenderRequirement.id).all())
    assert [r.requirement_name for r in rows] == ["GST Registration", "PAN Verification"]
    assert [r.weight for r in rows] == [60.0, 40.0]
    assert sum(r.weight for r in rows) == 100.0
    assert rows[0].mandatory is True
    assert rows[0].threshold == "present"


def test_wizard_create_without_requirements_still_works(db):
    out = tenders_mod.create_tender(payload=_payload(), db=db, user=_officer())
    tender = db.get(Tender, out.id)
    assert tender is not None
    assert tender.tender_type == "GOODS"
    assert db.query(TenderRequirement).filter(
        TenderRequirement.tender_id == tender.id).count() == 0


def test_wizard_duplicate_tender_number_rejected(db):
    tenders_mod.create_tender(payload=_payload(), db=db, user=_officer())
    with pytest.raises(HTTPException) as exc:
        tenders_mod.create_tender(payload=_payload(), db=db, user=_officer())
    assert exc.value.status_code == 409


# ---------------------------------------------------------------- validation
def test_wizard_rejects_total_weight_not_100(db):
    payload = _payload(requirements=[_req("A", 60.0), _req("B", 30.0)])  # 90
    with pytest.raises(HTTPException) as exc:
        tenders_mod.create_tender(payload=payload, db=db, user=_officer())
    assert exc.value.status_code == 422
    assert "must equal 100" in exc.value.detail
    # atomic: nothing persisted
    assert db.query(Tender).filter(Tender.tender_number == "WIZ/2026/001").count() == 0


def test_wizard_rejects_negative_weight(db):
    payload = _payload(requirements=[_req("A", 120.0), _req("B", -20.0)])
    with pytest.raises(HTTPException) as exc:
        tenders_mod.create_tender(payload=payload, db=db, user=_officer())
    assert exc.value.status_code == 422
    assert "non-negative" in exc.value.detail


def test_wizard_rejects_invalid_tender_type(db):
    with pytest.raises(Exception):  # pydantic Literal validation
        _payload(tender_type="INVALID")


# ------------------------------------------------------------- analyze-draft
def test_analyze_draft_needs_no_tender(db):
    resp = tenders_mod.analyze_draft(
        payload=TenderAnalyzeRequest(
            tender_text="Bidder must have GST registration and PAN. "
                        "Minimum turnover of Rs 50 lakh required."),
        user=_officer(),
    )
    names = [r.requirement_name for r in resp.requirements]
    assert "GST Registration" in names
    assert "PAN Verification" in names
    # drafts only — nothing persisted
    assert db.query(Tender).count() == 0
    assert db.query(TenderRequirement).count() == 0


# --------------------------------- compliance engine uses the FINAL weights
def test_compliance_scores_use_final_saved_weights(db):
    """The rules engine + scorer must consume the officer-approved weights
    persisted by the wizard, not the auto-generated drafts."""
    payload = _payload(requirements=[
        _req("GST Registration", 70.0, rule_type="EXISTENCE",
             rule_config={"value_source": "extracted.gstin"}),
        _req("PAN Verification", 30.0, rule_type="EXISTENCE",
             rule_config={"value_source": "extracted.pan"}),
    ])
    out = tenders_mod.create_tender(payload=payload, db=db, user=_officer())

    persisted = (db.query(TenderRequirement)
                 .filter(TenderRequirement.tender_id == out.id)
                 .order_by(TenderRequirement.id).all())
    # GST present (PASS), PAN missing (MISSING)
    ctx = {"bidder": {}, "extracted": {"gstin": "27AAFCA1234E1Z5"},
           "extracted_confidence": {}, "extracted_by_doc": {},
           "evidence_index": {}, "documents": [], "document_index": {},
           "verification": {}, "today": "2026-09-28"}
    results = [ENGINE.evaluate(r, ctx) for r in persisted]
    assert {r["weight"] for r in results} == {70.0, 30.0}
    score, _ = compute_score(results)
    assert score == 70.0  # only the 70-weight requirement passed


# ------------------------------------------- additive migration for old DBs
def test_wizard_column_migration_backfills_legacy_db(tmp_path):
    """A database created before the wizard (no new columns) gains them via
    _ensure_tender_wizard_columns without losing data."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.base import Base

    db_file = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # simulate a pre-wizard database
        for col in ("tender_type", "bid_type", "emd_amount_inr",
                    "delivery_period", "place_of_delivery"):
            conn.execute(text(f"ALTER TABLE tenders DROP COLUMN {col}"))
        conn.execute(text(
            "INSERT INTO tenders (tender_number, title, organization, department, status, created_at) "
            "VALUES ('OLD/1', 'Old Tender', 'CPCL', 'Materials', 'DRAFT', '2026-01-01 00:00:00')"))

    # run the migration against the legacy file
    import app.main as main_mod
    real_engine = main_mod.engine
    main_mod.engine = engine
    try:
        main_mod._ensure_tender_wizard_columns()
        main_mod._ensure_tender_wizard_columns()  # idempotent
    finally:
        main_mod.engine = real_engine

    cols = {c["name"] for c in inspect(engine).get_columns("tenders")}
    for col in ("tender_type", "bid_type", "emd_amount_inr",
                "delivery_period", "place_of_delivery"):
        assert col in cols
    session = sessionmaker(bind=engine)()
    try:
        tender = session.query(Tender).filter(
            Tender.tender_number == "OLD/1").one()
        assert tender.title == "Old Tender"  # data preserved
        assert tender.tender_type is None    # new columns nullable
    finally:
        session.close()
        engine.dispose()


# ------------------------------------------------- internal-field inference
from app.services.tender_intel_service import infer_requirement_metadata


def test_infer_gst_registration():
    m = infer_requirement_metadata("GST Registration", "Active")
    assert m["rule_type"] == "REGISTRATION_STATUS"
    assert m["verification_source"] == "GSTN"
    assert m["category"] == "STATUTORY"
    assert m["rule_config"]["source"] == "GSTN"
    assert m["rule_config"]["identifier_field"] == "gstin"


def test_infer_pan_verification():
    m = infer_requirement_metadata("PAN Verification", "Active PAN")
    assert m["rule_type"] == "REGISTRATION_STATUS"
    assert m["verification_source"] == "PAN_IT"
    assert m["rule_config"]["identifier_field"] == "pan"


def test_infer_turnover_parses_threshold():
    m = infer_requirement_metadata("Minimum Turnover", "₹25,00,000")
    assert m["rule_type"] == "MINIMUM"
    assert m["verification_source"] is None  # checked against bidder documents
    assert m["category"] == "FINANCIAL"
    assert m["rule_config"]["value_source"] == "extracted.turnover_inr"
    assert m["rule_config"]["operator"] == ">="
    assert m["rule_config"]["value"] == 2500000


def test_infer_experience_years():
    m = infer_requirement_metadata("Experience", "2 years")
    assert m["rule_type"] == "MINIMUM"
    assert m["rule_config"]["value_source"] == "extracted.experience_years"
    assert m["rule_config"]["value"] == 2.0


def test_infer_oem_is_boolean():
    m = infer_requirement_metadata("OEM Authorization", "Valid")
    assert m["rule_type"] == "BOOLEAN"
    assert m["rule_config"]["value_source"] == "extracted.oem_authorization_valid"
    assert m["rule_config"]["expected"] is True


def test_infer_mii_local_content():
    m = infer_requirement_metadata("MII / Local Content", "50%")
    assert m["rule_type"] == "MINIMUM"
    assert m["rule_config"]["value_source"] == "extracted.local_content_pct"
    assert m["rule_config"]["value"] == 50.0


def test_infer_required_documents():
    m = infer_requirement_metadata("Required Documents", "Submitted")
    assert m["rule_type"] == "DOCUMENT_REQUIRED"
    assert m["rule_config"]["document_types"] == ["BID_DOSSIER"]


def test_infer_blacklist_check():
    m = infer_requirement_metadata("Blacklisting / Debarment Check", "Not blacklisted")
    assert m["rule_type"] == "CUSTOM_RULE"
    assert m["verification_source"] == "BLACKLIST"
    assert m["category"] == "INTEGRITY"


def test_infer_unknown_name_safe_default():
    m = infer_requirement_metadata("Some Random Thing", "whatever")
    assert m["rule_type"] == "EXISTENCE"
    assert m["verification_source"] is None
    assert m["rule_config"] == {}


def test_infer_unparseable_minimum_threshold_falls_back_safe():
    # No number in the threshold: must NOT produce a MINIMUM without a value
    # (the engine would crash on float(None)); safe EXISTENCE instead.
    m = infer_requirement_metadata("Minimum Turnover", "as per NIT")
    assert m["rule_type"] == "EXISTENCE"
    assert m["rule_config"] == {}


def test_create_applies_inference_to_manual_requirements(db):
    """A manually typed requirement (no rule_config) gets internal fields
    inferred at save time; the compliance engine can then evaluate it."""
    payload = _payload(requirements=[
        _req("GST Registration", 60.0, rule_type="EXISTENCE", rule_config={},
             threshold="Active"),
        _req("Minimum Turnover", 40.0, rule_type="EXISTENCE", rule_config={},
             threshold="₹25,00,000"),
    ])
    tenders_mod.create_tender(payload=payload, db=db, user=_officer())
    tender = db.query(Tender).filter(
        Tender.tender_number == "WIZ/2026/001").one()
    rows = (db.query(TenderRequirement)
            .filter(TenderRequirement.tender_id == tender.id)
            .order_by(TenderRequirement.id).all())
    assert rows[0].rule_type == "REGISTRATION_STATUS"
    assert rows[0].verification_source == "GSTN"
    assert rows[0].category == "STATUTORY"
    assert rows[0].rule_config["identifier_field"] == "gstin"
    assert rows[1].rule_type == "MINIMUM"
    assert rows[1].rule_config["value"] == 2500000

    # The inferred requirement must evaluate through the real rules engine.
    res = ENGINE.evaluate(rows[0], {"verification": {"GSTN": {"data": {"status": "ACTIVE"}}},
                                      "documents": [], "extracted": {}})
    assert res["status"] in ("PASS", "REVIEW_REQUIRED", "MISSING")


def test_create_keeps_explicit_rule_config(db):
    """Requirements that already carry a rule_config (analyze-draft output,
    standard template) are stored exactly as supplied — no inference."""
    payload = _payload(requirements=[
        _req("Custom Check", 100.0, rule_type="BOOLEAN", category="TECHNICAL",
             rule_config={"value_source": "extracted.custom_flag", "expected": True}),
    ])
    tenders_mod.create_tender(payload=payload, db=db, user=_officer())
    tender = db.query(Tender).filter(
        Tender.tender_number == "WIZ/2026/001").one()
    row = (db.query(TenderRequirement)
           .filter(TenderRequirement.tender_id == tender.id).one())
    assert row.rule_type == "BOOLEAN"
    assert row.category == "TECHNICAL"
    assert row.rule_config == {"value_source": "extracted.custom_flag",
                               "expected": True}


# ------------------------------------------------- issue date + AI suggest
def test_issue_date_uses_server_date_not_client_supplied(db):
    """The backend ignores any client-supplied issue_date: issue_date is
    always the server-side creation date."""
    payload = _payload(issue_date="2020-01-15")  # client tries a past date
    out = tenders_mod.create_tender(payload=payload, db=db, user=_officer())
    tender = db.get(Tender, out.id)
    from datetime import date as _date
    assert tender.issue_date == _date.today()
    assert str(tender.issue_date) != "2020-01-15"


def test_closing_date_must_be_after_issue_date(db):
    """closing_date <= issue_date is rejected with 422 (issue_date = today)."""
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    with pytest.raises(HTTPException) as exc:
        tenders_mod.create_tender(
            payload=_payload(tender_number="WIZ/2026/010",
                             closing_date=today.isoformat()),
            db=db, user=_officer())
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc2:
        tenders_mod.create_tender(
            payload=_payload(tender_number="WIZ/2026/011",
                             closing_date=(today - _td(days=1)).isoformat()),
            db=db, user=_officer())
    assert exc2.value.status_code == 422
    # future closing date is fine
    out = tenders_mod.create_tender(
        payload=_payload(tender_number="WIZ/2026/012",
                         closing_date=(today + _td(days=30)).isoformat()),
        db=db, user=_officer())
    assert db.get(Tender, out.id).closing_date == today + _td(days=30)


def test_suggest_requirements_mock_provider_returns_503(db, monkeypatch):
    """With no real LLM configured the endpoint says so honestly (503),
    instead of fabricating 'AI' suggestions."""
    from app.schemas.schemas import SuggestRequirementsRequest
    from app.services import llm_service
    # suggest_requirements() imports get_llm_provider from llm_service at call
    # time, so patching the source module attribute is enough.
    monkeypatch.setattr(llm_service, "get_llm_provider",
                        lambda: llm_service.MockLLMProvider())
    with pytest.raises(HTTPException) as exc:
        tenders_mod.suggest_requirements(
            payload=SuggestRequirementsRequest(
                title="Supply of Industrial Electrical Equipment",
                description="LT panels and cabling for plant upgrade.",
                department="Electrical"),
            user=_officer())
    assert exc.value.status_code == 503


def test_suggest_requirements_parses_llm_json(monkeypatch):
    """The provider parses the LLM's JSON into clean suggestion dicts."""
    from app.services import llm_service

    canned = {"choices": [{"message": {"content": (
        '{"requirements": ['
        '{"requirement_name": "GST Registration", "threshold": "", '
        '"mandatory": true, "weight": 15, "description": "Valid GSTIN required."},'
        '{"requirement_name": "Minimum Turnover", "threshold": "Minimum Rs 50 lakh", '
        '"mandatory": true, "weight": "bad-number", "description": ""},'
        '{"threshold": "no name here"}'
        ']}'
    )}}]}
    provider = llm_service.GeminiProvider(model="test-model", api_key="test-key")
    monkeypatch.setattr(provider, "_post_with_retry", lambda req, timeout=90: canned)
    out = provider.suggest_requirements({"title": "Supply of Electrical Equipment"})
    assert len(out) == 2
    assert out[0]["requirement_name"] == "GST Registration"
    assert out[0]["mandatory"] is True
    assert out[1]["weight"] == 0  # unparseable weight -> safe 0, officer fixes it
    assert out[1]["threshold"] == "Minimum Rs 50 lakh"


def test_parse_threshold_plain_number_no_crash():
    """Regression: a plain-number threshold (e.g. '15000') must not raise
    IndexError — the fallback regex has no capture groups."""
    from app.services.tender_intel_service import _parse_threshold_number
    assert _parse_threshold_number("15000") == 15000.0
    assert _parse_threshold_number("15,000") == 15000.0
    assert _parse_threshold_number("28.5") == 28.5
    assert _parse_threshold_number("") is None
    assert _parse_threshold_number(None) is None
    assert _parse_threshold_number("not a number") is None
    assert _parse_threshold_number("₹25,00,000") == 2500000
    assert _parse_threshold_number("2 years") == 2.0
    assert _parse_threshold_number("50%") == 50.0


def test_wizard_create_with_plain_number_threshold(db):
    """End-to-end: tender creation with a manually typed plain-number
    threshold must succeed, not 500 (IndexError regression)."""
    from datetime import date
    from app.schemas.schemas import TenderCreate
    officer = _officer()
    db.add(officer)
    db.commit()
    payload = TenderCreate(
        tender_number="THR-001",
        title="Threshold Test",
        organization="CPCL",
        department="Proc",
        description="d",
        closing_date=date(2026, 12, 31),
        estimated_value_inr=100000,
        requirements=[
            {"requirement_name": "EMD Amount", "category": "FINANCIAL",
             "description": "d", "mandatory": True, "rule_type": "MINIMUM",
             "rule_config": {}, "threshold": "15000",
             "verification_source": None, "weight": 100},
        ],
    )
    out = tenders_mod.create_tender(payload, db, officer)
    assert out.tender_number == "THR-001"
    req = db.query(TenderRequirement).filter_by(tender_id=out.id).one()
    assert req.rule_type == "MINIMUM"
    assert req.rule_config["value"] == 15000.0
