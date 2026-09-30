"""Demo seed data (CONTRACT §14).

``run_seed(db=None) -> dict`` creates users, knowledge docs, three tenders
with requirements, eight fictional bidders with generated PDFs, and runs the
FULL pipeline for every document (process → verify → compliance → risk →
recommendation). Also seeds the GeM-style synthetic demo tender
``GEM-DEMO-2026-101`` (see ``app/seed/gem_demo_seed.py``) with three bidders.
Idempotent per tender: the legacy tenders are skipped if ``CPCL-DEMO-2026-001``
exists, while the GeM demo tender seeds independently. CLI: ``cd backend &&
python -m app.seed.seed_data``.

All companies, people, identifiers and addresses are fictional demo data.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

DEMO_PASSWORD = "Demo@123"
TENDER1 = "CPCL-DEMO-2026-001"

# Fictional demo policy documents (replaced 2026-09-30 by the source-grounded
# authoritative knowledge base). Any KnowledgeDoc still carrying one of these
# titles is removed from the database at seed time — fictional text must never
# be presented as government policy.
OLD_FICTIONAL_POLICY_TITLES = {
    "GeM Procurement Guidelines (Demo)",
    "Make in India — Local Content Guidelines (Demo)",
    "MSME / Udyam Registration Reference (Demo)",
    "OEM Authorization Policy (Demo)",
    "Blacklisting and Debarment Policy (Demo)",
    "CPCL Tender Conditions (Demo)",
    "Document Verification SOP (Demo)",
}

BLACKLIST_EXPR = (
    "not (ctx['verification'].get('BLACKLIST') or {}).get('data', {}).get('blacklisted', False) "
    "and not (ctx['verification'].get('BLACKLIST') or {}).get('data', {}).get('debarred', False)"
)
ITR_EXPR = (
    """"PASS" if (ctx['extracted'].get('itr') or (((ctx['verification'].get('PAN_IT') or {}).get('data') or {}).get('itr_filed_upto') or 0) >= 2024) """
    """else ("REVIEW_REQUIRED" if ((((ctx['verification'].get('PAN_IT') or {}).get('data') or {}).get('itr_filed_upto') or 0) or 0) >= 2022 else "FAIL")"""
)


def _policies_dir() -> Path:
    # The authoritative policy collection lives inside this repository.
    # (A stale Sept-2026 workspace copy at ~/workspace/cpcl-bidverify is
    # deliberately NOT consulted — it holds the old fictional demo files.)
    return Path(__file__).resolve().parent / "policies"


# --------------------------------------------------------------------------
# requirement builders (tender 1: 11 requirements, weights sum to 100)
# --------------------------------------------------------------------------

def _tender1_requirements() -> list[dict]:
    return [
        dict(requirement_name="GST Registration", category="STATUTORY",
             description="Bidder must hold an active GST registration.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "GSTN", "identifier_field": "gstin",
                          "require_status": "ACTIVE"},
             threshold="Active GSTIN", expected_value="Status: ACTIVE",
             verification_source="GSTN", weight=15,
             policy_reference="GeM GTC §4.2"),
        dict(requirement_name="PAN Verification", category="STATUTORY",
             description="Bidder PAN must be active in Income Tax records.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "PAN_IT", "identifier_field": "pan",
                          "require_status": "ACTIVE"},
             threshold="Active PAN", expected_value="Status: ACTIVE",
             verification_source="PAN_IT", weight=10,
             policy_reference="GeM GTC §4.2"),
        dict(requirement_name="Udyam/MSME Registration", category="REGISTRATION",
             description="Valid Udyam registration for the bidding enterprise.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "UDYAM", "identifier_field": "udyam_number",
                          "require_status": "ACTIVE"},
             threshold="Valid Udyam registration", expected_value="Status: ACTIVE",
             verification_source="UDYAM", weight=10,
             policy_reference="MSME Udyam Reference §3"),
        dict(requirement_name="Minimum Turnover ₹10 Crore", category="FINANCIAL",
             description="Average annual turnover of at least ₹10 crore.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.turnover_inr",
                          "operator": ">=", "value": 100000000},
             threshold="₹10 Crore", expected_value="turnover_inr ≥ 100000000",
             verification_source=None, weight=15,
             policy_reference="CPCL Tender Conditions §2"),
        dict(requirement_name="Minimum 5 Years Experience", category="EXPERIENCE",
             description="At least 5 years of relevant supply experience.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.experience_years",
                          "operator": ">=", "value": 5},
             threshold="5 years", expected_value="experience_years ≥ 5",
             verification_source=None, weight=10,
             policy_reference="CPCL Tender Conditions §2"),
        dict(requirement_name="OEM Authorization", category="OEM",
             description="OEM authorization declared in the bid dossier (single-document submission).",
             mandatory=False, rule_type="EXISTENCE",
             rule_config={"value_source": "extracted.oem_authorization_valid"},
             threshold="OEM authorization declared", expected_value="Information present",
             verification_source=None, weight=10,
             policy_reference="OEM Authorization Policy §2"),
        dict(requirement_name="Make in India Local Content ≥ 50%", category="LOCAL_CONTENT",
             description="Declared local content must be at least 50%.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.local_content_pct",
                          "operator": ">=", "value": 50},
             threshold="≥ 50%", expected_value="local_content_pct ≥ 50",
             verification_source=None, weight=10,
             policy_reference="Make in India Guidelines §2"),
        dict(requirement_name="EPFO Registration", category="STATUTORY",
             description="Active EPFO registration (desirable).",
             mandatory=False, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "EPFO", "identifier_field": "epfo_code",
                          "require_status": "ACTIVE"},
             threshold="Active EPFO code", expected_value="Status: ACTIVE",
             verification_source="EPFO", weight=5,
             policy_reference="CPCL Tender Conditions §5"),
        dict(requirement_name="ESIC Registration", category="STATUTORY",
             description="Active ESIC registration.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "ESIC", "identifier_field": "esic_code",
                          "require_status": "ACTIVE",
                          "not_found_status": "REVIEW_REQUIRED"},
             threshold="Active ESIC code", expected_value="Status: ACTIVE",
             verification_source="ESIC", weight=5,
             policy_reference="CPCL Tender Conditions §5"),
        dict(requirement_name="Income Tax Compliance", category="STATUTORY",
             description="ITR filed up to the latest assessment year.",
             mandatory=False, rule_type="CUSTOM_RULE",
             rule_config={"expression": ITR_EXPR},
             threshold="ITR filed up to AY 2024-25", expected_value="PASS",
             verification_source="PAN_IT", weight=5,
             policy_reference="CPCL Tender Conditions §6"),
        dict(requirement_name="Blacklisting / Debarment Check", category="INTEGRITY",
             description="Bidder must not be blacklisted or debarred.",
             mandatory=True, rule_type="CUSTOM_RULE",
             rule_config={"expression": BLACKLIST_EXPR},
             threshold="Not blacklisted / debarred", expected_value="PASS",
             verification_source="BLACKLIST", weight=5,
             policy_reference="Blacklist/Debarment Policy §4"),
    ]


def _tender2_requirements() -> list[dict]:
    return [
        dict(requirement_name="GST Registration", category="STATUTORY",
             description="Bidder must hold an active GST registration.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "GSTN", "identifier_field": "gstin",
                          "require_status": "ACTIVE"},
             threshold="Active GSTIN", expected_value="Status: ACTIVE",
             verification_source="GSTN", weight=20,
             policy_reference="GeM GTC §4.2"),
        dict(requirement_name="PAN Verification", category="STATUTORY",
             description="Bidder PAN must be active in Income Tax records.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "PAN_IT", "identifier_field": "pan",
                          "require_status": "ACTIVE"},
             threshold="Active PAN", expected_value="Status: ACTIVE",
             verification_source="PAN_IT", weight=15,
             policy_reference="GeM GTC §4.2"),
        dict(requirement_name="Udyam/MSME Registration", category="REGISTRATION",
             description="Valid Udyam registration for the bidding enterprise.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "UDYAM", "identifier_field": "udyam_number",
                          "require_status": "ACTIVE"},
             threshold="Valid Udyam registration", expected_value="Status: ACTIVE",
             verification_source="UDYAM", weight=15,
             policy_reference="MSME Udyam Reference §3"),
        dict(requirement_name="Minimum Turnover ₹2 Crore", category="FINANCIAL",
             description="Annual turnover of at least ₹2 crore.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.turnover_inr",
                          "operator": ">=", "value": 20000000},
             threshold="₹2 Crore", expected_value="turnover_inr ≥ 20000000",
             verification_source=None, weight=20,
             policy_reference="CPCL Tender Conditions §2"),
        dict(requirement_name="Minimum 3 Years Experience", category="EXPERIENCE",
             description="At least 3 years of relevant experience.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.experience_years",
                          "operator": ">=", "value": 3},
             threshold="3 years", expected_value="experience_years ≥ 3",
             verification_source=None, weight=15,
             policy_reference="CPCL Tender Conditions §2"),
        dict(requirement_name="Blacklisting / Debarment Check", category="INTEGRITY",
             description="Bidder must not be blacklisted or debarred.",
             mandatory=True, rule_type="CUSTOM_RULE",
             rule_config={"expression": BLACKLIST_EXPR},
             threshold="Not blacklisted / debarred", expected_value="PASS",
             verification_source="BLACKLIST", weight=15,
             policy_reference="Blacklist/Debarment Policy §4"),
    ]


def _tender3_requirements() -> list[dict]:
    return [
        dict(requirement_name="GST Registration", category="STATUTORY",
             description="Bidder must hold an active GST registration.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "GSTN", "identifier_field": "gstin",
                          "require_status": "ACTIVE"},
             threshold="Active GSTIN", expected_value="Status: ACTIVE",
             verification_source="GSTN", weight=20,
             policy_reference="GeM GTC §4.2"),
        dict(requirement_name="PAN Verification", category="STATUTORY",
             description="Bidder PAN must be active in Income Tax records.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "PAN_IT", "identifier_field": "pan",
                          "require_status": "ACTIVE"},
             threshold="Active PAN", expected_value="Status: ACTIVE",
             verification_source="PAN_IT", weight=15,
             policy_reference="GeM GTC §4.2"),
        dict(requirement_name="Udyam/MSME Registration", category="REGISTRATION",
             description="Valid Udyam registration for the bidding enterprise.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "UDYAM", "identifier_field": "udyam_number",
                          "require_status": "ACTIVE"},
             threshold="Valid Udyam registration", expected_value="Status: ACTIVE",
             verification_source="UDYAM", weight=15,
             policy_reference="MSME Udyam Reference §3"),
        dict(requirement_name="Minimum Turnover ₹50 Lakh", category="FINANCIAL",
             description="Annual turnover of at least ₹50 lakh.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.turnover_inr",
                          "operator": ">=", "value": 5000000},
             threshold="₹50 Lakh", expected_value="turnover_inr ≥ 5000000",
             verification_source=None, weight=15,
             policy_reference="CPCL Tender Conditions §2"),
        dict(requirement_name="Startup India Recognition", category="REGISTRATION",
             description="DPIIT Startup India recognition declared in the bid dossier.",
             mandatory=True, rule_type="EXISTENCE",
             rule_config={"value_source": "extracted.startup_certificate_number"},
             threshold="Startup India certificate number", expected_value="Information present",
             verification_source=None, weight=10,
             policy_reference="Startup India Recognition norms"),
        dict(requirement_name="Make in India Local Content ≥ 50%", category="LOCAL_CONTENT",
             description="Declared local content must be at least 50%.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.local_content_pct",
                          "operator": ">=", "value": 50},
             threshold="≥ 50%", expected_value="local_content_pct ≥ 50",
             verification_source=None, weight=10,
             policy_reference="Make in India Guidelines §2"),
        dict(requirement_name="Blacklisting / Debarment Check", category="INTEGRITY",
             description="Bidder must not be blacklisted or debarred.",
             mandatory=True, rule_type="CUSTOM_RULE",
             rule_config={"expression": BLACKLIST_EXPR},
             threshold="Not blacklisted / debarred", expected_value="PASS",
             verification_source="BLACKLIST", weight=15,
             policy_reference="Blacklist/Debarment Policy §4"),
        dict(requirement_name="Experience Certificate", category="EXPERIENCE",
             description="Experience declared in the bid dossier (informational; weight 0).",
             mandatory=False, rule_type="EXISTENCE",
             rule_config={"value_source": "extracted.experience_years"},
             threshold="Experience declared", expected_value="Information present",
             verification_source=None, weight=0,
             policy_reference="CPCL Tender Conditions §2"),
    ]


# --------------------------------------------------------------------------
# bidder document specs: (doc_type, filename, data)
# --------------------------------------------------------------------------

def _docs_for(spec: dict) -> list[tuple[str, str, dict]]:
    """Expand a bidder spec into (doc_type, filename, data) triples."""
    base = {
        "legal_name": spec["legal_name"],
        "address": spec["address"],
        "email": spec["email"],
        "phone": spec["phone"],
    }
    out: list[tuple[str, str, dict]] = []
    slug = spec["slug"]

    def add(doc_type: str, **data):
        merged = dict(base)
        merged.update(data)
        out.append((doc_type, f"{slug}_{doc_type.lower()}.pdf", merged))

    add("PAN_CERTIFICATE", pan=spec["pan"],
        incorporation_date=spec["incorporation_date"])
    add("GST_CERTIFICATE", trade_name=spec.get("trade_name", spec["legal_name"]),
        gstin=spec["gstin"], pan=spec["pan"],
        registration_date=spec["registration_date"])
    add("UDYAM_CERTIFICATE", udyam=spec["udyam"],
        valid_until=spec.get("udyam_valid_until", "31-12-2030"))
    if "turnover" in spec:
        add("TURNOVER_CERTIFICATE", turnover=spec["turnover"],
            turnover_period=spec["turnover_period"])
    if "experience" in spec:
        add("EXPERIENCE_CERTIFICATE", experience=spec["experience"])
    if "oem" in spec:
        oem = spec["oem"]
        add("OEM_AUTHORIZATION", oem_name=oem["name"],
            oem_authorization=oem["authorization"],
            valid_until=oem["valid_until"])
    if "epfo_code" in spec:
        add("EPFO_CERTIFICATE", epfo_code=spec["epfo_code"])
    if "esic_code" in spec:
        add("ESIC_CERTIFICATE", esic_code=spec["esic_code"],
            valid_until=spec.get("esic_valid_until", "31-12-2030"))
    if "local_content" in spec:
        add("MII_DECLARATION", local_content=spec["local_content"])
    if "acknowledgement_number" in spec:
        add("ITR", acknowledgement_number=spec["acknowledgement_number"],
            pan=spec["pan"])
    if "startup_cert" in spec:
        add("STARTUP_INDIA_CERTIFICATE",
            certificate_number=spec["startup_cert"],
            dpiit_recognition="Yes")
    return out


def _dossier_for(spec: dict) -> tuple[str, str, str, list[tuple[str, dict]]]:
    """One consolidated dossier per bidder: (doc_type, filename, legal_name, sections).

    Reuses the per-section templates/data of ``_docs_for`` — the bidder uploads
    a SINGLE document and all information is extracted from it.
    """
    sections = [(doc_type, data) for doc_type, _filename, data in _docs_for(spec)]
    return ("BID_DOSSIER", f"{spec['slug']}_bid_dossier.pdf",
            spec["legal_name"], sections)


_BIDDERS_T1 = [
    dict(slug="apex", legal_name="Apex Flow Systems Pvt Ltd",
         trade_name="Apex Flow Systems", pan="AAFCA1234E",
         gstin="27AAFCA1234E1Z5", udyam="UDYAM-MH-19-0012345",
         cin="U28999MH2015PTC123456",
         address="Plot 42, MIDC Industrial Area, Andheri East, Mumbai 400093",
         email="info@apexflow.example.in", phone="9820001234",
         incorporation_date="12-03-2015", registration_date="15-06-2021",
         turnover="Rs 12.4 crore", turnover_period="FY2022-23 to FY2024-25",
         experience="9 years",
         oem={"name": "Kirloskar Brothers Ltd", "authorization": "Yes",
              "valid_until": "31-12-2027"},
         epfo_code="MH/123456/001", esic_code="11000012345678901",
         local_content="62%"),
    dict(slug="bharat", legal_name="Bharat Mech Works",
         pan="BBMWB5678F", gstin="27BBMWB5678F1Z5",
         udyam="UDYAM-MH-19-0023456", cin="U29299MH2012PTC234567",
         address="Gala 7, MIDC Bhosari, Pune 411026",
         email="contact@bharatmech.example.in", phone="9820012345",
         incorporation_date="20-07-2012", registration_date="10-03-2019",
         turnover="Rs 8.2 crore", turnover_period="FY2022-23 to FY2024-25",
         experience="7 years", epfo_code="MH/999999/009",
         local_content="55%"),
    dict(slug="crestline", legal_name="Crestline Pumps Pvt Ltd",
         pan="CCPLC9012G", gstin="27CCPLC9012G1Z5",
         udyam="UDYAM-MH-19-0034567", cin="U29300MH2016PTC345678",
         address="Plot 18, TTC Industrial Area, Navi Mumbai 400705",
         email="sales@crestlinepumps.example.in", phone="9820023456",
         incorporation_date="05-11-2016", registration_date="22-07-2020",
         turnover="Rs 11.5 crore", turnover_period="FY2022-23 to FY2024-25",
         experience="3 years",
         oem={"name": "KSB Pumps Ltd", "authorization": "Yes",
              "valid_until": "31-12-2026"},
         esic_code="11000234567890123", local_content="58%"),
    dict(slug="deccan", legal_name="Deccan Industrial Traders",
         pan="DDITR3456H", gstin="27DDITR3456H1Z5",
         udyam="UDYAM-MH-19-0045678", cin="U28100MH2011PTC456789",
         address="Shop 5, Market Yard, Gulbarga Road, Solapur 413001",
         email="deccan.traders@example.in", phone="9820034567",
         incorporation_date="14-02-2011", registration_date="05-11-2018",
         turnover="Rs 15 crore", turnover_period="FY2022-23 to FY2024-25",
         experience="12 years",
         oem={"name": "Crompton Greaves Consumer Electricals Ltd",
              "authorization": "Yes", "valid_until": "31-12-2026"},
         epfo_code="MH/456789/004", local_content="52%"),
    dict(slug="everest", legal_name="Everest Engineering Co",
         pan="EEENG7890J", gstin="27EEENG7890J1Z5",
         udyam="UDYAM-MH-19-0056789", cin="U29100MH2010PTC567890",
         address="B-11, MIDC Chakan, Pune 410501",
         email="info@everestengg.example.in", phone="9820045678",
         incorporation_date="28-09-2010", registration_date="19-05-2017",
         udyam_valid_until="31-03-2024",
         turnover="Rs 13.2 crore", turnover_period="FY2022-23 to FY2024-25",
         experience="11 years",
         oem={"name": "Kirloskar Brothers Ltd", "authorization": "Yes",
              "valid_until": "31-12-2027"},
         epfo_code="MH/567890/005", esic_code="11000456789012345",
         esic_valid_until="31-03-2024", local_content="60%"),
    dict(slug="fusion", legal_name="Fusion Petro Equipment LLP",
         pan="FFPEQ2345K", gstin="27FFPEQ2345K1Z5",
         udyam="UDYAM-MH-19-0067890", cin="U28200MH2019PTC678901",
         address="Plot 99, GIDC Ankleshwar, Gujarat 393002",
         email="hello@fusionpetro.example.in", phone="9820056789",
         incorporation_date="17-06-2019", registration_date="30-09-2021",
         turnover="Rs 12.4 crore (approx)",
         turnover_period="FY2022-23 to FY2024-25",
         experience="8 years",
         oem={"name": "Siemens Ltd", "authorization": "Yes (approx)",
              "valid_until": "31-12-2026"},
         epfo_code="MH/678901/006", esic_code="11000567890123456",
         local_content="68%"),
]

_BIDDER_T2 = dict(
    slug="ganesh", legal_name="Ganesh Controls", pan="GGCON6789L",
    gstin="27GGCON6789L1Z5", udyam="UDYAM-MH-19-0078901",
    cin="U31900MH2014PTC789012",
    address="Shed C-3, MIDC Waluj, Aurangabad 431136",
    email="ganesh.controls@example.in", phone="9820067890",
    incorporation_date="09-04-2014", registration_date="11-02-2020",
    turnover="Rs 3.5 crore", turnover_period="FY2023-24 to FY2024-25",
    experience="8 years", acknowledgement_number="98765432101234",
)

_BIDDER_T3 = dict(
    slug="harsh", legal_name="Harsh Safety Gear", pan="HHSHG1234M",
    gstin="27HHSHG1234M1Z5", udyam="UDYAM-MH-19-0089012",
    cin="U25200MH2022PTC890123",
    address="Unit 12, MIDC Tarapur, Palghar 401506",
    email="harsh.safety@example.in", phone="9820078901",
    incorporation_date="22-01-2022", registration_date="01-08-2023",
    turnover="Rs 80 lakh", turnover_period="FY2023-24 to FY2024-25",
    local_content="55%", startup_cert="DIPP123456",
)


# --------------------------------------------------------------------------
# seed steps
# --------------------------------------------------------------------------

def _seed_users(db) -> dict:
    from app.core.security import get_password_hash
    from app.models.models import User

    specs = [
        ("Demo Officer", "officer@demo.cpcl.in", "PROCUREMENT_OFFICER", "Procurement"),
        ("Demo Verifier", "verifier@demo.cpcl.in", "VERIFIER", "Verification"),
        ("Demo Auditor", "auditor@demo.cpcl.in", "AUDITOR", "Audit"),
        ("Demo Admin", "admin@demo.cpcl.in", "ADMIN", "IT"),
    ]
    users = {}
    for name, email, role, dept in specs:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            user = User(name=name, email=email,
                        password_hash=get_password_hash(DEMO_PASSWORD),
                        role=role, department=dept)
            db.add(user)
            db.commit()
            db.refresh(user)
        users[email] = user
    return users


def _seed_knowledge(db) -> int:
    """Seed the authoritative, source-grounded policy knowledge base.

    Driven by ``policies/manifest.json`` — every document carries title,
    issuing authority, source URL, publication/effective dates, version and
    retrieval date. Fictional demo policy documents (and any POLICY doc not
    present in the manifest) are removed so fictional text is never presented
    as government policy. Documents whose manifest version changed are
    re-indexed so the current applicable version is always the one retrieved.
    Idempotent.
    """
    import json

    from app.models.models import KnowledgeChunk, KnowledgeDoc
    from app.services.rag_service import index_knowledge_doc

    policies_dir = _policies_dir()
    manifest_path = policies_dir / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            log.warning("Policy manifest unreadable: %s", manifest_path)

    manifest_titles = {m.get("title") for m in manifest.values() if m.get("title")}

    # 1. Remove fictional/demo policy docs and anything not in the manifest.
    removed = 0
    for doc in db.query(KnowledgeDoc).filter(KnowledgeDoc.doc_type == "POLICY").all():
        if doc.title in OLD_FICTIONAL_POLICY_TITLES or doc.title not in manifest_titles:
            db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete()
            db.delete(doc)
            removed += 1
    if removed:
        db.commit()
        log.info("Seed: removed %d fictional/stale policy docs", removed)

    # 2. Index manifest documents (re-index when the version changed).
    count = 0
    for filename, meta in manifest.items():
        title = meta.get("title")
        if not title:
            continue
        path = policies_dir / filename
        if not path.is_file():
            log.warning("Policy file missing: %s", path)
            continue
        version = str(meta.get("version") or "")[:50] or "1.0"
        existing = db.query(KnowledgeDoc).filter(KnowledgeDoc.title == title).one_or_none()
        if existing is not None:
            if (existing.version or "") == version:
                continue
            # Newer/current version available — replace content and re-index.
            existing.content = path.read_text(encoding="utf-8")
            existing.version = version
            db.flush()
            index_knowledge_doc(db, existing)
            count += 1
            continue
        doc = KnowledgeDoc(title=title, doc_type="POLICY", version=version,
                           content=path.read_text(encoding="utf-8"))
        db.add(doc)
        db.flush()
        index_knowledge_doc(db, doc)
        count += 1
    return count


# Demo tender → Step-1 wizard fields. Kept in one place so fresh seeds and the
# startup backfill (existing databases) use identical values. These are the
# four synthetic demo tenders only — never applied to officer-created tenders.
DEMO_TENDER_WIZARD_FIELDS: dict[str, dict[str, object]] = {
    "CPCL-DEMO-2026-001": {
        "tender_type": "GOODS",
        "bid_type": "TWO_PACKET",
        "emd_amount_inr": 900000,
        "delivery_period": "12 months",
        "place_of_delivery": "Chennai",
    },
    "CPCL-DEMO-2026-002": {
        "tender_type": "SERVICES",
        "bid_type": "TWO_PACKET",
        "emd_amount_inr": 160000,
        "delivery_period": "24 months",
        "place_of_delivery": "Chennai",
    },
    "CPCL-DEMO-2026-003": {
        "tender_type": "GOODS",
        "bid_type": "SINGLE_PACKET",
        "emd_amount_inr": 50000,
        "delivery_period": "60 days",
        "place_of_delivery": "Chennai",
    },
    "GEM-DEMO-2026-101": {
        "tender_type": "GOODS",
        "bid_type": "TWO_PACKET",
        "emd_amount_inr": 15000,
        "delivery_period": "12 months",
        "place_of_delivery": "Multiple consignee locations",
    },
}


def _create_tender(db, *, number, title, department, issue, closing,
                   value, requirements, created_by, tender_type=None,
                   bid_type=None, emd_amount_inr=None, delivery_period=None,
                   place_of_delivery=None) -> object:
    from app.models.models import Tender, TenderRequirement

    defaults = DEMO_TENDER_WIZARD_FIELDS.get(number, {})
    tender = Tender(tender_number=number, title=title, organization="CPCL",
                    department=department, issue_date=issue, closing_date=closing,
                    estimated_value_inr=value, status="OPEN",
                    tender_type=tender_type if tender_type is not None
                    else defaults.get("tender_type"),
                    bid_type=bid_type if bid_type is not None
                    else defaults.get("bid_type"),
                    emd_amount_inr=emd_amount_inr if emd_amount_inr is not None
                    else defaults.get("emd_amount_inr"),
                    delivery_period=delivery_period if delivery_period is not None
                    else defaults.get("delivery_period"),
                    place_of_delivery=place_of_delivery if place_of_delivery is not None
                    else defaults.get("place_of_delivery"),
                    created_by=created_by)
    db.add(tender)
    db.flush()
    for spec in requirements:
        db.add(TenderRequirement(tender_id=tender.id, **spec))
    db.commit()
    return tender


def _process_bidder_documents(db, bid, specs, admin_id, dossier=None) -> tuple[int, list]:
    """Generate PDFs, insert Document rows and run the real pipeline.

    ``dossier`` optionally overrides the dossier tuple built from ``specs``
    (a 4- or 5-tuple; the 5th element is an optional banner string).

    Per-doc try/except: one bad doc never kills the seed. Re-raises if zero
    docs were processed overall.
    """
    from app.core.config import ensure_upload_dir
    from app.models.models import Document
    from app.seed.demo_docs import generate_dossier_pdf
    from app.services.pipeline_service import process_document

    docs_dir = ensure_upload_dir() / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    rows = []
    dossier = dossier if dossier is not None else _dossier_for(specs)
    if len(dossier) == 5:
        _doc_type, filename, legal_name, sections, banner = dossier
    else:
        _doc_type, filename, legal_name, sections = dossier
        banner = None
    pdf = generate_dossier_pdf(legal_name, sections, banner=banner)
    path = docs_dir / f"bid{bid.id}_{filename}"
    path.write_bytes(pdf)
    # The type is intentionally NOT specified here — the processing pipeline
    # auto-detects it from the document content, exactly like an officer
    # upload. The dossier PDFs carry the "Consolidated Bid Dossier" marker,
    # so the classifier detects BID_DOSSIER.
    row = Document(
        bid_id=bid.id, document_type="UNCLASSIFIED", filename=filename,
        file_path=str(path), file_hash=hashlib.sha256(pdf).hexdigest(),
        file_size=len(pdf), mime_type="application/pdf",
        uploaded_by=admin_id, processing_status="UPLOADED",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    rows.append(row)
    try:
        result = process_document(db, row.id, user_id=admin_id)
        if result.get("status") == "PROCESSED":
            processed += 1
    except Exception as exc:  # noqa: BLE001 - one bad doc must not kill the seed
        log.exception("Seed: failed to process document %s (%s)", row.id, exc)
    if processed == 0:
        raise RuntimeError("Seed: zero documents processed for bid %s" % bid.id)
    log.info("Seed: bid %s (%s): %d/%d documents processed",
             bid.id, specs["legal_name"], processed, len(rows))
    return processed, rows


def _seed_bidder(db, tender, specs, admin_id, dossier=None) -> tuple:
    """Create bidder + bid, generate docs, run the full pipeline per bid."""
    from app.models.models import Bidder, BidSubmission
    from app.services.compliance_service import evaluate_bid
    from app.services.recommendation_service import generate_recommendation
    from app.services.verification_service import run_verification

    bidder = Bidder(
        tender_id=tender.id, legal_name=specs["legal_name"],
        trade_name=specs.get("trade_name"), pan=specs.get("pan"),
        gstin=specs.get("gstin"), udyam=specs.get("udyam"),
        cin=specs.get("cin"), registered_address=specs.get("address"),
        contact_name="Purchase Department",
        contact_email=specs.get("email"), contact_phone=specs.get("phone"),
        bid_status="SUBMITTED",
    )
    db.add(bidder)
    db.flush()
    bid = BidSubmission(tender_id=tender.id, bidder_id=bidder.id,
                        status="SUBMITTED")
    db.add(bid)
    db.commit()
    db.refresh(bid)

    processed, rows = _process_bidder_documents(db, bid, specs, admin_id,
                                                    dossier=dossier)

    run_verification(db, bid.id, user_id=admin_id)
    evaluate_bid(db, bid.id, user_id=admin_id)
    generate_recommendation(db, bid.id, user_id=admin_id)
    log.info("Seed: bid %s pipeline complete", bid.id)
    return bid, processed, rows


def _downgrade_fusion_turnover_confidence(db, bid) -> None:
    """Set F's turnover_inr extraction confidence to 0.62.

    The REGEX extractor pulls "Rs 12.4 crore" at 0.95+ confidence and wins
    dedupe over the mock-LLM 0.62 parse of the "(approx)" labeled line, so
    the persisted field would never be low-confidence on its own. We
    explicitly downgrade it to simulate the low-confidence extraction
    scenario: the compliance engine's <0.70 rule then genuinely downgrades
    the turnover PASS to REVIEW_REQUIRED.
    """
    from app.models.models import Document, ExtractedField

    doc = (db.query(Document)
           .filter(Document.bid_id == bid.id,
                   Document.document_type == "BID_DOSSIER")
           .one_or_none())
    if doc is None:  # never let a seed quirk kill the whole demo database
        log.warning("Seed: no BID_DOSSIER found for bid %s; skipping downgrade",
                    bid.id)
        return
    field = (db.query(ExtractedField)
             .filter(ExtractedField.document_id == doc.id,
                     ExtractedField.field_name == "turnover_inr")
             .one_or_none())
    if field is None:
        log.warning("Seed: no turnover_inr field for bid %s; skipping downgrade",
                    bid.id)
        return
    field.confidence = 0.62
    field.confidence = 0.62
    db.commit()
    log.info("Seed: downgraded turnover_inr confidence to 0.62 for bid %s",
             bid.id)


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------

def run_seed(db=None) -> dict:
    """Run the full demo seed.

    Idempotent per tender: tenders CPCL-DEMO-2026-001/002/003 seed together on
    a fresh database, while the GeM demo tender (GEM-DEMO-2026-101) seeds
    independently — so it also lands on databases seeded before it existed.
    """
    from app.models.models import Tender
    from app.seed.gem_demo_seed import seed_gem_demo_tender

    own_session = db is None
    if own_session:
        from app.database.base import Base
        from app.database.session import SessionLocal, engine
        Base.metadata.create_all(engine)
        db = SessionLocal()
    try:
        users = _seed_users(db)
        admin_id = users["admin@demo.cpcl.in"].id

        result: dict = {"skipped": False}
        if db.query(Tender).filter(
                Tender.tender_number == TENDER1).first() is None:
            kb = _seed_knowledge(db)
            log.info("Seed: %d knowledge docs indexed", kb)

            tender1 = _create_tender(
                db, number=TENDER1, title="Procurement of Industrial Pump Systems",
                department="Materials Department", issue=date(2026, 8, 1),
                closing=date(2026, 9, 30), value=45000000,
                requirements=_tender1_requirements(), created_by=admin_id)

            total_docs = 0
            bid_count = 0
            fusion_bid = None
            for spec in _BIDDERS_T1:
                bid, processed, _rows = _seed_bidder(db, tender1, spec, admin_id)
                total_docs += processed
                bid_count += 1
                if spec["slug"] == "fusion":
                    fusion_bid = bid
            if fusion_bid is not None:
                _downgrade_fusion_turnover_confidence(db, fusion_bid)
                # Re-evaluate F now that the extraction confidence is low, so the
                # stored compliance/risk results reflect the downgrade.
                from app.services.compliance_service import evaluate_bid
                from app.services.recommendation_service import generate_recommendation
                evaluate_bid(db, fusion_bid.id, user_id=admin_id)
                generate_recommendation(db, fusion_bid.id, user_id=admin_id)

            tender2 = _create_tender(
                db, number="CPCL-DEMO-2026-002",
                title="AMC for Refinery Instrumentation",
                department="Maintenance Department", issue=date(2026, 8, 15),
                closing=date(2026, 10, 15), value=8000000,
                requirements=_tender2_requirements(), created_by=admin_id)
            _bid, processed, _rows = _seed_bidder(db, tender2, _BIDDER_T2, admin_id)
            total_docs += processed
            bid_count += 1

            tender3 = _create_tender(
                db, number="CPCL-DEMO-2026-003",
                title="Supply of Safety Helmets (MSE)",
                department="Safety Department", issue=date(2026, 9, 1),
                closing=date(2026, 10, 31), value=2500000,
                requirements=_tender3_requirements(), created_by=admin_id)
            _bid, processed, _rows = _seed_bidder(db, tender3, _BIDDER_T3, admin_id)
            total_docs += processed
            bid_count += 1

            result.update({"tenders": 3, "bidders": bid_count,
                           "documents": total_docs})
        else:
            log.info("Seed skipped: %s already exists", TENDER1)
            result["skipped"] = True

        # GeM-style synthetic demo dataset — seeds independently of T1..T3.
        result["gem_demo"] = seed_gem_demo_tender(db, admin_id)
        log.info("Seed complete: %s", result)
        return result
    finally:
        if own_session:
            db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run_seed())