"""Clearly-labelled synthetic procurement history for the integrity demo.

Creates a SMALL, clearly-marked historical dataset — two CLOSED 2024 tenders
with the same fictional bidder cohort — so the deterministic integrity engine
has real (synthetic but honestly labelled) cross-tender relationships to
analyse. Every tender title carries a "[DEMO HISTORY]" prefix, the tender
numbers use a DEMO-HIST prefix, and the rows are flagged
``is_demo_history`` so they stay out of the normal tender list.

Idempotent: re-running creates nothing when the tender numbers exist.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Bidder, BidSubmission, Tender
from app.services.audit_service import append_audit

log = logging.getLogger(__name__)

HISTORY_TENDERS = (
    {
        "number": "DEMO-HIST-2024-001",
        "title": "[DEMO HISTORY] Supply of Process Pumps (2024)",
        "department": "Materials Department",
        "issue": date(2024, 3, 1),
        "closing": date(2024, 4, 15),
        "value": 38000000,
        "winner": "Apex Flow Systems Pvt. Ltd.",
    },
    {
        "number": "DEMO-HIST-2024-002",
        "title": "[DEMO HISTORY] Supply of Industrial Valves (2024)",
        "department": "Materials Department",
        "issue": date(2024, 7, 1),
        "closing": date(2024, 8, 20),
        "value": 21000000,
        "winner": "Nova Engineering Works Pvt. Ltd.",
    },
)

# Same fictional cohort in both history tenders -> the integrity engine can
# detect the recurring-cohort pattern from real bid rows.
_COHORT = (
    {
        "legal_name": "Apex Flow Systems Pvt. Ltd.",
        "pan": "AAFCA1234E",
        "gstin": "27AAFCA1234E1Z5",
        "contact_email": "contracts@apexflow-demo.in",
    },
    {
        "legal_name": "Nova Engineering Works Pvt. Ltd.",
        "pan": "AANNE5678P",
        "gstin": "27AANNE5678P1Z5",
        "contact_email": "tenders@nova-demo.in",
    },
    {
        "legal_name": "PrimeTech Industrial Systems Pvt. Ltd.",
        "pan": "AAKPT9876L",
        "gstin": "27AAKPT9876L1Z5",
        "contact_email": "bids@primetech-demo.in",
    },
)

_DESCRIPTION = (
    "SYNTHETIC PROCUREMENT HISTORY — DEMO DATA. Fictional closed tender "
    "created solely so the procurement-integrity demo has cross-tender "
    "relationships to analyse. Not a real government record."
)


def seed_demo_history(db: Session, user_id: int | None = None) -> dict:
    """Seed the synthetic history tenders (idempotent)."""
    created = 0
    for spec in HISTORY_TENDERS:
        existing = (
            db.query(Tender)
            .filter(Tender.tender_number == spec["number"])
            .first()
        )
        if existing is not None:
            continue
        tender = Tender(
            tender_number=spec["number"],
            title=spec["title"],
            organization="Chennai Petroleum Corporation Limited",
            department=spec["department"],
            description=_DESCRIPTION,
            issue_date=spec["issue"],
            closing_date=spec["closing"],
            estimated_value_inr=spec["value"],
            status="CLOSED",
            created_by=user_id,
            is_demo_history=True,
        )
        db.add(tender)
        db.flush()
        for bidder_spec in _COHORT:
            bidder = Bidder(
                tender_id=tender.id,
                legal_name=bidder_spec["legal_name"],
                pan=bidder_spec["pan"],
                gstin=bidder_spec["gstin"],
                contact_email=bidder_spec["contact_email"],
                bid_status="SUBMITTED",
            )
            db.add(bidder)
            db.flush()
            is_winner = bidder_spec["legal_name"] == spec["winner"]
            bid = BidSubmission(
                tender_id=tender.id,
                bidder_id=bidder.id,
                submitted_at=datetime(
                    spec["closing"].year, spec["closing"].month,
                    spec["closing"].day, tzinfo=timezone.utc,
                ),
                status="SUBMITTED",
                officer_decision="APPROVE" if is_winner else "REJECT",
                officer_decision_reason=(
                    "Synthetic history award (DEMO DATA)" if is_winner
                    else "Synthetic history non-award (DEMO DATA)"
                ),
                decided_by=user_id,
            )
            db.add(bid)
        append_audit(
            db,
            user_id=user_id,
            action="DEMO_HISTORY_SEEDED",
            entity_type="tender",
            entity_id=str(tender.id),
            metadata={
                "tender_number": spec["number"],
                "note": "Synthetic DEMO procurement history for integrity analysis",
            },
        )
        created += 1
    db.commit()
    log.info("Demo history seed: %d tender(s) created", created)
    return {"history_tenders_created": created}
