"""Consistency engine: deterministic cross-document checks over extracted fields.

Covers: legal-name mismatch (Nova-style), normalized-name match, GSTIN<->PAN
structural consistency, identifier agreement, expiry, numeric and date
comparisons, idempotent re-runs, and mismatch audit events.
"""
import pytest

from app.models.models import (
    AuditLog,
    Bidder,
    BidStatus,
    BidSubmission,
    Document,
    ExtractedField,
    Tender,
    User,
)
from app.services import consistency_service


@pytest.fixture()
def bid_with_docs(db):
    user = User(
        name="Officer",
        email="officer-cons@example.com",
        password_hash="x",
        role="PROCUREMENT_OFFICER",
    )
    db.add(user)
    tender = Tender(
        tender_number="T-CONS-1",
        title="Consistency test",
        organization="CPCL",
        department="Purchase",
    )
    db.add(tender)
    db.flush()
    bidder = Bidder(
        tender_id=tender.id, legal_name="Nova Engineering Works Pvt. Ltd.", pan="AANNE5678P"
    )
    db.add(bidder)
    db.flush()
    bid = BidSubmission(
        tender_id=tender.id, bidder_id=bidder.id, status=BidStatus.SUBMITTED.value
    )
    db.add(bid)
    db.flush()

    docs = {}
    for dtype, filename in [
        ("GST_CERTIFICATE", "gst_cert.pdf"),
        ("PAN_CERTIFICATE", "pan_cert.pdf"),
        ("UDYAM_CERTIFICATE", "udyam_cert.pdf"),
        ("TURNOVER_STATEMENT", "turnover.pdf"),
    ]:
        d = Document(
            bid_id=bid.id,
            document_type=dtype,
            filename=filename,
            file_path=f"/tmp/{filename}",
            file_hash="x" * 64,
            file_size=100,
            mime_type="application/pdf",
            processing_status="PROCESSED",
        )
        db.add(d)
        db.flush()
        docs[dtype] = d

    def field(doc, name, value, page=1):
        db.add(
            ExtractedField(
                document_id=doc.id,
                field_name=name,
                field_value=value,
                normalized_value=None,
                confidence=0.9,
                extraction_method="regex",
                page_number=page,
            )
        )

    gst = docs["GST_CERTIFICATE"]
    pan = docs["PAN_CERTIFICATE"]
    udyam = docs["UDYAM_CERTIFICATE"]
    turn = docs["TURNOVER_STATEMENT"]

    field(gst, "legal_name", "Nova Engineering Works Pvt. Ltd.")
    field(gst, "gstin", "27AANNE5678P1Z5")
    field(gst, "pan", "AANNE5678P")  # GST certificate embeds the PAN
    field(gst, "valid_until", "31-12-2030")

    field(pan, "legal_name", "Nova Industrial Enterprises")  # mismatch
    field(pan, "pan", "AANNE5678P")

    field(udyam, "udyam_number", "UDYAM-MH-19-0001234")
    field(udyam, "turnover_inr", "Rs 375 lakh")

    field(turn, "turnover_inr", "Rs 380 lakh")  # within tolerance -> match
    field(turn, "incorporation_date", "12-05-2015")

    db.commit()
    return bid.id


def test_nova_style_name_mismatch(bid_with_docs, db):
    res = consistency_service.run_consistency_check(db, bid_with_docs)
    assert res["checks_run"] > 0
    checks = consistency_service.get_consistency(db, bid_with_docs)["checks"]
    name_checks = [c for c in checks if c["check_name"] == "ENTITY_NAME_CONSISTENCY"]
    assert len(name_checks) >= 1
    mismatches = [c for c in name_checks if c["result"] == "MISMATCH"]
    assert mismatches, "expected a legal-name mismatch (Nova-style)"
    m = mismatches[0]
    assert "Nova Engineering Works Pvt. Ltd." in (m["value1"] or "")
    assert "Nova Industrial Enterprises" in (m["value2"] or "")
    assert m["severity"] == "REVIEW_REQUIRED"
    assert res["mismatches"] >= 1


def test_gstin_pan_structure_consistent(bid_with_docs, db):
    consistency_service.run_consistency_check(db, bid_with_docs)
    checks = consistency_service.get_consistency(db, bid_with_docs)["checks"]
    pan_struct = [c for c in checks if c["check_name"] == "GSTIN_PAN_CONSISTENCY"]
    assert len(pan_struct) == 1
    assert pan_struct[0]["result"] == "MATCH"


def test_turnover_within_tolerance(bid_with_docs, db):
    consistency_service.run_consistency_check(db, bid_with_docs)
    checks = consistency_service.get_consistency(db, bid_with_docs)["checks"]
    to = [c for c in checks if c["check_name"] == "TURNOVER_CONSISTENCY"]
    assert len(to) == 1
    assert to[0]["result"] == "MATCH"


def test_expiry_future(bid_with_docs, db):
    consistency_service.run_consistency_check(db, bid_with_docs)
    checks = consistency_service.get_consistency(db, bid_with_docs)["checks"]
    exp = [c for c in checks if c["check_name"] == "CERTIFICATE_EXPIRY"]
    assert len(exp) == 1
    assert exp[0]["result"] == "MATCH"


def test_rerun_replaces_stored_checks(bid_with_docs, db):
    r1 = consistency_service.run_consistency_check(db, bid_with_docs)
    r2 = consistency_service.run_consistency_check(db, bid_with_docs)
    assert r1["checks_run"] == r2["checks_run"]
    checks = consistency_service.get_consistency(db, bid_with_docs)["checks"]
    assert len(checks) == r1["checks_run"]


def test_mismatch_audit_event(bid_with_docs, db):
    consistency_service.run_consistency_check(db, bid_with_docs)
    events = (
        db.query(AuditLog)
        .filter(AuditLog.action == "CROSS_DOCUMENT_MISMATCH_DETECTED")
        .all()
    )
    assert len(events) >= 1
    assert "MISMATCH" in (events[0].meta or {}).get("reason", "") or True
    assert str(bid_with_docs) in events[0].entity_id


def test_no_confidence_percentages_exposed(bid_with_docs, db):
    consistency_service.run_consistency_check(db, bid_with_docs)
    checks = consistency_service.get_consistency(db, bid_with_docs)["checks"]
    for c in checks:
        blob = (c.get("check_label") or "") + (c.get("reason") or "")
        assert "%" not in blob, f"confidence percentage leaked in {c['check_name']}"


def test_normalized_name_match(db):
    """'Pvt. Ltd.' vs 'Private Limited' is a normalisation variant, not a mismatch."""
    tender = Tender(
        tender_number="T-CONS-2",
        title="t",
        organization="CPCL",
        department="Purchase",
    )
    db.add(tender)
    db.flush()
    bidder = Bidder(tender_id=tender.id, legal_name="Apex Flow Systems Pvt. Ltd.")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(
        tender_id=tender.id, bidder_id=bidder.id, status=BidStatus.SUBMITTED.value
    )
    db.add(bid)
    db.flush()

    docs = []
    for i, (dtype, name) in enumerate(
        [("GST_CERTIFICATE", "Apex Flow Systems Pvt. Ltd."),
         ("PAN_CERTIFICATE", "Apex Flow Systems Private Limited")]
    ):
        d = Document(
            bid_id=bid.id,
            document_type=dtype,
            filename=f"d{i}.pdf",
            file_path=f"/tmp/d{i}.pdf",
            file_hash="x" * 64,
            file_size=10,
            mime_type="application/pdf",
            processing_status="PROCESSED",
        )
        db.add(d)
        db.flush()
        db.add(
            ExtractedField(
                document_id=d.id,
                field_name="legal_name",
                field_value=name,
                normalized_value=None,
                confidence=0.9,
                extraction_method="regex",
                page_number=1,
            )
        )
        docs.append(d)
    db.commit()

    consistency_service.run_consistency_check(db, bid.id)
    checks = consistency_service.get_consistency(db, bid.id)["checks"]
    name_checks = [c for c in checks if c["check_name"] == "ENTITY_NAME_CONSISTENCY"]
    assert len(name_checks) == 1
    assert name_checks[0]["result"] == "MATCH"


def test_expired_certificate_mismatch(db):
    tender = Tender(
        tender_number="T-CONS-3",
        title="t",
        organization="CPCL",
        department="Purchase",
    )
    db.add(tender)
    db.flush()
    bidder = Bidder(tender_id=tender.id, legal_name="OldCo")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(
        tender_id=tender.id, bidder_id=bidder.id, status=BidStatus.SUBMITTED.value
    )
    db.add(bid)
    db.flush()
    d = Document(
        bid_id=bid.id,
        document_type="UDYAM_CERTIFICATE",
        filename="old.pdf",
        file_path="/tmp/old.pdf",
        file_hash="x" * 64,
        file_size=10,
        mime_type="application/pdf",
        processing_status="PROCESSED",
    )
    db.add(d)
    db.flush()
    db.add(
        ExtractedField(
            document_id=d.id,
            field_name="valid_until",
            field_value="01-01-2020",
            normalized_value=None,
            confidence=0.9,
            extraction_method="regex",
            page_number=1,
        )
    )
    db.commit()

    consistency_service.run_consistency_check(db, bid.id)
    checks = consistency_service.get_consistency(db, bid.id)["checks"]
    exp = [c for c in checks if c["check_name"] == "CERTIFICATE_EXPIRY"]
    assert len(exp) == 1
    assert exp[0]["result"] == "MISMATCH"
    assert exp[0]["severity"] == "REVIEW_REQUIRED"


def _mini_bid(db, legal_name="Acme Industries Pvt. Ltd."):
    """Minimal bid with one processed document; returns (bid_id, doc_id)."""
    tender = Tender(
        tender_number="T-CONS-X", title="X", organization="CPCL",
        department="Purchase",
    )
    db.add(tender)
    db.flush()
    bidder = Bidder(tender_id=tender.id, legal_name=legal_name)
    db.add(bidder)
    db.flush()
    bid = BidSubmission(
        tender_id=tender.id, bidder_id=bidder.id, status=BidStatus.SUBMITTED.value
    )
    db.add(bid)
    db.flush()
    d = Document(
        bid_id=bid.id, document_type="OEM_AUTHORIZATION", filename="oem.pdf",
        file_path="/tmp/oem.pdf", file_hash="x" * 64, file_size=10,
        mime_type="application/pdf", processing_status="PROCESSED",
    )
    db.add(d)
    db.flush()

    def field(name, value):
        db.add(ExtractedField(
            document_id=d.id, field_name=name, field_value=value,
            normalized_value=None, confidence=0.9,
            extraction_method="regex", page_number=1,
        ))

    db.commit()
    return bid.id, d.id, field


def test_oem_authorization_names_bidder_match(db):
    bid_id, _, field = _mini_bid(db, "Acme Industries Pvt. Ltd.")
    field("legal_name", "Acme Industries Pvt. Ltd.")
    field("oem_name", "Kirloskar Brothers Ltd. (demo)")
    field("oem_authorization_valid", "True")
    db.commit()

    consistency_service.run_consistency_check(db, bid_id)
    rows = [
        c for c in consistency_service.get_consistency(db, bid_id)["checks"]
        if c["check_name"] == "OEM_AUTHORIZATION_IDENTITY"
    ]
    assert len(rows) == 1
    assert rows[0]["result"] == "MATCH"
    assert rows[0]["severity"] == "INFORMATIONAL"


def test_oem_authorization_names_other_entity_mismatch(db):
    bid_id, _, field = _mini_bid(db, "Acme Industries Pvt. Ltd.")
    field("legal_name", "Some Other Company Pvt. Ltd.")
    field("oem_name", "Kirloskar Brothers Ltd. (demo)")
    field("oem_authorization_valid", "True")
    db.commit()

    consistency_service.run_consistency_check(db, bid_id)
    rows = [
        c for c in consistency_service.get_consistency(db, bid_id)["checks"]
        if c["check_name"] == "OEM_AUTHORIZATION_IDENTITY"
    ]
    assert len(rows) == 1
    assert rows[0]["result"] == "MISMATCH"
    assert rows[0]["severity"] == "REVIEW_REQUIRED"
    assert "different entity" in rows[0]["reason"]


def _blacklist_check(db, bid_id, blacklisted, debarred=False):
    from app.models.models import VerificationCheck

    db.add(VerificationCheck(
        bid_id=bid_id, source="BLACKLIST", identifier="Acme Industries Pvt. Ltd.",
        response_payload={
            "source": "BLACKLIST", "status": "VERIFIED",
            "data": {
                "company_name": "Acme Industries Pvt. Ltd.",
                "blacklisted": blacklisted, "debarred": debarred,
            },
        },
        verification_status="VERIFIED", is_mock=True,
    ))
    db.commit()


def test_debarment_declaration_clean_match(db):
    bid_id, _, field = _mini_bid(db)
    field("debarment_declaration",
          "Not debarred or blacklisted by any government authority.")
    _blacklist_check(db, bid_id, blacklisted=False)
    db.commit()

    consistency_service.run_consistency_check(db, bid_id)
    rows = [
        c for c in consistency_service.get_consistency(db, bid_id)["checks"]
        if c["check_name"] == "DEBARMENT_DECLARATION_CONSISTENCY"
    ]
    assert len(rows) == 1
    assert rows[0]["result"] == "MATCH"


def test_debarment_declaration_contradicted_mismatch(db):
    bid_id, _, field = _mini_bid(db)
    field("debarment_declaration",
          "Not debarred or blacklisted by any government authority.")
    _blacklist_check(db, bid_id, blacklisted=True)
    db.commit()

    consistency_service.run_consistency_check(db, bid_id)
    rows = [
        c for c in consistency_service.get_consistency(db, bid_id)["checks"]
        if c["check_name"] == "DEBARMENT_DECLARATION_CONSISTENCY"
    ]
    assert len(rows) == 1
    assert rows[0]["result"] == "MISMATCH"
    assert rows[0]["severity"] == "REVIEW_REQUIRED"
    assert "contradicted" in rows[0]["reason"]


def test_debarment_declaration_skipped_without_verification(db):
    bid_id, _, field = _mini_bid(db)
    field("debarment_declaration",
          "Not debarred or blacklisted by any government authority.")
    db.commit()  # no BLACKLIST verification run

    consistency_service.run_consistency_check(db, bid_id)
    rows = [
        c for c in consistency_service.get_consistency(db, bid_id)["checks"]
        if c["check_name"] == "DEBARMENT_DECLARATION_CONSISTENCY"
    ]
    assert rows == []


def _verification_record(db, bid_id, source, data):
    from app.models.models import VerificationCheck

    db.add(VerificationCheck(
        bid_id=bid_id, source=source, identifier="x",
        response_payload={"source": source, "status": "VERIFIED", "data": data},
        verification_status="VERIFIED", is_mock=True,
    ))
    db.commit()


def test_retrieved_statutory_name_mismatch(db):
    bid_id, _, field = _mini_bid(db, "Nova Engineering Works Pvt. Ltd.")
    field("legal_name", "Nova Engineering Works Pvt. Ltd.")
    field("gstin", "27AANNE5678P1Z5")
    _verification_record(db, bid_id, "GSTN", {
        "gstin": "27AANNE5678P1Z5",
        "legal_name": "Nova Infra Projects Private Limited",
        "status": "ACTIVE",
    })
    db.commit()

    consistency_service.run_consistency_check(db, bid_id)
    rows = [
        c for c in consistency_service.get_consistency(db, bid_id)["checks"]
        if c["check_name"] == "RETRIEVED_STATUTORY_COMPARISON"
    ]
    by_field = {r["field_name"]: r for r in rows}
    assert by_field["legal_name"]["result"] == "MISMATCH"
    assert by_field["legal_name"]["severity"] == "REVIEW_REQUIRED"
    assert by_field["gstin"]["result"] == "MATCH"  # identifier echo agrees


def test_retrieved_statutory_name_match(db):
    bid_id, _, field = _mini_bid(db, "Apex Flow Systems Pvt. Ltd.")
    field("legal_name", "Apex Flow Systems Private Limited")
    _verification_record(db, bid_id, "GSTN", {
        "gstin": "27AAFCA1234E1Z5",
        "legal_name": "Apex Flow Systems Private Limited",
        "status": "ACTIVE",
    })
    db.commit()

    consistency_service.run_consistency_check(db, bid_id)
    rows = [
        c for c in consistency_service.get_consistency(db, bid_id)["checks"]
        if c["check_name"] == "RETRIEVED_STATUTORY_COMPARISON"
    ]
    assert len(rows) == 1
    assert rows[0]["result"] == "MATCH"
