"""Semantic field layer for extracted information.

Raw extraction rows carry (document_type, field_name, value). Two rows with
the same field_name are NOT automatically the same semantic field: a
"registration_date" on a GST certificate and a "receipt_date" on an EMD
receipt must never be compared just because both are dates.

This module defines the semantic interpretation:

- SHARED_FIELDS: identifiers genuinely expected to stay consistent across
  documents (PAN, GSTIN, CIN, Udyam, legal/trade name, ...). Only these are
  ever cross-compared between documents.
- Everything else is document-scoped: the semantic key is
  (document_type, field_name), so document-specific fields remain separate.

build_semantic_view() groups raw rows into semantic entities for display:
- same shared field + same normalized value  → one entity, all sources kept
- same shared field + different values       → genuine CROSS-DOCUMENT MISMATCH,
  every value stays visible with its source document
- document-scoped fields                     → grouped per (document_type,
  field_name); differing values across documents of the same type are
  flagged for officer review, never silently merged

Raw extraction records are never altered here — this is a read-time
interpretation over stored rows.
"""

from __future__ import annotations

# Fields genuinely expected to remain consistent across documents. Only
# these participate in cross-document comparison.
SHARED_FIELDS = frozenset(
    {
        "pan",
        "gstin",
        "cin",
        "udyam_number",
        "legal_name",
        "trade_name",
        "epfo_code",
        "esic_code",
    }
)


def is_shared(field_name: str | None) -> bool:
    """True when the field is a cross-document identity/compliance field."""
    return (field_name or "").strip().lower() in SHARED_FIELDS


def semantic_key(document_type: str | None, field_name: str | None) -> tuple:
    """Grouping key for raw rows.

    Shared fields group globally by field name; everything else groups per
    (document_type, field_name) so document-specific fields never collide.
    """
    name = (field_name or "").strip().lower()
    if is_shared(name):
        return ("shared", name)
    return ("doc", (document_type or "UNKNOWN").upper(), name)


def display_label(document_type: str | None, field_name: str | None) -> str:
    """Human-readable label for a semantic entity."""
    name = (field_name or "").strip()
    pretty = name.replace("_", " ").strip().title() or "Unknown Field"
    if is_shared(name) or not document_type:
        return pretty
    return pretty


def _norm(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "")


def build_semantic_view(rows: list[dict]) -> list[dict]:
    """Group raw extraction rows into semantic entities.

    Each row: {field_name, field_value, normalized_value, extraction_method,
    page_number, document_id, document_type, filename}.
    Returns entities: {key, field_name, display_label, scope
    ("shared"|"document"), document_type, values: [{normalized_value,
    raw_value, method, confidence, page, sources: [{document_id,
    document_type, filename}]}], has_conflict, source_count}.
    Entities sort: shared first (by field name), then by document type.
    """
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        field_name = r.get("field_name")
        doc_type = r.get("document_type")
        key = semantic_key(doc_type, field_name)
        g = groups.get(key)
        if g is None:
            g = {
                "key": key,
                "field_name": (field_name or "").strip(),
                "display_label": display_label(doc_type, field_name),
                "scope": "shared" if key[0] == "shared" else "document",
                "document_type": doc_type,
                "by_value": {},
            }
            groups[key] = g
            order.append(key)
        norm = _norm(r.get("normalized_value") or r.get("field_value"))
        # Empty values never merge — each stays visible on its own.
        vkey = norm if norm else f"__empty__{r.get('document_id')}_{id(r)}"
        v = g["by_value"].get(vkey)
        if v is None:
            v = {
                "normalized_value": (r.get("normalized_value")
                                     or r.get("field_value") or ""),
                "raw_value": r.get("field_value") or "",
                "method": r.get("extraction_method"),
                "confidence": r.get("confidence"),
                "page": r.get("page_number"),
                "sources": [],
            }
            g["by_value"][vkey] = v
        v["sources"].append(
            {
                "document_id": r.get("document_id"),
                "document_type": doc_type,
                "filename": r.get("filename"),
            }
        )
        # Prefer the highest-confidence raw value as the representative.
        try:
            conf = float(r.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf > float(v.get("_best_conf") or -1):
            v["_best_conf"] = conf
            v["raw_value"] = r.get("field_value") or ""
            v["method"] = r.get("extraction_method")
            v["confidence"] = r.get("confidence")
            v["page"] = r.get("page_number")

    entities = []
    for key in order:
        g = groups[key]
        values = []
        for vkey, v in g["by_value"].items():
            v = dict(v)
            v.pop("_best_conf", None)
            # Empty placeholders never count as real values.
            v["_is_empty"] = vkey.startswith("__empty__")
            values.append(v)
        real = [v for v in values if not v["_is_empty"]]
        # Deterministic value order: most sources first, then value.
        values.sort(key=lambda v: (-len(v["sources"]), v["normalized_value"]))
        for v in values:
            v.pop("_is_empty", None)
        entities.append(
            {
                "field_name": g["field_name"],
                "display_label": g["display_label"],
                "scope": g["scope"],
                "document_type": g["document_type"],
                "values": values,
                # Only real (non-empty) distinct values can conflict.
                "has_conflict": len(real) > 1,
                "is_empty": len(real) == 0,
                "source_count": sum(len(v["sources"]) for v in values),
            }
        )
    # Shared identity fields first, then document-scoped by type and name.
    entities.sort(
        key=lambda e: (
            0 if e["scope"] == "shared" else 1,
            e["document_type"] or "",
            e["field_name"],
        )
    )
    return entities
