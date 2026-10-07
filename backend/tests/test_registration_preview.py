"""Tests for the bidder-registration extraction preview.

preview_registration_document runs the exact same pipeline steps as
process_document (text → OCR fallback → classification → regex + LLM)
without creating any Document row.
"""
from pathlib import Path
from datetime import datetime, timezone

from app.models.models import Document
from app.services import pipeline_service

SAMPLES = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "sample-documents"


def _sample_bytes(name: str) -> bytes:
    p = SAMPLES / name
    assert p.exists(), f"missing sample {p}"
    return p.read_bytes()


def test_preview_extracts_pan_card_without_db_row(db):
    content = _sample_bytes("sample-pan-card.pdf")
    before = db.query(Document).count()
    res = pipeline_service.preview_registration_document(content, "sample-pan-card.pdf")
    assert res["status"] == "PROCESSED"
    assert "PAN" in (res["document_type"] or "")
    fields = {f["field_name"]: f["field_value"] for f in res["extracted_fields"]}
    assert fields.get("pan"), f"expected pan field, got {sorted(fields)}"
    # No Document row was created.
    assert db.query(Document).count() == before


def test_preview_extracts_gst_certificate(db):
    content = _sample_bytes("sample-gst-certificate.pdf")
    res = pipeline_service.preview_registration_document(content, "gst.pdf")
    assert res["status"] == "PROCESSED"
    fields = {f["field_name"]: f["field_value"] for f in res["extracted_fields"]}
    assert fields.get("gstin"), f"expected gstin field, got {sorted(fields)}"


def test_preview_matches_process_document_fields(db, tmp_path):
    """The preview returns the same fields the persisted pipeline would."""
    from app.models.models import Bidder, BidSubmission, Tender
    from app.services import document_service

    content = _sample_bytes("sample-pan-card.pdf")
    preview = pipeline_service.preview_registration_document(content, "pan.pdf")
    preview_fields = {
        (f["field_name"], f["field_value"]) for f in preview["extracted_fields"]
    }

    tender = Tender(tender_number="REG-PREV-1", title="t", organization="o",
                    department="d")
    db.add(tender)
    db.commit()
    db.refresh(tender)
    bidder = Bidder(tender_id=tender.id, legal_name="Preview Pvt Ltd")
    db.add(bidder)
    db.commit()
    db.refresh(bidder)
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id)
    db.add(bid)
    db.commit()
    db.refresh(bid)

    file_path, file_hash, file_size = document_service.save_upload(
        content, "pan.pdf", bid.id
    )
    doc = Document(
        bid_id=bid.id,
        document_type="UNCLASSIFIED",
        filename="pan.pdf",
        file_path=file_path,
        file_hash=file_hash,
        file_size=file_size,
        mime_type="application/pdf",
        upload_time=datetime.now(timezone.utc),
        processing_status="UPLOADED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    try:
        out = pipeline_service.process_document(db, doc.id)
        assert out["status"] == "PROCESSED"
        persisted = {(f["field_name"], f["field_value"]) for f in out["extracted_fields"]}
        assert preview_fields == persisted
    finally:
        from app.models.models import ExtractedField

        db.query(ExtractedField).filter(
            ExtractedField.document_id == doc.id
        ).delete()
        db.delete(doc)
        db.commit()


def test_preview_garbage_pdf_fails_gracefully(db):
    res = pipeline_service.preview_registration_document(
        b"%PDF-1.4 not really a pdf with no text at all" + b" " * 200,
        "empty.pdf",
    )
    # Either FAILED (no usable text) or PROCESSED with zero fields — never a crash.
    assert res["status"] in ("FAILED", "PROCESSED")
    if res["status"] == "FAILED":
        assert res["error"]
