"""Single consolidated dossier upload: one PDF per bidder, all fields extracted.

Regression test for the real-case scenario where a bidder uploads ONE
consolidated document (bid dossier) instead of one file per certificate.
Covers: dossier generation, auto-classification as BID_DOSSIER, full field
extraction from the single file, and the EXISTENCE-based tender rules that
replaced the old DOCUMENT_REQUIRED checks.
"""
import hashlib

from app.models.models import (
    Bidder,
    BidSubmission,
    Document,
    Tender,
    TenderRequirement,
)
from app.seed.demo_docs import generate_dossier_pdf
from app.seed.seed_data import _BIDDERS_T1, _dossier_for
from app.services.compliance_service import evaluate_bid
from app.services.pipeline_service import process_document


def _make_bid_with_dossier(db, tmp_path, spec):
    doc_type, filename, legal_name, sections = _dossier_for(spec)
    assert doc_type == "BID_DOSSIER"
    pdf = generate_dossier_pdf(legal_name, sections)
    path = tmp_path / filename
    path.write_bytes(pdf)

    tender = Tender(
        tender_number="TEST-DOSSIER-001", title="Dossier test tender",
        organization="CPCL", department="Materials",
    )
    db.add(tender)
    db.commit()
    db.refresh(tender)

    bidder = Bidder(tender_id=tender.id, legal_name=spec["legal_name"])
    db.add(bidder)
    db.commit()
    db.refresh(bidder)

    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id)
    db.add(bid)
    db.commit()
    db.refresh(bid)

    doc = Document(
        bid_id=bid.id, document_type=doc_type, filename=filename,
        file_path=str(path), file_hash=hashlib.sha256(pdf).hexdigest(),
        file_size=len(pdf), mime_type="application/pdf",
        processing_status="UPLOADED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return tender, bid, doc


def test_dossier_single_upload_extracts_everything(db, tmp_path):
    """One dossier -> classified BID_DOSSIER, all sections' fields extracted."""
    spec = _BIDDERS_T1[0]  # apex: has oem, epfo, esic, mii; no startup cert
    _, _, doc = _make_bid_with_dossier(db, tmp_path, spec)

    result = process_document(db, doc.id)
    assert result["status"] == "PROCESSED"
    assert result["document_type"] == "BID_DOSSIER"

    by_name = {f["field_name"]: f["normalized_value"]
               for f in result["extracted_fields"]}
    assert by_name["pan"] == "AAFCA1234E"
    assert by_name["gstin"] == "27AAFCA1234E1Z5"
    assert by_name["udyam_number"] == "UDYAM-MH-19-0012345"
    assert by_name["legal_name"] == "Apex Flow Systems Pvt Ltd"
    assert float(by_name["turnover_inr"]) == 124000000
    assert float(by_name["experience_years"]) == 9.0
    assert by_name["oem_name"] == "Kirloskar Brothers Ltd"
    assert by_name["oem_authorization_valid"] == "True"
    assert by_name["epfo_code"] == "MH/123456/001"
    assert by_name["esic_code"] == "11000012345678901"
    assert float(by_name["local_content_pct"]) == 62.0
    # apex has no startup section -> no startup field from the single dossier
    assert "startup_certificate_number" not in by_name

    db.refresh(doc)
    assert doc.processing_status == "PROCESSED"


def test_existence_rules_evaluate_from_dossier(db, tmp_path):
    """EXISTENCE rules (not file-type checks) decide on dossier information."""
    spec = _BIDDERS_T1[0]  # apex: oem yes, experience yes, startup no
    tender, bid, doc = _make_bid_with_dossier(db, tmp_path, spec)
    assert process_document(db, doc.id)["status"] == "PROCESSED"

    db.add_all([
        TenderRequirement(
            tender_id=tender.id, requirement_name="OEM Authorization",
            category="OEM", mandatory=False, rule_type="EXISTENCE",
            rule_config={"value_source": "extracted.oem_authorization_valid"},
            weight=10),
        TenderRequirement(
            tender_id=tender.id, requirement_name="Startup India Recognition",
            category="REGISTRATION", mandatory=True, rule_type="EXISTENCE",
            rule_config={"value_source": "extracted.startup_certificate_number"},
            weight=10),
        TenderRequirement(
            tender_id=tender.id, requirement_name="Experience Certificate",
            category="EXPERIENCE", mandatory=False, rule_type="EXISTENCE",
            rule_config={"value_source": "extracted.experience_years"},
            weight=0),
    ])
    db.commit()

    result = evaluate_bid(db, bid.id)
    by_name = {r["requirement_name"]: r for r in result["results"]}
    # information present in the single dossier -> PASS
    assert by_name["OEM Authorization"]["status"] == "PASS"
    assert by_name["Experience Certificate"]["status"] == "PASS"
    # startup info absent from this bidder's dossier -> MISSING (mandatory)
    assert by_name["Startup India Recognition"]["status"] == "MISSING"
