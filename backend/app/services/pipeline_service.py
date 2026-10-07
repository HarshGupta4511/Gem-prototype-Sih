"""Document processing pipeline orchestration (CONTRACT §9).

process_document(db, document_id, *, user_id=None) runs steps 1–6:
  1. read file, sha256, PyMuPDF page_count + per-page text
  2. OCR fallback when text < 50 chars (FAILED + OCR_UNAVAILABLE if no OCR)
  3. keyword classification (auto-detect; officer corrects via PATCH later)
  4. regex extraction per page (method REGEX)
  5. LLM extraction (method LLM; LLMError recorded, never fatal)
  6. dedupe (highest confidence wins; REGEX wins ties), persist
     ExtractedField rows, set extraction_confidence = mean confidence,
     status PROCESSED, audit DOCUMENT_PROCESSED
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)

OCR_UNAVAILABLE_ERROR = (
    "OCR_UNAVAILABLE: scanned document requires OCR which is not installed"
)
MIN_TEXT_CHARS = 50

_NON_FIELD_KEYS = {"provider", "confidence"}


def _split_pages(full_text: str) -> list[tuple[int, str]]:
    from app.services.extraction_service import split_pages

    return split_pages(full_text)


def _method_counts(fields: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in fields:
        counts[f["method"]] = counts.get(f["method"], 0) + 1
    return counts


def _dedupe(fields: list[dict]) -> list[dict]:
    """One row per field_name: highest confidence wins; REGEX wins ties."""

    def rank(f: dict) -> tuple[float, int]:
        return (float(f["confidence"] or 0.0), 1 if f["method"] == "REGEX" else 0)

    best: dict[str, dict] = {}
    for f in fields:
        cur = best.get(f["field_name"])
        if cur is None or rank(f) > rank(cur):
            best[f["field_name"]] = f
    return list(best.values())


def _fail(db, doc, *, error: str, user_id, pages: int, ocr_used: bool) -> dict:
    from app.models.models import Document  # noqa: F401  (typing clarity)
    from app.services.audit_service import append_audit

    doc.processing_status = "FAILED"
    doc.error = error
    doc.extraction_warning = None
    doc.ocr_used = ocr_used
    db.commit()
    append_audit(
        db,
        user_id=user_id,
        action="DOCUMENT_PROCESSED",
        entity_type="document",
        entity_id=str(doc.id),
        metadata={
            "document_id": doc.id,
            "fields": 0,
            "by_method": {},
            "ocr_used": ocr_used,
            "pages": pages,
            "error": error,
        },
    )
    log.warning("Document %s processing FAILED: %s", doc.id, error)
    return {
        "document_id": doc.id,
        "status": "FAILED",
        "error": error,
        "document_type": None,
        "classification_confidence": None,
        "pages": pages,
        "ocr_used": ocr_used,
        "extracted_fields": [],
    }


def _extract_from_bytes(content: bytes, filename: str) -> dict:
    """Run pipeline steps 1–5 on raw file bytes without any DB writes.

    Returns {"ok", "error", "page_count", "ocr_used", "document_type",
    "classification_confidence", "type_detected", "fields", "llm_error",
    "provider"}. ``fields`` are deduped candidate dicts with keys
    field_name/field_value/normalized_value/confidence/method/page_number.
    Shared by process_document (persisted flow) and the bidder-registration
    preview (no document row is created).
    """
    import tempfile

    from app.models.models import DocumentType
    from app.services import (
        classification_service,
        extraction_service,
        regex_service,
    )
    from app.services.llm_service import LLMError, get_llm_provider

    # ---- step 1: text via PyMuPDF ---------------------------------------
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        try:
            full_text, page_count = extraction_service.extract_text_pymupdf(tmp.name)
        except Exception as exc:
            # Corrupt/unreadable PDF — report cleanly instead of crashing.
            log.warning("Registration preview: could not read PDF: %s", exc)
            return {
                "ok": False,
                "error": "Could not read this PDF — the file may be corrupt.",
                "page_count": 0,
                "ocr_used": False,
            }

        # ---- step 2: OCR fallback for scanned documents ------------------
        ocr_used = False
        page_texts = _split_pages(full_text)
        total_chars = sum(len(t.strip()) for _, t in page_texts)
        if total_chars < MIN_TEXT_CHARS:
            if extraction_service.ocr_available():
                ocr_used = True
                ocr_text, ocr_error = extraction_service.run_ocr(tmp.name)
                if ocr_error or not ocr_text or len(ocr_text.strip()) < MIN_TEXT_CHARS:
                    return {
                        "ok": False,
                        "error": ocr_error or "OCR produced no usable text",
                        "page_count": page_count,
                        "ocr_used": True,
                    }
                full_text = ocr_text
                page_texts = _split_pages(full_text)
                page_count = len(page_texts)
            else:
                return {
                    "ok": False,
                    "error": OCR_UNAVAILABLE_ERROR,
                    "page_count": page_count,
                    "ocr_used": False,
                }

    # ---- step 3: classification (auto-detect) -----------------------------
    doc_type, class_conf = classification_service.classify_document(
        filename or "", full_text
    )
    type_detected = class_conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD
    stored_type = doc_type if type_detected else DocumentType.UNCLASSIFIED.value

    # ---- step 4: regex extraction per page --------------------------------
    # Document-aware: the classified type scopes ambiguous values (a bare
    # date on an EMD receipt is not the same field as a bare date on a
    # GST certificate).
    candidates: list[dict] = []
    for page_number, page_text in page_texts:
        candidates.extend(regex_service.extract_all(page_text, page_number, stored_type))

    # ---- step 5: LLM extraction -------------------------------------------
    provider = get_llm_provider()
    llm_error: str | None = None
    try:
        llm_data = provider.extract_fields(
            doc_type if type_detected else "generic",
            full_text,
            filename or "",
        )
        overall_conf = float(llm_data.get("confidence") or 0.9)
        for key, value in llm_data.items():
            if key in _NON_FIELD_KEYS or value is None:
                continue
            raw = value if isinstance(value, str) else str(value)
            candidates.append(
                {
                    "field_name": key,
                    "field_value": raw,
                    "normalized_value": str(value),
                    "confidence": overall_conf,
                    "method": "LLM",
                    "page_number": None,
                }
            )
    except LLMError as exc:
        llm_error = str(exc)
        log.warning("Registration preview: LLM extraction failed: %s", exc)

    return {
        "ok": True,
        "error": None,
        "page_count": page_count,
        "ocr_used": ocr_used,
        "document_type": stored_type,
        "classification_confidence": class_conf,
        "type_detected": type_detected,
        "fields": _dedupe(candidates),
        "llm_error": llm_error,
        "provider": provider.name,
    }


def preview_registration_document(content: bytes, filename: str) -> dict:
    """Extract bidder-registration details from an uploaded PDF without
    creating any Document row. Uses the exact same pipeline steps as
    process_document (text → OCR fallback → classification → regex + LLM).
    """
    res = _extract_from_bytes(content, filename)
    if not res["ok"]:
        return {
            "status": "FAILED",
            "error": res["error"],
            "filename": filename,
            "document_type": None,
            "classification_confidence": None,
            "pages": res["page_count"],
            "ocr_used": res["ocr_used"],
            "extracted_fields": [],
        }
    out: dict = {
        "status": "PROCESSED",
        "filename": filename,
        "document_type": res["document_type"],
        "classification_confidence": res["classification_confidence"],
        "type_detected": res["type_detected"],
        "pages": res["page_count"],
        "ocr_used": res["ocr_used"],
        "provider": res["provider"],
        "extracted_fields": [
            {
                "field_name": f["field_name"],
                "field_value": f["field_value"],
                "normalized_value": f["normalized_value"],
                "confidence": f["confidence"],
                "extraction_method": f["method"],
                "page_number": f["page_number"],
            }
            for f in sorted(res["fields"], key=lambda x: x["field_name"])
        ],
    }
    if res["llm_error"]:
        out["extraction_warning"] = (
            f"AI field extraction was unavailable ({res['llm_error']}). Only "
            "rule-based fields were extracted."
        )
    return out


def process_document(db, document_id: int, *, user_id: int | None = None) -> dict:
    from app.models.models import Document, ExtractedField
    from app.services.audit_service import append_audit

    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document {document_id} not found")

    doc.processing_status = "PROCESSING"
    doc.error = None
    db.commit()

    path = Path(doc.file_path)
    content = path.read_bytes()
    doc.file_hash = hashlib.sha256(content).hexdigest()
    doc.file_size = len(content)

    # Steps 1–5 (text → OCR fallback → classification → regex + LLM) run
    # through the shared extractor; step 6 below persists the results.
    res = _extract_from_bytes(content, doc.filename or "")
    if not res["ok"]:
        return _fail(
            db, doc,
            error=res["error"],
            user_id=user_id, pages=res["page_count"], ocr_used=res["ocr_used"],
        )

    page_count = res["page_count"]
    ocr_used = res["ocr_used"]
    doc.page_count = page_count
    doc.ocr_used = ocr_used
    stored_type = res["document_type"]
    class_conf = res["classification_confidence"]
    type_detected = res["type_detected"]
    # Content-driven: filename is supporting context only. Below the
    # confidence threshold the system must NOT invent a type — the document
    # is stored as UNCLASSIFIED and flagged REVIEW_REQUIRED so the officer
    # classifies it manually (exception case only).
    doc.document_type = stored_type
    fields = res["fields"]
    llm_error = res["llm_error"]
    provider_name = res["provider"]

    # ---- step 6: dedupe, persist, finalize --------------------------------
    # (fields are already deduped by _extract_from_bytes)
    # Re-processing replaces the previous extraction — delete old rows first
    # so repeated runs never stack duplicate fields.
    db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).delete()
    for f in fields:
        db.add(
            ExtractedField(
                document_id=doc.id,
                field_name=f["field_name"],
                field_value=f["field_value"],
                normalized_value=f["normalized_value"],
                confidence=float(f["confidence"] or 0.0),
                extraction_method=f["method"],
                page_number=f["page_number"],
            )
        )

    doc.extraction_confidence = (
        sum(float(f["confidence"] or 0.0) for f in fields) / len(fields)
        if fields
        else None
    )
    doc.processing_status = (
        "REVIEW_REQUIRED" if not type_detected else "PROCESSED"
    )
    doc.error = None
    # Honest degradation signal: if the LLM provider failed, the document is
    # still processed (classification + regex fields are real), but the
    # officer must see WHY some fields may be missing instead of a silent
    # "0 structured fields extracted". Cleared on the next clean run.
    if llm_error:
        doc.extraction_warning = (
            f"AI field extraction was unavailable ({llm_error}). Only "
            "rule-based fields were extracted; re-process the document once "
            "the AI provider is reachable."
        )
    else:
        doc.extraction_warning = None
    db.commit()

    final_status = doc.processing_status
    by_method = _method_counts(fields)
    metadata: dict = {
        "document_id": doc.id,
        "fields": len(fields),
        "by_method": by_method,
        "ocr_used": ocr_used,
        "pages": page_count,
        "classification": stored_type,
        "classification_confidence": class_conf,
        "type_detected": type_detected,
        "provider": provider_name,
    }
    if llm_error:
        metadata["llm_error"] = llm_error
    append_audit(
        db,
        user_id=user_id,
        action="DOCUMENT_PROCESSED",
        entity_type="document",
        entity_id=str(doc.id),
        metadata=metadata,
    )

    log.info(
        "Document %s processed: type=%s fields=%d by_method=%s",
        doc.id, stored_type, len(fields), by_method,
    )
    return {
        "document_id": doc.id,
        "status": final_status,
        "document_type": stored_type,
        "classification_confidence": class_conf,
        "pages": page_count,
        "ocr_used": ocr_used,
        "extracted_fields": [
            {
                "field_name": f["field_name"],
                "field_value": f["field_value"],
                "normalized_value": f["normalized_value"],
                "confidence": f["confidence"],
                "extraction_method": f["method"],
                "page_number": f["page_number"],
            }
            for f in sorted(fields, key=lambda x: x["field_name"])
        ],
    }
