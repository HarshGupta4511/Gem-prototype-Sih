"""Verification orchestration service.

Resolves identifiers for a bid (extracted fields first, declared bidder data
as fallback), runs each applicable mock government adapter once, cross-checks
portal names against the declared legal name, and persists one
``VerificationCheck`` per source (``is_mock=True`` always).

Honesty: every adapter response is mock data labeled ``is_mock: True`` —
nothing here implies live government access.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.adapters.registry import get_adapter
from app.engines.entity_resolution import name_similarity, names_match
from app.models.models import (
    Bidder,
    BidSubmission,
    Document,
    ExtractedField,
    VerificationCheck,
)
from app.services.audit_service import append_audit

# AdapterSource -> canonical field names to try (in order) when resolving the
# identifier to verify. Extracted fields win; declared bidder fields fall back.
IDENTIFIER_SOURCES: list[tuple[str, list[str]]] = [
    ("GSTN", ["gstin"]),
    ("UDYAM", ["udyam_number"]),
    ("PAN_IT", ["pan"]),
    ("MCA21", ["cin"]),
    ("EPFO", ["epfo_code"]),
    ("ESIC", ["esic_code"]),
    ("STARTUP_INDIA", ["startup_certificate_number"]),
    ("NSIC", ["nsic_number"]),
    ("DIGILOCKER", ["digilocker_id"]),
    ("BLACKLIST", ["legal_name"]),
]

# Declared bidder attribute that backs each canonical field name.
_BIDDER_FIELD_FALLBACK: dict[str, str] = {
    "pan": "pan",
    "gstin": "gstin",
    "udyam_number": "udyam",
    "cin": "cin",
    "legal_name": "legal_name",
}

# Name keys looked for in adapter response data for the identity cross-check.
_NAME_FIELDS = (
    "legal_name",
    "enterprise_name",
    "company_name",
    "employer_name",
    "name",
    "startup_name",
)

# Sources for which the name cross-check is skipped. BLACKLIST is queried BY
# name and the adapter already performs the name match; comparing its echo
# against the declared name could produce false MISMATCH findings.
_SKIP_NAME_CHECK = {"BLACKLIST"}

_NAME_MATCH_THRESHOLD = 85
_MISMATCH_CONFIDENCE = 0.8


def resolve_identifiers(db, bid_id: int) -> dict[str, str]:
    """Resolve ``{AdapterSource: identifier}`` for a bid.

    Merges extracted fields across all PROCESSED documents of the bid
    (highest-confidence value wins per canonical field name), falling back to
    declared bidder fields (``bidder.pan/gstin/udyam/cin/legal_name``).
    Sources with no resolvable identifier are omitted.
    """
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"BidSubmission {bid_id} not found")
    bidder = db.get(Bidder, bid.bidder_id) if bid.bidder_id else None

    # Merge extracted fields: highest confidence wins per canonical field.
    merged: dict[str, str] = {}
    merged_conf: dict[str, float] = {}
    doc_ids = [
        row[0]
        for row in db.query(Document.id)
        .filter(Document.bid_id == bid_id, Document.processing_status == "PROCESSED")
        .all()
    ]
    if doc_ids:
        for field in (
            db.query(ExtractedField).filter(ExtractedField.document_id.in_(doc_ids)).all()
        ):
            name = (field.field_name or "").strip().lower()
            value = (field.normalized_value or field.field_value or "").strip()
            if not name or not value:
                continue
            conf = field.confidence if field.confidence is not None else 0.0
            if name not in merged or conf > merged_conf[name]:
                merged[name] = value
                merged_conf[name] = conf

    declared: dict[str, str] = {}
    for canonical, attr in _BIDDER_FIELD_FALLBACK.items():
        value = getattr(bidder, attr, None) if bidder is not None else None
        if value:
            declared[canonical] = str(value).strip()

    resolved: dict[str, str] = {}
    for source, field_names in IDENTIFIER_SOURCES:
        for field_name in field_names:
            identifier = merged.get(field_name) or declared.get(field_name)
            if identifier:
                resolved[source] = identifier
                break
    return resolved


def _similarity_0_100(a: str, b: str) -> float:
    """Name similarity on a 0-100 scale (tolerates a 0-1 return too)."""
    try:
        score = float(name_similarity(a, b))
    except Exception:
        return 0.0
    if 0 < score <= 1.0:
        score *= 100.0
    return score


def _names_match(a: str, b: str) -> bool:
    try:
        return bool(names_match(a, b, threshold=_NAME_MATCH_THRESHOLD))
    except TypeError:
        # names_match without a threshold kwarg: rely on its default.
        return bool(names_match(a, b))


def _apply_name_cross_check(
    source: str, declared_name: str, response: dict
) -> dict:
    """Compare the portal name in ``response`` with the declared legal name.

    On mismatch the check status becomes ``MISMATCH``, a ``name_match`` dict
    (declared/portal/similarity) is added to the response data, and confidence
    drops to 0.8. The original adapter status is kept in the data so no
    information (e.g. EXPIRED) is lost.
    """
    if source in _SKIP_NAME_CHECK or not declared_name:
        return response
    data = response.get("data") or {}
    portal_name = next(
        (str(data[key]).strip() for key in _NAME_FIELDS if data.get(key)), ""
    )
    if not portal_name:
        return response
    similarity = _similarity_0_100(declared_name, portal_name)
    if _names_match(declared_name, portal_name):
        return response

    data = dict(data)
    data["name_match"] = {
        "declared": declared_name,
        "portal": portal_name,
        "similarity": round(similarity, 2),
    }
    if response.get("status") != "VERIFIED":
        data["adapter_status"] = response.get("status")
    response["status"] = "MISMATCH"
    response["confidence"] = _MISMATCH_CONFIDENCE
    response["data"] = data
    return response


def run_verification(db, bid_id: int, *, user_id: int | None = None) -> list[dict]:
    """Run every applicable mock adapter for a bid and persist the checks.

    Replaces previous checks for the same bid+source, writes a
    ``VERIFICATION_RUN`` audit entry with per-status counts, and returns the
    persisted checks as dicts. ``requirement_id`` is left null — requirement
    linkage happens in the compliance engine.
    """
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"BidSubmission {bid_id} not found")
    bidder = db.get(Bidder, bid.bidder_id) if bid.bidder_id else None
    declared_name = (bidder.legal_name or "").strip() if bidder else ""

    resolved = resolve_identifiers(db, bid_id)
    results: list[dict] = []

    def _persist(source: str, identifier: str, response: dict,
                status: str, confidence: float) -> dict:
        """Replace the previous check for (bid, source) and persist one row."""
        db.query(VerificationCheck).filter(
            VerificationCheck.bid_id == bid_id,
            VerificationCheck.source == source,
        ).delete()

        check = VerificationCheck(
            bid_id=bid_id,
            requirement_id=None,
            source=source,
            identifier=identifier,
            request_payload={"source": source, "identifier": identifier},
            response_payload=response,
            verification_status=status,
            verified_at=datetime.now(timezone.utc),
            confidence=confidence,
            is_mock=True,
            evidence_reference=(
                f"MOCK {source} verification of {identifier} — "
                "demo data, not live government systems."
            ),
        )
        db.add(check)
        db.flush()
        return {
            "id": check.id,
            "bid_id": bid_id,
            "requirement_id": None,
            "source": source,
            "identifier": identifier,
            "request_payload": check.request_payload,
            "response_payload": response,
            "verification_status": status,
            "verified_at": check.verified_at.isoformat()
            if check.verified_at
            else None,
            "confidence": confidence,
            "is_mock": True,
            "evidence_reference": check.evidence_reference,
        }

    for source, identifier in resolved.items():
        adapter = get_adapter(source)
        if adapter is None:
            continue
        try:
            response = adapter.verify(identifier)
            response = _apply_name_cross_check(source, declared_name, response)
            status = response["status"]
            confidence = response["confidence"]
        except Exception as exc:
            # One failing adapter must not abort the whole run with zero
            # persisted rows: record the source as UNAVAILABLE so the rules
            # engine can distinguish "source unreachable" from non-compliance.
            response = {
                "source": source,
                "status": "UNAVAILABLE",
                "data": {},
                "error": f"{type(exc).__name__}: {exc}",
                "is_mock": True,
            }
            status, confidence = "UNAVAILABLE", 0.0
        results.append(_persist(source, identifier, response, status, confidence))

    counts: dict[str, int] = {}
    for item in results:
        counts[item["verification_status"]] = counts.get(item["verification_status"], 0) + 1
    append_audit(
        db,
        user_id=user_id,
        action="VERIFICATION_RUN",
        entity_type="bid_submission",
        entity_id=str(bid_id),
        metadata={
            "bid_id": bid_id,
            "sources": sorted(resolved.keys()),
            "counts": counts,
            "total": len(results),
            "is_mock": True,
        },
    )
    db.commit()
    return results


def get_checks(db, bid_id: int) -> list[VerificationCheck]:
    """Return the newest ``VerificationCheck`` per source for a bid."""
    rows = (
        db.query(VerificationCheck)
        .filter(VerificationCheck.bid_id == bid_id)
        .order_by(VerificationCheck.verified_at.desc(), VerificationCheck.id.desc())
        .all()
    )
    seen: set[str] = set()
    newest: list[VerificationCheck] = []
    for row in rows:
        if row.source in seen:
            continue
        seen.add(row.source)
        newest.append(row)
    return newest
