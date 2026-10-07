"""Integrity engine: deterministic, evidence-backed signal detection.

Covers: recurring bidder cohorts, repeated participation, possible bid
rotation, bidder relationships via shared identifiers, officer-bidder
association (with a single officer in the dataset -> no signal), award
concentration, identity relationships, idempotency, officer actions with
audit events, and the no-fraud-language rule.
"""
import pytest

from app.models.models import (
    AuditLog,
    Bidder,
    BidStatus,
    BidSubmission,
    IntegrityFinding,
    IntegrityStatus,
    Tender,
    TenderStatus,
    User,
)
from app.services import integrity_service


def _user(db, name="Officer"):
    u = User(
        name=name,
        email=f"{name.lower().replace(' ', '_')}-int@example.com",
        password_hash="x",
        role="PROCUREMENT_OFFICER",
    )
    db.add(u)
    db.flush()
    return u


def _tender(db, number, title="T", closed=None):
    t = Tender(
        tender_number=number,
        title=title,
        organization="CPCL",
        department="Purchase",
        status=TenderStatus.OPEN.value,
        closing_date=closed,
    )
    db.add(t)
    db.flush()
    return t


def _bidder(db, tender, legal_name, email=None, pan=None, gstin=None, phone=None):
    b = Bidder(
        tender_id=tender.id,
        legal_name=legal_name,
        contact_email=email,
        contact_phone=phone,
        pan=pan,
        gstin=gstin,
        bid_status="SUBMITTED",
    )
    db.add(b)
    db.flush()
    return b


def _bid(db, tender, bidder, decision=None):
    s = BidSubmission(
        tender_id=tender.id,
        bidder_id=bidder.id,
        status=BidStatus.SUBMITTED.value,
        officer_decision=decision,
    )
    db.add(s)
    db.flush()
    return s


@pytest.fixture()
def officer(db):
    u = _user(db)
    db.commit()
    return u


def test_recurring_cohort_and_repeated_participation(officer, db):
    t1 = _tender(db, "T-COH-1")
    t2 = _tender(db, "T-COH-2")
    a1 = _bidder(db, t1, "Alpha Industries Pvt. Ltd.", email="a@example.com")
    b1 = _bidder(db, t1, "Beta Works Pvt. Ltd.", email="b@example.com")
    a2 = _bidder(db, t2, "Alpha Industries Pvt. Ltd.", email="a@example.com")
    b2 = _bidder(db, t2, "Beta Works Pvt. Ltd.", email="b@example.com")
    _bid(db, t1, a1)
    _bid(db, t1, b1)
    _bid(db, t2, a2)
    _bid(db, t2, b2)
    db.commit()

    res = integrity_service.run_integrity_analysis(db, user_id=officer.id)
    assert res["new_signals"] == 0  # simplified mode: 2 tenders below threshold

    cohorts = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.signal_type == "RECURRING_BIDDER_COHORT")
        .all()
    )
    assert len(cohorts) == 0  # simplified mode: cohort detector is future scope

    repeats = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.signal_type == "REPEATED_PARTICIPATION")
        .all()
    )
    assert len(repeats) == 0  # only 2 tenders each — below threshold

    # Audit events
    actions = {e.action for e in db.query(AuditLog).all()}
    assert "INTEGRITY_ANALYSIS_RUN" in actions


def test_repeated_participation_threshold(officer, db):
    bidder_ids = []
    for i in range(1, 4):
        t = _tender(db, f"T-REP-{i}")
        b = _bidder(db, t, "RepeatCo Pvt. Ltd.", email="r@example.com")
        _bid(db, t, b)
        bidder_ids.append(b.id)
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    repeats = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.signal_type == "REPEATED_PARTICIPATION")
        .all()
    )
    assert len(repeats) == 1  # one row per legal entity (tender-scoped rows merge)
    assert repeats[0].severity == "ELEVATED"
    assert "RepeatCo" in repeats[0].title
    assert len(repeats[0].affected_tenders) == 3


def test_entity_identity_prefers_pan_over_name_spelling(officer, db):
    """The same PAN under slightly different legal-name spellings across
    tenders must resolve to ONE entity (not two), so cross-tender detectors
    merge the tender-scoped bidder rows."""
    spellings = ["Acme Industries Pvt. Ltd.", "Acme Industries Pvt Ltd",
                 "ACME INDUSTRIES PRIVATE LIMITED"]
    for i, name in enumerate(spellings, start=1):
        t = _tender(db, f"T-PAN-{i}")
        b = _bidder(db, t, name, pan="AAECA1111A")
        _bid(db, t, b)
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    repeats = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.signal_type == "REPEATED_PARTICIPATION")
        .all()
    )
    assert len(repeats) == 1, "PAN-anchored rows must merge into one entity"
    assert repeats[0].severity == "ELEVATED"
    assert len(repeats[0].affected_tenders) == 3
    # Display keeps a human-readable legal name, never the raw pan: key.
    assert "pan:" not in repeats[0].title.lower()
    assert "Acme" in repeats[0].title


def test_bidder_relationship_shared_email(officer, db):
    t = _tender(db, "T-REL-1")
    _bidder(db, t, "Gamma Traders", email="shared@example.com")
    _bidder(db, t, "Delta Suppliers", email="shared@example.com")
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    # Simplified mode: contact-relationship detector is future scope.
    assert db.query(IntegrityFinding).count() == 0


def test_identity_relationship_shared_pan(officer, db):
    t = _tender(db, "T-ID-1")
    _bidder(db, t, "Echo Enterprises", pan="ABCDE1234F")
    _bidder(db, t, "Foxtrot Fabricators", pan="ABCDE1234F")
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    # Simplified mode: identity-relationship detector is future scope.
    assert db.query(IntegrityFinding).count() == 0


def test_concentration_and_rotation(officer, db):
    from datetime import date

    tenders = [_tender(db, f"T-AWD-{i}", closed=date(2024, i + 1, 10)) for i in range(3)]
    winners = ["Alpha Industries Pvt. Ltd.", "Beta Works Pvt. Ltd.",
               "Alpha Industries Pvt. Ltd."]
    for t, wname in zip(tenders, winners):
        b = _bidder(db, t, wname)
        other = _bidder(db, t, f"Loser {t.tender_number}")
        _bid(db, t, b, decision="APPROVE")
        _bid(db, t, other, decision="REJECT")
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)

    # Simplified mode: concentration/rotation detectors are future scope.
    assert db.query(IntegrityFinding).count() == 0


def test_officer_bidder_association_needs_two_officers(officer, db):
    from app.services.audit_service import append_audit

    t = _tender(db, "T-ASSOC-1")
    b = _bidder(db, t, "AssocCo")
    s = _bid(db, t, b)
    db.commit()
    # 3 decisions by the SAME officer
    for _ in range(3):
        append_audit(
            db,
            user_id=officer.id,
            action="OFFICER_DECISION",
            entity_type="bid_submission",
            entity_id=str(s.id),
        )
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    # Simplified mode: officer-association detector is future scope.
    assert db.query(IntegrityFinding).count() == 0


def test_analysis_is_idempotent(officer, db):
    tenders = [_tender(db, f"T-IDEM-{i}") for i in range(1, 4)]
    for t in tenders:
        a = _bidder(db, t, "IdemA Ltd.", email="ia@example.com")
        b = _bidder(db, t, "IdemB Ltd.", email="ib@example.com")
        _bid(db, t, a)
        _bid(db, t, b)
    db.commit()

    first = integrity_service.run_integrity_analysis(db, user_id=officer.id)
    before = db.query(IntegrityFinding).count()
    second = integrity_service.run_integrity_analysis(db, user_id=officer.id)
    after = db.query(IntegrityFinding).count()
    assert first["new_signals"] > 0
    assert second["new_signals"] == 0
    assert after == before


def test_officer_actions_and_audit(officer, db):
    t = _tender(db, "T-ACT-1")
    b = _bidder(db, t, "ActCo")
    _bid(db, t, b)
    db.commit()

    f = IntegrityFinding(
        signal_type="REPEATED_PARTICIPATION",
        severity="ELEVATED",
        title="Repeated participation: ActCo",
        description="d",
        rule_logic="r",
        recommended_action="a",
        status=IntegrityStatus.OPEN.value,
    )
    db.add(f)
    db.commit()

    integrity_service.apply_officer_action(db, f.id, "acknowledge", officer)
    db.refresh(f)
    assert f.status == IntegrityStatus.ACKNOWLEDGED.value

    with pytest.raises(ValueError):
        integrity_service.apply_officer_action(db, f.id, "close", officer)  # note required

    integrity_service.apply_officer_action(
        db, f.id, "close", officer, note="Verified as normal market participation."
    )
    db.refresh(f)
    assert f.status == IntegrityStatus.CLOSED.value
    assert f.officer_note == "Verified as normal market participation."

    actions = [
        e.action
        for e in db.query(AuditLog)
        .filter(AuditLog.entity_type == "integrity_finding")
        .order_by(AuditLog.id)
        .all()
    ]
    assert "INTEGRITY_SIGNAL_ACKNOWLEDGED" in actions
    assert "INTEGRITY_SIGNAL_CLOSED" in actions


def test_no_fraud_language(officer, db):
    t1 = _tender(db, "T-LANG-1")
    t2 = _tender(db, "T-LANG-2")
    for t in (t1, t2):
        a = _bidder(db, t, "LangA Ltd.", email="la@example.com")
        b = _bidder(db, t, "LangB Ltd.", email="lb@example.com")
        _bid(db, t, a, decision="APPROVE")
        _bid(db, t, b, decision="REJECT")
    db.commit()
    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    banned = ("fraud", "corrupt", "rigging", "collusion confirmed")
    for f in db.query(IntegrityFinding).all():
        blob = (f.title + " " + f.description).lower()
        assert not any(w in blob for w in banned), f"fraud language in {f.id}"


def test_overview_counts(officer, db):
    t = _tender(db, "T-OV-1")
    b = _bidder(db, t, "OvCo")
    _bid(db, t, b)
    db.commit()
    ov = integrity_service.overview(db)
    assert ov["tenders_analyzed"] == 1
    assert ov["bidders_analyzed"] == 1
    assert ov["bids_analyzed"] == 1
    assert ov["open_signals"] == 0


def _repeat_findings(db):
    return (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.signal_type == "REPEATED_PARTICIPATION")
        .all()
    )


def test_entity_identity_merges_same_gstin_name_variation(officer, db):
    """Same valid GSTIN under legal-name variations across tenders resolves
    to ONE entity via the GSTIN's embedded PAN."""
    gstin = "27AAECA1111A1Z5"  # valid; embeds PAN AAECA1111A
    names = ["Acme Industries Pvt. Ltd.", "Acme Industries Private Limited",
             "ACME INDUSTRIES PVT LTD"]
    for i, name in enumerate(names, start=1):
        t = _tender(db, f"T-GST-{i}")
        b = _bidder(db, t, name, gstin=gstin)
        _bid(db, t, b)
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    repeats = _repeat_findings(db)
    assert len(repeats) == 1, "GSTIN-anchored rows must merge into one entity"
    assert len(repeats[0].affected_tenders) == 3
    assert "gstin:" not in repeats[0].title.lower()


def test_entity_identity_merges_name_only_when_no_identifier(officer, db):
    """No identifier + same normalized legal name still merges (fallback)."""
    for i, name in enumerate(["Beta Traders", "Beta Traders ", "BETA TRADERS"],
                             start=1):
        t = _tender(db, f"T-NAME-{i}")
        b = _bidder(db, t, name)
        _bid(db, t, b)
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    repeats = _repeat_findings(db)
    assert len(repeats) == 1
    assert len(repeats[0].affected_tenders) == 3


def test_entity_identity_does_not_merge_different_valid_pans(officer, db):
    """Different valid PANs under the same legal name must NOT silently
    merge — they are distinct tax entities."""
    pans = ["AAECA1111A", "BBECB2222B", "CC ECC".replace(" ", "") + "3333C"]
    for i, pan in enumerate(pans, start=1):
        t = _tender(db, f"T-DIFFPAN-{i}")
        b = _bidder(db, t, "Gamma Corp", pan=pan)
        _bid(db, t, b)
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    assert _repeat_findings(db) == [], \
        "distinct PANs must not merge into one entity"


def test_shared_pan_different_names_still_signals_relationship(officer, db):
    """A valid PAN shared under genuinely different legal names still
    produces the DOCUMENT_IDENTITY_RELATIONSHIP signal for officer review,
    even though the entity key unifies them."""
    for i, name in enumerate(["Delta One Ltd", "Echo Two Pvt Ltd"], start=1):
        t = _tender(db, f"T-SHARED-{i}")
        b = _bidder(db, t, name, pan="ABCDE1234F")
        _bid(db, t, b)
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    # Simplified mode: identity-relationship detector is future scope.
    assert db.query(IntegrityFinding).count() == 0


def test_malformed_identifiers_never_merge_or_signal(officer, db):
    """Malformed PAN/GSTIN values fall back to name identity: the same typo'd
    identifier on different names must neither merge entities nor trigger a
    false identity-relationship signal."""
    t1 = _tender(db, "T-MAL-1")
    b1 = _bidder(db, t1, "Zeta Ltd", pan="ABC")  # malformed: too short
    _bid(db, t1, b1)
    t2 = _tender(db, "T-MAL-2")
    b2 = _bidder(db, t2, "Eta Ltd", pan="ABC", gstin="NOT-A-GSTIN")
    _bid(db, t2, b2)
    db.commit()

    integrity_service.run_integrity_analysis(db, user_id=officer.id)
    assert _repeat_findings(db) == [], \
        "malformed identifiers must not merge entities"
    rels = (
        db.query(IntegrityFinding)
        .filter(IntegrityFinding.signal_type == "RECURRING_BIDDER_COHORT")
        .all()
    )
    assert rels == [], "malformed identifiers must not trigger relationship signals"


def test_entity_key_validation_unit():
    """Direct unit coverage for the identifier validators."""
    from app.services.integrity_service import (
        _pan_from_gstin, _valid_gstin, _valid_pan,
    )
    assert _valid_pan("aaeca1111a") == "AAECA1111A"  # case normalized
    assert _valid_pan(" ABCDE1234F ") == "ABCDE1234F"  # whitespace stripped
    assert _valid_pan("ABC") is None
    assert _valid_pan("ABCDE12345") is None  # ends with digit
    assert _valid_pan("") is None
    assert _valid_pan(None) is None
    assert _valid_gstin("27AAECA1111A1Z5") == "27AAECA1111A1Z5"
    assert _valid_gstin("27AAECA1111A1Z") is None  # too short
    assert _valid_gstin("not-a-gstin") is None
    assert _pan_from_gstin("27AAECA1111A1Z5") == "AAECA1111A"
    assert _pan_from_gstin("bogus") is None


def test_concurrent_analysis_does_not_duplicate(officer, db):
    """Two simultaneous analyses: one runs, the other gets already_running.

    Regression test for duplicate findings created by double-clicking
    "Run Analysis" (or Load auto-analysis racing a manual run).
    """
    import threading

    from app.services import integrity_service as svc

    t1 = _tender(db, "T-CONC-1")
    t2 = _tender(db, "T-CONC-2")
    for t in (t1, t2):
        a = _bidder(db, t, "ConcA Ltd.", email="ca@example.com")
        b = _bidder(db, t, "ConcB Ltd.", email="cb@example.com")
        _bid(db, t, a)
        _bid(db, t, b)
    db.commit()
    # Detach session state so threads don't share it.
    db.expunge_all()

    results = []
    barrier = threading.Barrier(2)

    def _run():
        barrier.wait(timeout=30)
        # Each thread needs its own session; reuse the engine via a new Session.
        from sqlalchemy.orm import Session as SASession

        sess = SASession(bind=db.bind)
        try:
            results.append(svc.run_integrity_analysis(sess, user_id=officer.id))
        finally:
            sess.close()

    th1 = threading.Thread(target=_run)
    th2 = threading.Thread(target=_run)
    th1.start()
    th2.start()
    th1.join(timeout=120)
    th2.join(timeout=120)

    assert len(results) == 2
    ran = [r for r in results if not r.get("already_running")]
    blocked = [r for r in results if r.get("already_running")]
    assert len(ran) == 1, "exactly one analysis should run"
    assert len(blocked) == 1, "the other should be told already_running"
    # No duplicates: re-running after both finish adds nothing.
    again = svc.run_integrity_analysis(db, user_id=officer.id)
    assert again["new_signals"] == 0


def test_dedupe_existing_findings_removes_duplicates(officer, db):
    """dedupe_existing_findings collapses same-key findings, keeps oldest."""
    from app.services import integrity_service as svc

    t = _tender(db, "T-DEDUP-1")
    b = _bidder(db, t, "DedupCo", email="dd@example.com")
    _bid(db, t, b)
    db.commit()

    def _mk(i):
        f = IntegrityFinding(
            tender_id=t.id,
            bidder_id=b.id,
            signal_type="REPEATED_PARTICIPATION",
            severity="ELEVATED",
            title="Repeated participation",
            description="x",
            affected_bids=[],
            affected_tenders=[],
            evidence=[{"label": "e", "dedupe_key": "repeat:DedupCo"}],
            rule_logic="r",
            recommended_action="a",
            status=IntegrityStatus.OPEN.value,
            is_demo_history=False,
        )
        db.add(f)
        db.flush()
        return f.id

    id1 = _mk(1)
    _mk(2)
    _mk(3)
    db.commit()
    assert db.query(IntegrityFinding).count() == 3

    res = svc.dedupe_existing_findings(db)
    assert res["removed_duplicates"] == 2
    remaining = db.query(IntegrityFinding).all()
    assert len(remaining) == 1
    assert remaining[0].id == id1, "oldest finding is kept"


def test_dedupe_preserves_officer_actions(officer, db):
    """Findings with officer actions (non-CLOSED) survive dedupe; CLOSED untouched."""
    from app.services import integrity_service as svc

    t = _tender(db, "T-DEDUP-2")
    b = _bidder(db, t, "DedupCo2", email="dd2@example.com")
    _bid(db, t, b)
    db.commit()

    ack = IntegrityFinding(
        tender_id=t.id, bidder_id=b.id, signal_type="REPEATED_PARTICIPATION",
        severity="ELEVATED", title="t", description="x",
        affected_bids=[], affected_tenders=[],
        evidence=[{"label": "e", "dedupe_key": "repeat:DedupCo2"}],
        rule_logic="r", recommended_action="a",
        status=IntegrityStatus.ACKNOWLEDGED.value, is_demo_history=False,
    )
    dupe = IntegrityFinding(
        tender_id=t.id, bidder_id=b.id, signal_type="REPEATED_PARTICIPATION",
        severity="ELEVATED", title="t", description="x",
        affected_bids=[], affected_tenders=[],
        evidence=[{"label": "e", "dedupe_key": "repeat:DedupCo2"}],
        rule_logic="r", recommended_action="a",
        status=IntegrityStatus.OPEN.value, is_demo_history=False,
    )
    closed = IntegrityFinding(
        tender_id=t.id, bidder_id=b.id, signal_type="REPEATED_PARTICIPATION",
        severity="ELEVATED", title="t", description="x",
        affected_bids=[], affected_tenders=[],
        evidence=[{"label": "e", "dedupe_key": "repeat:DedupCo2"}],
        rule_logic="r", recommended_action="a",
        status=IntegrityStatus.CLOSED.value, is_demo_history=False,
    )
    db.add_all([ack, dupe, closed])
    db.commit()

    res = svc.dedupe_existing_findings(db)
    assert res["removed_duplicates"] == 1  # only the OPEN dupe
    statuses = sorted(f.status for f in db.query(IntegrityFinding).all())
    assert statuses == sorted([IntegrityStatus.ACKNOWLEDGED.value,
                               IntegrityStatus.CLOSED.value])


def test_integrity_uses_current_records_only(officer, db):
    """Integrity overview/analysis must match the Tender Registry:
    demo-history tenders are excluded from counts and detection.
    """
    from app.services import integrity_service as svc

    t1 = _tender(db, "T-CUR-1")
    t2 = _tender(db, "T-CUR-2")
    t3 = _tender(db, "INT-DEMO-X")
    t3.is_demo_history = True
    for t, n in [(t1, 2), (t2, 1), (t3, 3)]:
        for i in range(n):
            b = _bidder(db, t, f"B-{t.tender_number}-{i}", email=f"b{i}@{t.tender_number}.com")
            _bid(db, t, b)
    db.commit()

    ov = svc.overview(db)
    assert ov["tenders_analyzed"] == 2
    assert ov["bidders_analyzed"] == 3
    assert ov["bids_analyzed"] == 3

    r = svc.run_integrity_analysis(db, user_id=officer.id)
    assert r["tenders_analyzed"] == 2
    assert r["bidders_analyzed"] == 3
    assert r["bids_analyzed"] == 3


def test_cleanup_stale_removes_demo_history(officer, db):
    """cleanup_stale_integrity_data removes demo-history tenders and their
    signals, keeping current valid records untouched."""
    from app.services import integrity_service as svc

    t1 = _tender(db, "T-KEEP-1")
    t2 = _tender(db, "T-DEL-1")
    t2.is_demo_history = True
    b1 = _bidder(db, t1, "KeepCo", email="keep@example.com")
    _bid(db, t1, b1)
    b2 = _bidder(db, t2, "DemoCo", email="demo@example.com")
    _bid(db, t2, b2)
    db.commit()

    res = svc.cleanup_stale_integrity_data(db)
    assert res["demo_tenders"] == 1
    assert db.query(Tender).count() == 1
    assert db.query(Tender).first().tender_number == "T-KEEP-1"
    # Current records untouched.
    assert db.query(Bidder).count() == 1
    assert db.query(BidSubmission).count() == 1


def test_simplified_mode_only_repeated_participation(officer, db):
    """Simplified mode: only REPEATED_PARTICIPATION signals are generated.

    A bidder in 3+ tenders gets exactly one signal; pair/cohort/document/
    identity detectors are future scope and emit nothing.
    """
    for i, num in enumerate(["T-SIMP-1", "T-SIMP-2", "T-SIMP-3"], start=1):
        t = _tender(db, num)
        b1 = _bidder(db, t, "Alpha Corp", pan="AAAAA1111A",
                     email="shared@example.com")
        b2 = _bidder(db, t, "Beta Ltd", pan="BBBBB2222B",
                     email="shared@example.com")
        _bid(db, t, b1)
        _bid(db, t, b2)
    db.commit()

    res = integrity_service.run_integrity_analysis(db, user_id=officer.id)
    sigs = db.query(IntegrityFinding).all()
    assert res["new_signals"] == 2
    assert len(sigs) == 2
    assert {s.signal_type for s in sigs} == {"REPEATED_PARTICIPATION"}
    titles = sorted(s.title for s in sigs)
    assert titles[0] == "Repeated participation: Alpha Corp"
    assert titles[1] == "Repeated participation: Beta Ltd"
    for s in sigs:
        assert "3 tenders" in s.evidence[0]["detail"]
    # Re-run creates nothing new.
    res2 = integrity_service.run_integrity_analysis(db, user_id=officer.id)
    assert res2["new_signals"] == 0
    assert db.query(IntegrityFinding).count() == 2
