"""GeM-style synthetic demo dataset (tender GEM-DEMO-2026-101).

Buyer-side requirements are modeled on a public GeM bid document for
haemodialysis consumables (two-packet bid: turnover, experience, past
performance, OEM authorization, MII local content, EMD, MSE/MII purchase
preference). All bidder-side data is SYNTHETIC and fictional — invented
companies, identifiers and addresses for prototype demonstration only.
Nothing here is copied from the reference PDFs.

Three bidders demonstrate the full pipeline spread:
  * Apex MediSupply Pvt Ltd — mostly compliant  -> PROCEED
  * BrightCare Traders Pvt Ltd — mismatches     -> REVIEW_REQUIRED
  * CareWell Enterprises Pvt Ltd — multi-issue   -> NOT_RECOMMENDED (blacklisted)

Each bidder submits ONE consolidated bid dossier (BID_DOSSIER) carrying a
synthetic-data banner. Idempotent: ``seed_gem_demo_tender`` skips when the
tender already exists, so it can run on databases seeded before this module
existed.
"""
from __future__ import annotations

import logging
from datetime import date

log = logging.getLogger(__name__)

T4_NUMBER = "GEM-DEMO-2026-101"

BANNER = (
    "SYNTHETIC DEMO DATA \u2014 fictional bidder dossier modeled on a public "
    "GeM bid document; not real."
)

EMD_REQUIRED_INR = 15000


# --------------------------------------------------------------------------
# tender requirements (weights sum to 100)
# --------------------------------------------------------------------------

def _tender4_requirements() -> list[dict]:
    return [
        dict(requirement_name="GST Registration", category="STATUTORY",
             description="Bidder must hold an active GST registration.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "GSTN", "identifier_field": "gstin",
                          "require_status": "ACTIVE"},
             threshold="Active GSTIN", expected_value="Status: ACTIVE",
             verification_source="GSTN", weight=15,
             policy_reference="GeM GTC \u00a74.2 (demo)"),
        dict(requirement_name="PAN Verification", category="STATUTORY",
             description="Bidder PAN must be active in Income Tax records.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "PAN_IT", "identifier_field": "pan",
                          "require_status": "ACTIVE"},
             threshold="Active PAN", expected_value="Status: ACTIVE",
             verification_source="PAN_IT", weight=10,
             policy_reference="GeM GTC \u00a74.2 (demo)"),
        dict(requirement_name="Udyam/MSME Registration", category="REGISTRATION",
             description="Valid Udyam registration for the bidding enterprise.",
             mandatory=True, rule_type="REGISTRATION_STATUS",
             rule_config={"source": "UDYAM", "identifier_field": "udyam_number",
                          "require_status": "ACTIVE"},
             threshold="Valid Udyam registration", expected_value="Status: ACTIVE",
             verification_source="UDYAM", weight=10,
             policy_reference="MSME Udyam Reference \u00a73 (demo)"),
        dict(requirement_name="Minimum Average Annual Turnover \u20b928 Lakh",
             category="FINANCIAL",
             description="Average annual turnover of at least \u20b928 lakh over 3 years.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.turnover_inr",
                          "operator": ">=", "value": 2800000},
             threshold="\u20b928 Lakh", expected_value="turnover_inr \u2265 2800000",
             verification_source=None, weight=12,
             policy_reference="GeM Bid Conditions \u00a75 (demo)"),
        dict(requirement_name="Minimum 2 Years Past Experience",
             category="EXPERIENCE",
             description="At least 2 years supplying same/similar category products.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.experience_years",
                          "operator": ">=", "value": 2},
             threshold="2 years", expected_value="experience_years \u2265 2",
             verification_source=None, weight=8,
             policy_reference="GeM Bid Conditions \u00a76 (demo)"),
        dict(requirement_name="Past Performance \u2265 20% of Bid Quantity",
             category="EXPERIENCE",
             description="Supplied \u2265 20% of bid quantity in one of the last 3 FYs.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.past_performance_pct",
                          "operator": ">=", "value": 20},
             threshold="20%", expected_value="past_performance_pct \u2265 20",
             verification_source=None, weight=8,
             policy_reference="GeM Bid Conditions \u00a711 (demo)"),
        dict(requirement_name="OEM Authorization", category="OEM",
             description="Valid OEM authorization declared in the bid dossier.",
             mandatory=True, rule_type="BOOLEAN",
             rule_config={"value_source": "extracted.oem_authorization_valid",
                          "expected": True},
             threshold="Authorized OEM", expected_value="oem_authorization_valid = true",
             verification_source=None, weight=10,
             policy_reference="OEM Authorization Policy \u00a72 (demo)"),
        dict(requirement_name="Make in India Local Content \u2265 50%",
             category="LOCAL_CONTENT",
             description="Class-1 local supplier needs \u226550% local content "
                         "(Class-2 \u226520% remains eligible without preference).",
             mandatory=False, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.local_content_pct",
                          "operator": ">=", "value": 50},
             threshold="\u2265 50%", expected_value="local_content_pct \u2265 50",
             verification_source=None, weight=10,
             policy_reference="Make in India Guidelines \u00a72 (demo)"),
        dict(requirement_name="Earnest Money Deposit \u20b915,000",
             category="FINANCIAL",
             description="EMD of \u20b915,000 deposited in favour of the beneficiary.",
             mandatory=True, rule_type="MINIMUM",
             rule_config={"value_source": "extracted.emd_amount_inr",
                          "operator": ">=", "value": EMD_REQUIRED_INR},
             threshold="\u20b915,000", expected_value="emd_amount_inr \u2265 15000",
             verification_source=None, weight=12,
             policy_reference="GeM Bid EMD Clause (demo)"),
        dict(requirement_name="Blacklisting / Debarment Check", category="INTEGRITY",
             description="Bidder must not be blacklisted or debarred.",
             mandatory=True, rule_type="CUSTOM_RULE",
             rule_config={"expression": (
                 # Never fabricate a clean chit: no BLACKLIST check -> REVIEW_REQUIRED.
                 "('REVIEW_REQUIRED' if ctx.get('verification', {}).get('BLACKLIST') is None "
                 "else ('FAIL' if (ctx['verification']['BLACKLIST'].get('data', {}).get('blacklisted', False) "
                 "or ctx['verification']['BLACKLIST'].get('data', {}).get('debarred', False)) else 'PASS'))"
             )},
             threshold="Not blacklisted / debarred", expected_value="PASS",
             verification_source="BLACKLIST", weight=5,
             policy_reference="Blacklist/Debarment Policy \u00a74 (demo)"),
    ]


# --------------------------------------------------------------------------
# bidder specs (all fictional)
# --------------------------------------------------------------------------

_BIDDERS_T4 = [
    # A — mostly compliant
    dict(slug="apexmed", legal_name="Apex MediSupply Pvt Ltd",
         trade_name="Apex MediSupply", pan="AAHCA2345M",
         gstin="27AAHCA2345M1Z5", udyam="UDYAM-MH-27-0011001",
         cin="U33110MH2021PTC234001",
         address="Plot 14, MIDC Industrial Area, Andheri East, Mumbai 400093",
         email="bids@apexmedisupply.example.in", phone="9820098765",
         incorporation_date="08-02-2021", registration_date="18-04-2022",
         turnover="Rs 42 lakh", turnover_period="FY2022-23 to FY2024-25",
         experience="6 years",
         past_performance="34% of bid quantity supplied in FY2024-25",
         past_performance_client="Demo General Hospital, Mumbai (fictional)",
         oem={"name": "Fresenius Medical Care India Pvt Ltd",
              "authorization": "Yes", "valid_until": "31-12-2027"},
         local_content="62%",
         emd={"amount": "Rs 15,000", "reference": "SBIN202609120045",
              "date": "12-09-2026", "beneficiary": "Demo General Hospital, Mumbai"}),
    # B — some missing / mismatched
    dict(slug="brightcare", legal_name="BrightCare Traders Pvt Ltd",
         trade_name="BrightCare Traders", pan="BBHCB3456N",
         gstin="27BBHCB3456N1Z5", udyam="UDYAM-MH-27-0022002",
         cin="U51900MH2020PTC345002",
         address="Gala 3, MIDC Bhosari, Pune 411026",
         email="tenders@brightcaretraders.example.in", phone="9820087654",
         incorporation_date="15-05-2020", registration_date="02-09-2021",
         turnover="Rs 31 lakh", turnover_period="FY2022-23 to FY2024-25",
         experience="2 years",
         past_performance="22% of bid quantity supplied in FY2024-25",
         past_performance_client="Demo Civil Hospital, Pune (fictional)",
         oem={"name": "Fresenius Medical Care India Pvt Ltd",
              "authorization": "Yes", "valid_until": "31-12-2026"},
         local_content="35%",
         emd={"amount": "Rs 15,000", "reference": "SBIN202609140078",
              "date": "14-09-2026", "beneficiary": "Demo General Hospital, Mumbai"}),
    # C — multiple compliance issues
    dict(slug="carewell", legal_name="CareWell Enterprises Pvt Ltd",
         trade_name="CareWell Enterprises", pan="CCHCC4567P",
         gstin="27CCHCC4567P1Z5", udyam="UDYAM-MH-27-0033003",
         cin="U33110MH2023PTC456003",
         address="Shop 9, APMC Market, Vashi, Navi Mumbai 400703",
         email="carewell.ent@example.in", phone="9820076543",
         incorporation_date="22-01-2023", registration_date="10-06-2023",
         turnover="Rs 19 lakh", turnover_period="FY2023-24 to FY2024-25",
         experience="1 year",
         local_content="12%"),
]


def _t4_dossier(spec: dict) -> tuple:
    """Build the (doc_type, filename, legal_name, sections, banner) dossier."""
    base = {
        "legal_name": spec["legal_name"],
        "address": spec["address"],
        "email": spec["email"],
        "phone": spec["phone"],
    }

    def sec(doc_type: str, **data):
        merged = dict(base)
        merged.update(data)
        return (doc_type, merged)

    sections = [
        sec("PAN_CERTIFICATE", pan=spec["pan"],
            incorporation_date=spec["incorporation_date"]),
        sec("GST_CERTIFICATE", trade_name=spec.get("trade_name", spec["legal_name"]),
            gstin=spec["gstin"], pan=spec["pan"],
            registration_date=spec["registration_date"]),
        sec("UDYAM_CERTIFICATE", udyam=spec["udyam"],
            valid_until=spec.get("udyam_valid_until", "31-12-2030")),
        sec("TURNOVER_CERTIFICATE", turnover=spec["turnover"],
            turnover_period=spec["turnover_period"]),
        sec("EXPERIENCE_CERTIFICATE", experience=spec["experience"]),
    ]
    if spec.get("past_performance"):
        sections.append(sec("PAST_PERFORMANCE_CERTIFICATE",
                            past_performance=spec["past_performance"],
                            past_performance_client=spec.get("past_performance_client", "")))
    if spec.get("oem"):
        oem = spec["oem"]
        sections.append(sec("OEM_AUTHORIZATION", oem_name=oem["name"],
                            oem_authorization=oem["authorization"],
                            valid_until=oem["valid_until"]))
    sections.append(sec("MII_DECLARATION", local_content=spec["local_content"]))
    if spec.get("emd"):
        emd = spec["emd"]
        sections.append(sec("EMD_PAYMENT", emd_amount=emd["amount"],
                            emd_reference=emd["reference"], emd_date=emd["date"],
                            emd_beneficiary=emd["beneficiary"]))
    return ("BID_DOSSIER", f"{spec['slug']}_bid_dossier.pdf",
            spec["legal_name"], sections, BANNER)


def seed_gem_demo_tender(db, officer_id: int) -> dict:
    """Create tender GEM-DEMO-2026-101 + 3 bidders through the full pipeline."""
    from app.models.models import Tender
    from app.seed.seed_data import _create_tender, _seed_bidder

    if db.query(Tender).filter(Tender.tender_number == T4_NUMBER).first() is not None:
        log.info("GeM demo seed skipped: %s already exists", T4_NUMBER)
        return {"tender": T4_NUMBER, "skipped": True}

    tender = _create_tender(
        db, number=T4_NUMBER,
        title="Supply of Haemodialysis Consumables & Accessories (Two-Packet Bid) "
              "\u2014 Synthetic Demo Dataset",
        department="Demo Medical Services Department",
        issue=date(2026, 9, 1), closing=date(2026, 10, 31),
        value=12500000, requirements=_tender4_requirements(),
        created_by=officer_id)
    log.info("GeM demo seed: tender %s created", T4_NUMBER)

    bids = []
    for spec in _BIDDERS_T4:
        bid, _processed, _rows = _seed_bidder(
            db, tender, spec, officer_id, dossier=_t4_dossier(spec))
        bids.append(bid)
    log.info("GeM demo seed: %d bidders seeded", len(bids))
    return {"tender": T4_NUMBER, "bidders": len(bids), "skipped": False}
