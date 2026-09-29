"""Tests for the hash-chained audit log (CONTRACT §4)."""
import json

from sqlalchemy import text

from app.services.audit_service import append_audit, verify_chain


def test_chain_valid_after_five_appends(db):
    for i in range(5):
        append_audit(db, user_id=None, action="LOGIN", entity_type="user",
                     entity_id=str(i), metadata={"n": i})
    out = verify_chain(db)
    assert out["valid"] is True
    assert out["checked"] == 5
    assert out["broken_at"] is None


def test_chain_genesis_previous_hash(db):
    entry = append_audit(db, user_id=1, action="LOGIN", entity_type="user",
                         entity_id="1", metadata={})
    assert entry.previous_hash == "GENESIS"


def test_tamper_detected_with_broken_id(db):
    entries = [append_audit(db, user_id=None, action="LOGIN", entity_type="user",
                            entity_id=str(i), metadata={"n": i})
               for i in range(5)]
    victim = entries[2]
    # Tamper with one row's metadata via direct SQL, bypassing the service.
    db.execute(text("UPDATE audit_logs SET metadata = :m WHERE id = :i"),
               {"m": json.dumps({"tampered": True}), "i": victim.id})
    db.commit()
    # The raw SQL bypassed the ORM identity map; force a re-read from the DB.
    db.expire_all()
    out = verify_chain(db)
    assert out["valid"] is False
    assert out["broken_at"]["id"] == victim.id
    assert out["broken_at"]["expected"] != out["broken_at"]["actual"]
    assert out["checked"] == 2  # entries 0 and 1 verified before the break
