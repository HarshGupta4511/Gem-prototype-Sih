"""Verifier -> Procurement Officer report workflow.

Flow: verifier adds observation -> generates report -> sends to officer ->
officer acknowledges receipt (RECEIVED) -> officer opens (UNDER_REVIEW) ->
officer decides (DECISION).
Asserts:
- lifecycle derives from audit events only (no schema changes),
- guards enforce the order (409 on out-of-order transitions),
- the report content reflects real stored evidence (documents, extracted
  fields, verification checks, compliance results, risk, stored AI rec),
- inbox shows NEW until the officer opens the report,
- every transition appends a hash-chained audit event.
"""
import pytest
from fastapi import HTTPException

import app.api.verifier_reports as reports_mod
from app.models.models import (
    AuditLog,
    Bidder,
    BidStatus,
    BidSubmission,
    ComplianceResult,
    Document,
    ExtractedField,
    RiskAssessment,
    Tender,
    TenderRequirement,
    User,
    VerificationCheck,
)
from app.services import verifier_report_service


def _setup(db):
    officer = User(
        name="Officer", email="officer-rep@example.com", password_hash="x",
        role="PROCUREMENT_OFFICER",
    )
    verifier = User(
        name="Verifier", email="verifier-rep@example.com", password_hash="x",
        role="VERIFIER",
    )
    db.add_all([officer, verifier])
    db.flush()

    tender = Tender(
        tender_number="T-REP-1", title="Report test", organization="CPCL",
        department="Purchase",
    )
    db.add(tender)
    db.flush()
    req = TenderRequirement(
        tender_id=tender.id, requirement_name="GST Registration",
        category="REGISTRATION", rule_type="DOCUMENT_REQUIRED",
        weight=50.0, mandatory=True,
    )
    db.add(req)
    db.flush()

    bidder = Bidder(tender_id=tender.id, legal_name="ReportMe Ltd", pan="RRRRR1111R")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(
        tender_id=tender.id, bidder_id=bidder.id, status=BidStatus.SUBMITTED.value,
    )
    db.add(bid)
    db.flush()

    doc = Document(
        bid_id=bid.id, document_type="GST_CERTIFICATE", filename="gst.pdf",
        file_path="/tmp/gst.pdf", file_hash="ab" * 32, file_size=10,
        mime_type="application/pdf", processing_status="PROCESSED",
    )
    db.add(doc)
    db.flush()
    db.add(ExtractedField(
        document_id=doc.id, field_name="gstin", field_value="33AAAAA0000A1Z5",
        confidence=0.9, extraction_method="REGEX",
    ))
    db.add(VerificationCheck(
        bid_id=bid.id, source="GSTN", identifier="33AAAAA0000A1Z5",
        verification_status="VERIFIED", evidence_reference="GST portal match",
        is_mock=True,
    ))
    db.add(ComplianceResult(
        bid_id=bid.id, requirement_id=req.id, status="PASS", weight=50.0,
        weighted_contribution=50.0, evidence=["gst.pdf"],
        explanation="GST certificate present and verified.",
        rule_applied="DOCUMENT_REQUIRED", source="RULE_ENGINE",
    ))
    db.add(RiskAssessment(
        bid_id=bid.id, risk_level="LOW", risk_score=12.0,
        signals=["no adverse signals"], explanation="Clean record.",
    ))
    bid.recommendation = "PROCEED"
    bid.recommendation_reason = "All mandatory requirements met."
    db.commit()
    return bid, officer, verifier


def _actions(db, bid_id):
    return [
        e.action
        for e in db.query(AuditLog)
        .filter(AuditLog.entity_type == "bid_submission",
                AuditLog.entity_id == str(bid_id))
        .order_by(AuditLog.id)
        .all()
    ]


def test_full_report_lifecycle(db):
    bid, officer, verifier = _setup(db)

    # Starts as DRAFT.
    assert verifier_report_service.report_lifecycle(db, bid.id)["status"] == "DRAFT"

    # Verifier adds an observation.
    lc = verifier_report_service.add_observation(db, bid.id, verifier, "GST verified OK.")
    assert lc["status"] == "DRAFT"
    assert lc["observations"][0]["text"] == "GST verified OK."
    assert lc["observations"][0]["added_by"] == "Verifier"

    # Generate -> GENERATED.
    report = verifier_report_service.generate_report(db, bid.id, verifier)
    assert report["status"] == "GENERATED"

    # Report content is real evidence, not invented.
    assert report["bid_info"]["tender_number"] == "T-REP-1"
    assert report["bid_info"]["bidder_name"] == "ReportMe Ltd"
    assert report["documents"]["submitted_count"] == 1
    assert report["documents"]["processed_count"] == 1
    assert report["extracted_fields"]["total"] == 1
    assert report["extracted_fields"]["items"][0]["field_value"] == "33AAAAA0000A1Z5"
    assert report["verification"][0]["source"] == "GSTN"
    assert report["verification"][0]["status"] == "VERIFIED"
    assert report["compliance"][0]["requirement"] == "GST Registration"
    assert report["compliance"][0]["result"] == "PASS"
    assert report["risk"]["level"] == "LOW"
    # AI section uses the stored recommendation only.
    assert report["ai_summary"]["recommendation"] == "PROCEED"
    assert len(report["observations"]) == 1

    # Send -> SENT.
    report = verifier_report_service.send_report(db, bid.id, verifier)
    assert report["status"] == "SENT"

    # Inbox shows it as NEW.
    items = verifier_report_service.inbox(db)
    assert len(items) == 1
    assert items[0]["bid_id"] == bid.id
    assert items[0]["bidder_name"] == "ReportMe Ltd"
    assert items[0]["sent_by"] == "Verifier"
    assert items[0]["is_new"] is True

    # Officer acknowledges receipt -> RECEIVED, no longer NEW.
    lc = verifier_report_service.receive_report(db, bid.id, officer)
    assert lc["status"] == "RECEIVED"
    assert verifier_report_service.inbox(db)[0]["is_new"] is False

    # Officer opens -> UNDER_REVIEW.
    lc = verifier_report_service.mark_opened(db, bid.id, officer)
    assert lc["status"] == "UNDER_REVIEW"

    # Officer decides -> DECISION with the outcome.
    import app.api.officer as officer_mod
    from app.schemas.schemas import DecisionRequest
    from app.models.models import OfficerDecision

    officer_mod.officer_decision(
        DecisionRequest(bid_id=bid.id, decision=OfficerDecision.APPROVE,
                        reason="Report reviewed; evidence satisfactory."),
        db=db, user=officer,
    )
    report = verifier_report_service.build_report(db, bid.id)
    assert report["status"] == "DECISION"
    assert report["decision"]["decision"] == "APPROVE"

    # Every transition is in the hash-chained audit log.
    actions = _actions(db, bid.id)
    for expected in (
        "VERIFIER_OBSERVATION_ADDED",
        "VERIFICATION_REPORT_GENERATED",
        "VERIFICATION_REPORT_SENT",
        "VERIFICATION_REPORT_OPENED",
        "OFFICER_DECISION",
    ):
        assert expected in actions, expected


def test_send_before_generate_is_rejected(db):
    bid, _officer, verifier = _setup(db)
    with pytest.raises(HTTPException) as exc:
        verifier_report_service.send_report(db, bid.id, verifier)
    assert exc.value.status_code == 409


def test_generate_after_send_is_rejected(db):
    bid, _officer, verifier = _setup(db)
    verifier_report_service.generate_report(db, bid.id, verifier)
    verifier_report_service.send_report(db, bid.id, verifier)
    with pytest.raises(HTTPException) as exc:
        verifier_report_service.generate_report(db, bid.id, verifier)
    assert exc.value.status_code == 409


def test_observation_locked_after_send(db):
    bid, _officer, verifier = _setup(db)
    verifier_report_service.generate_report(db, bid.id, verifier)
    verifier_report_service.send_report(db, bid.id, verifier)
    with pytest.raises(HTTPException) as exc:
        verifier_report_service.add_observation(db, bid.id, verifier, "Too late.")
    assert exc.value.status_code == 409


def test_mark_opened_is_idempotent(db):
    bid, officer, verifier = _setup(db)
    verifier_report_service.generate_report(db, bid.id, verifier)
    verifier_report_service.send_report(db, bid.id, verifier)
    verifier_report_service.mark_opened(db, bid.id, officer)
    verifier_report_service.mark_opened(db, bid.id, officer)
    opened = [a for a in _actions(db, bid.id) if a == "VERIFICATION_REPORT_OPENED"]
    assert len(opened) == 1


def test_report_without_evidence_is_honest(db):
    """Sections with no data are null/empty, never invented."""
    bid, _officer, verifier = _setup(db)
    # Strip all evidence rows.
    for model in (ExtractedField, VerificationCheck, ComplianceResult, RiskAssessment):
        db.query(model).delete()
    db.query(Document).delete()
    bid.recommendation = None
    db.commit()
    report = verifier_report_service.build_report(db, bid.id)
    assert report["documents"]["submitted_count"] == 0
    assert report["extracted_fields"]["total"] == 0
    assert report["verification"] == []
    assert report["compliance"] == []
    assert report["risk"] is None
    assert report["ai_summary"] is None


def test_report_endpoint_role_gates():
    """Endpoint-level gates (mirrors the API module, not just the service)."""
    verifier_gate = reports_mod._VERIFIER
    officer_gate = reports_mod._OFFICER
    viewer_gate = reports_mod._VIEWER

    def _user(role):
        return User(name="t", email=f"{role}@x.local", password_hash="x", role=role)

    # Verifier-only actions: generate / send / observations.
    for role in ("PROCUREMENT_OFFICER", "AUDITOR", "ADMIN"):
        with pytest.raises(HTTPException):
            verifier_gate(user=_user(role))
    assert verifier_gate(user=_user("VERIFIER"))

    # Officer-only: inbox + mark opened.
    for role in ("VERIFIER", "AUDITOR", "ADMIN"):
        with pytest.raises(HTTPException):
            officer_gate(user=_user(role))
    assert officer_gate(user=_user("PROCUREMENT_OFFICER"))

    # Viewers: officer, verifier, auditor, admin.
    for role in ("PROCUREMENT_OFFICER", "VERIFIER", "AUDITOR", "ADMIN"):
        assert viewer_gate(user=_user(role))


def test_lifecycle_backward_compat_skips_received(db):
    """Histories that predate the RECEIVED stage (SENT, no RECEIVED event)
    still work: opening jumps SENT -> UNDER_REVIEW directly."""
    from app.services import verifier_report_service

    user = User(name="Verifier", email="v-bc@example.com", password_hash="x",
                role="VERIFIER")
    officer = User(name="Officer", email="o-bc@example.com", password_hash="x",
                   role="PROCUREMENT_OFFICER")
    db.add_all([user, officer])
    db.flush()
    tender = Tender(tender_number="T-BC-1", title="BC", organization="CPCL",
                    department="Purchase")
    db.add(tender)
    db.flush()
    bidder = Bidder(tender_id=tender.id, legal_name="Compat Ltd")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id,
                        status=BidStatus.SUBMITTED.value)
    db.add(bid)
    db.commit()

    verifier_report_service.generate_report(db, bid.id, user)
    verifier_report_service.send_report(db, bid.id, user)
    # Officer opens without ever acknowledging receipt.
    lc = verifier_report_service.mark_opened(db, bid.id, officer)
    assert lc["status"] == "UNDER_REVIEW"
    # Out-of-order receive is rejected once under review.
    with pytest.raises(HTTPException):
        verifier_report_service.receive_report(db, bid.id, officer)
