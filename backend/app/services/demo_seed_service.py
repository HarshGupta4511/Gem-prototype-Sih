"""Seed fictional demo-bidder evidence through the REAL document pipeline.

Used by ``POST /api/bids/{bid_id}/seed-demo-evidence`` (called once per demo
bidder right after the Create-Tender wizard registers it as a normal bidder).
For the chosen profile it:

1. stamps the profile's authoritative fictional identifiers onto the normal
   ``Bidder`` row (the wizard only carries masked display identifiers),
2. builds requirement-driven dossier section(s) via
   :mod:`app.seed.demo_bidder_profiles` — one consolidated PDF per bidder,
   or one standalone evidence document per section for profiles whose
   scenario needs genuinely distinct documents (Nova's cross-document
   identity mismatch),
3. stores each as a normal ``Document`` row and runs the real
   :func:`process_document` pipeline (classification + regex/LLM extraction)
   — exactly what happens automatically when any document is uploaded.

Deliberately STOPS there: verification, compliance+risk evaluation and the
AI recommendation are NOT pre-computed. The officer runs those from the
existing Bid Detail buttons (Verification -> Run, Compliance -> Evaluate,
AI Recommendation -> Refresh), so the scores are genuinely derived live
during the demo instead of appearing pre-filled.

Everything downstream (PASS/FAIL/MISSING/MISMATCH/REVIEW_REQUIRED, scores,
risk, recommendation) is derived by the existing engines from the seeded
evidence; nothing is hardcoded.

Idempotent per (bid, profile): re-calling does not create duplicate bidder
or document rows. Re-running the Bid Detail pipeline actions afterwards keeps
working because every stage replaces its previous rows.
"""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.core.config import ensure_upload_dir
from app.models.models import BidSubmission, Bidder, Document, Tender
from app.seed.demo_bidder_profiles import PROFILES, build_dossier_sections, demo_banner
from app.seed.demo_docs import dossier_section_title, generate_dossier_pdf
from app.services import audit_service
from app.services.pipeline_service import process_document

_DEMO_FILENAME = "demo_{profile_key}_dossier.pdf"
_DEMO_SECTION_FILENAME = "demo_{profile_key}_{template}.pdf"


def seed_demo_bidder_evidence(
    db: Session, bid_id: int, profile_key: str, user_id: int | None = None
) -> dict:
    """Attach a profile's demo evidence dossier to an existing bid."""
    if profile_key not in PROFILES:
        raise ValueError(
            f"Unknown demo profile '{profile_key}'; "
            f"expected one of {sorted(PROFILES)}"
        )
    profile = PROFILES[profile_key]

    bid = db.get(BidSubmission, bid_id)
    if bid is None:
        raise ValueError(f"BidSubmission {bid_id} not found")
    bidder = db.get(Bidder, bid.bidder_id)
    if bidder is None:
        raise ValueError(f"Bidder for bid {bid_id} not found")
    tender = db.get(Tender, bid.tender_id)
    if tender is None:
        raise ValueError(f"Tender for bid {bid_id} not found")

    # Idempotency: if this bid already carries this profile's demo evidence
    # (consolidated dossier, per-section documents, or the retired
    # single-file name — all share the "demo_{profile}_" filename prefix),
    # never create duplicate bidder/document rows.
    already = (
        db.query(Document)
        .filter(
            Document.bid_id == bid.id,
            Document.filename.startswith(f"demo_{profile_key}_"),
        )
        .all()
    )
    if already:
        # Already seeded: never create duplicate bidder/document rows.
        return {
            "seeded": False,
            "reason": "already_seeded",
            "bid_id": bid.id,
            "bidder_id": bidder.id,
            "document_id": already[0].id,
            "document_ids": [d.id for d in already],
            "profile_key": profile_key,
        }

    # 1. Authoritative fictional identifiers onto the normal Bidder row.
    identifiers = profile["identifiers"]
    bidder.pan = identifiers.get("pan")
    bidder.gstin = identifiers.get("gstin")
    bidder.udyam = identifiers.get("udyam")
    bidder.cin = identifiers.get("cin")
    bidder.trade_name = profile.get("trade_name") or bidder.trade_name
    bidder.registered_address = profile["address"]
    bidder.contact_name = profile["contact_name"]
    bidder.contact_email = profile["contact_email"]
    bidder.contact_phone = profile["contact_phone"]
    db.flush()

    # 2. Requirement-driven dossier section(s).
    sections = build_dossier_sections(
        tender.requirements,
        profile_key,
        emd_beneficiary=tender.organization or "Demo Tendering Authority",
    )
    # Most profiles seed ONE consolidated dossier PDF. Profiles with the
    # "split_dossier_sections" scenario flag (Nova: cross-document identity
    # mismatch) seed one standalone evidence document PER SECTION — like a
    # real multi-upload bid — so the cross-document consistency engine has
    # genuinely distinct documents to compare.
    jobs: list[dict] = []
    if profile.get("split_dossier_sections"):
        for template_type, section_data in sections:
            pdf = generate_dossier_pdf(
                profile["legal_name"],
                [(template_type, section_data)],
                banner=demo_banner(),
                title=dossier_section_title(template_type, section_data),
                subtitle=(
                    "Standalone demo evidence document — prototype "
                    "demonstration only."
                ),
            )
            jobs.append(
                {
                    "filename": _DEMO_SECTION_FILENAME.format(
                        profile_key=profile_key,
                        template=template_type.lower(),
                    ),
                    "pdf": pdf,
                    "template_type": template_type,
                }
            )
    else:
        jobs.append(
            {
                "filename": _DEMO_FILENAME.format(profile_key=profile_key),
                "pdf": generate_dossier_pdf(
                    profile["legal_name"], sections, banner=demo_banner()
                ),
                "template_type": "BID_DOSSIER",
            }
        )
    docs_dir = ensure_upload_dir() / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    seeded_docs: list[dict] = []
    for job in jobs:
        pdf = job["pdf"]
        stored_name = f"bid{bid.id}_{job['filename']}"
        path = docs_dir / stored_name
        path.write_bytes(pdf)
        row = Document(
            bid_id=bid.id,
            document_type="UNCLASSIFIED",  # pipeline auto-detects from content
            filename=job["filename"],
            file_path=str(path),
            file_hash=hashlib.sha256(pdf).hexdigest(),
            file_size=len(pdf),
            mime_type="application/pdf",
            uploaded_by=user_id,
            processing_status="UPLOADED",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        # 3. Real document pipeline: classification + extraction — the same
        # service that runs automatically on every upload. Verification,
        # compliance/risk and recommendation are deliberately NOT run here;
        # the officer triggers those from the Bid Detail buttons, so scores
        # are computed live during the demo, not pre-filled.
        process_result = process_document(db, row.id, user_id=user_id)
        seeded_docs.append(
            {
                "document_id": row.id,
                "filename": job["filename"],
                "template_type": job["template_type"],
                "processing_status": process_result.get("status"),
                "fields_extracted": len(
                    process_result.get("extracted_fields") or []
                ),
            }
        )

    audit_service.append_audit(
        db,
        user_id=user_id,
        action="DEMO_EVIDENCE_SEEDED",
        entity_type="bid_submission",
        entity_id=str(bid.id),
        metadata={
            "profile_key": profile_key,
            "document_ids": [d["document_id"] for d in seeded_docs],
            "sections": len(sections),
            "split_documents": bool(profile.get("split_dossier_sections")),
        },
    )
    db.commit()

    total_fields = sum(d["fields_extracted"] for d in seeded_docs)
    statuses = {d["processing_status"] for d in seeded_docs}
    return {
        "seeded": True,
        "bid_id": bid.id,
        "bidder_id": bidder.id,
        "document_id": seeded_docs[0]["document_id"] if seeded_docs else None,
        "document_ids": [d["document_id"] for d in seeded_docs],
        "documents": seeded_docs,
        "profile_key": profile_key,
        "sections": len(sections),
        "processing_status": (
            seeded_docs[0]["processing_status"]
            if len(statuses) == 1
            else "MIXED"
        ),
        "fields_extracted": total_fields,
    }
