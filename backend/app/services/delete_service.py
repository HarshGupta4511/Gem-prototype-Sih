"""Explicit cascade deletion for tenders and bids.

The models intentionally carry no ORM/database-level cascades, so deletion
removes child rows explicitly in dependency order. No schema change is
involved. The append-only audit trail is preserved: a ``*_DELETED`` event is
appended *before* the rows are removed, and existing audit events are never
deleted (``AuditLog`` has no FK to tenders/bids — it references entities by
``entity_type``/``entity_id`` strings).

Only the API layer's role gate decides *who* may delete; this service only
decides *what* is removed.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models.models import (
    Bidder,
    BidSubmission,
    Clarification,
    ComplianceResult,
    Document,
    ExtractedField,
    Override,
    RiskAssessment,
    Tender,
    TenderRequirement,
    VerificationCheck,
)
from app.services import audit_service


def _delete_bid_rows(db: Session, bid: BidSubmission) -> dict:
    """Remove one bid and everything derived from it. Returns counts."""
    counts: dict[str, int] = {}

    doc_ids = [d.id for d in db.query(Document.id).filter_by(bid_id=bid.id).all()]

    # Extracted fields + overrides reference documents; drop them first.
    if doc_ids:
        counts["extracted_fields"] = (
            db.query(ExtractedField)
            .filter(ExtractedField.document_id.in_(doc_ids))
            .delete(synchronize_session=False)
        )
        counts["overrides"] = (
            db.query(Override).filter_by(bid_id=bid.id)
            .delete(synchronize_session=False)
        )
        # Remove the stored files; a missing file is not an error.
        for doc in db.query(Document).filter_by(bid_id=bid.id).all():
            try:
                if doc.file_path:
                    Path(doc.file_path).unlink(missing_ok=True)
            except OSError:
                pass
        counts["documents"] = (
            db.query(Document).filter_by(bid_id=bid.id)
            .delete(synchronize_session=False)
        )
    else:
        counts["extracted_fields"] = 0
        counts["overrides"] = (
            db.query(Override).filter_by(bid_id=bid.id)
            .delete(synchronize_session=False)
        )
        counts["documents"] = 0

    counts["verification_checks"] = (
        db.query(VerificationCheck).filter_by(bid_id=bid.id)
        .delete(synchronize_session=False)
    )
    counts["compliance_results"] = (
        db.query(ComplianceResult).filter_by(bid_id=bid.id)
        .delete(synchronize_session=False)
    )
    counts["risk_assessments"] = (
        db.query(RiskAssessment).filter_by(bid_id=bid.id)
        .delete(synchronize_session=False)
    )
    counts["clarifications"] = (
        db.query(Clarification).filter_by(bid_id=bid.id)
        .delete(synchronize_session=False)
    )

    bidder_id = bid.bidder_id
    # Same staleness guard as delete_tender: bulk deletes above bypassed the
    # session, so expire any loaded child collections before the ORM delete.
    db.expire(bid)
    db.delete(bid)
    db.flush()
    # The bidder row is 1:1 with the bid (bidder_id is unique on the bid).
    bidder = db.get(Bidder, bidder_id)
    if bidder is not None:
        db.delete(bidder)
        counts["bidders"] = 1
    else:
        counts["bidders"] = 0
    counts["bids"] = 1
    return counts


def delete_bid(db: Session, bid_id: int, user_id: int | None = None) -> dict:
    """Delete a single bid submission and all its derived data."""
    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"BidSubmission {bid_id} not found")
    tender_id = bid.tender_id
    bidder = db.get(Bidder, bid.bidder_id)
    bidder_name = bidder.legal_name if bidder is not None else None

    audit_service.append_audit(
        db,
        user_id=user_id,
        action="BID_DELETED",
        entity_type="bid_submission",
        entity_id=str(bid.id),
        metadata={"tender_id": tender_id, "legal_name": bidder_name},
    )
    counts = _delete_bid_rows(db, bid)
    db.commit()
    return {"deleted": True, "bid_id": bid_id, "tender_id": tender_id, **counts}


def delete_tender(db: Session, tender_id: int, user_id: int | None = None) -> dict:
    """Delete a tender, its requirements, and every bid with derived data."""
    tender = db.get(Tender, tender_id)
    if tender is None:
        raise ValueError(f"Tender {tender_id} not found")
    tender_number = tender.tender_number

    audit_service.append_audit(
        db,
        user_id=user_id,
        action="TENDER_DELETED",
        entity_type="tender",
        entity_id=str(tender.id),
        metadata={"tender_number": tender_number},
    )

    total: dict[str, int] = {}
    for bid in db.query(BidSubmission).filter_by(tender_id=tender.id).all():
        for key, value in _delete_bid_rows(db, bid).items():
            total[key] = total.get(key, 0) + value

    total["requirements"] = (
        db.query(TenderRequirement).filter_by(tender_id=tender.id)
        .delete(synchronize_session=False)
    )
    # Any bidder rows not already removed with their bids (defensive).
    total["bidders"] = total.get("bidders", 0) + (
        db.query(Bidder).filter_by(tender_id=tender.id)
        .delete(synchronize_session=False)
    )
    total["bids"] = total.get("bids", 0)

    # Bulk deletes above bypassed the ORM session: drop any loaded child
    # collections so deleting the parent doesn't try to nullify already
    # deleted rows (would raise StaleDataError at flush).
    db.expire(tender)
    db.delete(tender)
    db.commit()
    return {
        "deleted": True,
        "tender_id": tender_id,
        "tender_number": tender_number,
        **total,
    }
