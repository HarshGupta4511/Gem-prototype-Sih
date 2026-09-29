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


def process_document(db, document_id: int, *, user_id: int | None = None) -> dict:
    from app.models.models import Document, DocumentType, ExtractedField
    from app.services import (
        classification_service,
        extraction_service,
        llm_service,
        regex_service,
    )
    from app.services.audit_service import append_audit
    from app.services.llm_service import LLMError, get_llm_provider

    doc = db.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document {document_id} not found")

    # ---- step 1: read, hash, open with PyMuPDF ---------------------------
    doc.processing_status = "PROCESSING"
    doc.error = None
    db.commit()

    path = Path(doc.file_path)
    content = path.read_bytes()
    doc.file_hash = hashlib.sha256(content).hexdigest()
    doc.file_size = len(content)

    full_text, page_count = extraction_service.extract_text_pymupdf(str(path))
    doc.page_count = page_count

    # ---- step 2: OCR fallback for scanned documents ----------------------
    ocr_used = False
    page_texts = _split_pages(full_text)
    total_chars = sum(len(t.strip()) for _, t in page_texts)
    if total_chars < MIN_TEXT_CHARS:
        if extraction_service.ocr_available():
            ocr_used = True
            ocr_text, ocr_error = extraction_service.run_ocr(str(path))
            if ocr_error or not ocr_text or len(ocr_text.strip()) < MIN_TEXT_CHARS:
                return _fail(
                    db, doc,
                    error=ocr_error or "OCR produced no usable text",
                    user_id=user_id, pages=page_count, ocr_used=True,
                )
            full_text = ocr_text
            page_texts = _split_pages(full_text)
            doc.page_count = len(page_texts)
            page_count = len(page_texts)
            doc.ocr_used = True
        else:
            return _fail(
                db, doc,
                error=OCR_UNAVAILABLE_ERROR,
                user_id=user_id, pages=page_count, ocr_used=False,
            )

    # ---- step 3: classification (auto-detect) -----------------------------
    # Content-driven: filename is supporting context only. Below the
    # confidence threshold the system must NOT invent a type — the document
    # is stored as UNCLASSIFIED and flagged REVIEW_REQUIRED so the officer
    # classifies it manually (exception case only).
    doc_type, class_conf = classification_service.classify_document(
        doc.filename or "", full_text
    )
    type_detected = class_conf >= classification_service.CLASSIFICATION_CONFIDENCE_THRESHOLD
    stored_type = doc_type if type_detected else DocumentType.UNCLASSIFIED.value
    doc.document_type = stored_type

    # ---- step 4: regex extraction per page --------------------------------
    candidates: list[dict] = []
    for page_number, page_text in page_texts:
        candidates.extend(regex_service.extract_all(page_text, page_number))

    # ---- step 5: LLM extraction -------------------------------------------
    provider = get_llm_provider()
    llm_error: str | None = None
    try:
        llm_data = provider.extract_fields(
            doc_type if type_detected else "generic",
            full_text,
            doc.filename or "",
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
        log.warning("LLM extraction failed for document %s: %s", doc.id, exc)

    # ---- step 6: dedupe, persist, finalize --------------------------------
    fields = _dedupe(candidates)
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
        "provider": provider.name,
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
