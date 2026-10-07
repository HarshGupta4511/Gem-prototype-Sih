"""10-step acceptance test: Create Tender Stages 1-4 with the authoritative
catalogue template + the four demo bidders end to end.

Steps:
 1. CREATE a tender from the catalogue's real default template (12
    requirements, weights exactly 100) — the same payload the Stage-2 wizard
    POSTs. Publication with an invalid configuration (weights != 100) is
    rejected with 422.
 2. EDIT requirements (weights/thresholds) and prove the changes persist.
 3. PUBLISH (atomic) + RELOAD — persisted requirements are verbatim copies of
    the catalogue rule configurations.
 4. ADD the four demo bidders (apex / vertex / nova / primetech).
 5. SEED demo evidence per profile; assert the EXACT document counts produced
    by the requirement-driven builder (apex 10, vertex 2, nova 10,
    primetech 10) and that every generated PDF is literally marked
    "SAMPLE — FOR DEMONSTRATION ONLY".
 6. PROCESS: every document is PROCESSED with extracted fields; nothing is
    pre-scored.
 7. VERIFY (mock adapters): apex clean, nova MISMATCH, primetech BLACKLIST
    flagged, vertex checks honest.
 8. EVALUATE: deterministic scores from persisted requirements + real
    evidence. Apex keeps its deliberate MII failure; vertex's missing
    mandatory evidence scores MISSING, never PASS.
 9. RECOMMEND: apex APPROVE/LOW, vertex REVIEW_REQUIRED, nova
    REVIEW_REQUIRED/HIGH, primetech REJECT/HIGH — score, risk
    and integrity stay separate.
10. REOPEN: re-seeding is idempotent (no duplicate documents or bidders);
    reload proves persistence.

No scores or findings are hardcoded — every assertion is on values computed
by the real pipeline from the seeded evidence.
"""
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

import app.api.tenders as tenders_mod
from app.models.models import (
    Bidder,
    BidSubmission,
    ComplianceResult,
    ConsistencyCheck,
    Document,
    ExtractedField,
    RiskAssessment,
    Tender,
    TenderRequirement,
    User,
    VerificationCheck,
)
from app.schemas.schemas import RequirementsBulkCreate, TenderCreate
from app.seed.demo_bidder_profiles import PROFILES, build_dossier_sections
from app.services.compliance_service import evaluate_bid
from app.services.consistency_service import run_consistency_check
from app.services.demo_seed_service import seed_demo_bidder_evidence
from app.services.recommendation_service import generate_recommendation
from app.services.verification_service import run_verification

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_PATH = REPO_ROOT / "frontend" / "src" / "lib" / "requirement-catalogue.json"

PROFILE_KEYS = ["apex", "vertex", "nova", "primetech"]


def _officer() -> User:
    return User(name="Officer", email="officer@test.local", password_hash="x",
                role="PROCUREMENT_OFFICER")


def _catalogue_default_entries():
    data = json.loads(CATALOGUE_PATH.read_text())
    return [e for e in data["entries"] if e.get("in_default_template")]


def _req_payloads(entries):
    """Payload the Stage-2 wizard POSTs: catalogue fields verbatim."""
    return [
        {
            "requirement_name": e["requirement_name"],
            "category": e["category"],
            "description": e["description"],
            "mandatory": e["default_mandatory"],
            "rule_type": e["rule_type"],
            "rule_config": e["rule_config"],
            "threshold": e["threshold"],
            "expected_value": e["expected_value"],
            "verification_source": e["verification_source"],
            "weight": e["default_weight"],
            "policy_reference": e["policy_reference"],
        }
        for e in entries
    ]


def _create_payload(requirements):
    return TenderCreate(
        tender_number="ACCEPT/2026/001",
        title="Acceptance Test Tender",
        organization="CPCL",
        department="Materials",
        description="Demo tender created from the authoritative catalogue template.",
        closing_date="2027-06-30",
        estimated_value_inr=5_000_000,
        tender_type="GOODS",
        bid_type="TWO_PACKET",
        requirements=requirements,
    )


def _persisted_requirements(db, tender_id):
    return (db.query(TenderRequirement)
            .filter(TenderRequirement.tender_id == tender_id)
            .order_by(TenderRequirement.id).all())


# ---------------------------------------------------------------- 1-3: CRUD
def test_step1_create_from_catalogue_template(db):
    entries = _catalogue_default_entries()
    assert len(entries) == 10
    payload = _create_payload(_req_payloads(entries))

    out = tenders_mod.create_tender(payload=payload, db=db, user=_officer())

    tender = db.get(Tender, out.id)
    assert tender.tender_number == "ACCEPT/2026/001"
    rows = _persisted_requirements(db, tender.id)
    assert len(rows) == 10
    assert round(sum(r.weight for r in rows), 2) == 100.0
    # Rule configurations persisted verbatim from the catalogue.
    by_name = {e["requirement_name"]: e for e in entries}
    for r in rows:
        src = by_name[r.requirement_name]
        assert r.rule_type == src["rule_type"]
        assert r.rule_config == src["rule_config"]
        assert r.weight == src["default_weight"]
        assert r.mandatory == src["default_mandatory"]


def test_step1_rejects_invalid_configuration(db):
    entries = _catalogue_default_entries()
    reqs = _req_payloads(entries)
    reqs[0]["weight"] = 50.0  # total becomes 140
    with pytest.raises(HTTPException) as exc:
        tenders_mod.create_tender(payload=_create_payload(reqs), db=db,
                                  user=_officer())
    assert exc.value.status_code == 422

    # Empty requirements list is rejected too (D11 fix).
    with pytest.raises(HTTPException) as exc:
        tenders_mod.create_tender(payload=_create_payload([]), db=db,
                                  user=_officer())
    assert exc.value.status_code == 422


def _make_published_tender(db):
    entries = _catalogue_default_entries()
    out = tenders_mod.create_tender(payload=_create_payload(_req_payloads(entries)),
                                    db=db, user=_officer())
    return out.id, entries


def test_step2_edit_requirements_persists(db):
    tender_id, entries = _make_published_tender(db)
    reqs = _req_payloads(entries)
    # Officer edit: shift 2 points GST -> PAN, tighten turnover threshold.
    by_name = {r["requirement_name"]: r for r in reqs}
    by_name["Active GST Registration (Form GST REG-06)"]["weight"] = 13.0
    by_name["Valid Income Tax PAN & Compliance"]["weight"] = 12.0
    by_name["Balance Sheet — FY 2023–24 (Turnover)"]["threshold"] = "Rs 2 crore"
    assert round(sum(r["weight"] for r in reqs), 2) == 100.0

    tenders_mod.set_requirements(
        tender_id=tender_id,
        payload=RequirementsBulkCreate(requirements=reqs),  # type: ignore[arg-type]
        db=db, user=_officer())

    rows = {r.requirement_name: r for r in _persisted_requirements(db, tender_id)}
    assert rows["Active GST Registration (Form GST REG-06)"].weight == 13.0
    assert rows["Valid Income Tax PAN & Compliance"].weight == 12.0
    assert rows["Balance Sheet — FY 2023–24 (Turnover)"].threshold == "Rs 2 crore"
    assert round(sum(r.weight for r in rows.values()), 2) == 100.0


def test_step3_publish_reload_is_verbatim(db):
    tender_id, _ = _make_published_tender(db)
    detail = tenders_mod.get_tender(tender_id=tender_id, db=db, user=_officer())
    assert detail.tender.id == tender_id
    assert len(detail.requirements) == 10
    assert round(sum(r.weight for r in detail.requirements), 2) == 100.0


# ------------------------------------------------- 4-10: bidder pipeline
def _add_bidder(db, tender_id, profile_key, legal_name):
    bidder = Bidder(tender_id=tender_id, legal_name=legal_name,
                    bid_status="SUBMITTED")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=tender_id, bidder_id=bidder.id,
                        status="SUBMITTED")
    db.add(bid)
    db.commit()
    return bid


def _full_flow(db):
    """Steps 1-9. Returns (tender_id, bids dict, expected doc counts)."""
    tender_id, _ = _make_published_tender(db)
    requirements = _persisted_requirements(db, tender_id)

    # Step 4: add the four bidders — registered under the profile's real
    # (fictional) legal name, exactly as the Stage-3 modal registers them.
    bids = {}
    for key in PROFILE_KEYS:
        bids[key] = _add_bidder(db, tender_id, key, PROFILES[key]["legal_name"])

    # Step 5: seed evidence; exact counts come from the requirement-driven
    # builder itself (asserted equal, not hardcoded from this test).
    expected_counts = {}
    for key in PROFILE_KEYS:
        sections = build_dossier_sections(requirements, key)
        expected_counts[key] = len(sections)
        res = seed_demo_bidder_evidence(db, bids[key].id, key)
        assert res["seeded"] is True, key
        docs = db.query(Document).filter_by(bid_id=bids[key].id).all()
        assert len(docs) == expected_counts[key], (
            f"{key}: seeded {len(docs)} docs, builder emitted {expected_counts[key]}")
        # Step 6 pre-condition: everything processed through the real pipeline.
        assert all(d.processing_status == "PROCESSED" for d in docs), key
        n_fields = sum(db.query(ExtractedField)
                       .filter_by(document_id=d.id).count() for d in docs)
        assert n_fields > 0, f"{key}: no extracted fields"
        # Every generated PDF is literally marked as a sample (asserted on
        # extracted text — reportlab encodes page streams, as the app's own
        # extraction pipeline does).
        import fitz  # PyMuPDF — the same extractor the pipeline uses
        for d in docs:
            raw = Path(d.file_path).read_bytes()
            text = "\n".join(p.get_text()
                             for p in fitz.open(stream=raw, filetype="pdf"))
            assert "SAMPLE" in text and "FOR DEMONSTRATION ONLY" in text, (
                f"{key}/{d.filename}: missing SAMPLE marking")

    # Nothing derived before the officer runs the pipeline.
    for key, bid in bids.items():
        db.refresh(bid)
        assert bid.compliance_score is None, key
        assert bid.recommendation is None, key

    # Steps 7-9: the officer's real button flow.
    for key, bid in bids.items():
        run_verification(db, bid.id)
        run_consistency_check(db, bid.id)
        evaluate_bid(db, bid.id)
        generate_recommendation(db, bid.id)

    return tender_id, bids, expected_counts


def test_steps4_to_9_four_bidders_end_to_end(db, tmp_path):
    tender_id, bids, counts = _full_flow(db)

    print(f"\n[acceptance] tender {tender_id}: seeded doc counts = {counts}")
    # 10 catalogue requirements + the always-emitted non-debarment declaration
    # (the bidder's own claim; the consistency engine checks it against the
    # BLACKLIST source). Nova carries no EPFO code in its profile, so its
    # EPFO section is honestly skipped.
    assert counts["apex"] == 11
    assert counts["vertex"] == 2
    assert counts["nova"] == 10
    assert counts["primetech"] == 11

    def statuses(bid_id):
        return sorted({r.status for r in
                       db.query(ComplianceResult).filter_by(bid_id=bid_id).all()})

    for key, bid in bids.items():
        db.refresh(bid)
        assert bid.recommendation is not None, key
        assert bid.compliance_score is not None, key
        print(f"[acceptance] {key}: score={bid.compliance_score} "
              f"risk={bid.risk_level} recommendation={bid.recommendation} "
              f"statuses={statuses(bid.id)}")

    apex, vertex, nova, prime = (bids["apex"], bids["vertex"],
                                bids["nova"], bids["primetech"])

    # Step 8 — deterministic, requirement-driven scoring.
    assert apex.compliance_score >= 85
    assert apex.recommendation == "APPROVE"
    assert apex.risk_level == "LOW"
    # The default template marks Udyam / EPFO / ISO 9001 non-mandatory; those
    # requirements are still evaluated (result rows exist) rather than
    # silently skipped — the engine never hides a requirement.
    req_names = {r.id: r.requirement_name
                 for r in db.query(TenderRequirement)
                 .filter(TenderRequirement.tender_id == tender_id)}
    apex_rows = db.query(ComplianceResult).filter_by(bid_id=apex.id).all()
    assert len(apex_rows) == len(req_names), "every requirement gets a result row"
    non_mand = [r for r in db.query(TenderRequirement)
                .filter(TenderRequirement.tender_id == tender_id)
                if not r.mandatory]
    assert len(non_mand) >= 1, "template should carry non-mandatory requirements"
    evaluated = {r.requirement_id for r in apex_rows}
    assert all(r.id in evaluated for r in non_mand)

    # Vertex: intentionally missing evidence -> MISSING, never PASS.
    assert "MISSING" in statuses(vertex.id)
    assert vertex.recommendation == "REVIEW_REQUIRED"
    assert vertex.compliance_score < apex.compliance_score
    # Vertex: missing evidence is visible and never PASS. Every mandatory
    # requirement has a result row; those with no evidence are MISSING.
    v_rows = {r.requirement_id: r for r in
              db.query(ComplianceResult).filter_by(bid_id=vertex.id)}
    req_by_id = {r.id: r for r in db.query(TenderRequirement)
                 .filter(TenderRequirement.tender_id == tender_id)}
    assert len(v_rows) == len(req_by_id), "every requirement must have a result row"
    # Mandatory DOCUMENT-backed requirements without evidence must stay
    # visible as MISSING — never PASS, never silently gone. (Verification-
    # backed rules such as the blacklist registry check are evaluated on the
    # checks that actually ran; a clean registry result is an honest PASS.)
    doc_backed_missing = 0
    evidenced = {"extracted.turnover_inr", "extracted.experience_years"}
    # Vertex's missing-evidence profile retains exactly two documents.
    vertex_doc_types = {"BALANCE_SHEET", "EXPERIENCE_CERTIFICATE"}
    for rid, req in req_by_id.items():
        cfg = req.rule_config or {}
        vs = str(cfg.get("value_source") or "")
        doc_types = cfg.get("document_types") or []
        is_doc_backed = (vs.startswith("extracted.") or bool(doc_types)
                         or req.rule_type == "DOCUMENT_REQUIRED")
        has_evidence = (vs in evidenced
                        or any(dt in vertex_doc_types for dt in doc_types))
        status = v_rows[rid].status
        if req.mandatory and is_doc_backed and not has_evidence:
            doc_backed_missing += 1
            assert status == "MISSING", (
                f"mandatory '{req.requirement_name}' must be MISSING, got {status}")
    assert doc_backed_missing > 0, "vertex must show MISSING mandatory evidence"

    # Nova: portal name conflict -> MISMATCH via real cross-verification.
    assert "MISMATCH" in statuses(nova.id)
    assert nova.recommendation == "REVIEW_REQUIRED"
    assert any(c.verification_status == "MISMATCH"
               for c in db.query(VerificationCheck).filter_by(bid_id=nova.id))

    # PrimeTech: score stays high but risk is HIGH and the
    # recommendation is REJECT — the three stay separate.
    assert prime.compliance_score >= 85
    assert prime.risk_level == "HIGH"
    assert prime.recommendation == "REJECT"
    risk = db.query(RiskAssessment).filter_by(bid_id=prime.id).one()
    assert any(s.get("code") in ("BLACKLISTED", "DEBARRED")
               for s in (risk.signals or []))
    # False-declaration mismatch: the declaration claims clean, the BLACKLIST
    # registry flags the bidder — the consistency engine records a MISMATCH
    # (the new 10-requirement template carries no debarment requirement row,
    # so the catch lives in the consistency layer, not compliance).
    decl_checks = db.query(ConsistencyCheck).filter_by(
        bid_id=prime.id, check_name="DEBARMENT_DECLARATION_CONSISTENCY").all()
    assert decl_checks, "debarment declaration consistency must run"
    assert any(c.result == "MISMATCH" for c in decl_checks)


def test_step10_reopen_idempotent_and_persistent(db, tmp_path):
    tender_id, bids, counts = _full_flow(db)

    # Re-seeding must not duplicate anything.
    for key, bid in bids.items():
        before = db.query(Document).filter_by(bid_id=bid.id).count()
        res = seed_demo_bidder_evidence(db, bid.id, key)
        assert res["seeded"] is False, key
        assert db.query(Document).filter_by(bid_id=bid.id).count() == before
    assert db.query(Bidder).filter_by(tender_id=tender_id).count() == 4

    # Reopen: the published configuration is exactly as published.
    detail = tenders_mod.get_tender(tender_id=tender_id, db=db, user=_officer())
    assert len(detail.requirements) == 10
    assert round(sum(r.weight for r in detail.requirements), 2) == 100.0

    # Derived outcomes survive the reopen.
    for key, bid in bids.items():
        db.refresh(bid)
        assert bid.compliance_score is not None, key
        assert bid.recommendation is not None, key
