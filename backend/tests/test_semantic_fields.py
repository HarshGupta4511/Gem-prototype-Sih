"""Tests for semantic extraction and cross-document consistency.

Covers the required cases:
A. GST registration date + EMD receipt date -> NO mismatch
B. PAN same in PAN Card + GST Certificate -> consolidated, NO mismatch
C. PAN different -> genuine PAN MISMATCH, both values visible
D. GSTIN same -> consolidated, NO mismatch
E. GSTIN different -> genuine mismatch
F. ISO issue date + GST registration date -> NO mismatch
G. Balance Sheet FY + ITR FY -> separate fields, no forced comparison
H. Same document, multiple dates -> kept by semantic label, never collapsed
"""
from app.services import semantic_fields
from app.services.regex_service import extract_all


def _row(doc_type, field_name, value, doc_id=1, filename="d.pdf"):
    return {
        "field_name": field_name,
        "field_value": value,
        "normalized_value": value,
        "extraction_method": "REGEX",
        "confidence": 0.95,
        "page_number": 1,
        "document_id": doc_id,
        "document_type": doc_type,
        "filename": filename,
    }


def _by_label(entities, label):
    return [e for e in entities if e["field_name"] == label]


def test_a_gst_reg_date_vs_emd_receipt_date_no_mismatch():
    # Document-aware classification gives them different semantic names.
    gst_fields = extract_all("Registration Date: 15-06-2021", 1, "GST_CERTIFICATE")
    emd_fields = extract_all("Payment Date: 20-09-2026", 1, "EMD_RECEIPT")
    gst_date = next(f["field_name"] for f in gst_fields)
    emd_date = next(f["field_name"] for f in emd_fields)
    assert gst_date == "registration_date"
    assert emd_date == "receipt_date"
    assert gst_date != emd_date

    entities = semantic_fields.build_semantic_view([
        _row("GST_CERTIFICATE", gst_date, "15-06-2021", doc_id=1, filename="gst.pdf"),
        _row("EMD_RECEIPT", emd_date, "20-09-2026", doc_id=2, filename="emd.pdf"),
    ])
    assert len(entities) == 2
    assert all(not e["has_conflict"] for e in entities)


def test_b_pan_same_consolidated():
    entities = semantic_fields.build_semantic_view([
        _row("PAN_CERTIFICATE", "pan", "ABCDE1234F", doc_id=1, filename="pan.pdf"),
        _row("GST_CERTIFICATE", "pan", "ABCDE1234F", doc_id=2, filename="gst.pdf"),
    ])
    assert len(entities) == 1
    e = entities[0]
    assert e["scope"] == "shared"
    assert not e["has_conflict"]
    assert len(e["values"]) == 1
    assert e["values"][0]["normalized_value"] == "ABCDE1234F"
    assert e["source_count"] == 2
    assert {s["filename"] for s in e["values"][0]["sources"]} == {"pan.pdf", "gst.pdf"}


def test_c_pan_different_genuine_mismatch():
    entities = semantic_fields.build_semantic_view([
        _row("PAN_CERTIFICATE", "pan", "ABCDE1234F", doc_id=1, filename="pan.pdf"),
        _row("GST_CERTIFICATE", "pan", "XYZAB9876K", doc_id=2, filename="gst.pdf"),
    ])
    assert len(entities) == 1
    e = entities[0]
    assert e["has_conflict"] is True
    vals = {v["normalized_value"] for v in e["values"]}
    assert vals == {"ABCDE1234F", "XYZAB9876K"}
    # Each value keeps its own source document.
    for v in e["values"]:
        assert len(v["sources"]) == 1


def test_d_gstin_same_consolidated():
    entities = semantic_fields.build_semantic_view([
        _row("GST_CERTIFICATE", "gstin", "27ABCDE1234F1Z5", doc_id=1),
        _row("GST_CERTIFICATE", "gstin", "27ABCDE1234F1Z5", doc_id=2),
    ])
    assert len(entities) == 1
    assert not entities[0]["has_conflict"]


def test_e_gstin_different_genuine_mismatch():
    entities = semantic_fields.build_semantic_view([
        _row("GST_CERTIFICATE", "gstin", "27ABCDE1234F1Z5", doc_id=1),
        _row("GST_CERTIFICATE", "gstin", "27XYZAB9876K1Z5", doc_id=2),
    ])
    assert len(entities) == 1
    assert entities[0]["has_conflict"] is True


def test_f_iso_issue_date_vs_gst_reg_date_no_mismatch():
    iso_fields = extract_all("Date of Issue: 01-03-2022", 1, "ISO_9001_CERTIFICATE")
    gst_fields = extract_all("Registration Date: 15-06-2021", 1, "GST_CERTIFICATE")
    iso_date = next(f["field_name"] for f in iso_fields)
    gst_date = next(f["field_name"] for f in gst_fields)
    assert iso_date == "issue_date"
    assert gst_date == "registration_date"
    entities = semantic_fields.build_semantic_view([
        _row("ISO_9001_CERTIFICATE", iso_date, "01-03-2022", doc_id=1),
        _row("GST_CERTIFICATE", gst_date, "15-06-2021", doc_id=2),
    ])
    assert len(entities) == 2
    assert all(not e["has_conflict"] for e in entities)


def test_g_balance_sheet_fy_vs_itr_fy_stay_separate():
    # Different semantic fields already; the semantic layer must not
    # force-compare them — compliance rules reference each explicitly.
    entities = semantic_fields.build_semantic_view([
        _row("BALANCE_SHEET", "financial_year", "2023-24", doc_id=1),
        _row("ITR_DOCUMENT", "itr_financial_year", "2022-23", doc_id=2),
    ])
    assert len(entities) == 2
    assert all(not e["has_conflict"] for e in entities)
    assert all(e["scope"] == "document" for e in entities)


def test_h_same_doc_multiple_dates_kept_separate():
    fields = extract_all(
        "Date of Issue: 01-03-2022. Date of Expiry: 28-02-2025.", 1,
        "ISO_9001_CERTIFICATE",
    )
    names = {f["field_name"] for f in fields}
    assert "issue_date" in names
    assert "expiry_date" in names
    # Both survive the pipeline dedupe (keyed by field_name).
    from app.services.pipeline_service import _dedupe

    deduped = _dedupe(fields)
    assert {f["field_name"] for f in deduped} == {"issue_date", "expiry_date"}


def test_bare_date_fallback_is_document_aware():
    # A context-free date never collapses to a bare generic "date" shared
    # across document types.
    gst = extract_all("15-06-2021", 1, "GST_CERTIFICATE")
    emd = extract_all("20-09-2026", 1, "EMD_RECEIPT")
    assert gst and emd
    assert gst[0]["field_name"] != emd[0]["field_name"]
    assert gst[0]["field_name"] == "registration_date"
    assert emd[0]["field_name"] == "receipt_date"


def test_shared_fields_set():
    for f in ("pan", "gstin", "cin", "udyam_number", "legal_name", "trade_name"):
        assert semantic_fields.is_shared(f), f
    for f in ("registration_date", "receipt_date", "date", "amount_inr",
              "address", "turnover_inr"):
        assert not semantic_fields.is_shared(f), f


def test_empty_values_never_merge_or_mismatch():
    entities = semantic_fields.build_semantic_view([
        _row("PAN_CERTIFICATE", "pan", "", doc_id=1),
        _row("GST_CERTIFICATE", "pan", "", doc_id=2),
    ])
    # Empty values stay visible but never read as a value conflict.
    assert len(entities) == 1
    assert entities[0]["is_empty"] is True
    assert entities[0]["has_conflict"] is False


def test_empty_plus_real_value_no_conflict():
    entities = semantic_fields.build_semantic_view([
        _row("PAN_CERTIFICATE", "pan", "", doc_id=1),
        _row("GST_CERTIFICATE", "pan", "ABCDE1234F", doc_id=2),
    ])
    assert len(entities) == 1
    assert entities[0]["has_conflict"] is False
