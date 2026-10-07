"""Automatic document classification: the officer never selects a document type.

Covers the Documents-module automation contract:
- upload accepts no ``document_type`` (officer input) — the pipeline detects it
- content-driven classification (filename is supporting context only)
- low-confidence documents are stored as UNCLASSIFIED / REVIEW_REQUIRED —
  the system never invents a type
- manual correction is allowed ONLY for UNCLASSIFIED documents
"""
import asyncio
import io

import pytest

import app.api.documents as documents_mod
from app.models.models import (
    Bidder,
    BidSubmission,
    Document,
    Tender,
    User,
)
from app.schemas.schemas import DocumentTypeUpdate
from app.services import classification_service, pipeline_service
from app.core.config import settings


def _pdf_with_text(tmp_path, name, text):
    import fitz  # PyMuPDF — already a pipeline dependency

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    path = tmp_path / name
    doc.save(str(path))
    return path


def _make_bid(db):
    tender = Tender(
        tender_number="TEST-AUTOCLASS-001", title="Auto-classification test",
        organization="CPCL", department="Materials",
    )
    db.add(tender)
    db.commit()
    db.refresh(tender)
    bidder = Bidder(tender_id=tender.id, legal_name="Test Bidder Pvt Ltd")
    db.add(bidder)
    db.commit()
    db.refresh(bidder)
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id)
    db.add(bid)
    db.commit()
    db.refresh(bid)
    return bid


def _make_officer(db):
    user = User(
        name="officer", email="officer@test.local",
        password_hash="x", role="PROCUREMENT_OFFICER",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _insert_doc(db, bid, path):
    pdf = path.read_bytes()
    doc = Document(
        bid_id=bid.id, document_type="UNCLASSIFIED", filename=path.name,
        file_path=str(path), file_hash="0" * 64, file_size=len(pdf),
        mime_type="application/pdf", processing_status="UPLOADED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ---------------------------------------------------------------------------
# Classifier unit tests (content-driven, filename is supporting context only)
# ---------------------------------------------------------------------------

def test_classify_gst_certificate_from_content():
    text = (
        "Certificate of Registration under Goods and Services Tax. "
        "GSTIN: 33ABCDE1234F1Z5. Legal name of business: Test Bidder Pvt Ltd."
    )
    doc_type, conf = classification_service.classify_document("scan001.pdf", text)
    assert doc_type == "GST_CERTIFICATE"
    assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_turnover_certificate():
    text = (
        "This is to certify the annual turnover of the firm for FY 2023-24 "
        "is Rs. 45,00,000 (Rupees forty-five lakh only)."
    )
    doc_type, conf = classification_service.classify_document("doc.pdf", text)
    assert doc_type == "TURNOVER_CERTIFICATE"
    assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_oem_authorization_needs_manufacturing_context():
    text = (
        "OEM Authorization Letter. We, the Original Equipment Manufacturer, "
        "hereby authorize Test Bidder to bid for our manufactured products."
    )
    doc_type, conf = classification_service.classify_document("letter.pdf", text)
    assert doc_type == "OEM_AUTHORIZATION"
    assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_unknown_content_never_invents_a_type():
    text = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod "
        "tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim "
        "veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea "
        "commodo consequat. Duis aute irure dolor in reprehenderit in voluptate "
        "velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint "
        "occaecat cupidatat non proident, sunt in culpa qui officia deserunt "
        "mollit anim id est laborum. Additional neutral filler text to make the "
        "document long enough for the extraction pipeline to proceed normally."
    )
    doc_type, conf = classification_service.classify_document("random.pdf", text)
    assert doc_type == "UNCLASSIFIED"
    assert conf < classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_dossier_marker():
    doc_type, conf = classification_service.classify_document(
        "apex_bid_dossier.pdf", "Consolidated Bid Dossier — Test Bidder Pvt Ltd"
    )
    assert doc_type == "BID_DOSSIER"
    assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_emd_payment():
    text = (
        "Earnest Money Deposit (EMD) — Payment Proof. "
        "EMD Amount: Rs. 5,00,000. Payment Reference: NEFT/2026/001234. "
        "This evidences payment of the Earnest Money Deposit for the bid."
    )
    doc_type, conf = classification_service.classify_document("emd_receipt.pdf", text)
    assert doc_type == "EMD_PAYMENT"
    assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_past_performance_certificate():
    text = (
        "Past Performance Certificate. "
        "Past Performance: 87% of bid quantity. Client: CPCL. "
        "This certificate confirms the supply performance of the entity "
        "against earlier government orders."
    )
    doc_type, conf = classification_service.classify_document("performance.pdf", text)
    assert doc_type == "PAST_PERFORMANCE_CERTIFICATE"
    assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_non_debarment_declaration():
    text = (
        "Non-Debarment Declaration. "
        "Debarment Declaration: Not debarred or blacklisted by any "
        "government authority. The bidder declares the debarment status "
        "stated above as on the date of this bid."
    )
    doc_type, conf = classification_service.classify_document("declaration.pdf", text)
    assert doc_type == "NON_DEBARMENT_DECLARATION"
    assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_ambiguous_document_picks_most_keyword_hits():
    # Mentions EMD once but is really a turnover certificate — the type with
    # the most keyword hits wins deterministically.
    text = (
        "Turnover Certificate. The annual turnover of the firm for FY 2023-24 "
        "is Rs. 45,00,000. Turnover certified by the statutory auditor. "
        "(EMD amount field left blank.)"
    )
    doc_type, conf = classification_service.classify_document("mixed.pdf", text)
    assert doc_type == "TURNOVER_CERTIFICATE"
    assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_blacklist_mention_without_declaration_stays_unclassified():
    # "blacklisted" alone is not a declaration — without a debarment keyword
    # the system must not invent NON_DEBARMENT_DECLARATION.
    text = (
        "We confirm the firm was never blacklisted by any authority. "
        "Additional neutral filler text to avoid accidental keyword matches "
        "with any other document type in the classifier rules."
    )
    doc_type, conf = classification_service.classify_document("affidavit.pdf", text)
    assert doc_type == "UNCLASSIFIED"
    assert conf < classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_classify_debarment_doc_not_confused_with_dossier():
    # A standalone declaration must not be swallowed by the dossier marker.
    text = (
        "Standalone demo evidence document. Non-Debarment Declaration: "
        "Not debarred or blacklisted by any government authority."
    )
    doc_type, conf = classification_service.classify_document("declaration.pdf", text)
    assert doc_type == "NON_DEBARMENT_DECLARATION"
    assert doc_type != "BID_DOSSIER"


# ---------------------------------------------------------------------------
# Pipeline: detected type stored, review-required on low confidence
# ---------------------------------------------------------------------------

def test_pipeline_detects_type_without_officer_input(db, tmp_path):
    bid = _make_bid(db)
    text = (
        "Certificate of Registration under Goods and Services Tax. "
        "GSTIN: 33ABCDE1234F1Z5. Legal name of business: Test Bidder Pvt Ltd. "
        "Date of registration: 01-07-2017."
    )
    path = _pdf_with_text(tmp_path, "upload.pdf", text)
    doc = _insert_doc(db, bid, path)

    result = pipeline_service.process_document(db, doc.id)

    db.refresh(doc)
    assert doc.document_type == "GST_CERTIFICATE"
    assert doc.processing_status == "PROCESSED"
    assert result["status"] == "PROCESSED"
    assert result["document_type"] == "GST_CERTIFICATE"


def test_pipeline_marks_review_required_when_type_unsure(db, tmp_path):
    bid = _make_bid(db)
    text = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod "
        "tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim "
        "veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea "
        "commodo consequat. Duis aute irure dolor in reprehenderit in voluptate "
        "velit esse cillum dolore eu fugiat nulla pariatur. Additional neutral "
        "filler text to make the document long enough for the pipeline to run."
    )
    path = _pdf_with_text(tmp_path, "mystery.pdf", text)
    doc = _insert_doc(db, bid, path)

    result = pipeline_service.process_document(db, doc.id)

    db.refresh(doc)
    # The system must NOT invent a type — it flags the document for review.
    assert doc.document_type == "UNCLASSIFIED"
    assert doc.processing_status == "REVIEW_REQUIRED"
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["document_type"] == "UNCLASSIFIED"


# ---------------------------------------------------------------------------
# Endpoints: upload without type; correction only for UNCLASSIFIED
# ---------------------------------------------------------------------------

def test_upload_without_document_type_autodetects(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path / "uploads")
    from fastapi import UploadFile

    bid = _make_bid(db)
    user = _make_officer(db)
    text = (
        "Certificate of Registration under Goods and Services Tax. "
        "GSTIN: 33ABCDE1234F1Z5. Legal name of business: Test Bidder Pvt Ltd. "
        "Date of registration: 01-07-2017."
    )
    pdf_bytes = _pdf_with_text(tmp_path, "gst_certificate.pdf", text).read_bytes()
    upload = UploadFile(file=io.BytesIO(pdf_bytes), filename="gst_certificate.pdf")

    # No document_type passed — the officer does not choose one.
    doc = asyncio.run(documents_mod.upload_document(
        bid_id=bid.id, document_type=None, file=upload, db=db, user=user
    ))

    assert doc.document_type == "GST_CERTIFICATE"
    assert doc.processing_status == "PROCESSED"


def test_correction_allowed_only_for_unclassified(db):
    user = _make_officer(db)
    bid = _make_bid(db)

    detected = Document(
        bid_id=bid.id, document_type="GST_CERTIFICATE", filename="a.pdf",
        file_path="/tmp/a.pdf", file_hash="0" * 64, file_size=1,
        mime_type="application/pdf", processing_status="PROCESSED",
    )
    db.add(detected)
    db.commit()

    # Correcting an auto-detected type is rejected — normal flow is automatic.
    with pytest.raises(Exception) as exc_info:
        documents_mod.correct_classification(
            detected.id,
            DocumentTypeUpdate(document_type="PAN_CERTIFICATE"),
            db=db, user=user,
        )
    assert exc_info.value.status_code == 400

    unknown = Document(
        bid_id=bid.id, document_type="UNCLASSIFIED", filename="b.pdf",
        file_path="/tmp/b.pdf", file_hash="0" * 64, file_size=1,
        mime_type="application/pdf", processing_status="REVIEW_REQUIRED",
    )
    db.add(unknown)
    db.commit()

    # Exception case: the officer classifies it manually.
    updated = documents_mod.correct_classification(
        unknown.id,
        DocumentTypeUpdate(document_type="GST_CERTIFICATE"),
        db=db, user=user,
    )
    assert updated.document_type == "GST_CERTIFICATE"
    assert updated.processing_status == "PROCESSED"

    # Correcting to UNCLASSIFIED is meaningless — rejected.
    unknown2 = Document(
        bid_id=bid.id, document_type="UNCLASSIFIED", filename="c.pdf",
        file_path="/tmp/c.pdf", file_hash="0" * 64, file_size=1,
        mime_type="application/pdf", processing_status="REVIEW_REQUIRED",
    )
    db.add(unknown2)
    db.commit()
    with pytest.raises(Exception) as exc_info2:
        documents_mod.correct_classification(
            unknown2.id,
            DocumentTypeUpdate(document_type="UNCLASSIFIED"),
            db=db, user=user,
        )
    assert exc_info2.value.status_code == 400


# ---------------------------------------------------------------------------
# New document types: pipeline storage + officer correction path
# ---------------------------------------------------------------------------

def test_pipeline_detects_emd_payment_type(db, tmp_path):
    bid = _make_bid(db)
    text = (
        "Earnest Money Deposit (EMD) — Payment Proof. "
        "Legal Name: Test Bidder Pvt Ltd. EMD Amount: Rs. 5,00,000. "
        "Payment Reference: NEFT/2026/001234. "
        "This evidences payment of the Earnest Money Deposit for the bid."
    )
    path = _pdf_with_text(tmp_path, "emd_receipt.pdf", text)
    doc = _insert_doc(db, bid, path)

    result = pipeline_service.process_document(db, doc.id)

    db.refresh(doc)
    assert doc.document_type == "EMD_PAYMENT"
    assert doc.processing_status == "PROCESSED"
    assert result["status"] == "PROCESSED"
    assert result["document_type"] == "EMD_PAYMENT"


def test_correction_to_new_document_types_allowed_for_unclassified(db):
    user = _make_officer(db)
    bid = _make_bid(db)

    unknown = Document(
        bid_id=bid.id, document_type="UNCLASSIFIED", filename="d.pdf",
        file_path="/tmp/d.pdf", file_hash="0" * 64, file_size=1,
        mime_type="application/pdf", processing_status="REVIEW_REQUIRED",
    )
    db.add(unknown)
    db.commit()

    # The officer can assign the newly added types in the exception case.
    for new_type in (
        "EMD_PAYMENT",
        "PAST_PERFORMANCE_CERTIFICATE",
        "NON_DEBARMENT_DECLARATION",
    ):
        updated = documents_mod.correct_classification(
            unknown.id,
            DocumentTypeUpdate(document_type=new_type),
            db=db, user=user,
        )
        assert updated.document_type == new_type
        # Reset to UNCLASSIFIED for the next iteration via direct update
        # (the API only corrects FROM unclassified).
        unknown.document_type = "UNCLASSIFIED"
        unknown.processing_status = "REVIEW_REQUIRED"
        db.commit()
