"""Cross-document consistency checks for a bid.

Compares extracted fields across the bid's processed documents using the
shared ``entity_resolution`` normalisation (no ad-hoc fuzzy logic):

  - entity legal names across documents (GST vs PAN vs Udyam ...)
  - GSTIN <-> PAN structural consistency (chars 3-12 of GSTIN == PAN)
  - identifier agreement (PAN / GSTIN / Udyam / CIN identical everywhere)
  - certificate expiry (valid_until in the past)
  - date contradictions (incorporation after issue dates)
  - numeric agreement (turnover / local content / experience across docs)
  - OEM authorization names the bidding entity (vs bidder master identity)
  - debarment declaration vs the BLACKLIST verification source
  - extracted document values vs retrieved statutory records (per source)

Verification compares retrieved portal records against the DECLARED bidder
master; the retrieved-statutory check compares them against what the
DOCUMENTS actually say, so the officer sees "documents say X, portal says Y"
in one view.

Every check explains exactly what mismatched. Re-running replaces the bid's
stored checks. Mismatches are audit-logged.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.engines.entity_resolution import names_match, normalize_name
from app.models.models import (
    Bidder,
    BidSubmission,
    ConsistencyCheck,
    Document,
    ExtractedField,
    User,
    VerificationCheck,
)
from app.services.audit_service import append_audit
from app.services.regex_service import normalize_amount, normalize_date

log = logging.getLogger(__name__)

SEV_REVIEW = "REVIEW_REQUIRED"
SEV_INFO = "INFORMATIONAL"
RES_MATCH = "MATCH"
RES_MISMATCH = "MISMATCH"
RES_REVIEW = "REVIEW_REQUIRED"

# Human-readable check metadata: name -> (label, field_hint).
_CHECK_LABELS: dict[str, str] = {
    "ENTITY_NAME_CONSISTENCY": "Entity Identity Consistency",
    "GSTIN_PAN_CONSISTENCY": "GSTIN ↔ PAN Consistency",
    "IDENTIFIER_CONSISTENCY": "Identifier Agreement Across Documents",
    "CERTIFICATE_EXPIRY": "Certificate Validity",
    "DATE_CONTRADICTION": "Date Contradiction",
    "TURNOVER_CONSISTENCY": "Turnover Agreement",
    "LOCAL_CONTENT_CONSISTENCY": "Local Content Agreement",
    "EXPERIENCE_CONSISTENCY": "Experience Agreement",
    "OEM_AUTHORIZATION_IDENTITY": "OEM Authorization — Bidder Identity",
    "DEBARMENT_DECLARATION_CONSISTENCY": "Debarment Declaration vs Verification Source",
    "RETRIEVED_STATUTORY_COMPARISON": "Extracted vs Retrieved Statutory Values",
}

_TOLERANCE = {
    "turnover_inr": 0.10,      # 10 % relative tolerance
    "local_content_pct": 5.0,  # percentage points
    "experience_years": 1.0,   # years
}


def check_label(name: str) -> str:
    return _CHECK_LABELS.get(name, name.replace("_", " ").title())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _doc_fields(db: Session, bid_id: int) -> tuple[dict[int, Document], dict[int, dict[str, dict]]]:
    """Return (documents, {doc_id: {field_name: field-info}})."""
    docs = {
        d.id: d
        for d in db.query(Document)
        .filter(Document.bid_id == bid_id,
                Document.processing_status == "PROCESSED")
        .all()
    }
    fields: dict[int, dict[str, dict]] = {}
    if docs:
        rows = (
            db.query(ExtractedField)
            .filter(ExtractedField.document_id.in_(list(docs)))
            .all()
        )
        for r in rows:
            info = fields.setdefault(r.document_id, {})
            # first occurrence wins (pipeline dedupes already)
            info.setdefault(r.field_name, {
                "value": r.field_value,
                "normalized": r.normalized_value,
                "page": r.page_number,
                "method": r.extraction_method,
            })
    return docs, fields


def _doc_ref(docs: dict[int, Document], doc_id: int | None) -> dict[str, Any]:
    d = docs.get(doc_id) if doc_id else None
    if d is None:
        return {"document_id": doc_id, "name": None, "type": None}
    return {"document_id": d.id, "name": d.filename, "type": d.document_type}


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        n = normalize_amount(str(value))
        return float(n) if n is not None else None
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> date | None:
    try:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        iso = normalize_date(str(value))
        return date.fromisoformat(iso) if iso else None
    except (TypeError, ValueError):
        return None


def run_consistency_check(
    db: Session, bid_id: int, user_id: int | None = None
) -> dict:
    """Run all cross-document checks for a bid; persist; audit; return summary."""
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"Bid {bid_id} not found")
    docs, fields = _doc_fields(db, bid_id)

    bidder = db.get(Bidder, bid.bidder_id) if bid.bidder_id else None
    bidder_name = (bidder.legal_name or "").strip() if bidder else ""

    # Retrieved statutory records for this bid (verification is a separate
    # officer step; these checks only run when it has been run).
    retrieved: dict[str, dict] = {}
    blacklist_verdict: dict | None = None
    for row in db.query(VerificationCheck).filter(
        VerificationCheck.bid_id == bid_id
    ).all():
        data = (row.response_payload or {}).get("data") or {}
        if not isinstance(data, dict) or not data:
            continue
        if row.source == "BLACKLIST":
            blacklist_verdict = data
        else:
            retrieved[row.source] = data

    checks: list[dict] = []
    checks.extend(_check_entity_names(docs, fields))
    checks.extend(_check_gstin_pan(docs, fields))
    checks.extend(_check_identifiers(docs, fields))
    checks.extend(_check_expiry(docs, fields))
    checks.extend(_check_dates(docs, fields))
    checks.extend(_check_numerics(docs, fields))
    checks.extend(_check_oem_authorization_identity(docs, fields, bidder_name))
    checks.extend(_check_debarment_declaration(docs, fields, blacklist_verdict))
    checks.extend(_check_retrieved_statutory(docs, fields, retrieved))

    # Re-run replaces previous checks for this bid.
    db.query(ConsistencyCheck).filter(ConsistencyCheck.bid_id == bid_id).delete()
    for c in checks:
        db.add(ConsistencyCheck(
            bid_id=bid_id,
            check_name=c["check_name"],
            field_name=c["field_name"],
            doc1_id=c["doc1_id"],
            doc2_id=c["doc2_id"],
            value1=c["value1"],
            value2=c["value2"],
            result=c["result"],
            reason=c["reason"],
            severity=c["severity"],
            evidence=c["evidence"],
        ))
    db.commit()

    mismatches = [c for c in checks if c["result"] == RES_MISMATCH]
    append_audit(
        db, user_id=user_id, action="CONSISTENCY_CHECK_RUN",
        entity_type="bid_submission", entity_id=str(bid_id),
        metadata={"checks": len(checks), "mismatches": len(mismatches)},
    )
    if mismatches:
        append_audit(
            db, user_id=user_id, action="CROSS_DOCUMENT_MISMATCH_DETECTED",
            entity_type="bid_submission", entity_id=str(bid_id),
            metadata={
                "mismatch_count": len(mismatches),
                "checks": [m["check_name"] for m in mismatches],
            },
        )
    return {
        "bid_id": bid_id,
        "checks_run": len(checks),
        "mismatches": len(mismatches),
        "evaluated_at": _utcnow().isoformat(),
        "checks": [
            {**c, "check_label": check_label(c["check_name"]),
             "doc1": _doc_ref(docs, c["doc1_id"]),
             "doc2": _doc_ref(docs, c["doc2_id"])}
            for c in checks
        ],
    }


def get_consistency(db: Session, bid_id: int) -> dict:
    """Stored consistency checks for a bid (with document references)."""
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"Bid {bid_id} not found")
    docs = {d.id: d for d in db.query(Document).filter(Document.bid_id == bid_id).all()}
    rows = (
        db.query(ConsistencyCheck)
        .filter(ConsistencyCheck.bid_id == bid_id)
        .order_by(ConsistencyCheck.id)
        .all()
    )
    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "bid_id": r.bid_id,
            "check_name": r.check_name,
            "check_label": check_label(r.check_name),
            "field_name": r.field_name,
            "doc1": _doc_ref(docs, r.doc1_id),
            "doc2": _doc_ref(docs, r.doc2_id),
            "value1": r.value1,
            "value2": r.value2,
            "result": r.result,
            "reason": r.reason,
            "severity": r.severity,
            "evidence": r.evidence or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return {
        "bid_id": bid_id,
        "checks": items,
        "mismatches": sum(1 for i in items if i["result"] == RES_MISMATCH),
        "evaluated_at": items[0]["created_at"] if items else None,
    }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_entity_names(docs, fields) -> list[dict]:
    """Legal entity name must agree across documents (normalized)."""
    named = [
        (doc_id, f["value"])
        for doc_id, fmap in fields.items()
        if (f := fmap.get("legal_name")) and f["value"]
        for doc_id in [doc_id]
    ]
    # pairwise compare; report each disagreeing pair once
    out = []
    seen = set()
    for i in range(len(named)):
        for j in range(i + 1, len(named)):
            d1, v1 = named[i]
            d2, v2 = named[j]
            key = (d1, d2)
            if key in seen:
                continue
            seen.add(key)
            match = names_match(v1, v2)
            out.append({
                "check_name": "ENTITY_NAME_CONSISTENCY",
                "field_name": "legal_name",
                "doc1_id": d1, "doc2_id": d2,
                "value1": v1, "value2": v2,
                "result": RES_MATCH if match else RES_MISMATCH,
                "reason": (
                    "Legal entity names match after normalization."
                    if match else
                    "Legal entity names do not match after normalization "
                    f"(normalized: '{normalize_name(v1)}' vs "
                    f"'{normalize_name(v2)}')."
                ),
                "severity": SEV_INFO if match else SEV_REVIEW,
                "evidence": {
                    "comparison": "normalized legal-name comparison",
                    "normalized_1": normalize_name(v1),
                    "normalized_2": normalize_name(v2),
                },
            })
    return out


def _check_gstin_pan(docs, fields) -> list[dict]:
    """GSTIN chars 3-12 must equal the PAN (structural rule)."""
    out = []
    for doc_id, fmap in fields.items():
        g = (fmap.get("gstin") or {}).get("value")
        p = (fmap.get("pan") or {}).get("value")
        if not g or not p:
            continue
        g, p = g.strip().upper(), p.strip().upper()
        if len(g) != 15:
            continue  # malformed GSTIN is the verification engine's job
        embedded = g[2:12]
        match = embedded == p
        out.append({
            "check_name": "GSTIN_PAN_CONSISTENCY",
            "field_name": "gstin/pan",
            "doc1_id": doc_id, "doc2_id": None,
            "value1": g, "value2": p,
            "result": RES_MATCH if match else RES_MISMATCH,
            "reason": (
                "PAN embedded in GSTIN matches the declared PAN."
                if match else
                f"PAN embedded in GSTIN ({embedded}) does not match the "
                f"declared PAN ({p})."
            ),
            "severity": SEV_INFO if match else SEV_REVIEW,
            "evidence": {"rule": "GSTIN[3:12] == PAN", "embedded_pan": embedded},
        })
    return out


def _check_identifiers(docs, fields) -> list[dict]:
    """PAN / GSTIN / Udyam / CIN must be identical wherever they appear."""
    out = []
    for field in ("pan", "gstin", "udyam_number", "cin"):
        seen: dict[str, int] = {}
        for doc_id, fmap in fields.items():
            v = (fmap.get(field) or {}).get("value")
            if v:
                seen.setdefault(v.strip().upper(), doc_id)
        vals = list(seen)
        if len(vals) > 1:
            d1, d2 = seen[vals[0]], seen[vals[1]]
            out.append({
                "check_name": "IDENTIFIER_CONSISTENCY",
                "field_name": field,
                "doc1_id": d1, "doc2_id": d2,
                "value1": vals[0], "value2": vals[1],
                "result": RES_MISMATCH,
                "reason": (
                    f"Conflicting {field} values across documents: "
                    f"'{vals[0]}' vs '{vals[1]}'."
                ),
                "severity": SEV_REVIEW,
                "evidence": {"occurrences": [
                    {"document_id": did, "value": val}
                    for val, did in seen.items()
                ]},
            })
    return out


def _check_expiry(docs, fields) -> list[dict]:
    """valid_until dates in the past are flagged."""
    out = []
    today = date.today()
    for doc_id, fmap in fields.items():
        v = (fmap.get("valid_until") or {}).get("value")
        d = _as_date(v)
        if not d:
            continue
        expired = d < today
        out.append({
            "check_name": "CERTIFICATE_EXPIRY",
            "field_name": "valid_until",
            "doc1_id": doc_id, "doc2_id": None,
            "value1": str(v), "value2": None,
            "result": RES_MISMATCH if expired else RES_MATCH,
            "reason": (
                f"Certificate expired on {d.isoformat()}."
                if expired else
                f"Certificate valid until {d.isoformat()}."
            ),
            "severity": SEV_REVIEW if expired else SEV_INFO,
            "evidence": {"expiry_date": d.isoformat(), "today": today.isoformat()},
        })
    return out


def _check_dates(docs, fields) -> list[dict]:
    """Incorporation date must not be after other issue/validity dates."""
    out = []
    for doc_id, fmap in fields.items():
        inc = _as_date((fmap.get("incorporation_date") or {}).get("value"))
        if not inc:
            continue
        for other_field in ("valid_until",):
            ov = (fmap.get(other_field) or {}).get("value")
            od = _as_date(ov)
            if od and inc > od:
                out.append({
                    "check_name": "DATE_CONTRADICTION",
                    "field_name": f"incorporation_date/{other_field}",
                    "doc1_id": doc_id, "doc2_id": None,
                    "value1": inc.isoformat(), "value2": od.isoformat(),
                    "result": RES_MISMATCH,
                    "reason": (
                        f"Incorporation date ({inc.isoformat()}) is after "
                        f"{other_field} ({od.isoformat()}) — contradictory."
                    ),
                    "severity": SEV_REVIEW,
                    "evidence": {},
                })
    return out


def _check_numerics(docs, fields) -> list[dict]:
    """Turnover / local content / experience must agree within tolerance."""
    out = []
    for field, label in (
        ("turnover_inr", "TURNOVER_CONSISTENCY"),
        ("local_content_pct", "LOCAL_CONTENT_CONSISTENCY"),
        ("experience_years", "EXPERIENCE_CONSISTENCY"),
    ):
        vals: list[tuple[int, float, str]] = []
        for doc_id, fmap in fields.items():
            raw = (fmap.get(field) or {}).get("value")
            n = _num(raw)
            if n is not None:
                vals.append((doc_id, n, str(raw)))
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                d1, n1, r1 = vals[i]
                d2, n2, r2 = vals[j]
                tol = _TOLERANCE[field]
                if field == "turnover_inr":
                    diff = abs(n1 - n2) / max(abs(n1), abs(n2), 1e-9)
                    bad = diff > tol
                    detail = f"relative difference {diff:.1%} exceeds {tol:.0%} tolerance"
                else:
                    diff = abs(n1 - n2)
                    bad = diff > tol
                    detail = f"absolute difference {diff:g} exceeds tolerance {tol:g}"
                out.append({
                    "check_name": label,
                    "field_name": field,
                    "doc1_id": d1, "doc2_id": d2,
                    "value1": r1, "value2": r2,
                    "result": RES_MISMATCH if bad else RES_MATCH,
                    "reason": (
                        f"Conflicting {field} values across documents — {detail}."
                        if bad else
                        f"{field} values agree within tolerance."
                    ),
                    "severity": SEV_REVIEW if bad else SEV_INFO,
                    "evidence": {"tolerance": tol, "values": [n1, n2]},
                })
    return out


def _check_oem_authorization_identity(
    docs, fields, bidder_name: str
) -> list[dict]:
    """The entity named on an OEM authorization must be the bidding entity.

    An OEM certificate authorizes a specific party to quote/supply. If the
    named party is not this bid's bidder, the certificate may belong to a
    different bid or entity. ``doc2`` is empty: the reference is the
    registered bidder master, cited in evidence.
    """
    out = []
    if not (bidder_name or "").strip():
        return out
    for doc_id, fmap in fields.items():
        if not (fmap.get("oem_name") or fmap.get("oem_authorization_valid")):
            continue
        named = (fmap.get("legal_name") or {}).get("value") or ""
        oem = (fmap.get("oem_name") or {}).get("value") or ""
        if not named.strip():
            out.append({
                "check_name": "OEM_AUTHORIZATION_IDENTITY",
                "field_name": "legal_name",
                "doc1_id": doc_id, "doc2_id": None,
                "value1": "", "value2": bidder_name,
                "result": RES_REVIEW,
                "reason": (
                    "The OEM authorization document names no bidder entity, "
                    "so it cannot be tied to this bid."
                ),
                "severity": SEV_REVIEW,
                "evidence": {
                    "oem_name": oem,
                    "bidder_identity_source": "registered bidder master",
                },
            })
            continue
        match = names_match(named, bidder_name)
        out.append({
            "check_name": "OEM_AUTHORIZATION_IDENTITY",
            "field_name": "legal_name",
            "doc1_id": doc_id, "doc2_id": None,
            "value1": named, "value2": bidder_name,
            "result": RES_MATCH if match else RES_MISMATCH,
            "reason": (
                "The OEM authorization names the bidding entity."
                if match else
                "The OEM authorization names a different entity than the "
                f"bidder (normalized: '{normalize_name(named)}' vs "
                f"'{normalize_name(bidder_name)}'). Verify the certificate "
                "belongs to this bid."
            ),
            "severity": SEV_INFO if match else SEV_REVIEW,
            "evidence": {
                "comparison": "normalized legal-name comparison",
                "oem_name": oem,
                "normalized_named": normalize_name(named),
                "normalized_bidder": normalize_name(bidder_name),
                "bidder_identity_source": "registered bidder master",
            },
        })
    return out


# Declaration phrases that unambiguously claim a clean debarment record.
# Kept as literal keywords (documented in evidence) — no ML, no guessing.
_CLEAN_DEBARMENT_CLAIMS = (
    "not debarred",
    "not blacklisted",
    "never debarred",
    "never blacklisted",
    "never been debarred",
    "never been blacklisted",
    "no debarment",
    "no blacklisting",
)


def _check_debarment_declaration(
    docs, fields, blacklist_verdict: dict | None
) -> list[dict]:
    """Bidder's debarment declaration vs the BLACKLIST verification source.

    Runs only when a declaration exists AND a BLACKLIST check was run for the
    bid. The declaration is the bidder's own claim; the verification source is
    the retrieved record. A clean claim contradicted by the source is a
    MISMATCH for officer review — the declaration alone never clears the bid.
    """
    out = []
    if not blacklist_verdict:
        return out
    for doc_id, fmap in fields.items():
        decl = (fmap.get("debarment_declaration") or {}).get("value") or ""
        if not decl.strip():
            continue
        if not any(p in decl.lower() for p in _CLEAN_DEBARMENT_CLAIMS):
            continue  # declaration does not make a clean claim; not our call
        flagged = bool(blacklist_verdict.get("blacklisted")) or bool(
            blacklist_verdict.get("debarred")
        )
        out.append({
            "check_name": "DEBARMENT_DECLARATION_CONSISTENCY",
            "field_name": "debarment_declaration",
            "doc1_id": doc_id, "doc2_id": None,
            "value1": decl, "value2": (
                "blacklisted/debarred per verification source"
                if flagged else
                "no blacklist/debarment record per verification source"
            ),
            "result": RES_MISMATCH if flagged else RES_MATCH,
            "reason": (
                "The bidder declares non-debarment, and the BLACKLIST "
                "verification source reports no blacklist/debarment record."
                if not flagged else
                "The bidder declares non-debarment, but the BLACKLIST "
                "verification source reports a blacklist/debarment record. "
                "The declaration is contradicted — requires Procurement "
                "Officer review."
            ),
            "severity": SEV_INFO if not flagged else SEV_REVIEW,
            "evidence": {
                "verification_source": "BLACKLIST",
                "retrieved_blacklisted": bool(blacklist_verdict.get("blacklisted")),
                "retrieved_debarred": bool(blacklist_verdict.get("debarred")),
                "retrieved_authority": blacklist_verdict.get("authority"),
                "claim_detection": "literal keyword match on declaration text",
            },
        })
    return out


# Retrieved-record name keys (per adapter) and identifier key per source.
_RETRIEVED_NAME_KEYS = (
    "legal_name", "enterprise_name", "company_name", "employer_name",
    "name", "startup_name",
)
_RETRIEVED_ID_KEYS = {
    "GSTN": "gstin",
    "PAN_IT": "pan",
    "UDYAM": "udyam_number",
    "MCA21": "cin",
    "EPFO": "epfo_code",
    "ESIC": "esic_code",
}


def _consensus_extracted_name(fields) -> tuple[int | None, str]:
    """Most common normalized legal_name across docs -> (doc_id, raw value)."""
    counts: dict[str, int] = {}
    first: dict[str, tuple[int | None, str]] = {}
    for doc_id, fmap in fields.items():
        raw = (fmap.get("legal_name") or {}).get("value") or ""
        norm = normalize_name(raw)
        if not norm:
            continue
        counts[norm] = counts.get(norm, 0) + 1
        first.setdefault(norm, (doc_id, raw))
    if not counts:
        return None, ""
    best = max(counts, key=lambda k: (counts[k], k))
    return first[best]


def _merged_extracted_value(fields, field_name: str) -> tuple[int | None, str]:
    """First non-empty extracted value for a field -> (doc_id, value)."""
    for doc_id, fmap in fields.items():
        v = (fmap.get(field_name) or {}).get("value") or ""
        if str(v).strip():
            return doc_id, str(v).strip()
    return None, ""


def _check_retrieved_statutory(
    docs, fields, retrieved: dict[str, dict]
) -> list[dict]:
    """Extracted document values vs retrieved statutory records, per source.

    Verification compares retrieved records against the DECLARED bidder master;
    this compares them against what the DOCUMENTS actually say, so the officer
    sees "documents say X, portal says Y" in one place. BLACKLIST is excluded:
    it is queried by name and its echo would be a trivial self-comparison (it
    has its own dedicated declaration check above).
    """
    out = []
    name_doc, name_val = _consensus_extracted_name(fields)
    for source, record in retrieved.items():
        id_key = _RETRIEVED_ID_KEYS.get(source)
        if not id_key:
            continue
        # -- retrieved name vs consensus document name ---------------------
        retrieved_name = ""
        for k in _RETRIEVED_NAME_KEYS:
            v = record.get(k)
            if v and str(v).strip():
                retrieved_name = str(v).strip()
                break
        if retrieved_name and name_val:
            match = names_match(retrieved_name, name_val)
            out.append({
                "check_name": "RETRIEVED_STATUTORY_COMPARISON",
                "field_name": "legal_name",
                "doc1_id": name_doc, "doc2_id": None,
                "value1": name_val, "value2": retrieved_name,
                "result": RES_MATCH if match else RES_MISMATCH,
                "reason": (
                    f"Document-extracted entity name agrees with the {source} "
                    "retrieved record."
                    if match else
                    f"Document-extracted entity name disagrees with the {source} "
                    f"retrieved record (normalized: '{normalize_name(name_val)}' "
                    f"vs '{normalize_name(retrieved_name)}')."
                ),
                "severity": SEV_INFO if match else SEV_REVIEW,
                "evidence": {
                    "verification_source": source,
                    "comparison": "normalized legal-name comparison",
                    "document_side": "consensus extracted legal_name across documents",
                    "retrieved_side": f"{source} retrieved record",
                },
            })
        # -- retrieved identifier vs extracted identifier (echo check) -------
        retrieved_id = record.get(id_key)
        _, extracted_id = _merged_extracted_value(fields, id_key)
        if retrieved_id and extracted_id:
            same = str(retrieved_id).strip().upper() == extracted_id.strip().upper()
            out.append({
                "check_name": "RETRIEVED_STATUTORY_COMPARISON",
                "field_name": id_key,
                "doc1_id": _merged_extracted_value(fields, id_key)[0],
                "doc2_id": None,
                "value1": extracted_id, "value2": str(retrieved_id).strip(),
                "result": RES_MATCH if same else RES_MISMATCH,
                "reason": (
                    f"Extracted {id_key.upper()} matches the {source} "
                    "retrieved record."
                    if same else
                    f"Extracted {id_key.upper()} differs from the {source} "
                    "retrieved record — the retrieved record may have been "
                    "queried with a different identifier than the documents "
                    "carry."
                ),
                "severity": SEV_INFO if same else SEV_REVIEW,
                "evidence": {
                    "verification_source": source,
                    "comparison": "case-insensitive identifier equality",
                },
            })
    return out


def mismatch_summary_for_report(db: Session, bid_id: int) -> list[dict]:
    """Mismatch-only summary for the verification report (read-only)."""
    data = get_consistency(db, bid_id)
    return [c for c in data["checks"] if c["result"] == RES_MISMATCH]
