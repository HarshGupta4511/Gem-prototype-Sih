"""Keyword-based document classification (CONTRACT §9 step 3).

Score = count of keyword hits over (filename + text), lowercased.
confidence = min(0.95, 0.55 + 0.10 * hits). No hits -> ("UNCLASSIFIED", 0.4).

The filename is supporting context only — classification is driven by
document content keywords. The OEM rule additionally requires a
manufacturing-context keyword ("manufactur" / "original equipment")
alongside "oem" / "authoriz".

Callers treat confidence < CLASSIFICATION_CONFIDENCE_THRESHOLD as
"system could not confidently identify the type": the document is stored
as UNCLASSIFIED / REVIEW_REQUIRED and the officer corrects it manually.
"""
from __future__ import annotations

# (DocumentType, primary keywords, required-context keywords or None)
_RULES: list[tuple[str, list[str], list[str] | None]] = [
    ("GST_CERTIFICATE", ["gstin", "goods and services tax"], None),
    ("UDYAM_CERTIFICATE", ["udyam"], None),
    ("PAN_CERTIFICATE", ["permanent account number"], None),
    ("TURNOVER_CERTIFICATE", ["turnover"], None),
    ("OEM_AUTHORIZATION", ["oem", "authoriz"], ["manufactur", "original equipment"]),
    ("EPFO_CERTIFICATE", ["provident fund", "epfo"], None),
    ("ESIC_CERTIFICATE", ["state insurance", "esic"], None),
    ("MII_DECLARATION", ["local content", "make in india"], None),
    ("EXPERIENCE_CERTIFICATE", ["experience", "completion certificate"], None),
    ("ITR", ["income tax", "itr-", "acknowledgement"], None),
    ("STARTUP_INDIA_CERTIFICATE", ["startup india", "dpiit"], None),
    ("NSIC_CERTIFICATE", ["nsic"], None),
    (
        "AUDITED_FINANCIAL_STATEMENT",
        ["audited", "balance sheet", "financial statement"],
        None,
    ),
    ("DIGILOCKER_DOCUMENT", ["digilocker"], None),
    ("GST_RETURN", ["gst return", "gstr"], None),
]

_FALLBACK = ("UNCLASSIFIED", 0.4)

# Minimum confidence for the pipeline to accept the detected type.
# Below this the document is stored as UNCLASSIFIED and marked
# REVIEW_REQUIRED instead of inventing a type.
CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.55


def _hits(haystack: str, phrases: list[str]) -> int:
    return sum(haystack.count(p) for p in phrases)


def classify_document(filename: str, text: str) -> tuple[str, float]:
    """Return (DocumentType value, confidence)."""
    haystack = f"{filename or ''}\n{text or ''}".lower()

    # Consolidated single-upload dossier: deterministic marker emitted by
    # our dossier generator (title "Consolidated Bid Dossier").
    if "consolidated bid dossier" in haystack:
        return "BID_DOSSIER", 0.95

    best_type, best_hits = _FALLBACK[0], 0
    for doc_type, keywords, required in _RULES:
        if required and not any(r in haystack for r in required):
            continue  # e.g. OEM mention without manufacturing context
        hits = _hits(haystack, keywords)
        if required:
            hits += _hits(haystack, required)
        if hits > best_hits:
            best_type, best_hits = doc_type, hits

    if best_hits == 0:
        return _FALLBACK
    return best_type, min(0.95, 0.55 + 0.10 * best_hits)
