"""End-to-end pipeline test on a generated demo PDF (CONTRACT §9, §17).

Generates one GST certificate via ``demo_docs.generate_pdf``, inserts the
Document row, runs the REAL ``pipeline_service.process_document`` and asserts
the document is PROCESSED with the expected extracted fields. No seed data.
"""
import hashlib

from app.models.models import Document
from app.seed.demo_docs import generate_pdf
from app.services.pipeline_service import process_document


def test_pipeline_e2e_gst_certificate(db, tmp_path):
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

    result = process_document(db, doc.id)

    assert result["status"] == "PROCESSED"
    assert result["document_type"] == "GST_CERTIFICATE"
    by_name = {f["field_name"]: f for f in result["extracted_fields"]}
    assert by_name["gstin"]["normalized_value"] == "27AAFCA1234E1Z5"
    assert by_name["pan"]["normalized_value"] == "AAFCA1234E"
    assert by_name["legal_name"]["normalized_value"] == "Apex Flow Systems Pvt Ltd"
    methods = {f["extraction_method"] for f in result["extracted_fields"]}
    assert methods <= {"REGEX", "LLM"}
    assert methods & {"REGEX", "LLM"}

    db.refresh(doc)
    assert doc.processing_status == "PROCESSED"
    assert doc.extraction_confidence is not None
