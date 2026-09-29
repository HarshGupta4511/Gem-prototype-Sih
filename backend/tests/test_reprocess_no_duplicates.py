"""Re-processing a document must replace fields, never duplicate them."""
import hashlib

from app.models.models import Document, ExtractedField
from app.seed.demo_docs import generate_pdf
from app.services.pipeline_service import process_document


def _make_doc(db, tmp_path):
    pdf = generate_pdf("GST_CERTIFICATE", {
        "legal_name": "Apex Flow Systems Pvt Ltd",
        "trade_name": "Apex Flow Systems",
        "gstin": "27AAFCA1234E1Z5",
        "pan": "AAFCA1234E",
        "registration_date": "15-06-2021",
        "address": "Plot 42, MIDC Industrial Area, Mumbai 400093",
    })
    path = tmp_path / "gst_certificate.pdf"
    path.write_bytes(pdf)
    doc = Document(
        bid_id=1, document_type="GST_CERTIFICATE", filename="gst_certificate.pdf",
        file_path=str(path), file_hash=hashlib.sha256(pdf).hexdigest(),
        file_size=len(pdf), mime_type="application/pdf",
        processing_status="UPLOADED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _field_count(db, doc_id):
    return (
        db.query(ExtractedField)
        .filter(ExtractedField.document_id == doc_id)
        .count()
    )


def test_reprocess_does_not_duplicate_fields(db, tmp_path):
    doc = _make_doc(db, tmp_path)

    r1 = process_document(db, doc.id)
    assert r1["status"] == "PROCESSED"
    n1 = _field_count(db, doc.id)
    assert n1 > 0

    r2 = process_document(db, doc.id)
    assert r2["status"] == "PROCESSED"
    n2 = _field_count(db, doc.id)

    assert n2 == n1, f"re-process duplicated fields: {n1} -> {n2}"
