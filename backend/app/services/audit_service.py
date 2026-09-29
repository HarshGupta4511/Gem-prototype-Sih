"""Hash-chained audit log service (CONTRACT.md §4).

Chain rule (exact):
    sha256(f"{previous_hash}|{timestamp_iso}|{user_id or 'system'}|{action}|{entity_type}|{entity_id}|{canonical_json(metadata)}")
Genesis previous_hash = "GENESIS".

Timestamps are stored tz-aware; on backends that drop tzinfo (SQLite) the
reader normalizes to UTC before hashing so append and verify always agree.
"""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import AuditLog

GENESIS_HASH = "GENESIS"


def canonical_json(data: dict) -> str:
    """Deterministic JSON: sorted keys, compact separators, str() fallback."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(
    previous_hash: str,
    timestamp_iso: str,
    user_id_or_system: int | str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict | None,
) -> str:
    """Compute one audit chain link hash, exactly per the contract formula."""
    who = "system" if user_id_or_system is None else str(user_id_or_system)
    payload = (
        f"{previous_hash}|{timestamp_iso}|{who}|{action}|{entity_type}|{entity_id}"
        f"|{canonical_json(metadata or {})}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _timestamp_iso(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()


def append_audit(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict | None = None,
) -> AuditLog:
    """Append one entry to the hash chain and commit. Returns the AuditLog row."""
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    previous_hash = last.current_hash if last is not None else GENESIS_HASH
    ts = datetime.now(timezone.utc)
    metadata = dict(metadata or {})
    current_hash = compute_hash(
        previous_hash, _timestamp_iso(ts), user_id, action, entity_type,
        str(entity_id), metadata,
    )
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        timestamp=ts,
        previous_hash=previous_hash,
        current_hash=current_hash,
        meta=metadata,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_chain(db: Session) -> dict:
    """Recompute every link in id order.

    Returns {"valid": bool, "checked": int, "broken_at": None | {"id", "expected", "actual"}}.
    """
    entries = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    expected_prev = GENESIS_HASH
    checked = 0
    for entry in entries:
        expected = compute_hash(
            entry.previous_hash,
            _timestamp_iso(entry.timestamp),
            entry.user_id,
            entry.action,
            entry.entity_type,
            entry.entity_id,
            entry.meta or {},
        )
        if entry.previous_hash != expected_prev or entry.current_hash != expected:
            return {
                "valid": False,
                "checked": checked,
                "broken_at": {
                    "id": entry.id,
                    "expected": expected,
                    "actual": entry.current_hash,
                },
            }
        expected_prev = entry.current_hash
        checked += 1
    return {"valid": True, "checked": checked, "broken_at": None}
