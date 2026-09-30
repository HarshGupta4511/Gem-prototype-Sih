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

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations

from sqlalchemy.orm import Session

from app.engines.entity_resolution import normalize_name
from app.models.models import (
    AuditLog,
    Bidder,
    BidSubmission,
    IntegrityFinding,
    IntegritySeverity,
    IntegritySignalType,
    IntegrityStatus,
    Tender,
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


def _bidder_entity_map(db: Session) -> tuple[dict[int, str], dict[str, int], dict[str, str]]:
    """Return ({bidder_id: entity key}, {key: first bidder_id},
    {key: display legal name}).

    Bidder rows are tender-scoped, so cross-tender entity identity is the
    PAN/GSTIN-anchored entity key — never the raw bidder_id.
    """
    to_key: dict[int, str] = {}
    first_id: dict[str, int] = {}
    display: dict[str, str] = {}
    for b in db.query(Bidder).all():
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
    bids = db.query(BidSubmission).all()
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
            }
        )
    return signals


def _detect_repeated_participation(db: Session) -> list[dict]:
    """One bidder appearing across many tenders (grouped by legal entity)."""
    to_key, first_id, display = _bidder_entity_map(db)
    counts: dict[str, set[int]] = defaultdict(set)
    for bid in db.query(BidSubmission).all():
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
    for bid in db.query(BidSubmission).all():
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
    bidders = db.query(Bidder).all()
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
                    "Consider decision-rotation or a second reviewer for this "
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
    for bid in db.query(BidSubmission).all():
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
    bidders = db.query(Bidder).all()
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
            }
        )
    return signals


_DETECTORS = (
    _detect_recurring_cohorts,
    _detect_repeated_participation,
    _detect_bid_rotation,
    _detect_bidder_relationships,
    _detect_officer_bidder_association,
    _detect_concentration,
    _detect_identity_relationships,
)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_integrity_analysis(
    db: Session, user_id: int | None = None
) -> dict:
    """Run all detectors; persist new signals; audit the run.

    Idempotent: a signal whose dedupe key already has a non-CLOSED finding is
    not duplicated — its ``evaluated_at`` is refreshed instead.
    """
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

    bids = db.query(BidSubmission).count()
    bidders = db.query(Bidder).count()
    tenders = db.query(Tender).count()
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
    return {
        "tenders_analyzed": db.query(Tender).count(),
        "bidders_analyzed": db.query(Bidder).count(),
        "bids_analyzed": db.query(BidSubmission).count(),
        "open_signals": len(open_findings),
        "high_priority_signals": sum(
            1 for f in open_findings if f.severity == SEV_REVIEW
        ),
        "last_analysis_at": last_run.timestamp.isoformat() if last_run else None,
    }
