"""Deterministic procurement-integrity signal detection.

Operates ONLY on existing tender / bid / bidder / audit data (plus the
clearly-labelled synthetic DEMO procurement history, which is flagged on
every signal it sources). Signals are *patterns that warrant human review* —
never findings of corruption or misconduct. The Procurement Officer reviews
every signal and retains full decision authority.

Signal severities:
  REVIEW_REQUIRED — pattern is strong enough to need officer review
  ELEVATED        — emerging pattern worth monitoring
  INFORMATIONAL   — recorded for the record
"""
from __future__ import annotations

import difflib
import logging
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from sqlalchemy.orm import Session

from app.engines.entity_resolution import normalize_name
from app.models.models import (
    AuditLog,
    Bidder,
    BidSubmission,
    ComplianceResult,
    Document,
    ExtractedField,
    IntegrityFinding,
    IntegritySeverity,
    IntegritySignalType,
    IntegrityStatus,
    Tender,
    TenderRequirement,
    User,
)
from app.services.audit_service import append_audit

log = logging.getLogger(__name__)

SEV_REVIEW = IntegritySeverity.REVIEW_REQUIRED.value
SEV_ELEVATED = IntegritySeverity.ELEVATED.value
SEV_INFO = IntegritySeverity.INFORMATIONAL.value

# Stable, evidence-backed detection thresholds (documented in rule_logic).
_COHORT_MIN_TENDERS_ELEVATED = 2
_COHORT_MIN_TENDERS_REVIEW = 3
_REPEAT_MIN_TENDERS_ELEVATED = 3
_REPEAT_MIN_TENDERS_REVIEW = 4
_ROTATION_MIN_AWARDS = 3
_ROTATION_MAX_WINNERS = 3
_ASSOCIATION_MIN_DECISIONS = 3
_CONCENTRATION_MIN_WINS_ELEVATED = 2
_CONCENTRATION_MIN_WINS_REVIEW = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tender_ref(db: Session, tender_id: int) -> dict:
    t = db.get(Tender, tender_id)
    if t is None:
        return {"tender_id": tender_id, "tender_number": "?", "title": "?"}
    return {
        "tender_id": t.id,
        "tender_number": t.tender_number,
        "title": t.title,
        "is_demo_history": bool(getattr(t, "is_demo_history", False)),
    }


def _bidder_name(db: Session, bidder_id: int) -> str:
    b = db.get(Bidder, bidder_id)
    return b.legal_name if b else f"bidder #{bidder_id}"


def _entity_key_for_bidder(b: Bidder) -> str:
    """Stable cross-tender entity key for one bidder row.

    Bidder rows are tender-scoped, so the same legal company gets a new row
    per tender. Identity strength order: a structurally validated PAN first
    (a valid GSTIN contributes its embedded PAN, unifying PAN-only and
    GSTIN-carrying rows for the same entity), then the normalized legal name
    as fallback. Malformed identifiers are NEVER used as keys — they fall
    through, so two entities can never merge because of a typo'd identifier.
    Raw bidder ids are never used as cross-tender identity.
    """
    pan = _valid_pan(b.pan)
    if pan:
        return f"pan:{pan}"
    embedded = _pan_from_gstin(b.gstin)
    if embedded:
        return f"pan:{embedded}"
    return f"name:{normalize_name(b.legal_name or '')}"


# Structural validators for Indian tax identifiers. A malformed identifier
# must never merge entities or trigger an identity-relationship signal —
# it falls back to name-based identity instead.
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def _valid_pan(value: str | None) -> str | None:
    v = (value or "").strip().upper()
    return v if _PAN_RE.match(v) else None


def _valid_gstin(value: str | None) -> str | None:
    v = (value or "").strip().upper()
    return v if _GSTIN_RE.match(v) else None


def _pan_from_gstin(value: str | None) -> str | None:
    """Embedded PAN (chars 3-12) of a structurally valid GSTIN."""
    v = _valid_gstin(value)
    return v[2:12] if v else None


def _bidder_entity_key(db: Session, bidder_id: int) -> str:
    b = db.get(Bidder, bidder_id)
    return _entity_key_for_bidder(b) if b else ""


def _current_tender_ids(db: Session) -> list[int]:
    """IDs of tenders in the Tender Registry (excludes demo-history)."""
    rows = (
        db.query(Tender.id)
        .filter((Tender.is_demo_history.is_(False)) | (Tender.is_demo_history.is_(None)))
        .all()
    )
    return [r[0] for r in rows]


def _current_bids(db: Session) -> list:
    """BidSubmissions belonging to current (registry-visible) tenders only."""
    return db.query(BidSubmission).filter(
        BidSubmission.tender_id.in_(_current_tender_ids(db))).all()


def _current_bidders(db: Session) -> list:
    """Bidders belonging to current (registry-visible) tenders only."""
    return db.query(Bidder).filter(
        Bidder.tender_id.in_(_current_tender_ids(db))).all()


def _bidder_entity_map(db: Session) -> tuple[dict[int, str], dict[str, int], dict[str, str]]:
    """Return ({bidder_id: entity key}, {key: first bidder_id},
    {key: display legal name}).

    Bidder rows are tender-scoped, so cross-tender entity identity is the
    PAN/GSTIN-anchored entity key — never the raw bidder_id.
    """
    to_key: dict[int, str] = {}
    first_id: dict[str, int] = {}
    display: dict[str, str] = {}
    for b in _current_bidders(db):
        key = _entity_key_for_bidder(b)
        if key == "name:":
            continue
        to_key[b.id] = key
        first_id.setdefault(key, b.id)
        display.setdefault(key, b.legal_name or key)
    return to_key, first_id, display


# ---------------------------------------------------------------------------
# Detectors — each returns a list of signal dicts (no DB writes)
# ---------------------------------------------------------------------------


def _detect_recurring_cohorts(db: Session) -> list[dict]:
    """Same bidder pairs repeatedly participating together across tenders.

    Bidder rows are tender-scoped, so the pair key is the normalized legal
    name — the entity identity across tenders.
    """
    to_key, first_id, display = _bidder_entity_map(db)
    bids = _current_bids(db)
    names_by_tender: dict[int, set[str]] = defaultdict(set)
    for bid in bids:
        nm = to_key.get(bid.bidder_id)
        if nm:
            names_by_tender[bid.tender_id].add(nm)
    pair_tenders: dict[tuple[str, str], set[int]] = defaultdict(set)
    for tender_id, names in names_by_tender.items():
        if len(names) < 2:
            continue
        for pair in combinations(sorted(names), 2):
            pair_tenders[pair].add(tender_id)

    signals = []
    for (n1, n2), tender_ids in sorted(pair_tenders.items()):
        n = len(tender_ids)
        if n < _COHORT_MIN_TENDERS_ELEVATED:
            continue
        severity = SEV_REVIEW if n >= _COHORT_MIN_TENDERS_REVIEW else SEV_ELEVATED
        refs = [_tender_ref(db, tid) for tid in sorted(tender_ids)]
        demo = any(r["is_demo_history"] for r in refs)
        d1, d2 = display.get(n1, n1), display.get(n2, n2)
        signals.append(
            {
                "signal_type": IntegritySignalType.RECURRING_BIDDER_COHORT.value,
                "severity": severity,
                "title": f"Recurring bidder cohort: {d1} + {d2}",
                "description": (
                    f"These two bidders participated together in {n} tender(s). "
                    "Recurring cohorts are a normal part of specialised markets, but "
                    "persistent co-participation is worth a procedural review."
                ),
                "bidder_id": first_id.get(n1),
                "tender_id": None,
                "affected_bids": sorted(
                    bid.id
                    for bid in bids
                    if bid.tender_id in tender_ids
                    and to_key.get(bid.bidder_id) in (n1, n2)
                ),
                "affected_tenders": refs,
                "evidence": [
                    {
                        "label": "Co-participation record",
                        "detail": (
                            f"{d1} and {d2} both submitted bids in: "
                            + ", ".join(r["tender_number"] for r in refs)
                        ),
                        "records": n,
                    }
                ],
                "rule_logic": (
                    "Bidder pairs co-occurring in >= "
                    f"{_COHORT_MIN_TENDERS_ELEVATED} tenders (ELEVATED) or >= "
                    f"{_COHORT_MIN_TENDERS_REVIEW} tenders (REVIEW_REQUIRED), "
                    "computed from bid_submissions grouped by stable entity identity "
                    "(PAN, else GSTIN, else normalized legal name)."                ),
                "recommended_action": (
                    "Review the tender history for these bidders; confirm the "
                    "participation pattern is consistent with open competition."
                ),
                "is_demo_history": demo,
                "dedupe_key": f"cohort:{n1}:{n2}",
                # Pair identity for consolidation: distinct legal names, so
                # two names sharing one PAN still form a visible pair.
                "entity_keys": sorted({d1, d2}),
            }
        )
    return signals


def _detect_repeated_participation(db: Session) -> list[dict]:
    """One bidder appearing across many tenders (grouped by legal entity)."""
    to_key, first_id, display = _bidder_entity_map(db)
    counts: dict[str, set[int]] = defaultdict(set)
    for bid in _current_bids(db):
        nm = to_key.get(bid.bidder_id)
        if nm:
            counts[nm].add(bid.tender_id)
    signals = []
    for name, tender_ids in sorted(counts.items()):
        n = len(tender_ids)
        if n < _REPEAT_MIN_TENDERS_ELEVATED:
            continue
        severity = SEV_REVIEW if n >= _REPEAT_MIN_TENDERS_REVIEW else SEV_ELEVATED
        refs = [_tender_ref(db, tid) for tid in sorted(tender_ids)]
        demo = any(r["is_demo_history"] for r in refs)
        disp = display.get(name, name)
        signals.append(
            {
                "signal_type": IntegritySignalType.REPEATED_PARTICIPATION.value,
                "severity": severity,
                "title": f"Repeated participation: {disp}",
                "description": (
                    f"{disp} has participated in {n} tender(s). Frequent "
                    "participation is expected from established vendors; the "
                    "pattern is recorded so the officer can correlate it with "
                    "award outcomes."
                ),
                "bidder_id": first_id.get(name),
                "tender_id": None,
                "affected_bids": [],
                "affected_tenders": refs,
                "evidence": [
                    {
                        "label": "Participation record",
                        "detail": (
                            f"{n} tenders: "
                            + ", ".join(r["tender_number"] for r in refs)
                        ),
                        "records": n,
                    }
                ],
                "rule_logic": (
                    f"Bidder present in >= {_REPEAT_MIN_TENDERS_ELEVATED} tenders "
                    f"(ELEVATED) or >= {_REPEAT_MIN_TENDERS_REVIEW} (REVIEW_REQUIRED)."
                ),
                "recommended_action": (
                    "Correlate participation frequency with award outcomes before "
                    "drawing any conclusion."
                ),
                "is_demo_history": demo,
                "dedupe_key": f"repeat:{name}",
            }
        )
    return signals


def _detect_bid_rotation(db: Session) -> list[dict]:
    """Alternating award sequences among a small winner set.

    Winner identity is the PAN/GSTIN-anchored entity key (bidder rows are
    tender-scoped), so the same entity winning across tenders is detected.
    """
    to_key, _, display = _bidder_entity_map(db)
    awards: list[tuple[datetime, int, str]] = []  # (date, tender_id, winner name)
    for bid in _current_bids(db):
        if (bid.officer_decision or "").upper() == "APPROVE":
            nm = to_key.get(bid.bidder_id)
            if not nm:
                continue
            t = db.get(Tender, bid.tender_id)
            awards.append(
                (t.closing_date or t.created_at, bid.tender_id, nm)
            )
    awards.sort(key=lambda a: (a[0] is None, a[0]))
    if len(awards) < _ROTATION_MIN_AWARDS:
        return []
    winners = [name for _, _, name in awards]
    distinct = set(winners)
    # Alternation: no winner takes two consecutive awards AND the winner set
    # stays small — a pattern that warrants review, not a verdict.
    alternating = all(winners[i] != winners[i + 1] for i in range(len(winners) - 1))
    if not (alternating and len(distinct) <= _ROTATION_MAX_WINNERS):
        return []
    seq = [_tender_ref(db, tid) for _, tid, _ in awards]
    demo = any(r["is_demo_history"] for r in seq)
    disp_winners = [display.get(w, w) for w in winners]
    return [
        {
            "signal_type": IntegritySignalType.BID_ROTATION_PATTERN.value,
            "severity": SEV_REVIEW,
            "title": "Possible bid rotation pattern",
            "description": (
                f"Award sequence across {len(awards)} tenders alternates between "
                f"{len(distinct)} bidder(s) with no consecutive repeat: "
                + " → ".join(disp_winners)
                + ". This is a pattern for review, not evidence of misconduct."
            ),
            "bidder_id": None,
            "tender_id": None,
            "affected_bids": [],
            "affected_tenders": seq,
            "evidence": [
                {
                    "label": "Award sequence",
                    "detail": "; ".join(
                        f"{r['tender_number']}: {n}" for r, n in zip(seq, disp_winners)
                    ),
                    "records": len(awards),
                }
            ],
            "rule_logic": (
                f">= {_ROTATION_MIN_AWARDS} APPROVE decisions, alternating "
                f"winners, distinct winner set <= {_ROTATION_MAX_WINNERS}."
            ),
            "recommended_action": (
                "Examine bid prices and evaluation notes across these tenders "
                "for independent competitive behaviour."
            ),
            "is_demo_history": demo,
            "dedupe_key": "rotation:" + ":".join(winners),
        }
    ]


def _detect_bidder_relationships(db: Session) -> list[dict]:
    """Same contact identifiers shared across different legal names."""
    bidders = _current_bidders(db)
    buckets: dict[str, set[int]] = defaultdict(set)
    for b in bidders:
        keys = []
        if b.contact_email:
            keys.append("email:" + b.contact_email.strip().lower())
        if b.contact_phone:
            digits = "".join(ch for ch in b.contact_phone if ch.isdigit())[-10:]
            if digits:
                keys.append("phone:" + digits)
        if b.registered_address:
            keys.append("addr:" + normalize_name(b.registered_address))
        for k in keys:
            buckets[k].add(b.id)
    signals = []
    for key, bidder_ids in sorted(buckets.items()):
        names = {normalize_name(_bidder_name(db, i)) for i in bidder_ids}
        if len(bidder_ids) < 2 or len(names) < 2:
            continue
        kind = key.split(":", 1)[0]
        kind_label = {"email": "contact email", "phone": "contact phone",
                      "addr": "registered address"}.get(kind, kind)
        bidder_names = [_bidder_name(db, i) for i in sorted(bidder_ids)]
        # Pair identity for consolidation: distinct legal names, so two
        # names sharing one identifier still form a visible pair.
        entity_keys = sorted(set(bidder_names))
        signals.append(
            {
                "signal_type": IntegritySignalType.BIDDER_RELATIONSHIP.value,
                "severity": SEV_REVIEW,
                "title": f"Shared {kind_label} across bidder identities",
                "description": (
                    f"{len(bidder_names)} different legal names share the same "
                    f"{kind_label}: " + ", ".join(bidder_names)
                    + ". May be a shared office/consultant — or related entities."
                ),
                "bidder_id": sorted(bidder_ids)[0],
                "tender_id": None,
                "affected_bids": [],
                "affected_tenders": [],
                "evidence": [
                    {
                        "label": f"Shared {kind_label}",
                        "detail": f"{key.split(':', 1)[1]} used by: "
                        + ", ".join(bidder_names),
                        "records": len(bidder_ids),
                    }
                ],
                "rule_logic": (
                    "Identical normalized contact email / phone / address across "
                    ">= 2 distinct legal names in the bidders table."
                ),
                "recommended_action": (
                    "Ask the bidders to confirm their relationship, if any, and "
                    "record the clarification."
                ),
                "is_demo_history": False,
                "dedupe_key": f"rel:{key}",
                "entity_keys": entity_keys,
            }
        )
    return signals


def _detect_officer_bidder_association(db: Session) -> list[dict]:
    """Same officer repeatedly deciding the same bidder's bids.

    Requires at least two distinct deciding officers in the dataset — with a
    single officer doing everything (typical demo), no signal is raised.
    The bidder key is the PAN/GSTIN-anchored entity key (bidder rows are
    tender-scoped).
    """
    to_key, first_id, display = _bidder_entity_map(db)
    events = (
        db.query(AuditLog)
        .filter(
            AuditLog.action.in_(("OFFICER_DECISION", "OFFICER_DECISION_CHANGED"))
        )
        .all()
    )
    by_pair: dict[tuple[int, str], int] = defaultdict(int)
    officers: set[int] = set()
    for e in events:
        try:
            bid_id = int(e.entity_id)
        except (TypeError, ValueError):
            continue
        bid = db.get(BidSubmission, bid_id)
        if bid is None or e.user_id is None:
            continue
        nm = to_key.get(bid.bidder_id)
        if not nm:
            continue
        officers.add(e.user_id)
        by_pair[(e.user_id, nm)] += 1
    if len(officers) < 2:
        return []  # insufficient data for a meaningful association signal
    signals = []
    for (user_id, name), n in sorted(by_pair.items()):
        if n < _ASSOCIATION_MIN_DECISIONS:
            continue
        user = db.get(User, user_id)
        officer = user.name if user else f"user #{user_id}"
        disp = display.get(name, name)
        signals.append(
            {
                "signal_type": IntegritySignalType.OFFICER_BIDDER_ASSOCIATION.value,
                "severity": SEV_REVIEW,
                "title": f"Repeated officer–bidder association: {officer} / {disp}",
                "description": (
                    f"{officer} recorded {n} decisions on bids from {disp}. "
                    "Workload concentration is common; flag for rotation review."
                ),
                "bidder_id": first_id.get(name),
                "tender_id": None,
                "affected_bids": [],
                "affected_tenders": [],
                "evidence": [
                    {
                        "label": "Decision record",
                        "detail": f"{n} OFFICER_DECISION audit events by {officer} "
                        f"on {disp} bids",
                        "records": n,
                    }
                ],
                "rule_logic": (
                    f">= {_ASSOCIATION_MIN_DECISIONS} OFFICER_DECISION events for "
                    "one (officer, bidder) pair with >= 2 distinct officers in "
                    "the dataset."
                ),
                "recommended_action": (
                    "Consider decision-rotation for this "
                    "bidder's future bids."
                ),
                "is_demo_history": False,
                "dedupe_key": f"assoc:{user_id}:{name}",
            }
        )
    return signals


def _detect_concentration(db: Session) -> list[dict]:
    """Same legal entity repeatedly winning across tenders."""
    to_key, first_id, display = _bidder_entity_map(db)
    wins: dict[str, list[int]] = defaultdict(list)  # normalized name -> tender_ids
    for bid in _current_bids(db):
        if (bid.officer_decision or "").upper() == "APPROVE":
            nm = to_key.get(bid.bidder_id)
            if nm:
                wins[nm].append(bid.tender_id)
    signals = []
    for name, tender_ids in sorted(wins.items()):
        n = len(set(tender_ids))
        if n < _CONCENTRATION_MIN_WINS_ELEVATED:
            continue
        severity = SEV_REVIEW if n >= _CONCENTRATION_MIN_WINS_REVIEW else SEV_ELEVATED
        refs = [_tender_ref(db, tid) for tid in sorted(set(tender_ids))]
        demo = any(r["is_demo_history"] for r in refs)
        disp = display.get(name, name)
        signals.append(
            {
                "signal_type": IntegritySignalType.CROSS_TENDER_CONCENTRATION.value,
                "severity": severity,
                "title": f"Award concentration: {disp}",
                "description": (
                    f"{disp} received APPROVE decisions in {n} tender(s). "
                    "Concentration can reflect genuine capability; recorded for "
                    "officer awareness."
                ),
                "bidder_id": first_id.get(name),
                "tender_id": None,
                "affected_bids": [],
                "affected_tenders": refs,
                "evidence": [
                    {
                        "label": "Award record",
                        "detail": f"APPROVE in: "
                        + ", ".join(r["tender_number"] for r in refs),
                        "records": n,
                    }
                ],
                "rule_logic": (
                    f">= {_CONCENTRATION_MIN_WINS_ELEVATED} APPROVE decisions "
                    f"(ELEVATED) or >= {_CONCENTRATION_MIN_WINS_REVIEW} "
                    "(REVIEW_REQUIRED) for one bidder across tenders."
                ),
                "recommended_action": (
                    "Confirm awards followed the published evaluation criteria."
                ),
                "is_demo_history": demo,
                "dedupe_key": f"conc:{name}",
            }
        )
    return signals


def _detect_identity_relationships(db: Session) -> list[dict]:
    """Same validated PAN/GSTIN registered under different legal names.

    Only structurally valid identifiers are bucketed — a malformed value can
    never trigger a false "identifier reused" signal.
    """
    bidders = _current_bidders(db)
    buckets: dict[str, set[int]] = defaultdict(set)
    for b in bidders:
        pan = _valid_pan(b.pan)
        if pan:
            buckets["pan:" + pan].add(b.id)
        gstin = _valid_gstin(b.gstin)
        if gstin:
            buckets["gstin:" + gstin].add(b.id)
    signals = []
    for key, bidder_ids in sorted(buckets.items()):
        names = {normalize_name(_bidder_name(db, i)) for i in bidder_ids}
        if len(names) < 2:
            continue
        kind, ident = key.split(":", 1)
        bidder_names = [_bidder_name(db, i) for i in sorted(bidder_ids)]
        # Pair identity for consolidation: distinct legal names, so two
        # names sharing one identifier still form a visible pair.
        entity_keys = sorted(set(bidder_names))
        signals.append(
            {
                "signal_type": IntegritySignalType.DOCUMENT_IDENTITY_RELATIONSHIP.value,
                "severity": SEV_REVIEW,
                "title": f"Identifier reused across identities ({kind.upper()})",
                "description": (
                    f"{kind.upper()} {ident} is registered under {len(names)} "
                    "different legal names: " + ", ".join(bidder_names)
                    + ". Requires review — identifiers must be unique per entity."
                ),
                "bidder_id": sorted(bidder_ids)[0],
                "tender_id": None,
                "affected_bids": [],
                "affected_tenders": [],
                "evidence": [
                    {
                        "label": f"Shared {kind.upper()}",
                        "detail": f"{ident} → " + ", ".join(bidder_names),
                        "records": len(bidder_ids),
                    }
                ],
                "rule_logic": (
                    "Identical structurally-valid PAN/GSTIN linked to >= 2 "
                    "distinct normalized legal names (malformed identifiers "
                    "are excluded, never bucketed)."
                ),
                "recommended_action": (
                    "Verify which legal name legitimately holds the identifier; "
                    "seek clarification from the bidders."
                ),
                "is_demo_history": False,
                "dedupe_key": f"ident:{key}",
                "entity_keys": entity_keys,
            }
        )
    return signals


# ---------------------------------------------------------------------------
# New detectors: document similarity, identity inconsistency, repeated anomalies
# ---------------------------------------------------------------------------

_SIMILARITY_MIN_CHARS = 150
_SIMILARITY_REVIEW = 0.95
_SIMILARITY_ELEVATED = 0.85
_ANOMALY_MIN_TENDERS_ELEVATED = 2
_ANOMALY_MIN_TENDERS_REVIEW = 3

_BOILERPLATE_MARKERS = (
    "sample",
    "demonstration only",
    "demo data",
    "prototype demonstration",
)


def _doc_substantive_text(doc: Document) -> str | None:
    """Normalized document text with shared boilerplate stripped.

    Returns None when the document cannot be evaluated (missing/unreadable
    file, or too little substantive content). Callers treat that as "could
    not be evaluated" — never as a signal.
    """
    path = getattr(doc, "file_path", None)
    if not path or not Path(path).is_file():
        return None
    try:
        import fitz

        with fitz.open(path) as pdf:
            raw = "\n".join(page.get_text() for page in pdf)
    except Exception:
        return None
    kept = []
    for line in raw.splitlines():
        low = line.strip().lower()
        if not low:
            continue
        if any(m in low for m in _BOILERPLATE_MARKERS):
            continue
        kept.append(line.strip())
    text = re.sub(r"\s+", " ", " ".join(kept)).strip().lower()
    if len(text) < _SIMILARITY_MIN_CHARS:
        return None
    return text


def _detect_document_similarity(db: Session) -> list[dict]:
    """Near-identical substantive document content across different entities.

    Compares normalized document text pairwise within each document type.
    Shared template boilerplate is stripped first, so identical common
    templates alone cannot trigger a strong signal — only genuinely similar
    substantive content does. Consolidated dossiers and unclassified uploads
    are excluded (containers, not single evidence documents).
    """
    docs = (
        db.query(Document)
        .filter(
            Document.processing_status == "PROCESSED",
            Document.document_type.notin_(("BID_DOSSIER", "UNCLASSIFIED")),
        )
        .all()
    )
    if not docs:
        return []
    to_key, first_id, display = _bidder_entity_map(db)
    bid_entity: dict[int, str] = {}
    for bid in _current_bids(db):
        key = to_key.get(bid.bidder_id)
        if key:
            bid_entity[bid.id] = key

    texts: dict[int, str] = {}
    doc_by_id: dict[int, Document] = {}
    for doc in docs:
        if doc.bid_id not in bid_entity:
            continue
        text = _doc_substantive_text(doc)
        if text:
            texts[doc.id] = text
            doc_by_id[doc.id] = doc
    by_type: dict[str, list[int]] = defaultdict(list)
    for doc_id, doc in doc_by_id.items():
        by_type[doc.document_type].append(doc_id)

    # Extracted identifier values per document, for the "matching identifiers"
    # evidence (same PAN/GSTIN appearing in two entities' documents).
    idents: dict[int, set[str]] = defaultdict(set)
    if doc_by_id:
        for f in (
            db.query(ExtractedField)
            .filter(ExtractedField.document_id.in_(list(doc_by_id)))
            .all()
        ):
            if f.field_name in ("pan", "gstin", "udyam_number", "cin"):
                val = (f.normalized_value or f.field_value or "").strip().upper()
                if val:
                    idents[f.document_id].add(val)

    signals: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for doc_type, ids in sorted(by_type.items()):
        for a_id, b_id in combinations(sorted(ids), 2):
            a, b = doc_by_id[a_id], doc_by_id[b_id]
            ka, kb = bid_entity[a.bid_id], bid_entity[b.bid_id]
            if ka == kb:
                continue  # same entity: not a cross-bid signal
            pair = (min(ka, kb), max(ka, kb), doc_type)
            if pair in seen:
                continue
            ratio = difflib.SequenceMatcher(None, texts[a_id], texts[b_id]).ratio()
            shared = sorted(idents[a_id] & idents[b_id])
            # Noise guard: pure text similarity in the 85-95% band without any
            # shared extracted identifier is too weak to be a meaningful signal
            # (template-generated documents routinely exceed 85%). A signal
            # requires either near-identical text (>=95%, REVIEW_REQUIRED) or
            # a concrete shared identifier linking the two entities.
            if ratio < _SIMILARITY_REVIEW and not shared:
                continue
            seen.add(pair)
            # A signal requires near-identical text (>=95%) or a concrete
            # shared identifier — both warrant officer review.
            severity = SEV_REVIEW
            da, db_ = display.get(ka, ka), display.get(kb, kb)
            detail = (
                f"{doc_type}: substantive text similarity "
                f"{ratio:.0%} between {da} ({a.filename}) and {db_} ({b.filename})"
            )
            if shared:
                detail += f"; shared extracted identifier(s): {', '.join(shared)}"
            # Flag demo-sourced findings so the UI can badge synthetic data.
            demo = any(
                (db.get(Tender, db.get(BidSubmission, bid_id).tender_id).tender_number
                 or "").startswith("INT-DEMO-")
                for bid_id in (a.bid_id, b.bid_id)
                if db.get(BidSubmission, bid_id) is not None
            )
            signals.append(
                {
                    "signal_type": IntegritySignalType.CROSS_BID_DOCUMENT_SIMILARITY.value,
                    "severity": severity,
                    "title": f"Similar {doc_type.lower().replace('_', ' ')} content: {da} + {db_}",
                    "description": (
                        "Two different bidders submitted unusually similar document "
                        "content. Similar documents do not prove coordination — "
                        "common agents or templates are innocent explanations — "
                        "but near-identical substantive content warrants review."
                    ),
                    "bidder_id": first_id.get(ka),
                    "tender_id": None,
                    "affected_bids": sorted({a.bid_id, b.bid_id}),
                    "affected_tenders": [],
                    "evidence": [
                        {
                            "label": "Document similarity",
                            "detail": detail,
                            "records": 2,
                        }
                    ],
                    "rule_logic": (
                        "Pairwise normalized-text similarity within a document type "
                        f"(boilerplate stripped; >= {_SIMILARITY_REVIEW:.0%} "
                        "REVIEW_REQUIRED). Shared extracted PAN/GSTIN/Udyam/CIN "
                        "across entities also triggers REVIEW_REQUIRED. "
                        "Consolidated dossiers and unclassified uploads are excluded."
                    ),
                    "recommended_action": (
                        "Compare the two documents side by side; ask the bidders "
                        "whether a common preparer was used and confirm independent "
                        "preparation."
                    ),
                    "is_demo_history": demo,
                    "dedupe_key": f"docsim:{pair[0]}:{pair[1]}:{doc_type}",
                    # Pair identity for consolidation: distinct legal names.
                    "entity_keys": sorted({da, db_}),
                }
            )
    return signals


def _detect_identity_inconsistency(db: Session) -> list[dict]:
    """Conflicting identity/registration data for one bidder across sources.

    Compares the bidder row (registered PAN/GSTIN/legal name) against values
    extracted from its own documents. A conflict is reported only when both
    sides carry structurally valid values; missing data is never a conflict.
    """
    signals: list[dict] = []
    bids_by_bidder: dict[int, list[int]] = defaultdict(list)
    for bid in _current_bids(db):
        bids_by_bidder[bid.bidder_id].append(bid.id)

    for bidder in _current_bidders(db):
        bid_ids = bids_by_bidder.get(bidder.id, [])
        if not bid_ids:
            continue
        doc_ids = [
            d.id for d in db.query(Document).filter(Document.bid_id.in_(bid_ids)).all()
        ]
        if not doc_ids:
            continue
        fields = (
            db.query(ExtractedField)
            .filter(ExtractedField.document_id.in_(doc_ids))
            .all()
        )
        ext_pans = {
            (f.normalized_value or f.field_value or "").strip().upper()
            for f in fields
            if f.field_name == "pan"
        }
        ext_pans = {p for p in ext_pans if _valid_pan(p)}
        ext_gstins = {
            (f.normalized_value or f.field_value or "").strip().upper()
            for f in fields
            if f.field_name == "gstin"
        }
        ext_gstins = {g for g in ext_gstins if _valid_gstin(g)}
        ext_names = {
            normalize_name(f.normalized_value or f.field_value or "")
            for f in fields
            if f.field_name == "legal_name"
        }
        ext_names.discard("")

        conflicts: list[str] = []
        reg_pan = _valid_pan(bidder.pan)
        if reg_pan and ext_pans and reg_pan not in ext_pans:
            conflicts.append(
                f"registered PAN {reg_pan} but document(s) show "
                f"{', '.join(sorted(ext_pans))}"
            )
        reg_gstin = _valid_gstin(bidder.gstin)
        if reg_gstin and ext_gstins and reg_gstin not in ext_gstins:
            conflicts.append(
                f"registered GSTIN {reg_gstin} but document(s) show "
                f"{', '.join(sorted(ext_gstins))}"
            )
        reg_name = normalize_name(bidder.legal_name)
        if reg_name and ext_names:
            reg_tokens = set(reg_name.split())
            # Flag only genuine divergence, not suffix/abbreviation variants.
            if reg_tokens and all(
                len(reg_tokens & set(n.split())) / len(reg_tokens) < 0.5
                for n in ext_names
            ):
                conflicts.append(
                    f"registered as '{bidder.legal_name}' but document(s) name "
                    f"{', '.join(sorted(ext_names)[:3])}"
                )
        if not conflicts:
            continue
        demo = any(
            (db.get(Tender, db.get(BidSubmission, bid_id).tender_id).tender_number
             or "").startswith("INT-DEMO-")
            for bid_id in bid_ids
            if db.get(BidSubmission, bid_id) is not None
        )
        signals.append(
            {
                "signal_type": IntegritySignalType.IDENTITY_REGISTRATION_INCONSISTENCY.value,
                "severity": SEV_REVIEW,
                "title": f"Identity inconsistency: {bidder.legal_name}",
                "description": (
                    "The bidder's registered identity conflicts with identity "
                    "data extracted from its own submitted documents. "
                    + " ".join(conflicts)
                ),
                "bidder_id": bidder.id,
                "tender_id": None,
                "affected_bids": sorted(bid_ids),
                "affected_tenders": [],
                "evidence": [
                    {
                        "label": "Identity conflict",
                        "detail": "; ".join(conflicts),
                        "records": len(conflicts),
                    }
                ],
                "rule_logic": (
                    "Bidder-row PAN/GSTIN/legal name compared against values "
                    "extracted from the bidder's own documents. A conflict "
                    "needs structurally valid values on both sides; missing "
                    "data is never a conflict."
                ),
                "recommended_action": (
                    "Seek clarification on which identity is correct and verify "
                    "against the statutory registry before proceeding."
                ),
                "is_demo_history": demo,
                "dedupe_key": f"identinc:{bidder.id}",
            }
        )
    return signals


def _detect_repeated_anomalies(db: Session) -> list[dict]:
    """Same entity with compliance FAIL/MISMATCH in 2+ distinct tenders.

    Each anomaly is an independently computed compliance result; the signal
    only notes the repetition across tender history.
    """
    to_key, first_id, display = _bidder_entity_map(db)
    tender_of_bid: dict[int, int] = {}
    entity_of_bid: dict[int, str] = {}
    for bid in _current_bids(db):
        key = to_key.get(bid.bidder_id)
        if key:
            tender_of_bid[bid.id] = bid.tender_id
            entity_of_bid[bid.id] = key

    anomalies: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    req_names: dict[int, str] = {}
    for row in (
        db.query(ComplianceResult)
        .filter(ComplianceResult.status.in_(("FAIL", "MISMATCH")))
        .all()
    ):
        key = entity_of_bid.get(row.bid_id)
        if not key:
            continue
        if row.requirement_id not in req_names:
            req = db.get(TenderRequirement, row.requirement_id)
            req_names[row.requirement_id] = (
                req.requirement_name if req else f"requirement {row.requirement_id}"
            )
        anomalies[key][tender_of_bid[row.bid_id]].append(
            f"{req_names[row.requirement_id]}: {row.status}"
        )

    signals: list[dict] = []
    for key, by_tender in sorted(anomalies.items()):
        n = len(by_tender)
        if n < _ANOMALY_MIN_TENDERS_ELEVATED:
            continue
        severity = (
            SEV_REVIEW if n >= _ANOMALY_MIN_TENDERS_REVIEW else SEV_ELEVATED
        )
        refs = [_tender_ref(db, tid) for tid in sorted(by_tender)]
        demo = any(r["is_demo_history"] for r in refs)
        name = display.get(key, key)
        detail = "; ".join(
            f"{_tender_ref(db, tid)['tender_number']} "
            f"({len(v)} anomaly(ies): {', '.join(sorted(set(v))[:3])})"
            for tid, v in sorted(by_tender.items())
        )
        signals.append(
            {
                "signal_type": IntegritySignalType.REPEATED_HISTORICAL_ANOMALIES.value,
                "severity": severity,
                "title": f"Repeated anomalies: {name} ({n} tenders)",
                "description": (
                    f"{name} recorded compliance FAIL/MISMATCH outcomes in "
                    f"{n} distinct tenders. Each outcome was computed "
                    "independently by the compliance engine; the repetition "
                    "across history is what warrants review."
                ),
                "bidder_id": first_id.get(key),
                "tender_id": None,
                "affected_bids": [],
                "affected_tenders": refs,
                "rule_logic": (
                    "Compliance FAIL/MISMATCH results grouped by stable entity "
                    f"identity; >= {_ANOMALY_MIN_TENDERS_ELEVATED} tenders ELEVATED, "
                    f">= {_ANOMALY_MIN_TENDERS_REVIEW} tenders REVIEW_REQUIRED."
                ),
                "evidence": [
                    {
                        "label": "Anomalies by tender",
                        "detail": detail,
                        "records": sum(len(v) for v in by_tender.values()),
                    }
                ],
                "recommended_action": (
                    "Review the bidder's compliance history across these tenders "
                    "before award; consider enhanced verification of new bids."
                ),
                "is_demo_history": demo,
                "dedupe_key": f"repanom:{key}",
            }
        )
    return signals


# SIMPLIFIED MODE (2026-10-06): Integrity currently detects ONLY repeated
# tender participation by the same bidder. All other detectors below are
# FUTURE SCOPE — their code is kept but they do not run and must not
# generate signals right now (no document matching, no GST/PAN/Udyam
# correlation, no bidder-pair/cohort signals).
_DETECTORS = (
    _detect_repeated_participation,
    # FUTURE SCOPE (disabled):
    # _detect_recurring_cohorts,
    # _detect_bid_rotation,
    # _detect_bidder_relationships,
    # _detect_officer_bidder_association,
    # _detect_concentration,
    # _detect_identity_relationships,
    # _detect_document_similarity,
    # _detect_identity_inconsistency,
    # _detect_repeated_anomalies,
)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


# Signal types that describe a *bidder pair* relationship. Findings of these
# types are consolidated so that ONE unique bidder pair yields ONE signal,
# with every detector's output kept as supporting evidence inside it.
_PAIR_RELATIONSHIP_TYPES = frozenset(
    {
        IntegritySignalType.RECURRING_BIDDER_COHORT.value,
        IntegritySignalType.CROSS_BID_DOCUMENT_SIMILARITY.value,
        IntegritySignalType.DOCUMENT_IDENTITY_RELATIONSHIP.value,
        IntegritySignalType.BIDDER_RELATIONSHIP.value,
    }
)


def _consolidate_pair_signals(db: Session, detected: list[dict]) -> list[dict]:
    """Merge pair-based findings into one signal per unique bidder pair.

    One unique bidder pair = one integrity signal. ``A + B`` and ``B + A``
    are the same relationship (legal names are sorted). All supporting
    evidence — co-participation records, similar documents, shared
    identifiers/contacts — is preserved inside the single signal's evidence
    list. Non-pair findings pass through unchanged.
    """
    name_to_bidder: dict[str, int] = {}
    for b in _current_bidders(db):
        if b.legal_name:
            name_to_bidder.setdefault(b.legal_name, b.id)
    pair_buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    others: list[dict] = []
    for sig in detected:
        if sig.get("signal_type") in _PAIR_RELATIONSHIP_TYPES:
            keys = sorted({k for k in (sig.get("entity_keys") or []) if k})
            if len(keys) >= 2:
                for a, b in combinations(keys, 2):
                    pair_buckets[(a, b)].append(sig)
                continue
        others.append(sig)

    for (d1, d2), sigs in sorted(pair_buckets.items()):
        severity = (
            SEV_REVIEW
            if any(s.get("severity") == SEV_REVIEW for s in sigs)
            else SEV_ELEVATED
        )
        evidence: list[dict] = []
        affected_bids: list[int] = []
        affected_tenders: list[dict] = []
        seen_tenders: set[str] = set()
        demo = False
        for s in sigs:
            for ev in s.get("evidence") or []:
                item = dict(ev)
                item.setdefault("source_signal", s.get("signal_type"))
                evidence.append(item)
            for bid_id in s.get("affected_bids") or []:
                if bid_id not in affected_bids:
                    affected_bids.append(bid_id)
            for t in s.get("affected_tenders") or []:
                tn = t.get("tender_number") if isinstance(t, dict) else str(t)
                if tn not in seen_tenders:
                    seen_tenders.add(tn)
                    affected_tenders.append(t)
            if s.get("is_demo_history"):
                demo = True
        pair_key = f"{normalize_name(d1)}|{normalize_name(d2)}"
        others.append(
            {
                "signal_type": IntegritySignalType.RECURRING_BIDDER_COHORT.value,
                "severity": severity,
                "title": f"Recurring bidder relationship: {d1} + {d2}",
                "description": (
                    f"{d1} and {d2} show a recurring relationship across the "
                    f"tender data ({len(evidence)} supporting record(s)). "
                    "Review the supporting evidence to assess whether the "
                    "pattern is consistent with open competition."
                ),
                "bidder_id": name_to_bidder.get(d1),
                "tender_id": None,
                "affected_bids": affected_bids,
                "affected_tenders": affected_tenders,
                "evidence": evidence,
                "rule_logic": (
                    "One signal per unique bidder pair (A+B == B+A). "
                    "Consolidates co-participation records, similar-document "
                    "findings, and shared identifier/contact findings for the "
                    "pair into a single relationship signal with supporting "
                    "evidence."
                ),
                "recommended_action": (
                    "Review the supporting evidence for this bidder pair; "
                    "confirm the relationship pattern is consistent with open "
                    "competition and record the outcome."
                ),
                "is_demo_history": demo,
                "dedupe_key": f"pairrel:{pair_key}",
            }
        )
    return others


def run_integrity_analysis(
    db: Session, user_id: int | None = None
) -> dict:
    """Run all detectors; persist new signals; audit the run.

    Idempotent: a signal whose dedupe key already has a non-CLOSED finding is
    not duplicated — its ``evaluated_at`` is refreshed instead.

    Concurrency-safe: only one analysis runs at a time per process. A second
    concurrent call returns ``{"already_running": True}`` instead of running,
    so double-clicks (or a Load-triggered auto-analysis racing a manual run)
    can never create duplicate findings.
    """
    if not _ANALYSIS_LOCK.acquire(blocking=False):
        return {
            "already_running": True,
            "new_signals": 0,
            "total_open": None,
            "message": "Integrity analysis is already running.",
        }
    try:
        return _run_integrity_analysis_locked(db, user_id=user_id)
    finally:
        _ANALYSIS_LOCK.release()


_ANALYSIS_LOCK = threading.Lock()


def _run_integrity_analysis_locked(
    db: Session, user_id: int | None = None
) -> dict:
    detected: list[dict] = []
    for detector in _DETECTORS:
        try:
            detected.extend(detector(db))
        except Exception:
            log.exception("Integrity detector %s failed", detector.__name__)

    new_count = 0
    for sig in detected:
        existing = (
            db.query(IntegrityFinding)
            .filter(
                IntegrityFinding.signal_type == sig["signal_type"],
                IntegrityFinding.status != IntegrityStatus.CLOSED.value,
            )
            .all()
        )
        dupe = next(
            (
                f
                for f in existing
                if (f.evidence and f.evidence[0].get("dedupe_key") == sig["dedupe_key"])
                or _legacy_dedupe_match(f, sig)
            ),
            None,
        )
        if dupe is not None:
            dupe.evaluated_at = _utcnow()
            continue
        evidence = list(sig["evidence"])
        evidence[0]["dedupe_key"] = sig["dedupe_key"]
        finding = IntegrityFinding(
            tender_id=sig["tender_id"],
            bidder_id=sig["bidder_id"],
            signal_type=sig["signal_type"],
            severity=sig["severity"],
            title=sig["title"],
            description=sig["description"],
            affected_bids=sig["affected_bids"],
            affected_tenders=sig["affected_tenders"],
            evidence=evidence,
            rule_logic=sig["rule_logic"],
            recommended_action=sig["recommended_action"],
            status=IntegrityStatus.OPEN.value,
            is_demo_history=sig["is_demo_history"],
        )
        db.add(finding)
        db.flush()
        append_audit(
            db,
            user_id=user_id,
            action="INTEGRITY_SIGNAL_DETECTED",
            entity_type="integrity_finding",
            entity_id=str(finding.id),
            metadata={
                "signal_type": sig["signal_type"],
                "severity": sig["severity"],
                "title": sig["title"],
            },
        )
        new_count += 1
    db.commit()

    bids = db.query(BidSubmission).filter(
        BidSubmission.tender_id.in_(_current_tender_ids(db))).count()
    bidders = db.query(Bidder).filter(
        Bidder.tender_id.in_(_current_tender_ids(db))).count()
    tenders = db.query(Tender).filter(
        (Tender.is_demo_history.is_(False)) | (Tender.is_demo_history.is_(None))).count()
    append_audit(
        db,
        user_id=user_id,
        action="INTEGRITY_ANALYSIS_RUN",
        entity_type="integrity_analysis",
        entity_id="global",
        metadata={
            "signals_detected": len(detected),
            "new_signals": new_count,
            "tenders_analyzed": tenders,
            "bidders_analyzed": bidders,
            "bids_analyzed": bids,
        },
    )
    return {
        "signals_detected": len(detected),
        "new_signals": new_count,
        "tenders_analyzed": tenders,
        "bidders_analyzed": bidders,
        "bids_analyzed": bids,
        "evaluated_at": _utcnow().isoformat(),
    }


def _legacy_dedupe_match(finding: IntegrityFinding, sig: dict) -> bool:
    """Match older findings created before dedupe_key was stored."""
    if finding.signal_type != sig["signal_type"]:
        return False
    if sig["signal_type"] == IntegritySignalType.RECURRING_BIDDER_COHORT.value:
        return finding.title == sig["title"]
    if sig["signal_type"] == IntegritySignalType.REPEATED_PARTICIPATION.value:
        return finding.bidder_id == sig["bidder_id"]
    return False


def _finding_dedupe_key(finding: IntegrityFinding) -> str | None:
    """Stable identity key for an existing finding.

    Prefers the stored ``dedupe_key`` in evidence[0]; falls back to a legacy
    key built from signal_type + title + bidder for findings created before
    dedupe keys were stored.
    """
    try:
        ev = finding.evidence or []
        if ev and isinstance(ev[0], dict) and ev[0].get("dedupe_key"):
            return str(ev[0]["dedupe_key"])
    except Exception:
        pass
    # Legacy fallback: signal_type + title + bidder identity.
    title = (finding.title or "").strip()
    if not title:
        return None
    return f"legacy:{finding.bidder_id}:{title}"


def dedupe_existing_findings(db: Session) -> dict:
    """Remove duplicate non-CLOSED findings, keeping the oldest of each group.

    Two findings are duplicates when they share signal_type and dedupe key.
    This repairs databases that accumulated duplicates (e.g. from concurrent
    analysis runs before the run lock existed, or from pre-dedupe-key data).
    Officer actions on surviving findings are preserved; CLOSED findings are
    never touched.
    """
    findings = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.status != IntegrityStatus.CLOSED.value)
        .order_by(IntegrityFinding.id.asc())
        .all()
    )
    seen: dict[tuple[str, str], int] = {}
    removed = 0
    for f in findings:
        key = _finding_dedupe_key(f)
        if key is None:
            continue
        group = (f.signal_type, key)
        if group in seen:
            db.delete(f)
            removed += 1
        else:
            seen[group] = f.id
    db.commit()
    return {"removed_duplicates": removed, "remaining_open": len(findings) - removed}


_ACTION_TRANSITIONS: dict[str, dict[str, str]] = {
    "acknowledge": {"from": (IntegrityStatus.OPEN.value,), "to": IntegrityStatus.ACKNOWLEDGED.value,
                    "audit": "INTEGRITY_SIGNAL_ACKNOWLEDGED"},
    "mark_review": {"from": (IntegrityStatus.OPEN.value, IntegrityStatus.ACKNOWLEDGED.value),
                    "to": IntegrityStatus.UNDER_REVIEW.value, "audit": "INTEGRITY_SIGNAL_REVIEWED"},
    "investigate": {"from": (IntegrityStatus.ACKNOWLEDGED.value, IntegrityStatus.UNDER_REVIEW.value),
                    "to": IntegrityStatus.INVESTIGATING.value, "audit": "INTEGRITY_SIGNAL_INVESTIGATED"},
    "close": {"from": (IntegrityStatus.OPEN.value, IntegrityStatus.ACKNOWLEDGED.value,
                       IntegrityStatus.UNDER_REVIEW.value, IntegrityStatus.INVESTIGATING.value),
              "to": IntegrityStatus.CLOSED.value, "audit": "INTEGRITY_SIGNAL_CLOSED"},
}


def apply_officer_action(
    db: Session,
    finding_id: int,
    action: str,
    user: User,
    note: str | None = None,
) -> IntegrityFinding:
    """Apply an officer action to a finding (audited)."""
    finding = db.get(IntegrityFinding, finding_id)
    if finding is None:
        raise ValueError(f"Integrity finding {finding_id} not found")
    action = (action or "").lower()
    if action == "add_note":
        if not (note or "").strip():
            raise ValueError("A review note is required")
        finding.officer_note = note.strip()
        append_audit(
            db, user_id=user.id, action="INTEGRITY_NOTE_ADDED",
            entity_type="integrity_finding", entity_id=str(finding.id),
            metadata={"note": note.strip()[:2000]},
        )
        db.commit()
        return finding
    spec = _ACTION_TRANSITIONS.get(action)
    if spec is None:
        raise ValueError(f"Unknown integrity action '{action}'")
    if finding.status not in spec["from"]:
        raise ValueError(
            f"Cannot '{action}' a signal in status {finding.status}"
        )
    if action == "close" and not (note or "").strip():
        raise ValueError("Closing a signal requires an officer note")
    finding.status = spec["to"]
    finding.reviewed_at = _utcnow()
    finding.reviewed_by = user.id
    if note and note.strip():
        finding.officer_note = note.strip()
    append_audit(
        db, user_id=user.id, action=spec["audit"],
        entity_type="integrity_finding", entity_id=str(finding.id),
        metadata={
            "from_status": spec["from"],
            "to_status": spec["to"],
            "note": (note or "").strip()[:2000] or None,
        },
    )
    db.commit()
    return finding


def active_signals_for_bid(db: Session, bid_id: int) -> list[IntegrityFinding]:
    """Non-closed findings whose evidence touches the given bid.

    Matches on stored bid ids, or on the same legal entity (normalized name)
    as the bid's bidder — bidder rows are tender-scoped.
    """
    findings = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.status != IntegrityStatus.CLOSED.value)
        .all()
    )
    bid = db.get(BidSubmission, bid_id)
    bid_norm = _bidder_entity_key(db, bid.bidder_id) if bid is not None else ""
    out = []
    for f in findings:
        bids = f.affected_bids or []
        if bid_id in bids:
            out.append(f)
            continue
        if bid_norm and f.bidder_id is not None:
            if _bidder_entity_key(db, f.bidder_id) == bid_norm:
                out.append(f)
    return out


def cleanup_stale_integrity_data(db: Session) -> dict:
    """Remove stale integrity data, keeping only current valid records.

    1. Deletes INT-DEMO demo-history tenders (via the surgical reset).
    2. Deletes findings referencing non-existent bids/tenders/bidders (orphans).
    3. Deletes findings tied to demo-history tenders.
    4. Collapses duplicate findings (dedupe).

    Never touches current valid Tender/Bid/Bidder records or CLOSED findings
    unrelated to stale data. Returns counts.
    """
    from app.seed.integrity_demo_seed import reset_integrity_demo_dataset

    removed = {"demo_tenders": 0, "orphan_findings": 0, "demo_findings": 0,
               "duplicate_findings_removed": 0}

    # 1. Remove INT-DEMO demo-history dataset (surgical) + any other
    # demo-history tenders not covered by the numbered reset.
    try:
        reset_res = reset_integrity_demo_dataset(db)
        removed["demo_tenders"] = reset_res.get("tenders", 0)
    except Exception:
        log.exception("Failed to reset integrity demo dataset during cleanup")
    # Catch-all: any remaining is_demo_history tenders.
    from app.services.delete_service import delete_tender
    for t in db.query(Tender).filter(Tender.is_demo_history.is_(True)).all():
        try:
            delete_tender(db, t.id)
            removed["demo_tenders"] += 1
        except Exception:
            log.exception("Failed to delete demo-history tender %s", t.id)
    db.flush()

    # Gather valid IDs.
    valid_tender_ids = set(_current_tender_ids(db))
    # Also include demo-history tender ids for the finding filter below
    # (they're being removed; findings tied to them are stale).
    all_tender_ids = {t.id for t in db.query(Tender.id).all()}
    valid_bid_ids = {b.id for b in db.query(BidSubmission.id).all()}
    valid_bidder_ids = {b.id for b in db.query(Bidder.id).all()}

    # 2 & 3. Remove orphan findings and findings tied to non-current tenders.
    for f in db.query(IntegrityFinding).all():
        if f.status == IntegrityStatus.CLOSED.value:
            continue
        # Orphan: tender_id points to nothing.
        if f.tender_id is not None and f.tender_id not in all_tender_ids:
            db.delete(f)
            removed["orphan_findings"] += 1
            continue
        # Stale: tied to a demo-history (non-current) tender.
        if f.tender_id is not None and f.tender_id not in valid_tender_ids:
            db.delete(f)
            removed["demo_findings"] += 1
            continue
        # Simplified mode: only REPEATED_PARTICIPATION signals are valid.
        # Remove every other signal type (cohorts, pairs, document matches,
        # identity correlations, anomalies, etc.) — they belong to future
        # scope and are regenerated only if their detectors are re-enabled.
        if f.signal_type != IntegritySignalType.REPEATED_PARTICIPATION.value:
            db.delete(f)
            removed["demo_findings"] += 1
            continue
        # Orphan: bidder_id points to nothing.
        if f.bidder_id is not None and f.bidder_id not in valid_bidder_ids:
            db.delete(f)
            removed["orphan_findings"] += 1
            continue
        # Orphan: affected_bids contains non-existent bids (and no valid refs).
        bids = [b for b in (f.affected_bids or []) if isinstance(b, int)]
        if bids and not any(b in valid_bid_ids for b in bids):
            # Only delete if the finding has no other valid anchor.
            if f.tender_id is None and f.bidder_id is None:
                db.delete(f)
                removed["orphan_findings"] += 1
                continue
    db.flush()

    # 4. Collapse duplicates.
    dedupe_res = dedupe_existing_findings(db)
    removed["duplicate_findings_removed"] = dedupe_res["removed_duplicates"]

    db.commit()
    return removed


def overview(db: Session) -> dict:
    """Counts for the Integrity overview screen."""
    open_findings = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.status != IntegrityStatus.CLOSED.value)
        .all()
    )
    last_run = (
        db.query(AuditLog)
        .filter(AuditLog.action == "INTEGRITY_ANALYSIS_RUN")
        .order_by(AuditLog.id.desc())
        .first()
    )
    current_ids = _current_tender_ids(db)
    return {
        "tenders_analyzed": db.query(Tender).filter(
            (Tender.is_demo_history.is_(False)) | (Tender.is_demo_history.is_(None))).count(),
        "bidders_analyzed": db.query(Bidder).filter(
            Bidder.tender_id.in_(current_ids)).count(),
        "bids_analyzed": db.query(BidSubmission).filter(
            BidSubmission.tender_id.in_(current_ids)).count(),
        "open_signals": len(open_findings),
        "high_priority_signals": sum(
            1 for f in open_findings if f.severity == SEV_REVIEW
        ),
        "last_analysis_at": last_run.timestamp.isoformat() if last_run else None,
    }
