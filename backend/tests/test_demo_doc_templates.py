"""Tests for the five new demo evidence templates (Stage 2 catalogue).

Each template must:
  1. generate via ``generate_pdf`` / ``generate_dossier_pdf`` without error,
  2. render the literal "SAMPLE — FOR DEMONSTRATION ONLY" marking in the
     extracted PDF text (PyMuPDF — the same extractor the pipeline uses),
  3. yield its key fields through the deterministic regex extractors,
  4. classify to its own DocumentType via the keyword classifier
     (no confusion with neighbouring types, e.g. EMD_RECEIPT vs
     EMD_PAYMENT or BALANCE_SHEET vs AUDITED_FINANCIAL_STATEMENT),
  5. expose its labeled lines through the MockLLM label map.

All data is fictional.
"""
import fitz  # PyMuPDF — the same extractor the pipeline uses

from app.seed.demo_bidder_profiles import demo_banner
from app.seed.demo_docs import (
    _paragraphs,
    dossier_section_title,
    generate_dossier_pdf,
    generate_pdf,
)
from app.services import classification_service, regex_service
from app.services.llm_service import MockLLMProvider

LEGAL_NAME = "Apex Flow Systems Private Limited"

SPECS: dict[str, dict] = {
    "BALANCE_SHEET": {
        "legal_name": LEGAL_NAME,
        "financial_year": "2023-24",
        "turnover": "Rs 1.8 crore",
        "auditor_name": "R. Krishnan & Associates (demo)",
    },
    "ISO_9001_CERTIFICATE": {
        "legal_name": LEGAL_NAME,
        "iso_certificate_number": "ISO-2024-88412",
        "iso_valid_from": "01-04-2024",
        "iso_valid_until": "31-03-2027",
    },
    "MCA21_CERTIFICATE": {
        "legal_name": LEGAL_NAME,
        "cin": "U28999MH2015PTC123456",
        "incorporation_date": "12-03-2015",
        "company_status": "Active",
    },
    "ITR_DOCUMENT": {
        "legal_name": LEGAL_NAME,
        "pan": "AAFCA1234E",
        "itr_financial_year": "2023-24",
        "assessment_year": "2024-25",
        "total_income": "Rs 48,50,000",
    },
    "EMD_RECEIPT": {
        "legal_name": LEGAL_NAME,
        "emd_amount": "Rs 5,00,000",
        "emd_reference": "DEMO-UTR-20260920",
        "emd_date": "20-09-2026",
        "emd_beneficiary": "Demo Tendering Authority",
    },
}


def _text(pdf: bytes) -> str:
    return "\n".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))


def _fields(pdf: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in regex_service.extract_all(_text(pdf)):
        out.setdefault(f["field_name"], f["normalized_value"])
    return out


# ------------------------------------------------------- template rendering
def test_all_new_templates_generate_with_titles():
    for doc_type, data in SPECS.items():
        title, lines, paras = _paragraphs(doc_type, data)
        assert title, doc_type
        assert lines and paras, doc_type
        # dossier_section_title() is the standalone-document heading path.
        assert dossier_section_title(doc_type, data) == title, doc_type
        pdf = generate_pdf(doc_type, data)
        assert pdf.startswith(b"%PDF"), doc_type


def test_sample_marking_in_extracted_text():
    for doc_type, data in SPECS.items():
        pdf = generate_dossier_pdf(
            LEGAL_NAME, [(doc_type, data)], banner=demo_banner(),
            title=dossier_section_title(doc_type, data),
        )
        text = _text(pdf)
        assert "SAMPLE" in text and "FOR DEMONSTRATION ONLY" in text, doc_type


# ------------------------------------------------------- classification
def test_new_types_classify_correctly():
    for doc_type, data in SPECS.items():
        pdf = generate_pdf(doc_type, data)
        detected, conf = classification_service.classify_document(
            f"demo_test_{doc_type.lower()}.pdf", _text(pdf))
        assert detected == doc_type, f"{doc_type}: got {detected}"
        assert conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD


def test_new_types_do_not_confuse_neighbours():
    # EMD_RECEIPT must not steal EMD_PAYMENT documents and vice versa.
    emd_old = _text(generate_pdf("EMD_PAYMENT", {
        "legal_name": LEGAL_NAME, "emd_amount": "Rs 5,00,000",
        "emd_reference": "X", "emd_date": "20-09-2026",
        "emd_beneficiary": "Demo Tendering Authority",
    }))
    detected, _ = classification_service.classify_document("pay.pdf", emd_old)
    assert detected == "EMD_PAYMENT"
    # ITR_DOCUMENT must not collapse into the legacy ITR type.
    itr_old = _text(generate_pdf("ITR", {
        "legal_name": LEGAL_NAME, "pan": "AAFCA1234E",
        "acknowledgement_number": "123456789012345",
    }))
    detected, _ = classification_service.classify_document("old_itr.pdf", itr_old)
    assert detected == "ITR"


# ------------------------------------------------------- regex extraction
def test_balance_sheet_extraction():
    f = _fields(generate_pdf("BALANCE_SHEET", SPECS["BALANCE_SHEET"]))
    assert f["turnover_inr"] == "18000000"
    # The balance sheet's year is its own field — it must NOT leak into
    # itr_financial_year (that field belongs to the ITR document alone).
    assert f["financial_year"] == "2023-24"
    assert "itr_financial_year" not in f


def test_iso_extraction():
    f = _fields(generate_pdf("ISO_9001_CERTIFICATE", SPECS["ISO_9001_CERTIFICATE"]))
    assert f["iso_certificate_number"] == "ISO-2024-88412"
    assert f["iso_valid_until"] == "2027-03-31"


def test_mca21_extraction_reuses_cin_extractor():
    f = _fields(generate_pdf("MCA21_CERTIFICATE", SPECS["MCA21_CERTIFICATE"]))
    assert f["cin"] == "U28999MH2015PTC123456"
    assert f["incorporation_date"] == "2015-03-12"


def test_itr_document_extraction():
    f = _fields(generate_pdf("ITR_DOCUMENT", SPECS["ITR_DOCUMENT"]))
    assert f["itr_financial_year"] == "2023-24"
    assert f["pan"] == "AAFCA1234E"


def test_emd_receipt_extraction_reuses_emd_extractor():
    f = _fields(generate_pdf("EMD_RECEIPT", SPECS["EMD_RECEIPT"]))
    assert f["emd_amount_inr"] == "500000"


# ------------------------------------------------------- MockLLM label map
def test_mockllm_labels_for_new_templates():
    llm = MockLLMProvider()
    iso_text = _text(generate_pdf("ISO_9001_CERTIFICATE", SPECS["ISO_9001_CERTIFICATE"]))
    out = llm.extract_fields("ISO_9001_CERTIFICATE", iso_text, "iso.pdf")
    assert out["iso_certificate_number"] == "ISO-2024-88412"
    assert out["iso_valid_from"] == "2024-04-01"
    assert out["iso_valid_until"] == "2027-03-31"

    itr_text = _text(generate_pdf("ITR_DOCUMENT", SPECS["ITR_DOCUMENT"]))
    out = llm.extract_fields("ITR_DOCUMENT", itr_text, "itr.pdf")
    assert out["itr_financial_year"] == "2023-24"
    assert out["assessment_year"] == "2024-25"
    assert out["total_income"] == 4850000

    bs_text = _text(generate_pdf("BALANCE_SHEET", SPECS["BALANCE_SHEET"]))
    out = llm.extract_fields("BALANCE_SHEET", bs_text, "bs.pdf")
    assert out["auditor_name"] == "R. Krishnan & Associates (demo)"

    mca_text = _text(generate_pdf("MCA21_CERTIFICATE", SPECS["MCA21_CERTIFICATE"]))
    out = llm.extract_fields("MCA21_CERTIFICATE", mca_text, "mca.pdf")
    assert out["company_status"] == "Active"
    assert out["cin"] == "U28999MH2015PTC123456"
