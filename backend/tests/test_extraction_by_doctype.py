"""Per-document-type extraction regression tests.

Every supported document template is rendered to a real PDF, run through the
real pipeline (PDF text extraction -> classification -> regex + LLM field
extraction -> persistence), and checked for its expected fields.

The Experience Certificate case is the regression test for the reported
issue: ``demo_apex_experience_certificate.pdf`` was classified correctly and
marked Processed, yet showed "0 structured fields extracted".

Also covered:
- regex fallbacks keep working when the LLM provider is unavailable
  (honest ``extraction_warning`` instead of a silent 0-field PROCESSED)
- re-processing replaces fields (no duplicates) and clears the warning
- normalization of amounts, dates and percents
"""
import hashlib

import pytest

from app.models.models import (
    Bidder,
    BidSubmission,
    Document,
    ExtractedField,
    Tender,
)
from app.seed.demo_bidder_profiles import demo_banner
from app.seed.demo_docs import (
    dossier_section_title,
    generate_dossier_pdf,
)
from app.services import pipeline_service
from app.services.llm_service import LLMError

# document type -> fields that MUST be extracted from the template's labeled
# lines (values come from _sample_data below, not hardcoded per bidder).
EXPECTED_FIELDS = {
    "PAN_CERTIFICATE": {"legal_name", "pan", "incorporation_date", "address",
                        "email", "phone"},
    "GST_CERTIFICATE": {"legal_name", "trade_name", "gstin", "pan",
                        "registration_date", "address"},
    "UDYAM_CERTIFICATE": {"legal_name", "udyam_number", "valid_until", "address"},
    "ITR": {"itr", "legal_name", "pan"},
    "TURNOVER_CERTIFICATE": {"legal_name", "turnover_inr", "turnover_period"},
    "EXPERIENCE_CERTIFICATE": {"legal_name", "experience_years"},
    "OEM_AUTHORIZATION": {"legal_name", "oem_name", "oem_authorization_valid",
                          "valid_until"},
    "EPFO_CERTIFICATE": {"legal_name", "epfo_code", "address"},
    "ESIC_CERTIFICATE": {"legal_name", "esic_code", "valid_until", "address"},
    "MII_DECLARATION": {"legal_name", "local_content_pct"},
    "STARTUP_INDIA_CERTIFICATE": {"legal_name", "startup_certificate_number",
                                  "dpiit_recognition"},
    "EMD_PAYMENT": {"legal_name", "emd_amount_inr", "payment_reference",
                    "payment_date", "beneficiary"},
    "PAST_PERFORMANCE_CERTIFICATE": {"legal_name", "past_performance_pct",
                                     "client_name"},
    "NON_DEBARMENT_DECLARATION": {"legal_name", "debarment_declaration"},
}

_SAMPLE_DATA = {
    "legal_name": "Apex Flow Systems Pvt. Ltd.",
    "trade_name": "Apex Flow",
    "pan": "AAKCA1234F",
    "gstin": "27AAKCA1234F1Z5",
    "incorporation_date": "12/04/2015",
    "registration_date": "01/07/2017",
    "address": "Plot 42, MIDC, Pune - 411026",
    "email": "contracts@apexflow-demo.in",
    "phone": "+91 98400 10001",
    "udyam": "UDYAM-MH-19-0012345",
    "valid_until": "31/12/2028",
    "acknowledgement_number": "ACK123456789012",
    "turnover": "Rs 12,40,00,000",
    "turnover_period": "FY 2022-23 to FY 2024-25",
    "experience": "5 years",
    "oem_name": "Kirloskar Demo Pumps Ltd.",
    "oem_authorization": "Yes, authorized",
    "epfo_code": "MH/123456/001",
    "esic_code": "11000123456789012",
    "local_content": "62%",
    "certificate_number": "DIPP12345",
    "dpiit_recognition": "Recognized",
    "emd_amount": "Rs 5,00,000",
    "emd_reference": "UTR SBIN2024001234",
    "emd_date": "15/03/2024",
    "emd_beneficiary": "CPCL Tender Account",
    "past_performance": "92%",
    "past_performance_client": "Demo Refinery Ltd.",
    "debarment_declaration": "Not debarred by any government body",
}


def _make_bid(db):
    t = Tender(tender_number="EXT-001", title="Extraction", organization="CPCL",
               department="P", status="OPEN")
    db.add(t)
    db.flush()
    bidder = Bidder(tender_id=t.id, legal_name=_SAMPLE_DATA["legal_name"],
                    bid_status="SUBMITTED")
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=t.id, bidder_id=bidder.id, status="SUBMITTED")
    db.add(bid)
    db.commit()
    return bid


def _process_template(db, tmp_path, bid, doc_type):
    pdf = generate_dossier_pdf(
        _SAMPLE_DATA["legal_name"],
        [(doc_type, dict(_SAMPLE_DATA))],
        banner=demo_banner(),
        title=dossier_section_title(doc_type, _SAMPLE_DATA),
        subtitle="Standalone demo evidence document.",
    )
    path = str(tmp_path / f"doc_{doc_type.lower()}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf)
    doc = Document(
        bid_id=bid.id, document_type="UNCLASSIFIED",
        filename=f"doc_{doc_type.lower()}.pdf", file_path=path,
        file_hash=hashlib.sha256(pdf).hexdigest(), file_size=len(pdf),
        mime_type="application/pdf", processing_status="UPLOADED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    pipeline_service.process_document(db, doc.id)
    db.refresh(doc)
    fields = {
        f.field_name: f
        for f in db.query(ExtractedField).filter_by(document_id=doc.id).all()
    }
    return doc, fields


@pytest.mark.parametrize("doc_type,expected", sorted(EXPECTED_FIELDS.items()))
def test_each_doctype_extracts_expected_fields(db, tmp_path, doc_type, expected):
    """Every supported template yields its labeled fields via the real pipeline."""
    bid = _make_bid(db)
    doc, fields = _process_template(db, tmp_path, bid, doc_type)
    assert doc.document_type == doc_type
    assert doc.processing_status == "PROCESSED"
    missing = expected - set(fields)
    assert not missing, f"{doc_type}: missing fields {sorted(missing)}"
    # every field persisted against this document
    assert all(f.document_id == doc.id for f in fields.values())


def test_experience_certificate_regression(db, tmp_path):
    """The reported case: readable experience certificate must not yield 0 fields.

    legal_name and experience_years come from the visible labeled lines; the
    experience value must reach the numeric form the MINIMUM rule consumes.
    """
    bid = _make_bid(db)
    doc, fields = _process_template(db, tmp_path, bid, "EXPERIENCE_CERTIFICATE")
    assert len(fields) >= 2
    assert fields["legal_name"].normalized_value == "Apex Flow Systems Pvt. Ltd."
    assert float(fields["experience_years"].normalized_value) == 5.0


def test_experience_regex_fallback_without_llm(db, tmp_path, monkeypatch):
    """If the LLM provider is down, experience_years still extracts via regex."""
    from app.services import llm_service

    class _Dead:
        name = "dead-provider"

        def extract_fields(self, *a, **k):
            raise LLMError("dead-provider: simulated outage")

    monkeypatch.setattr(llm_service, "get_llm_provider", lambda: _Dead())
    bid = _make_bid(db)
    doc, fields = _process_template(db, tmp_path, bid, "EXPERIENCE_CERTIFICATE")
    assert doc.processing_status == "PROCESSED"
    assert "experience_years" in fields
    assert fields["experience_years"].extraction_method == "REGEX"
    # honest, actionable status instead of a silent 0-field PROCESSED
    assert doc.extraction_warning
    assert "re-process" in doc.extraction_warning.lower()


def test_epfo_esic_regex_fallback_without_llm(db, tmp_path, monkeypatch):
    from app.services import llm_service

    class _Dead:
        name = "dead-provider"

        def extract_fields(self, *a, **k):
            raise LLMError("dead-provider: simulated outage")

    monkeypatch.setattr(llm_service, "get_llm_provider", lambda: _Dead())
    bid = _make_bid(db)
    doc, fields = _process_template(db, tmp_path, bid, "EPFO_CERTIFICATE")
    assert "epfo_code" in fields
    assert fields["epfo_code"].normalized_value == "MH/123456/001"
    doc2, fields2 = _process_template(db, tmp_path, bid, "ESIC_CERTIFICATE")
    assert "esic_code" in fields2
    assert fields2["esic_code"].normalized_value == "11000123456789012"
    assert doc2.extraction_warning


def test_reprocess_clears_warning_without_duplicates(db, tmp_path, monkeypatch):
    """A clean re-process clears the warning and replaces (not stacks) fields."""
    from app.services import llm_service

    class _Dead:
        name = "dead-provider"

        def extract_fields(self, *a, **k):
            raise LLMError("dead-provider: simulated outage")

    monkeypatch.setattr(llm_service, "get_llm_provider", lambda: _Dead())
    bid = _make_bid(db)
    doc, fields = _process_template(db, tmp_path, bid, "EXPERIENCE_CERTIFICATE")
    assert doc.extraction_warning
    n_before = len(fields)

    monkeypatch.setattr(
        llm_service, "get_llm_provider", lambda: llm_service.MockLLMProvider()
    )
    pipeline_service.process_document(db, doc.id)
    db.refresh(doc)
    after = db.query(ExtractedField).filter_by(document_id=doc.id).all()
    assert doc.extraction_warning is None
    assert len(after) == n_before + 1  # legal_name added by the live LLM
    names = [f.field_name for f in after]
    assert len(names) == len(set(names)), "duplicate field rows after reprocess"


def test_normalization_variants():
    """Amounts, dates and percents normalize across realistic spellings."""
    from app.services import regex_service as r

    assert r.normalize_amount("Rs 12,40,00,000") == 124000000
    assert r.normalize_amount("₹12.4 crore") == 124000000
    assert r.normalize_amount("INR 50 lakh") == 5000000
    assert r.normalize_date("15/03/2024") == "2024-03-15"
    assert r.normalize_date("15 Mar 2024") == "2024-03-15"
    assert r.normalize_percent("62%") == 62.0
    assert r.normalize_percent("62 percent") == 62.0


def test_experience_label_variants():
    """'Experience: 5 years' and '5 years of experience' both extract."""
    from app.services import regex_service as r

    got = {f["field_name"]: f["normalized_value"]
           for f in r.extract_all("Experience: 5 years")}
    assert got.get("experience_years") == "5.0"
    got = {f["field_name"]: f["normalized_value"]
           for f in r.extract_all("The firm has 12 years of experience.")}
    assert got.get("experience_years") == "12.0"
    # ...but a bare duration with no experience context must not match
    got = {f["field_name"] for f in r.extract_all("Incorporated 5 years ago.")}
    assert "experience_years" not in got


def test_startup_india_identifier_resolves(db, tmp_path):
    """The STARTUP_INDIA verification source resolves from the extracted
    ``startup_certificate_number`` field (previously looked up a
    ``startup_cert_no`` key that extraction never produces, so the adapter
    never ran)."""
    from app.services.verification_service import resolve_identifiers

    bid = _make_bid(db)
    doc, fields = _process_template(db, tmp_path, bid, "STARTUP_INDIA_CERTIFICATE")
    assert "startup_certificate_number" in fields
    resolved = resolve_identifiers(db, bid.id)
    assert resolved.get("STARTUP_INDIA") == fields["startup_certificate_number"].normalized_value


def test_mock_llm_empty_label_does_not_swallow_next_line():
    """An empty 'Label:' must not capture the following paragraph.

    Regression: the earlier \\s*-based pattern let an empty label cross the
    line boundary and store the next paragraph as the field value
    (a false-positive client_name on past-performance docs).
    """
    from app.services.llm_service import MockLLMProvider

    text = (
        "SAMPLE — FOR DEMONSTRATION ONLY\n"
        "Legal Name: Apex Flow Systems Pvt. Ltd.\n"
        "Client:\n"
        "\n"
        "This is a body paragraph about services rendered.\n"
    )
    got = MockLLMProvider().extract_fields("PAST_PERFORMANCE_CERTIFICATE", text, "x.pdf")
    assert got["legal_name"] == "Apex Flow Systems Pvt. Ltd."
    assert "client_name" not in got
