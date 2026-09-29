"""Entity resolution: name normalization + fuzzy matching (CONTRACT §6).

Used by the IDENTITY_MATCH rule: exact identifier (PAN/GSTIN/CIN) match
across documents is a strong pass; otherwise fuzzy name similarity via
rapidfuzz token_set_ratio (difflib fallback) must reach >= 85.
"""
from __future__ import annotations

import difflib
import re

NAME_MATCH_THRESHOLD = 85.0

# Order matters: longer forms first so "PRIVATE LIMITED" is stripped before
# the bare "LIMITED" rule would leave "PRIVATE" behind.
_SUFFIXES = (
    "PRIVATE LIMITED",
    "PVT LTD",
    "PVT.",
    "LIMITED",
    "LTD",
    "LLP",
    "INC",
    "CORP",
)


def normalize_name(name: str) -> str:
    """Upper-case, strip legal suffixes, punctuation -> space, collapse."""
    if not name:
        return ""
    out = name.upper()
    for suffix in _SUFFIXES:
        out = out.replace(suffix, "")
    out = re.sub(r"[^A-Z0-9 ]", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _token_set_ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz.fuzz import token_set_ratio

        return float(token_set_ratio(a, b))
    except ImportError:
        return difflib.SequenceMatcher(None, a, b).ratio() * 100.0


def name_similarity(a: str, b: str) -> float:
    """0–100 similarity on normalized names."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 100.0
    return _token_set_ratio(na, nb)


def names_match(a: str, b: str, threshold: float = NAME_MATCH_THRESHOLD) -> bool:
    return name_similarity(a, b) >= threshold


def identifiers_match(a: str | None, b: str | None) -> bool:
    """Both non-empty and equal after upper/strip."""
    if not a or not b:
        return False
    return a.strip().upper() == b.strip().upper()


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if v]
    return [str(value)] if str(value).strip() else []


def check_identity(
    declared_name: str,
    doc_names: list[str],
    declared_ids: dict,
    doc_ids: dict,
) -> dict:
    """Compare declared identity vs document-extracted identity.

    Returns {"match": bool, "score": float, "flags": [...]} where each flag is
    {"code": ..., "message": ...} with codes PAN_MISMATCH / GSTIN_MISMATCH /
    CIN_MISMATCH / NAME_MISMATCH. Exact identifier agreement is a strong pass
    even when the fuzzy name score is low (the name flag is still recorded).
    """
    flags: list[dict] = []
    id_keys = (("pan", "PAN_MISMATCH"), ("gstin", "GSTIN_MISMATCH"), ("cin", "CIN_MISMATCH"))

    compared = 0
    matched = 0
    for key, code in id_keys:
        declared_vals = _as_list((declared_ids or {}).get(key))
        doc_vals = _as_list((doc_ids or {}).get(key))
        declared = declared_vals[0] if declared_vals else ""
        if not declared or not doc_vals:
            continue  # cannot compare — no flag either way
        compared += 1
        if any(identifiers_match(declared, dv) for dv in doc_vals):
            matched += 1
        else:
            flags.append(
                {
                    "code": code,
                    "message": (
                        f"Declared {key.upper()} '{declared}' does not match "
                        f"document {key.upper()} value(s): "
                        f"{', '.join(doc_vals)}."
                    ),
                }
            )
    strong_identifier_pass = compared > 0 and matched == compared

    name_score = 0.0
    doc_names = [n for n in (doc_names or []) if n and n.strip()]
    if declared_name and declared_name.strip() and doc_names:
        name_score = max(name_similarity(declared_name, dn) for dn in doc_names)
        if name_score < NAME_MATCH_THRESHOLD:
            flags.append(
                {
                    "code": "NAME_MISMATCH",
                    "message": (
                        f"Declared name '{declared_name}' does not match document "
                        f"name(s) (best similarity {name_score:.1f} < "
                        f"{NAME_MATCH_THRESHOLD:.0f})."
                    ),
                }
            )

    score = 100.0 if strong_identifier_pass else name_score
    match = (not any(f["code"].endswith("_MISMATCH") and f["code"] != "NAME_MISMATCH"
                     for f in flags)) and (
        strong_identifier_pass or not any(f["code"] == "NAME_MISMATCH" for f in flags)
    )
    return {"match": match, "score": score, "flags": flags}
