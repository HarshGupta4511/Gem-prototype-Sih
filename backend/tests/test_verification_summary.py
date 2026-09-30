"""Bid Verification Summary workflow (single-role model).

Flow: officer adds observation -> generates summary -> regenerates summary.
Lifecycle (audit-derived): DRAFT -> GENERATED -> UPDATED. The final officer
decision is recorded separately and is NOT a summary-lifecycle state.

Asserts:
- lifecycle derives from audit events only (no schema changes),
- guards enforce the order (409 on regenerate-before-generate),
- the summary content reflects real stored evidence (documents, extracted
  fields, verification checks, compliance results, risk, stored AI rec),
- legacy verifier-handoff events (SENT/RECEIVED/OPENED) map to GENERATED,
- every transition appends a hash-chained audit event.
"""
import pytest
from fastapi import HTTPException

import app.api.verification_summaries as summaries_mod
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
from app.services import audit_service, verification_summary_service as vss


def _setup(db):
    officer = User(
        name="Officer", email="officer-sum@example.com", password_hash="x",
        role="PROCUREMENT_OFFICER",
    )
    db.add(officer)
    db.flush()

    tender = Tender(
        tender_number="T-SUM-1", title="Summary test", organization="CPCL",
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

    bidder = Bidder(tender_id=tender.id, legal_name="SummaryMe Ltd", pan="RRRRR1111R")
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
    return bid, officer


def _actions(db, bid_id):
    return [
        e.action
        for e in db.query(AuditLog)
        .filter(AuditLog.entity_type == "bid_submission",
                AuditLog.entity_id == str(bid_id))
        .order_by(AuditLog.id)
        .all()
    ]


def test_full_summary_lifecycle(db):
    bid, officer = _setup(db)

    # Starts as DRAFT.
    assert vss.summary_lifecycle(db, bid.id)["status"] == "DRAFT"

    # Officer adds an observation.
    lc = vss.add_observation(db, bid.id, officer, "GST verified OK.")
    assert lc["status"] == "DRAFT"
    assert lc["observations"][0]["text"] == "GST verified OK."
    assert lc["observations"][0]["added_by"] == "Officer"

    # Generate -> GENERATED.
    summary = vss.generate_summary(db, bid.id, officer)
    assert summary["status"] == "GENERATED"

    # Summary content is real evidence, not invented.
    assert summary["bid_info"]["tender_number"] == "T-SUM-1"
    assert summary["bid_info"]["bidder_name"] == "SummaryMe Ltd"
    assert summary["documents"]["submitted_count"] == 1
    assert summary["documents"]["processed_count"] == 1
    assert summary["extracted_fields"]["total"] == 1
    assert summary["extracted_fields"]["items"][0]["field_value"] == "33AAAAA0000A1Z5"
    assert summary["verification"][0]["source"] == "GSTN"
    assert summary["verification"][0]["status"] == "VERIFIED"
    assert summary["compliance"][0]["requirement"] == "GST Registration"
    assert summary["compliance"][0]["result"] == "PASS"
    assert summary["risk"]["level"] == "LOW"
    # AI section uses the stored recommendation only.
    assert summary["ai_summary"]["recommendation"] == "PROCEED"
    # Observations are officer observations (renamed key).
    assert "officer_observations" in summary
    assert len(summary["officer_observations"]) == 1

    # Regenerate -> UPDATED.
    summary = vss.regenerate_summary(db, bid.id, officer)
    assert summary["status"] == "UPDATED"

    # Officer decides separately: the summary shows the decision but the
    # lifecycle is not a "DECISION" state.
    import app.api.officer as officer_mod
    from app.schemas.schemas import DecisionRequest
    from app.models.models import OfficerDecision

    officer_mod.officer_decision(
        DecisionRequest(bid_id=bid.id, decision=OfficerDecision.APPROVE,
                        reason="Summary reviewed; evidence satisfactory."),
        db=db, user=officer,
    )
    summary = vss.build_summary(db, bid.id)
    assert summary["status"] == "UPDATED"
    assert summary["decision"]["decision"] == "APPROVE"

    # Every transition is in the hash-chained audit log.
    actions = _actions(db, bid.id)
    for expected in (
        "OFFICER_OBSERVATION_ADDED",
        "VERIFICATION_REPORT_GENERATED",
        "VERIFICATION_SUMMARY_REGENERATED",
        "OFFICER_DECISION",
    ):
        assert expected in actions, expected


def test_generate_is_idempotent(db):
    bid, officer = _setup(db)
    vss.generate_summary(db, bid.id, officer)
    before = len(_actions(db, bid.id))
    summary = vss.generate_summary(db, bid.id, officer)
    assert summary["status"] == "GENERATED"
    assert len(_actions(db, bid.id)) == before


def test_regenerate_before_generate_is_rejected(db):
    bid, officer = _setup(db)
    with pytest.raises(HTTPException) as exc:
        vss.regenerate_summary(db, bid.id, officer)
    assert exc.value.status_code == 409


def test_legacy_handoff_events_map_to_generated(db):
    """Histories from the retired verifier workflow (SENT/RECEIVED/OPENED)
    read as GENERATED; the old stages are never written again."""
    bid, officer = _setup(db)
    vss.generate_summary(db, bid.id, officer)
    for action in (
        "VERIFICATION_REPORT_SENT",
        "VERIFICATION_REPORT_RECEIVED",
        "VERIFICATION_REPORT_OPENED",
    ):
        audit_service.append_audit(
            db, user_id=officer.id, action=action,
            entity_type="bid_submission", entity_id=str(bid.id), metadata={},
        )
    assert vss.summary_lifecycle(db, bid.id)["status"] == "GENERATED"
    # Regenerate still works on top of a legacy history.
    assert vss.regenerate_summary(db, bid.id, officer)["status"] == "UPDATED"


def test_legacy_verifier_observation_still_read(db):
    """A VERIFIER_OBSERVATION_ADDED event from an old history is still shown
    as an officer observation (read-only backward compatibility)."""
    bid, officer = _setup(db)
    audit_service.append_audit(
        db, user_id=officer.id, action="VERIFIER_OBSERVATION_ADDED",
        entity_type="bid_submission", entity_id=str(bid.id),
        metadata={"observation": "Old note."},
    )
    lc = vss.summary_lifecycle(db, bid.id)
    assert lc["status"] == "DRAFT"
    assert lc["observations"][0]["text"] == "Old note."


def test_summary_without_evidence_is_honest(db):
    """Sections with no data are null/empty, never invented."""
    bid, officer = _setup(db)
    # Strip all evidence rows.
    for model in (ExtractedField, VerificationCheck, ComplianceResult, RiskAssessment):
        db.query(model).delete()
    db.query(Document).delete()
    bid.recommendation = None
    db.commit()
    summary = vss.build_summary(db, bid.id)
    assert summary["documents"]["submitted_count"] == 0
    assert summary["extracted_fields"]["total"] == 0
    assert summary["verification"] == []
    assert summary["compliance"] == []
    assert summary["risk"] is None
    assert summary["ai_summary"] is None


def test_summary_endpoints_require_officer():
    """The API module exposes a single _OFFICER gate; legacy roles denied."""
    gate = summaries_mod._OFFICER

    def _user(role):
        return User(name="t", email=f"{role}@x.local", password_hash="x", role=role)

    assert gate(user=_user("PROCUREMENT_OFFICER"))
    for role in ("VERIFIER", "AUDITOR", "ADMIN"):
        with pytest.raises(HTTPException):
            gate(user=_user(role))

    paths = sorted({r.path for r in summaries_mod.router.routes})
    assert f"/api/verification-summaries/bids/{{bid_id}}" in paths
    assert f"/api/verification-summaries/bids/{{bid_id}}/lifecycle" in paths
    assert f"/api/verification-summaries/bids/{{bid_id}}/observations" in paths
    assert f"/api/verification-summaries/bids/{{bid_id}}/generate" in paths
    assert f"/api/verification-summaries/bids/{{bid_id}}/regenerate" in paths
    # No handoff endpoints remain.
    assert not any(p.endswith(("/inbox", "/send", "/received", "/opened"))
                   for p in paths)
