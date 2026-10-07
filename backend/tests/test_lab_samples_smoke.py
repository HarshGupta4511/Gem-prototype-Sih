"""Regression test: the 10 Verification Lab benchmark PDFs run through the real
upload → classify → extract pipeline and produce the expected document types
and identifier fields."""
import asyncio
import io
import pathlib

import pytest
from fastapi import UploadFile

import app.api.documents as documents_mod
from app.models.models import Bidder, BidSubmission, ExtractedField, Tender, User

SAMPLE_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend" / "public" / "sample-documents"
)

SAMPLES = [
    ("sample-udyam-certificate.pdf", "UDYAM_CERTIFICATE", "udyam_number"),
    ("sample-gst-certificate.pdf", "GST_CERTIFICATE", "gstin"),
    ("sample-pan-card.pdf", "PAN_CERTIFICATE", "pan"),
    ("sample-itr-document.pdf", "ITR_DOCUMENT", "pan"),
    ("sample-mca21-certificate.pdf", "MCA21_CERTIFICATE", "cin"),
    ("sample-balance-sheet.pdf", "BALANCE_SHEET", None),
    ("sample-experience-certificate.pdf", "EXPERIENCE_CERTIFICATE", None),
    ("sample-iso-9001-certificate.pdf", "ISO_9001_CERTIFICATE", None),
    ("sample-emd-receipt.pdf", "EMD_RECEIPT", None),
    ("sample-epfo-registration.pdf", "EPFO_CERTIFICATE", None),
]


def _make_bid(db):
    tender = Tender(
        tender_number="TEST-LAB-001", title="Lab smoke test",
        organization="CPCL", department="Materials",
    )
    db.add(tender)
    db.commit()
    db.refresh(tender)
    bidder = Bidder(tender_id=tender.id, legal_name="Lab Bidder Pvt Ltd")
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
        name="officer", email="labofficer@test.local",
        password_hash="x", role="PROCUREMENT_OFFICER",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.parametrize("filename,expected_type,expected_field", SAMPLES)
def test_lab_sample_pipeline(db, filename, expected_type, expected_field):
    src = SAMPLE_DIR / filename
    assert src.exists(), f"missing sample {filename}"
    bid = _make_bid(db)
    user = _make_officer(db)

    upload = UploadFile(file=io.BytesIO(src.read_bytes()), filename=filename)
    doc = asyncio.run(documents_mod.upload_document(
        bid_id=bid.id, document_type=None, file=upload, db=db, user=user
    ))

    assert doc.document_type == expected_type, (
        f"{filename}: got {doc.document_type}"
    )
    assert doc.processing_status == "PROCESSED", (
        f"{filename}: status {doc.processing_status}"
    )
    fields = db.query(ExtractedField).filter_by(document_id=doc.id).all()
    names = {f.field_name for f in fields}
    assert len(names) > 0, f"{filename}: no fields extracted"
    if expected_field:
        assert expected_field in names, f"{filename}: missing {expected_field}"
