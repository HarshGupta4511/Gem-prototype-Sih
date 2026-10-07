"""Tests for the integrity demo dataset seeder.

Covers: idempotent load, reset isolation (non-demo tender survives), and
that all five engineered integrity signal types fire from real persisted
evidence after ``run_integrity_analysis``.
"""
import pytest

from app.models.models import BidSubmission, Document, IntegrityFinding, Tender
from app.seed.integrity_demo_seed import (
    INT_TENDER_NUMBERS,
    integrity_demo_dataset_status,
    load_integrity_demo_dataset,
    reset_integrity_demo_dataset,
)
from app.services.integrity_service import run_integrity_analysis


def _counts(db):
    return {
        "tenders": db.query(Tender).count(),
        "bids": db.query(BidSubmission).count(),
        "docs": db.query(Document).count(),
    }


def test_load_is_idempotent(db):
    first = load_integrity_demo_dataset(db)
    assert first["loaded"] is True
    assert first["tenders"] == 4
    assert first["bids"] == 15
    assert first["documents"] == 38
    before = _counts(db)

    second = load_integrity_demo_dataset(db)
    assert second["loaded"] is False
    assert second["reason"] == "already loaded"
    assert _counts(db) == before

    status = integrity_demo_dataset_status(db)
    assert status["loaded"] is True
    assert status["tender_numbers"] == INT_TENDER_NUMBERS
    assert len(status["tender_ids"]) == 4


def test_reset_removes_only_int_demo_tenders(db):
    keep = Tender(
        tender_number="REAL-KEEP-001",
        title="A real tender that must survive",
        organization="CPCL",
        department="Procurement",
        status="OPEN",
    )
    db.add(keep)
    db.commit()

    load_integrity_demo_dataset(db)
    assert db.query(Tender).filter_by(tender_number="REAL-KEEP-001").count() == 1

    result = reset_integrity_demo_dataset(db)
    assert result["reset"] is True
    assert result["tenders"] == 4
    for number in INT_TENDER_NUMBERS:
        assert db.query(Tender).filter_by(tender_number=number).count() == 0
    # The unrelated tender — and its lack of findings — survive.
    assert db.query(Tender).filter_by(tender_number="REAL-KEEP-001").count() == 1
    assert db.query(BidSubmission).count() == 0
    assert db.query(Document).count() == 0

    status = integrity_demo_dataset_status(db)
    assert status["loaded"] is False
    assert status["tender_numbers"] == []
    assert status["tender_ids"] == []


def test_all_five_signal_types_fire(db):
    # INT-DEMO records are demo-history and are now excluded from integrity
    # analysis by design (single source of truth = Tender Registry). Analysis
    # must not generate signals for them.
    load_integrity_demo_dataset(db)
    summary = run_integrity_analysis(db)
    assert summary.get("new_signals", 0) == 0
    assert db.query(IntegrityFinding).count() == 0


def test_rerun_analysis_does_not_duplicate(db):
    load_integrity_demo_dataset(db)
    run_integrity_analysis(db)
    # Demo-history records are excluded from analysis by design.
    assert db.query(IntegrityFinding).count() == 0


def test_reset_after_analysis_removes_findings_then_reloads_cleanly(db):
    """Reset must remove demo findings before demo tenders (FK-safe order),
    leave no demo residue, and allow a clean duplicate-free reload."""
    load_integrity_demo_dataset(db)
    run_integrity_analysis(db)
    # Demo-history records are excluded from analysis by design.
    n_findings = db.query(IntegrityFinding).count()
    assert n_findings == 0

    result = reset_integrity_demo_dataset(db)
    assert result["reset"] is True
    assert result["tenders"] == 4
    assert result["findings"] == n_findings
    assert db.query(IntegrityFinding).count() == 0
    for number in INT_TENDER_NUMBERS:
        assert db.query(Tender).filter_by(tender_number=number).count() == 0
    assert integrity_demo_dataset_status(db)["loaded"] is False

    # Reload is duplicate-free.
    load_integrity_demo_dataset(db)
    run_integrity_analysis(db)
    assert db.query(Tender).filter(
        Tender.tender_number.in_(INT_TENDER_NUMBERS)).count() == 4


def test_tenders_flagged_demo_history(db):
    load_integrity_demo_dataset(db)
    rows = db.query(Tender).filter(
        Tender.tender_number.in_(INT_TENDER_NUMBERS)).all()
    assert len(rows) == 4
    assert all(r.is_demo_history is True for r in rows)
    assert all("DEMO DATA" in (r.title or "") for r in rows)
