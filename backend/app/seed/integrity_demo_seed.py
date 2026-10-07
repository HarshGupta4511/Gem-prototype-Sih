"""Integrity demonstration dataset seeder — DEMO DATA, fully synthetic.

This module builds a *separate* integrity-demo dataset that never touches the
existing Apex / Vertex / Nova / PrimeTech demo records, documents, or
scenarios:

- 4 historical tenders (``INT-DEMO-2024-01`` … ``INT-DEMO-2025-01``), each
  flagged ``is_demo_history=True`` and titled
  ``"DEMO DATA — Integrity demonstration: …"``.
- 8 fictional bidder rows (7 distinct PANs) across 15 bids.
- 38 real generated PDF evidence documents (all through the shared
  ``generate_dossier_pdf`` template path, so every page carries the
  ``SAMPLE — FOR DEMONSTRATION ONLY`` footer).
- Additive mock registry fixtures (``pan_it.json`` / ``gstn.json``) keyed by
  the fictional identifiers.

The dataset is engineered so the *existing* integrity detectors in
``app.services.integrity_service`` fire from real persisted evidence:

1. ``DOCUMENT_IDENTITY_RELATIONSHIP`` — "Solace Engineering Works" and
   "Solace Engg. Works Pvt. Ltd." share PAN ``SEWPL9012S`` under different
   normalized legal names.
2. ``RECURRING_BIDDER_COHORT`` — Kestrel + Meridian co-participate in exactly
   3 tenders (01, 02, 03).
3. ``CROSS_BID_DOCUMENT_SIMILARITY`` — Kestrel's and Vardaan's
   EXPERIENCE_CERTIFICATE documents carry near-identical substantive text
   (only the legal name differs).
4. ``IDENTITY_REGISTRATION_INCONSISTENCY`` — Brightline's bidder row carries
   PAN ``BTRPL6789B`` but its own PAN certificate document shows
   ``XYZPL9999X``.
5. ``REPEATED_HISTORICAL_ANOMALIES`` — Aarohan records compliance FAILs
   (turnover below threshold) in 2 distinct tenders.

Northline Process Equipment Ltd. is deliberately clean and must trigger no
signals. No compliance scores are hardcoded — every outcome is computed by
the real verification / compliance engines. Integrity findings stay separate
from compliance scores and risk; nothing here rejects or disqualifies a
bidder.

Idempotency: :func:`load_integrity_demo_dataset` is a no-op when the four
tenders already exist. :func:`reset_integrity_demo_dataset` deletes only the
four ``INT-DEMO-*`` tenders (via ``delete_tender``, which cascades) plus any
integrity findings referencing them.

The mock fixture records added here are *left in place* on reset: they are
additive, keyed by fictional identifiers that collide with nothing real, and
removing them would require rewriting shared fixture files.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import date
from pathlib import Path

# Guards against concurrent dataset loads (double-clicks / retries).
_LOAD_LOCK = threading.Lock()

INT_TENDER_NUMBERS = [
    "INT-DEMO-2024-01",
    "INT-DEMO-2024-02",
    "INT-DEMO-2024-03",
    "INT-DEMO-2025-01",
]

MOCK_DATA_DIR = Path(__file__).resolve().parent.parent / "adapters" / "mock_data"

# Fictional companies. Every identifier is structurally valid but invented.
# Contact details are unique per row so the shared-contact detector stays
# silent; only the engineered signals fire.
COMPANIES: dict[str, dict] = {
    "kestrel": {
        "legal_name": "Kestrel Pumps & Valves Pvt. Ltd.",
        "pan": "KPVPL1234K",
        "gstin": "27KPVPL1234K1Z5",
        "address": "Plot 42, MIDC Industrial Area, Chakan, Pune - 410501",
        "email": "tenders@kestrel-pumps-demo.in",
        "phone": "+91 98220 41001",
        "contact_name": "R. Deshmukh",
        "incorporation_date": "12-04-2018",
    },
    "meridian": {
        "legal_name": "Meridian Flow Controls Pvt. Ltd.",
        "pan": "MFCPL5678M",
        "gstin": "27MFCPL5678M1Z5",
        "address": "Gat 88, Talegaon Industrial Belt, Pune - 410507",
        "email": "bids@meridian-flow-demo.in",
        "phone": "+91 98220 41002",
        "contact_name": "S. Kulkarni",
        "incorporation_date": "03-09-2016",
    },
    "solace1": {
        "legal_name": "Solace Engineering Works",
        "pan": "SEWPL9012S",
        "gstin": "27SEWPL9012S1Z5",
        "address": "Shed 7, GIDC Estate, Ankleshwar - 393002",
        "email": "info@solace-engg-demo.in",
        "phone": "+91 98220 41003",
        "contact_name": "M. Patel",
        "incorporation_date": "21-01-2019",
    },
    "solace2": {
        # Same PAN as solace1 under a different normalized legal name ->
        # DOCUMENT_IDENTITY_RELATIONSHIP. Distinct GSTIN keeps the GSTIN
        # bucket a singleton so only the PAN relationship fires.
        "legal_name": "Solace Engg. Works Pvt. Ltd.",
        "pan": "SEWPL9012S",
        "gstin": "29SEWPL9012S1Z5",
        "address": "Plot 15-B, KIADB Industrial Area, Bengaluru - 562157",
        "email": "contact@solace-engg-works-demo.in",
        "phone": "+91 98220 41004",
        "contact_name": "A. Rao",
        "incorporation_date": "21-01-2019",
    },
    "vardaan": {
        "legal_name": "Vardaan Industrial Traders",
        "pan": "VITPL3456V",
        "gstin": "27VITPL3456V1Z5",
        "address": "Shop 12, APMC Market Yard, Navi Mumbai - 400705",
        "email": "sales@vardaan-traders-demo.in",
        "phone": "+91 98220 41005",
        "contact_name": "P. Shah",
        "incorporation_date": "14-07-2020",
    },
    "northline": {
        # Deliberately clean: valid identifiers, matching documents,
        # single-tender participation -> no integrity signals.
        "legal_name": "Northline Process Equipment Ltd.",
        "pan": "NPEPL7890N",
        "gstin": "27NPEPL7890N1Z5",
        "address": "Plot 3, SIDCO Industrial Estate, Guindy, Chennai - 600032",
        "email": "tenders@northline-process-demo.in",
        "phone": "+91 98220 41006",
        "contact_name": "K. Iyer",
        "incorporation_date": "30-11-2015",
    },
    "aarohan": {
        "legal_name": "Aarohan Systems Pvt. Ltd.",
        "pan": "ASPL2345A",
        "gstin": "27ASPL2345A1Z5",
        "address": "B-44, MIDC Bhosari, Pune - 411026",
        "email": "bids@aarohan-systems-demo.in",
        "phone": "+91 98220 41007",
        "contact_name": "D. Joshi",
        "incorporation_date": "09-05-2021",
    },
    "brightline": {
        # Bidder-row PAN (BTRPL6789B) differs from the PAN shown on its own
        # PAN certificate document (XYZPL9999X) ->
        # IDENTITY_REGISTRATION_INCONSISTENCY.
        "legal_name": "Brightline Traders",
        "pan": "BTRPL6789B",
        "gstin": "27BTRPL6789B1Z5",
        "doc_pan": "XYZPL9999X",
        "address": "Gala 9, MIDC Andheri East, Mumbai - 400093",
        "email": "hello@brightline-traders-demo.in",
        "phone": "+91 98220 41008",
        "contact_name": "N. Mehta",
        "incorporation_date": "17-02-2022",
    },
}

TENDERS: list[dict] = [
    {
        "tender_number": "INT-DEMO-2024-01",
        "title": "DEMO DATA — Integrity demonstration: pump supply tender 2024-01",
        "issue_date": date(2024, 1, 15),
        "closing_date": date(2024, 3, 15),
        "members": ["kestrel", "meridian", "northline", "solace1"],
    },
    {
        "tender_number": "INT-DEMO-2024-02",
        "title": "DEMO DATA — Integrity demonstration: valve supply tender 2024-02",
        "issue_date": date(2024, 6, 10),
        "closing_date": date(2024, 8, 10),
        "members": ["kestrel", "meridian", "vardaan", "aarohan"],
    },
    {
        "tender_number": "INT-DEMO-2024-03",
        "title": "DEMO DATA — Integrity demonstration: flow equipment tender 2024-03",
        "issue_date": date(2024, 10, 5),
        "closing_date": date(2024, 12, 5),
        "members": ["kestrel", "meridian", "solace2"],
    },
    {
        "tender_number": "INT-DEMO-2025-01",
        "title": "DEMO DATA — Integrity demonstration: process skid tender 2025-01",
        "issue_date": date(2025, 1, 20),
        "closing_date": date(2025, 3, 20),
        "members": ["meridian", "vardaan", "aarohan", "brightline"],
    },
]

# (requirement_name, category, rule_type, rule_config, weight, mandatory)
REQUIREMENTS: list[tuple] = [
    (
        "GST Registration",
        "STATUTORY",
        "REGISTRATION_STATUS",
        {"source": "GSTN", "identifier_field": "gstin",
         "require_status": "ACTIVE"},
        30,
        True,
    ),
    (
        "PAN Verification",
        "STATUTORY",
        "REGISTRATION_STATUS",
        {"source": "PAN_IT", "identifier_field": "pan",
         "require_status": "ACTIVE"},
        30,
        True,
    ),
    (
        "Balance Sheet Turnover",
        "FINANCIAL",
        "MINIMUM",
        {"value_source": "extracted.turnover_inr", "operator": ">=",
         "value": 15000000},
        30,
        True,
    ),
    (
        "ISO 9001 Validity",
        "TECHNICAL",
        "DATE_VALIDITY",
        {"value_source": "extracted.iso_valid_until",
         "document_type": "ISO_9001_CERTIFICATE"},
        10,
        True,
    ),
]

# Identical substantive text for Kestrel's and Vardaan's experience
# certificates — only the legal name on each document differs, which is what
# makes the CROSS_BID_DOCUMENT_SIMILARITY signal genuine.
EXPERIENCE_TEXT = (
    "Client: Demo Municipal Corp (demo). Work: design, manufacture, supply, "
    "installation supervision and commissioning support for industrial pumping "
    "equipment including centrifugal pumps, valves and flow control assemblies "
    "for the municipal water supply augmentation project. Contract value: "
    "Rs 2.4 crore. Date of completion: 15-03-2024. Scope covered preparation "
    "of general arrangement drawings, procurement of raw materials, stage "
    "inspection by the client's third-party inspection agency, dispatch, "
    "erection supervision and trial runs. Performance: the equipment has "
    "performed satisfactorily since commissioning with no penalty levied; "
    "the completion certificate was issued after successful trial operation."
)

_DEMO_SUBTITLE = "DEMO DATA — synthetic record for integrity demonstration only"


# ---------------------------------------------------------------------------
# Mock fixtures (additive, idempotent)
# ---------------------------------------------------------------------------

def _write_fixtures() -> int:
    """Add mock registry records for the fictional identifiers.

    Records are only added when absent (idempotent). Mirrors the pattern in
    ``app.seed.demo_scenarios.ensure_scenario_fixtures``.
    """
    added = 0
    pan_path = MOCK_DATA_DIR / "pan_it.json"
    pan_data = json.loads(pan_path.read_text(encoding="utf-8"))
    gstn_path = MOCK_DATA_DIR / "gstn.json"
    gstn_data = json.loads(gstn_path.read_text(encoding="utf-8"))

    seen_pans: set[str] = set()
    for key, c in COMPANIES.items():
        pan = c["pan"]
        if pan not in pan_data and pan not in seen_pans:
            # solace1's name anchors the shared-PAN record; solace2's
            # divergent name is what the detector flags.
            pan_data[pan] = {
                "pan": pan,
                "name": c["legal_name"],
                "legal_name": c["legal_name"],
                "status": "ACTIVE",
                "name_match": True,
                "itr_filed_upto": 2025,
            }
            added += 1
        seen_pans.add(pan)
        gstin = c["gstin"]
        if gstin not in gstn_data:
            gstn_data[gstin] = {
                "gstin": gstin,
                "legal_name": c["legal_name"],
                "registration_date": "2021-06-15",
                "state": "Maharashtra",
                "status": "ACTIVE",
            }
            added += 1

    # The PAN shown on Brightline's own document must resolve in the mock
    # registry too (it is a structurally valid fictional PAN).
    xyz = COMPANIES["brightline"]["doc_pan"]
    if xyz not in pan_data:
        pan_data[xyz] = {
            "pan": xyz,
            "name": "XYZ Plastics Pvt. Ltd.",
            "legal_name": "XYZ Plastics Pvt. Ltd.",
            "status": "ACTIVE",
            "name_match": True,
            "itr_filed_upto": 2025,
        }
        added += 1

    if added:
        pan_path.write_text(json.dumps(pan_data, indent=2), encoding="utf-8")
        gstn_path.write_text(json.dumps(gstn_data, indent=2), encoding="utf-8")
        # The mock adapters cache fixture JSON in memory; invalidate so the
        # new records are visible to verification runs in this process.
        try:
            from app.adapters.base import _mock_data_cache

            _mock_data_cache.clear()
        except ImportError:
            pass
    return added


# ---------------------------------------------------------------------------
# Document generation
# ---------------------------------------------------------------------------

def _section_data(company: dict, template_type: str) -> dict:
    """Build the template data dict for one standalone evidence document."""
    doc_pan = company.get("doc_pan", company["pan"])
    if template_type == "PAN_CERTIFICATE":
        return {
            "legal_name": company["legal_name"],
            "pan": doc_pan,
            "incorporation_date": company["incorporation_date"],
            "address": company["address"],
            "email": company["email"],
            "phone": company["phone"],
        }
    if template_type == "GST_CERTIFICATE":
        return {
            "legal_name": company["legal_name"],
            "trade_name": company["legal_name"],
            "gstin": company["gstin"],
            "pan": doc_pan,
            "registration_date": "15-06-2021",
            "address": company["address"],
        }
    if template_type == "EXPERIENCE_CERTIFICATE":
        return {
            "legal_name": company["legal_name"],
            "experience": EXPERIENCE_TEXT,
        }
    if template_type == "BALANCE_SHEET":
        return {
            "legal_name": company["legal_name"],
            "financial_year": "2023-24",
            "turnover": "Rs 80,00,000",
            "auditor_name": "Demo Audit Associates",
        }
    if template_type == "ISO_9001_CERTIFICATE":
        return {
            "legal_name": company["legal_name"],
            "iso_certificate_number": "ISO-2023-44551",
            "iso_valid_from": "2020-07-01",
            "iso_valid_until": "2023-06-30",
        }
    raise ValueError(f"Unsupported integrity demo template {template_type}")


def _doc_templates_for(company_key: str, tender_number: str) -> list[str]:
    """Which standalone documents each bid gets."""
    templates = ["PAN_CERTIFICATE", "GST_CERTIFICATE"]
    if company_key == "kestrel" and tender_number in (
        "INT-DEMO-2024-01", "INT-DEMO-2024-02", "INT-DEMO-2024-03"
    ):
        templates.append("EXPERIENCE_CERTIFICATE")
    if company_key == "vardaan" and tender_number == "INT-DEMO-2024-02":
        templates.append("EXPERIENCE_CERTIFICATE")
    if company_key == "aarohan":
        templates.extend(["BALANCE_SHEET", "ISO_9001_CERTIFICATE"])
    return templates


def _persist_document(db, bid, company_key: str, template_type: str,
                      user_id: int | None) -> dict:
    """Generate one standalone PDF, persist it, and run the real pipeline."""
    from app.core.config import ensure_upload_dir
    from app.models.models import Document
    from app.seed.demo_docs import generate_dossier_pdf
    from app.seed.demo_bidder_profiles import demo_banner
    from app.services.pipeline_service import process_document

    company = COMPANIES[company_key]
    section_data = _section_data(company, template_type)
    pdf = generate_dossier_pdf(
        company["legal_name"],
        [(template_type, section_data)],
        banner=demo_banner(),
        title=f"{template_type.replace('_', ' ').title()} — DEMO DATA",
        subtitle=_DEMO_SUBTITLE,
    )
    filename = (
        f"intdemo_{bid.tender_id}_{company_key}_{template_type.lower()}.pdf"
    )
    docs_dir = ensure_upload_dir() / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    path = docs_dir / f"bid{bid.id}_{filename}"
    path.write_bytes(pdf)

    row = Document(
        bid_id=bid.id,
        document_type="UNCLASSIFIED",  # pipeline auto-detects from content
        filename=filename,
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
    result = process_document(db, row.id, user_id=user_id)
    db.refresh(row)
    return {
        "document_id": row.id,
        "template_type": template_type,
        "document_type": row.document_type,
        "processing_status": result.get("status"),
    }


# ---------------------------------------------------------------------------
# Load / reset / status
# ---------------------------------------------------------------------------

def integrity_demo_dataset_status(db) -> dict:
    """Report whether the integrity demo dataset is present."""
    from app.models.models import Tender

    found = (
        db.query(Tender)
        .filter(Tender.tender_number.in_(INT_TENDER_NUMBERS))
        .all()
    )
    by_number = {t.tender_number: t.id for t in found}
    return {
        "loaded": all(n in by_number for n in INT_TENDER_NUMBERS),
        "tender_numbers": [n for n in INT_TENDER_NUMBERS if n in by_number],
        "tender_ids": [by_number[n] for n in INT_TENDER_NUMBERS
                       if n in by_number],
    }


def load_integrity_demo_dataset(db, user_id: int | None = None) -> dict:
    """Create the integrity demo dataset (idempotent).

    Builds 4 tenders, 15 bids and 38 real PDF evidence documents, writes mock
    fixtures, then runs verification + compliance per bid through the real
    engines. Returns counts; a second call is a no-op. Concurrent calls are
    serialized; a call arriving while a load is in progress returns
    ``{"already_running": True}``.
    """
    if not _LOAD_LOCK.acquire(blocking=False):
        return {"already_running": True, "loaded": False,
                "reason": "load already in progress"}
    try:
        return _load_integrity_demo_dataset_locked(db, user_id=user_id)
    finally:
        _LOAD_LOCK.release()


def _load_integrity_demo_dataset_locked(db, user_id: int | None = None) -> dict:
    from app.models.models import Bidder, BidSubmission, Tender, TenderRequirement
    from app.services import audit_service
    from app.services.compliance_service import evaluate_bid
    from app.services.verification_service import run_verification

    if integrity_demo_dataset_status(db)["loaded"]:
        return {"loaded": False, "reason": "already loaded"}

    _write_fixtures()

    counts = {"tenders": 0, "bidders": 0, "bids": 0, "documents": 0}
    for spec in TENDERS:
        tender = Tender(
            tender_number=spec["tender_number"],
            title=spec["title"],
            organization="DEMO DATA — Integrity demonstration",
            department="Procurement (demo)",
            description=(
                "DEMO DATA — synthetic tender created solely for integrity "
                "module demonstrations. All companies, identifiers, documents "
                "and outcomes are fictional."
            ),
            issue_date=spec["issue_date"],
            closing_date=spec["closing_date"],
            status="OPEN",
            is_demo_history=True,
        )
        db.add(tender)
        db.flush()
        counts["tenders"] += 1

        for name, category, rule_type, rule_config, weight, mandatory in REQUIREMENTS:
            db.add(TenderRequirement(
                tender_id=tender.id,
                requirement_name=name,
                category=category,
                rule_type=rule_type,
                rule_config=dict(rule_config),
                threshold=None,
                description=f"DEMO DATA integrity requirement: {name}.",
                weight=weight,
                mandatory=mandatory,
            ))
        db.commit()

        for company_key in spec["members"]:
            company = COMPANIES[company_key]
            bidder = Bidder(
                tender_id=tender.id,
                legal_name=company["legal_name"],
                pan=company["pan"],
                gstin=company["gstin"],
                registered_address=company["address"],
                contact_name=company["contact_name"],
                contact_email=company["email"],
                contact_phone=company["phone"],
                bid_status="SUBMITTED",
            )
            db.add(bidder)
            db.flush()
            counts["bidders"] += 1
            bid = BidSubmission(
                tender_id=tender.id,
                bidder_id=bidder.id,
                status="SUBMITTED",
            )
            db.add(bid)
            db.commit()
            counts["bids"] += 1

            for template_type in _doc_templates_for(company_key,
                                                    spec["tender_number"]):
                info = _persist_document(db, bid, company_key, template_type,
                                         user_id)
                counts["documents"] += 1

            # Real verification + compliance per bid (no recommendation/risk —
            # integrity stays separate from scoring).
            run_verification(db, bid.id, user_id=user_id)
            evaluate_bid(db, bid.id, user_id=user_id)

    audit_service.append_audit(
        db,
        user_id=user_id,
        action="INTEGRITY_DEMO_DATASET_LOADED",
        entity_type="tender",
        entity_id=",".join(INT_TENDER_NUMBERS),
        metadata={"counts": counts},
    )
    db.commit()
    return {"loaded": True, **counts}


def reset_integrity_demo_dataset(db, user_id: int | None = None) -> dict:
    """Delete only the INT-DEMO tenders and findings referencing them.

    Findings are removed before their tenders so the operation is safe
    on databases that enforce the integrity_findings.tender_id FK.
    """
    from app.models.models import Bidder, BidSubmission, IntegrityFinding, Tender
    from app.services import audit_service
    from app.services.delete_service import delete_tender

    wanted = set(INT_TENDER_NUMBERS)
    removed = {"tenders": 0, "findings": 0}

    # Resolve demo tender ids up-front (without deleting yet).
    demo_tender_ids: set[int] = set()
    for number in INT_TENDER_NUMBERS:
        tender = db.query(Tender).filter_by(tender_number=number).first()
        if tender is not None:
            demo_tender_ids.add(tender.id)

    # Demo bid / bidder ids — some detectors reference only bids/bidders,
    # never tender numbers.
    demo_bid_ids: set[int] = set()
    demo_bidder_ids: set[int] = set()
    if demo_tender_ids:
        demo_bid_ids = {
            r[0] for r in
            db.query(BidSubmission.id)
            .filter(BidSubmission.tender_id.in_(demo_tender_ids)).all()
        }
        demo_bidder_ids = {
            r[0] for r in
            db.query(Bidder.id)
            .filter(Bidder.tender_id.in_(demo_tender_ids)).all()
        }

    def _is_demo_finding(finding: IntegrityFinding) -> bool:
        refs = finding.affected_tenders or []
        numbers = {r.get("tender_number") for r in refs
                   if isinstance(r, dict)}
        if numbers & wanted:
            return True
        if finding.tender_id in demo_tender_ids:
            return True
        if finding.bidder_id in demo_bidder_ids:
            return True
        bids = finding.affected_bids or []
        return any(b in demo_bid_ids for b in bids if isinstance(b, int))

    # 1. Findings first: anything generated from the demo records, by
    #    tender number, tender FK, bidder FK, or affected bid ids.
    for finding in db.query(IntegrityFinding).all():
        if _is_demo_finding(finding):
            db.delete(finding)
            removed["findings"] += 1
    db.flush()

    # 2. Then the demo tenders themselves (cascades to bids/documents).
    for tender_id in demo_tender_ids:
        delete_tender(db, tender_id, user_id=user_id)
        removed["tenders"] += 1

    audit_service.append_audit(
        db,
        user_id=user_id,
        action="INTEGRITY_DEMO_DATASET_RESET",
        entity_type="tender",
        entity_id=",".join(INT_TENDER_NUMBERS),
        metadata={"removed": removed},
    )
    db.commit()
    return {"reset": True, **removed}
