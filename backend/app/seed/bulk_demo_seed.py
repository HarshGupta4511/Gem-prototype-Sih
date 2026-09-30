"""Bulk CPCL demo procurement environment: CPCL-DEMO-2026-004 .. 045.

One-shot seeder that turns the application into an already-running
procurement platform for demonstration/jury purposes. It creates ~42
tenders (004-045; 001-003 already exist via the base seed) with realistic
titles, departments, values and varied requirement sets, registers 4-18
bidders per tender, and runs EVERY bidder through the REAL pipeline:

    dossier PDF  ->  process_document  ->  run_verification
    ->  evaluate_bid (rules + scoring + risk)  ->  generate_recommendation

Nothing is hardcoded: compliance scores, risk levels and recommendations
are engine-generated from the seeded evidence. Officer decisions and
verification summaries are then recorded through the existing workflows, so the
dashboard, tenders list, bidder evaluation and bid detail pages are
naturally populated.

Idempotent: existing CPCL-DEMO-2026-* tenders are skipped (never
duplicated) and mock-adapter records are merged by key. Re-running only
fills gaps.

Run once inside the backend container::

    docker compose exec backend python -m app.seed.bulk_demo_seed

The mock ``adapters/mock_data`` records added here are fictional and stay
labelled as mock data; the dossier PDFs carry the DEMO DATA banner.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import date
from pathlib import Path
from string import ascii_uppercase

log = logging.getLogger(__name__)

# Deterministic roster: the same bidder identities (and therefore the same
# mock-adapter keys) are generated on every run / every machine.
SEED = 20260930

MOCK_DIR = Path(__file__).resolve().parent.parent / "adapters" / "mock_data"

ORGANIZATION = "CPCL"
EMD_BENEFICIARY = "Chennai Petroleum Corporation Ltd."

# --------------------------------------------------------------------------
# Tender catalog: (suffix, title, department, value_inr, emd_inr,
#                  req_profile, status, issue_date, closing_date)
# --------------------------------------------------------------------------

_TENDERS: list[tuple] = [
    (4, "Supply of Carbon Steel Pipes and Fittings", "Materials", 32_000_000, 640_000, "goods", "OPEN", date(2026, 8, 20), date(2026, 11, 10)),
    (5, "Procurement of Industrial Valves (Gate, Globe & Ball)", "Materials", 21_000_000, 420_000, "full", "CLOSED", date(2026, 6, 5), date(2026, 8, 20)),
    (6, "Supply of Stainless Steel Fasteners and Gaskets", "Materials", 4_800_000, 96_000, "goods", "OPEN", date(2026, 9, 2), date(2026, 10, 25)),
    (7, "Procurement of HDPE and PVC Piping Materials", "Materials", 14_000_000, 280_000, "goods", "AWARDED", date(2026, 4, 12), date(2026, 7, 2)),
    (8, "Procurement of Electrical Control Panels (LT/HT)", "Electrical", 46_000_000, 920_000, "heavy", "OPEN", date(2026, 8, 28), date(2026, 11, 18)),
    (9, "Supply of Power and Control Cables", "Electrical", 28_000_000, 560_000, "goods", "CLOSED", date(2026, 5, 20), date(2026, 8, 5)),
    (10, "Procurement of Distribution Transformers (11kV/433V)", "Electrical", 61_000_000, 1_220_000, "heavy", "AWARDED", date(2026, 3, 15), date(2026, 6, 10)),
    (11, "Supply of Flameproof Industrial Lighting Fixtures", "Electrical", 9_200_000, 184_000, "goods", "OPEN", date(2026, 9, 5), date(2026, 11, 2)),
    (12, "Procurement of Variable Frequency Drives", "Electrical", 19_000_000, 380_000, "full", "CLOSED", date(2026, 6, 18), date(2026, 9, 2)),
    (13, "Procurement of Mechanical Seals and Spares", "Mechanical", 11_000_000, 220_000, "full", "OPEN", date(2026, 8, 15), date(2026, 10, 30)),
    (14, "Supply of Industrial Bearings and Housings", "Mechanical", 7_600_000, 152_000, "goods", "CLOSED", date(2026, 5, 28), date(2026, 8, 12)),
    (15, "Procurement of Screw-Type Air Compressors", "Mechanical", 24_000_000, 480_000, "full", "AWARDED", date(2026, 4, 2), date(2026, 6, 25)),
    (16, "Supply of Heat Exchanger Tubes and Bundles", "Mechanical", 38_000_000, 760_000, "heavy", "OPEN", date(2026, 9, 1), date(2026, 11, 22)),
    (17, "Procurement of Cooling Tower Spares", "Mechanical", 12_000_000, 240_000, "goods", "CLOSED", date(2026, 6, 25), date(2026, 9, 10)),
    (18, "Supply of Instrumentation Components (Transmitters & Gauges)", "Instrumentation", 16_000_000, 320_000, "full", "OPEN", date(2026, 8, 22), date(2026, 11, 5)),
    (19, "Procurement of Control Valves with Actuators", "Instrumentation", 29_000_000, 580_000, "full", "AWARDED", date(2026, 3, 28), date(2026, 6, 18)),
    (20, "Supply of Gas Detection Systems", "Instrumentation", 13_000_000, 260_000, "services", "CLOSED", date(2026, 6, 10), date(2026, 8, 28)),
    (21, "Procurement of Fire Hydrant and Alarm Systems", "Safety & Fire", 22_000_000, 440_000, "works", "OPEN", date(2026, 8, 30), date(2026, 11, 15)),
    (22, "Supply of Personal Protective Equipment (Annual Contract)", "Safety & Fire", 6_800_000, 136_000, "goods", "CLOSED", date(2026, 5, 15), date(2026, 7, 30)),
    (23, "Procurement of Fire-Fighting Foam and Extinguishers", "Safety & Fire", 5_400_000, 108_000, "goods", "AWARDED", date(2026, 4, 20), date(2026, 7, 8)),
    (24, "Construction of RCC Drainage Network \u2014 Phase II", "Civil", 84_000_000, 1_680_000, "works", "OPEN", date(2026, 7, 25), date(2026, 12, 5)),
    (25, "Supply of Structural Steel for Pipe Racks", "Projects", 52_000_000, 1_040_000, "heavy", "CLOSED", date(2026, 5, 8), date(2026, 8, 15)),
    (26, "Procurement of Ready-Mix Concrete (Annual Rate Contract)", "Civil", 18_000_000, 360_000, "works", "AWARDED", date(2026, 3, 22), date(2026, 6, 5)),
    (27, "Supply of Corrosion Inhibitor Chemicals", "Operations", 15_000_000, 300_000, "services", "OPEN", date(2026, 9, 8), date(2026, 11, 28)),
    (28, "Procurement of Catalyst for Hydrocracker Unit", "Process", 125_000_000, 2_500_000, "heavy", "CLOSED", date(2026, 4, 28), date(2026, 8, 22)),
    (29, "Supply of Lube Oils and Greases (Rate Contract)", "Operations", 8_800_000, 176_000, "goods", "AWARDED", date(2026, 4, 5), date(2026, 6, 28)),
    (30, "Procurement of DM Water Treatment Chemicals", "Utilities", 11_000_000, 220_000, "services", "OPEN", date(2026, 8, 18), date(2026, 10, 28)),
    (31, "Annual Maintenance Contract \u2014 Rotating Equipment", "Maintenance", 34_000_000, 680_000, "services", "OPEN", date(2026, 8, 12), date(2026, 11, 8)),
    (32, "Procurement of Workshop Machinery (Lathe & Milling)", "Maintenance", 26_000_000, 520_000, "full", "CLOSED", date(2026, 6, 2), date(2026, 8, 25)),
    (33, "Supply of Welding Electrodes and Consumables", "Maintenance", 4_200_000, 84_000, "goods", "AWARDED", date(2026, 4, 15), date(2026, 7, 5)),
    (34, "Supply of Laboratory Glassware and Reagents", "Quality Control", 3_600_000, 72_000, "mse", "OPEN", date(2026, 9, 10), date(2026, 11, 30)),
    (35, "Procurement of Online Analyser Systems", "Instrumentation", 41_000_000, 820_000, "full", "CLOSED", date(2026, 5, 25), date(2026, 9, 5)),
    (36, "Hiring of Cranes and Heavy Equipment (Annual Contract)", "Projects", 27_000_000, 540_000, "services", "OPEN", date(2026, 8, 25), date(2026, 11, 12)),
    (37, "Supply of Bitumen in Bulk (Rate Contract)", "Operations", 19_000_000, 380_000, "goods", "CLOSED", date(2026, 6, 15), date(2026, 9, 8)),
    (38, "Procurement of Nitrogen Gas (Bulk Supply)", "Utilities", 9_600_000, 192_000, "services", "AWARDED", date(2026, 4, 8), date(2026, 7, 1)),
    (39, "Annual Rate Contract \u2014 Industrial Painting Works", "Maintenance", 14_000_000, 280_000, "works", "OPEN", date(2026, 9, 3), date(2026, 12, 1)),
    (40, "Supply of Centrifugal Pumps (API 610)", "Mechanical", 56_000_000, 1_120_000, "heavy", "CLOSED", date(2026, 5, 12), date(2026, 8, 18)),
    (41, "Procurement of EOT Cranes for Central Warehouse", "Materials", 31_000_000, 620_000, "full", "AWARDED", date(2026, 3, 30), date(2026, 6, 22)),
    (42, "Supply of Solar Street Lighting Systems", "Electrical", 7_200_000, 144_000, "mse", "OPEN", date(2026, 9, 6), date(2026, 11, 25)),
    (43, "Procurement of Effluent Treatment Plant Spares", "Environment", 17_000_000, 340_000, "full", "CLOSED", date(2026, 6, 8), date(2026, 9, 1)),
    (44, "Supply of Calibrated Safety Relief Valves", "Inspection", 8_400_000, 168_000, "services", "AWARDED", date(2026, 4, 18), date(2026, 7, 12)),
    (45, "Annual Contract \u2014 Calibration of Instruments", "Inspection", 5_800_000, 116_000, "services", "OPEN", date(2026, 9, 12), date(2026, 12, 10)),
]

assert len(_TENDERS) == 42, "catalog must cover suffixes 004..045"


# --------------------------------------------------------------------------
# Requirement templates (weights are normalized to sum to 100)
# --------------------------------------------------------------------------

def _base_req(name, category, description, mandatory, rule_type, rule_config,
              threshold, verification_source, weight):
    return {
        "requirement_name": name,
        "category": category,
        "description": description,
        "mandatory": mandatory,
        "rule_type": rule_type,
        "rule_config": rule_config,
        "threshold": threshold,
        "expected_value": "",
        "verification_source": verification_source,
        "weight": weight,
        "policy_reference": "",
    }


def _inr_label(amount_inr: int) -> str:
    if amount_inr >= 10_000_000:
        cr = amount_inr / 10_000_000
        return f"\u20b9{cr:g} Crore"
    return f"\u20b9{amount_inr / 100_000:g} Lakh"


def _r_gst(w=12):
    return _base_req("GST Registration", "STATUTORY",
                     "Bidder must hold an active GST registration.", True,
                     "REGISTRATION_STATUS",
                     {"source": "GSTN", "identifier_field": "gstin",
                      "require_status": "ACTIVE"},
                     "Active GSTIN", "GSTN", w)


def _r_pan(w=8):
    return _base_req("PAN Verification", "STATUTORY",
                     "Bidder PAN must be active in Income Tax records.", True,
                     "REGISTRATION_STATUS",
                     {"source": "PAN_IT", "identifier_field": "pan",
                      "require_status": "ACTIVE"},
                     "Active PAN", "PAN_IT", w)


def _r_udyam(w=8):
    return _base_req("Udyam/MSME Registration", "REGISTRATION",
                     "Valid Udyam registration for the bidding enterprise.", True,
                     "REGISTRATION_STATUS",
                     {"source": "UDYAM", "identifier_field": "udyam_number",
                      "require_status": "ACTIVE"},
                     "Valid Udyam registration", "UDYAM", w)


def _r_turnover(value_inr, w=12):
    label = _inr_label(value_inr)
    return _base_req(f"Minimum Average Annual Turnover {label}", "FINANCIAL",
                     f"Average annual turnover of at least {label} over the "
                     "last 3 financial years.", True, "MINIMUM",
                     {"value_source": "extracted.turnover_inr",
                      "operator": ">=", "value": value_inr},
                     label, None, w)


def _r_experience(years, w=8):
    return _base_req(f"Minimum {years} Years Past Experience", "EXPERIENCE",
                     f"At least {years} years supplying same/similar category "
                     "goods or services.", True, "MINIMUM",
                     {"value_source": "extracted.experience_years",
                      "operator": ">=", "value": years},
                     f"{years} years", None, w)


def _r_past_perf(pct=20, w=7):
    return _base_req(f"Past Performance \u2265 {pct}% of Bid Quantity",
                     "EXPERIENCE",
                     f"Supplied \u2265 {pct}% of bid quantity in one of the "
                     "last 3 financial years.", True, "MINIMUM",
                     {"value_source": "extracted.past_performance_pct",
                      "operator": ">=", "value": pct},
                     f"{pct}%", None, w)


def _r_oem(w=10):
    return _base_req("OEM Authorization", "OEM",
                     "Valid OEM authorization declared in the bid dossier.",
                     True, "BOOLEAN",
                     {"value_source": "extracted.oem_authorization_valid",
                      "expected": True},
                     "Authorized OEM", None, w)


def _r_mii(pct, mandatory, w=8):
    return _base_req(f"Make in India Local Content \u2265 {pct}%", "LOCAL_CONTENT",
                     "Minimum local content declaration as per the Make in "
                     "India order.", mandatory, "MINIMUM",
                     {"value_source": "extracted.local_content_pct",
                      "operator": ">=", "value": pct},
                     f"\u2265 {pct}%", None, w)


def _r_emd(amount_inr, w=12):
    label = _inr_label(amount_inr)
    return _base_req(f"Earnest Money Deposit {label}", "FINANCIAL",
                     f"EMD of {label} deposited in favour of the beneficiary.",
                     True, "MINIMUM",
                     {"value_source": "extracted.emd_amount_inr",
                      "operator": ">=", "value": amount_inr},
                     label, None, w)


def _r_blacklist(w=5):
    return _base_req("Blacklisting / Debarment Check", "INTEGRITY",
                     "Bidder must not be blacklisted or debarred.", True,
                     "CUSTOM_RULE",
                     {"expression": (
                         "not (ctx['verification'].get('BLACKLIST') or {}).get('data', {}).get('blacklisted', False) "
                         "and not (ctx['verification'].get('BLACKLIST') or {}).get('data', {}).get('debarred', False)"
                     )},
                     "Not blacklisted / debarred", "BLACKLIST", w)


def _r_epfo(w=5):
    return _base_req("EPFO Registration", "STATUTORY",
                     "Bidder must hold an active EPFO establishment code.",
                     True, "REGISTRATION_STATUS",
                     {"source": "EPFO", "identifier_field": "epfo_code",
                      "require_status": "ACTIVE"},
                     "Active EPFO code", "EPFO", w)


def _r_startup(w=4):
    return _base_req("Startup India Recognition (Optional)", "REGISTRATION",
                     "DPIIT-recognized startups may claim applicable relaxations.",
                     False, "DOCUMENT_REQUIRED",
                     {"document_types": ["STARTUP_INDIA_CERTIFICATE"]},
                     "DPIIT recognition", None, w)


def _normalize_weights(reqs: list[dict]) -> None:
    total = sum(r["weight"] for r in reqs)
    acc = 0.0
    for i, r in enumerate(reqs):
        if i < len(reqs) - 1:
            r["weight"] = round(r["weight"] / total * 100, 1)
            acc += r["weight"]
        else:
            r["weight"] = round(100.0 - acc, 1)


def requirements_for(profile: str, emd_inr: int, rng: random.Random) -> list[dict]:
    """Build a varied requirement set for one tender (weights sum to 100)."""
    turnover = rng.choice([2_500_000, 5_000_000, 10_000_000,
                           20_000_000, 50_000_000, 80_000_000])
    exp = rng.choice([2, 3, 5, 7, 10])
    if profile == "full":
        reqs = [_r_gst(12), _r_pan(8), _r_udyam(8), _r_turnover(turnover, 12),
                _r_experience(exp, 8), _r_past_perf(20, 7), _r_oem(10),
                _r_mii(50, False, 8), _r_emd(emd_inr, 12), _r_blacklist(5)]
    elif profile == "works":
        reqs = [_r_gst(12), _r_pan(8), _r_udyam(8),
                _r_turnover(turnover, 14), _r_experience(exp, 10),
                _r_past_perf(20, 8), _r_emd(emd_inr, 12), _r_blacklist(5),
                _r_epfo(6)]
    elif profile == "goods":
        reqs = [_r_gst(14), _r_pan(10), _r_turnover(turnover, 14),
                _r_experience(exp, 10), _r_mii(50, True, 12),
                _r_emd(emd_inr, 14), _r_blacklist(6)]
    elif profile == "services":
        reqs = [_r_gst(12), _r_pan(8), _r_udyam(8), _r_turnover(turnover, 12),
                _r_experience(exp, 10), _r_past_perf(20, 8),
                _r_mii(20, False, 6), _r_emd(emd_inr, 10), _r_blacklist(5),
                _r_startup(4)]
    elif profile == "mse":
        reqs = [_r_gst(12), _r_pan(8), _r_udyam(14),
                _r_turnover(2_500_000, 12), _r_experience(2, 10),
                _r_emd(emd_inr, 12), _r_blacklist(6), _r_mii(20, False, 6)]
    elif profile == "heavy":
        reqs = [_r_gst(10), _r_pan(7), _r_udyam(7),
                _r_turnover(80_000_000, 14), _r_experience(10, 10),
                _r_past_perf(20, 7), _r_oem(8), _r_mii(50, True, 8),
                _r_emd(emd_inr, 10), _r_blacklist(4), _r_epfo(5)]
    else:
        raise ValueError(f"Unknown requirement profile '{profile}'")
    _normalize_weights(reqs)
    return reqs

# --------------------------------------------------------------------------
# Bidder roster generation (deterministic; all identifiers fictional)
# --------------------------------------------------------------------------

_NAME_A = [
    "Shakti", "Vishal", "Narmada", "Satpura", "Vindhya", "Aravalli", "Nilgiri",
    "Deccan", "Konark", "Malwa", "Saurashtra", "Vidarbha", "Chambal", "Kaveri",
    "Godavari", "Tapi", "Sahyadri", "Marathwada", "Kutch", "Chettinad", "Kongu",
    "Dharwad", "Ankleshwar", "Bharuch", "Jamnagar", "Bhavnagar", "Nashik",
    "Solapur", "Kolhapur", "Latur", "Amravati", "Jalgaon", "Sangli", "Erode",
    "Salem", "Karur", "Namakkal", "Dindigul", "Sivakasi", "Hosur", "Vellore",
    "Kanchipuram", "Thoothukudi", "Alappuzha", "Palakkad", "Thrissur", "Kollam",
    "Belagavi", "Tumakuru", "Davangere", "Ballari", "Raichur", "Gulbarga",
    "Vijayapura", "Nandyal", "Kurnool", "Guntur", "Nellore", "Tirupati",
]
_NAME_B = [
    "Industrial", "Engineering", "Process", "Mechanical", "Flow", "Power",
    "Precision", "Heavy", "Fabrication", "Control", "Instrumentation", "Alloy",
    "Steel", "Pumps", "Valve", "Electrical", "Automation", "Thermal",
    "Hydraulic", "Polymer",
]
_NAME_C = [
    "Systems", "Solutions", "Equipment", "Works", "Enterprises", "Technocrats",
    "Associates", "Fabricators", "Services", "Industries",
]
_NAME_SUFFIX = ["Pvt. Ltd.", "LLP"]

_CONTACTS = [
    "R. Ramanathan", "S. Iyer", "N. Kulkarni", "P. Deshmukh", "A. Sharma",
    "V. Menon", "K. Rao", "M. Patel", "D. Singh", "R. Nair", "S. Gupta",
    "P. Joshi", "A. Khan", "V. Reddy", "K. Nair", "T. Das", "B. Mishra",
    "H. Shah", "J. Verma", "L. Pillai",
]
_CONTACT_ROLES = ["Director", "Partner", "Proprietor", "Manager - Contracts"]

# (city, state_name, gst_state_code, state_alpha, pincode)
_CITIES = [
    ("Pune", "Maharashtra", "27", "MH", "411026"),
    ("Mumbai", "Maharashtra", "27", "MH", "400093"),
    ("Nagpur", "Maharashtra", "27", "MH", "440026"),
    ("Chennai", "Tamil Nadu", "33", "TN", "600103"),
    ("Coimbatore", "Tamil Nadu", "33", "TN", "641004"),
    ("Salem", "Tamil Nadu", "33", "TN", "636005"),
    ("Bengaluru", "Karnataka", "29", "KA", "560058"),
    ("Hubli", "Karnataka", "29", "KA", "580030"),
    ("Ahmedabad", "Gujarat", "24", "GJ", "382330"),
    ("Vadodara", "Gujarat", "24", "GJ", "391243"),
    ("Ankleshwar", "Gujarat", "24", "GJ", "393002"),
    ("Faridabad", "Haryana", "06", "HR", "121004"),
    ("Kanpur", "Uttar Pradesh", "09", "UP", "208022"),
    ("Kolkata", "West Bengal", "19", "WB", "700001"),
    ("Hyderabad", "Telangana", "36", "TS", "500026"),
]

# Bidder scenario distribution. Every scenario flows through the real
# engines; the scenario only shapes the evidence / mock portal records.
_SCENARIOS = (
    ("clean", 0.50),      # valid identifiers + full evidence
    ("partial", 0.12),    # valid identifiers; one evidence section omitted
    ("missing", 0.12),    # identifiers absent; only turnover+experience evidence
    ("mismatch", 0.10),   # portal records carry a different legal name
    ("inactive", 0.05),   # portal records exist but are INACTIVE
    ("not_found", 0.05),  # identifiers have no portal record at all
    ("debarred", 0.06),   # valid evidence + mock debarment record
)

_PARTIAL_OMISSIONS = [
    ("PAST_PERFORMANCE_CERTIFICATE",),
    ("MII_DECLARATION",),
    ("OEM_AUTHORIZATION",),
    ("EMD_PAYMENT",),
    ("EXPERIENCE_CERTIFICATE",),
]


def _roll_scenario(rng: random.Random) -> str:
    x = rng.random()
    acc = 0.0
    for name, prob in _SCENARIOS:
        acc += prob
        if x < acc:
            return name
    return "clean"


def _gen_identifiers(rng: random.Random, used_pans: set, city: tuple) -> dict:
    """Fictional but format-valid identifiers (never real)."""
    while True:
        pan = (
            "".join(rng.choice(ascii_uppercase) for _ in range(3))
            + "C"
            + rng.choice(ascii_uppercase)
            + f"{rng.randint(1000, 9999)}"
            + rng.choice(ascii_uppercase)
        )
        if pan not in used_pans:
            used_pans.add(pan)
            break
    gstin = (
        f"{city[2]}{pan}{rng.randint(1, 9)}Z"
        f"{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789')}"
    )
    udyam = f"UDYAM-{city[3]}-{rng.randint(10, 99)}-{rng.randint(1_000_000, 9_999_999):07d}"
    cin = f"U28999{city[3]}20{rng.randint(10, 25):02d}PTC{rng.randint(100_000, 999_999):06d}"
    epfo = (
        f"{city[3]}/{rng.randint(100_000, 999_999):06d}/{rng.randint(1, 999):03d}"
        if rng.random() < 0.40
        else None
    )
    return {"pan": pan, "gstin": gstin, "udyam": udyam, "cin": cin,
            "epfo_code": epfo}


def _gen_bidder(rng: random.Random, tender_idx: int, j: int,
                used_names: set, used_pans: set) -> dict:
    while True:
        a = rng.choice(_NAME_A)
        b = rng.choice(_NAME_B)
        c = rng.choice(_NAME_C)
        suffix = rng.choice(_NAME_SUFFIX)
        legal_name = f"{a} {b} {c} {suffix}"
        if legal_name not in used_names:
            used_names.add(legal_name)
            break
    trade_name = f"{a} {b}"
    city = rng.choice(_CITIES)
    scenario = _roll_scenario(rng)
    identifiers = {} if scenario == "missing" else _gen_identifiers(rng, used_pans, city)
    portal_name = (
        f"{a} Infra Projects Private Limited"
        if scenario == "mismatch" else legal_name
    )
    omit_sections: tuple = ()
    if scenario == "partial":
        omit_sections = rng.choice(_PARTIAL_OMISSIONS)
    plot = rng.randint(3, 210)
    phase = rng.randint(1, 4)
    slug = "".join(ch for ch in trade_name.lower() if ch.isalnum())
    return {
        "key": f"bulk_{tender_idx:02d}_{j:02d}",
        "legal_name": legal_name,
        "trade_name": trade_name,
        "portal_name": portal_name,
        "scenario": scenario,
        "identifiers": identifiers,
        "omit_sections": omit_sections,
        "address": f"Plot {plot}, MIDC Industrial Area Phase {phase}, {city[0]} - {city[4]}",
        "contact_name": f"{rng.choice(_CONTACTS)}, {rng.choice(_CONTACT_ROLES)}",
        "contact_email": f"tenders@{slug}.demo.in",
        "contact_phone": f"+91 98{rng.randint(10_000_000, 99_999_999):08d}",
        "city": city,
        "reg_year": rng.randint(2015, 2023),
    }


def _bidder_count(rng: random.Random) -> int:
    """4-18 bidders per tender, averaging ~8.5, never the same everywhere."""
    return min(18, max(4, int(rng.gauss(8.5, 3.2))))


def _build_roster() -> list[list[dict]]:
    """Deterministic per-tender bidder rosters (stable across runs)."""
    rng = random.Random(SEED)
    used_names: set = set()
    used_pans: set = set()
    roster = []
    for ti in range(len(_TENDERS)):
        n = _bidder_count(rng)
        roster.append([_gen_bidder(rng, ti, j, used_names, used_pans)
                       for j in range(n)])
    return roster


# --------------------------------------------------------------------------
# Mock-adapter data merge (additive, idempotent; fictional records only)
# --------------------------------------------------------------------------

def _load_mock(name: str):
    path = MOCK_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _save_mock(name: str, data) -> None:
    path = MOCK_DIR / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def _merge_mock_data(roster: list[list[dict]]) -> dict:
    """Add fictional portal records for the roster; never touch existing keys."""
    gstn = _load_mock("gstn.json")
    pan_it = _load_mock("pan_it.json")
    udyam = _load_mock("udyam.json")
    epfo = _load_mock("epfo.json")
    blacklist: list = _load_mock("blacklist.json")
    existing_bl = {str(r.get("company_name", "")).strip().upper() for r in blacklist}

    added = {"gstn": 0, "pan_it": 0, "udyam": 0, "epfo": 0, "blacklist": 0}
    for bidders in roster:
        for b in bidders:
            ids = b["identifiers"]
            if not ids:
                continue  # "missing" scenario: no identifiers, no records
            scenario = b["scenario"]
            city = b["city"]
            portal = b["portal_name"]
            status = "INACTIVE" if scenario == "inactive" else "ACTIVE"
            reg_date = f"{b['reg_year']}-{random.Random(hash(b['key']) % (2 ** 31)).randint(1, 12):02d}-{random.Random((hash(b['key']) + 7) % (2 ** 31)).randint(1, 28):02d}"

            if ids["gstin"] not in gstn:
                gstn[ids["gstin"]] = {
                    "gstin": ids["gstin"],
                    "legal_name": portal,
                    "registration_date": reg_date,
                    "state": city[1],
                    "status": status,
                }
                added["gstn"] += 1
            if ids["pan"] not in pan_it:
                pan_it[ids["pan"]] = {
                    "pan": ids["pan"],
                    "name": portal,
                    "itr_filed_upto": 2025,
                    "status": status,
                }
                added["pan_it"] += 1
            if ids["udyam"] not in udyam:
                udyam[ids["udyam"]] = {
                    "udyam_number": ids["udyam"],
                    "enterprise_name": portal,
                    "category": random.Random((hash(b["key"]) + 13) % (2 ** 31)).choice(
                        ["MICRO", "SMALL", "MEDIUM"]),
                    "registration_date": reg_date,
                    "status": status,
                }
                added["udyam"] += 1
            if ids.get("epfo_code") and ids["epfo_code"] not in epfo:
                epfo[ids["epfo_code"]] = {
                    "epfo_code": ids["epfo_code"],
                    "employer_name": portal,
                    "status": status,
                }
                added["epfo"] += 1

            if scenario == "debarred" and b["legal_name"].strip().upper() not in existing_bl:
                blacklist.append({
                    "authority": "CPCL",
                    "company_name": b["legal_name"],
                    "blacklisted": random.Random((hash(b["key"]) + 29) % (2 ** 31)).random() < 0.5,
                    "debarred": True,
                    "period": "2024-06-01 to 2027-05-31",
                    "reason": ("Debarred for submission of unsatisfactory performance "
                               "credentials in tender CPCL-2023-214 (demo record)"),
                })
                existing_bl.add(b["legal_name"].strip().upper())
                added["blacklist"] += 1

    for name, data in (("gstn.json", gstn), ("pan_it.json", pan_it),
                       ("udyam.json", udyam), ("epfo.json", epfo),
                       ("blacklist.json", blacklist)):
        _save_mock(name, data)
    log.info("Mock data merged (added): %s", added)
    return added

# --------------------------------------------------------------------------
# Seeding: tenders + bidders through the real pipeline
# --------------------------------------------------------------------------

def _seed_tender(db, spec: tuple, users: dict, bidders: list[dict],
                 stats: dict) -> None:
    from app.models.models import Tender
    from app.seed.demo_bidder_profiles import (
        build_dossier_sections, demo_banner, register_generated_profile,
    )
    from app.seed.seed_data import _create_tender, _seed_bidder

    (suffix, title, department, value_inr, emd_inr, req_profile,
     status, issue, closing) = spec
    number = f"CPCL-DEMO-2026-{suffix:03d}"
    if db.query(Tender).filter(Tender.tender_number == number).first() is not None:
        stats["tenders_skipped"] += 1
        log.info("Bulk seed: %s already exists; skipped", number)
        return

    officer = users["officer@demo.cpcl.in"]
    rng = random.Random(SEED + suffix)  # per-tender requirement variation
    tender_type = rng.choice(["OPEN", "LIMITED", "OPEN"])
    bid_type = rng.choice(["SINGLE", "TWO_PACKET", "SINGLE"])
    tender = _create_tender(
        db, number=number, title=title, department=department,
        issue=issue, closing=closing, value=value_inr,
        requirements=requirements_for(req_profile, emd_inr, rng),
        created_by=officer.id, tender_type=tender_type, bid_type=bid_type,
        emd_amount_inr=emd_inr,
        delivery_period=f"{rng.choice([30, 45, 60, 90, 120, 180])} days",
        place_of_delivery="CPCL Refinery, Manali, Chennai",
    )
    if status != "OPEN":
        tender.status = status
        db.commit()
    db.refresh(tender)
    stats["tenders_created"] += 1
    log.info("Bulk seed: tender %s created (%s, %d bidders)",
             number, status, len(bidders))

    for b in bidders:
        key = b["key"]
        register_generated_profile(key, {
            "legal_name": b["legal_name"],
            "trade_name": b["trade_name"],
            "identifiers": dict(b["identifiers"]),
            "address": b["address"],
            "contact_name": b["contact_name"],
            "contact_email": b["contact_email"],
            "contact_phone": b["contact_phone"],
            "omit_evidence": b["scenario"] == "missing",
            "omit_sections": b["omit_sections"],
        })
        sections = build_dossier_sections(
            tender.requirements, key, emd_beneficiary=EMD_BENEFICIARY)
        dossier = ("BID_DOSSIER", f"{key}_dossier.pdf", b["legal_name"],
                   sections, demo_banner())
        ids = b["identifiers"]
        specs = {
            "legal_name": b["legal_name"],
            "trade_name": b["trade_name"],
            "pan": ids.get("pan"),
            "gstin": ids.get("gstin"),
            "udyam": ids.get("udyam"),
            "cin": ids.get("cin"),
            "address": b["address"],
            "email": b["contact_email"],
            "phone": b["contact_phone"],
        }
        try:
            bid, processed, _rows = _seed_bidder(
                db, tender, specs, officer.id, dossier=dossier)
        except Exception:  # noqa: BLE001 - one bad bidder never kills the seed
            log.exception("Bulk seed: bidder failed %s (%s)",
                          b["legal_name"], b["scenario"])
            stats["bidders_failed"] += 1
            continue
        stats["bidders_created"] += 1
        stats["documents_created"] += 1
        stats["documents_processed"] += processed
        stats["new_tender_ids"].add(tender.id)
        stats["new_bid_ids"].append(bid.id)


# --------------------------------------------------------------------------
# Officer decisions (through the real officer workflow)
# --------------------------------------------------------------------------

def _record_decisions(db, users: dict, stats: dict) -> None:
    from app.api.officer import officer_decision
    from app.models.models import BidSubmission, ComplianceResult, Tender
    from app.models.models import OfficerDecision
    from app.schemas.schemas import DecisionRequest

    officer = users["officer@demo.cpcl.in"]
    rng = random.Random(SEED + 777)
    tender_ids = list(stats["new_tender_ids"])
    if not tender_ids:
        return
    tenders = {t.id: t for t in
               db.query(Tender).filter(Tender.id.in_(tender_ids)).all()}
    bids = db.query(BidSubmission).filter(
        BidSubmission.tender_id.in_(tender_ids)).all()

    # Awarded tenders: the highest-compliance LOW-risk bid wins (L1).
    top_bid_by_tender: dict[int, int] = {}
    for tid in tender_ids:
        if tenders[tid].status != "AWARDED":
            continue
        scored = [(b.compliance_score or 0, b.id) for b in bids
                  if b.tender_id == tid and (b.compliance_score or 0) > 0
                  and (b.risk_level or "LOW") == "LOW"]
        if scored:
            top_bid_by_tender[tid] = max(scored)[1]

    for bid in bids:
        db.refresh(bid)
        score = bid.compliance_score or 0
        risk = bid.risk_level or "UNKNOWN"
        statuses = {r.status for r in db.query(ComplianceResult).filter(
            ComplianceResult.bid_id == bid.id).all()}
        decision = reason = None
        x = rng.random()

        if top_bid_by_tender.get(bid.tender_id) == bid.id:
            decision = OfficerDecision.APPROVE
            reason = (f"Approved as L1 bidder: highest evaluated compliance "
                      f"score {score:.1f}% with {risk} risk.")
        elif score >= 85 and risk == "LOW":
            if x < 0.65:
                decision = OfficerDecision.APPROVE
                reason = (f"Compliant bid ({score:.1f}%) with low risk; "
                          f"approved for award consideration.")
        elif score < 50 or risk == "CRITICAL":
            if x < 0.60:
                decision = OfficerDecision.REJECT
                reason = (f"Rejected: compliance {score:.1f}% / risk {risk} "
                          f"below acceptable thresholds.")
            elif x < 0.75:
                decision = OfficerDecision.ESCALATE
                reason = (f"Escalated: compliance {score:.1f}% with {risk} "
                          f"risk requires higher-authority review.")
        elif "MISMATCH" in statuses:
            if x < 0.35:
                decision = OfficerDecision.REQUEST_CLARIFICATION
                reason = ("Clarification sought on verification mismatches "
                          "in statutory records.")
            elif x < 0.50:
                decision = OfficerDecision.ESCALATE
                reason = "Escalated due to unresolved verification mismatches."
        elif statuses & {"MISSING", "REVIEW_REQUIRED", "FAIL", "EXPIRED"}:
            if x < 0.28:
                decision = OfficerDecision.REQUEST_CLARIFICATION
                reason = ("Clarification sought on missing/incomplete "
                          "evidence.")
            elif x < 0.40:
                decision = OfficerDecision.ESCALATE
                reason = "Escalated for review of incomplete documentation."
            elif x < 0.50 and score >= 70:
                decision = OfficerDecision.APPROVE
                reason = (f"Approved with recorded observations "
                          f"({score:.1f}% compliance).")
        else:
            if x < 0.35:
                decision = OfficerDecision.APPROVE
                reason = f"Approved ({score:.1f}% compliance, {risk} risk)."
            elif x < 0.48:
                decision = OfficerDecision.REQUEST_CLARIFICATION
                reason = "Minor clarification sought before award."
            elif x < 0.56:
                decision = OfficerDecision.ESCALATE
                reason = "Escalated for committee review."

        if decision is None:
            stats["decisions"]["PENDING"] += 1
            continue
        try:
            officer_decision(
                DecisionRequest(bid_id=bid.id, decision=decision, reason=reason),
                db, officer)
            stats["decisions"][decision.value] += 1
        except Exception:  # noqa: BLE001
            log.exception("Bulk seed: decision failed for bid %s", bid.id)
            stats["decisions"]["PENDING"] += 1


# --------------------------------------------------------------------------
# Verification summaries (through the real summary workflow)
# --------------------------------------------------------------------------

_OBSERVATIONS = [
    "Turnover certificate covers FY 2021-22 to FY 2023-24; figures cross-checked against the extracted summary.",
    "GST registration verified active; legal name matches the bid dossier.",
    "Experience certificate lists relevant supply orders; past performance meets the threshold.",
    "EMD payment reference verified in the dossier; beneficiary matches the tender conditions.",
    "OEM authorization letter is valid through the delivery period.",
    "Local content declaration reviewed; supporting cost break-up not attached.",
    "PAN and Udyam records verified; enterprise category noted for purchase preference.",
    "Statutory verification completed across applicable mock sources.",
]


def _seed_reports(db, users: dict, stats: dict) -> None:
    from collections import Counter
    from app.services import verification_summary_service as vss

    officer = users["officer@demo.cpcl.in"]
    rng = random.Random(SEED + 4242)
    for bid_id in stats["new_bid_ids"]:
        # Only DRAFT summaries can move forward.
        try:
            if vss.summary_lifecycle(db, bid_id)["status"] != "DRAFT":
                continue
        except Exception:  # noqa: BLE001
            continue
        if rng.random() >= 0.55:
            continue
        try:
            if rng.random() < 0.30:
                vss.add_observation(
                    db, bid_id, officer, rng.choice(_OBSERVATIONS))
            vss.generate_summary(db, bid_id, officer)
        except Exception:  # noqa: BLE001
            log.exception("Bulk seed: summary generate failed for bid %s", bid_id)
            continue
        if rng.random() < 0.40:
            try:
                vss.regenerate_summary(db, bid_id, officer)
            except Exception:  # noqa: BLE001
                continue
    # True distribution, derived from the audit-backed lifecycle.
    dist: Counter = Counter()
    for bid_id in stats["new_bid_ids"]:
        try:
            dist[vss.summary_lifecycle(db, bid_id)["status"]] += 1
        except Exception:  # noqa: BLE001
            pass
    stats["reports"] = dict(dist)


# --------------------------------------------------------------------------
# Final acceptance report
# --------------------------------------------------------------------------

def _final_report(db, stats: dict) -> dict:
    from collections import Counter
    from app.models.models import (
        BidSubmission, ComplianceResult, Document, RiskAssessment, Tender,
        VerificationCheck,
    )

    report: dict = {
        "tenders_created": stats["tenders_created"],
        "tenders_skipped": stats["tenders_skipped"],
        "tender_reference_range": "CPCL-DEMO-2026-001 .. CPCL-DEMO-2026-045",
    }
    demo_tenders = db.query(Tender).filter(
        Tender.tender_number.like("CPCL-DEMO-2026-%")).all()
    report["total_demo_tenders"] = len(demo_tenders)
    numbers = sorted(t.tender_number for t in demo_tenders)
    report["references_sequential"] = (
        numbers == [f"CPCL-DEMO-2026-{i:03d}" for i in range(1, len(numbers) + 1)]
    )
    report["no_duplicate_references"] = len(set(numbers)) == len(numbers)

    bids = db.query(BidSubmission).filter(
        BidSubmission.tender.has(
            Tender.tender_number.like("CPCL-DEMO-2026-%"))).all()
    per_tender = Counter(b.tender_id for b in bids)
    report["total_bidders"] = len(bids)
    report["min_bidders_per_tender"] = min(per_tender.values()) if per_tender else 0
    report["max_bidders_per_tender"] = max(per_tender.values()) if per_tender else 0
    report["over_25_bidders"] = sum(1 for c in per_tender.values() if c > 25)

    docs = db.query(Document).filter(
        Document.bid_id.in_([b.id for b in bids])).all()
    report["total_documents"] = len(docs)
    report["processed_documents"] = sum(
        1 for d in docs if d.processing_status == "PROCESSED")
    report["bidders_without_documents"] = sum(
        1 for b in bids
        if not any(d.bid_id == b.id for d in docs))

    comp = db.query(ComplianceResult).filter(
        ComplianceResult.bid_id.in_([b.id for b in bids])).all()
    report["compliance_evaluations"] = len({r.bid_id for r in comp})
    report["bids_with_score"] = sum(1 for b in bids if b.compliance_score is not None)

    checks = db.query(VerificationCheck).filter(
        VerificationCheck.bid_id.in_([b.id for b in bids])).all()
    report["verification_checks"] = len(checks)
    report["verification_by_status"] = dict(
        Counter(c.verification_status for c in checks))

    risks = db.query(RiskAssessment).filter(
        RiskAssessment.bid_id.in_([b.id for b in bids])).all()
    report["risk_distribution"] = dict(Counter(r.risk_level for r in risks))

    report["officer_decisions"] = dict(stats["decisions"])
    report["verification_summaries"] = dict(stats["reports"])
    report["bidders_failed"] = stats["bidders_failed"]
    report["mock_records_added"] = stats["mock_added"]
    return report


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def seed_bulk_demo(db, *, decisions: bool = True, reports: bool = True) -> dict:
    """Create the bulk demo environment. Returns the acceptance report."""
    from app.seed.seed_data import _seed_users

    users = _seed_users(db)
    roster = _build_roster()
    stats = {
        "tenders_created": 0,
        "tenders_skipped": 0,
        "bidders_created": 0,
        "bidders_failed": 0,
        "documents_created": 0,
        "documents_processed": 0,
        "new_tender_ids": set(),
        "new_bid_ids": [],
        "decisions": {"APPROVE": 0, "REJECT": 0, "ESCALATE": 0,
                      "REQUEST_CLARIFICATION": 0, "PENDING": 0},
        "reports": {"DRAFT": 0, "GENERATED": 0, "SENT": 0, "RECEIVED": 0,
                    "UNDER_REVIEW": 0, "DECISION": 0},
        "mock_added": _merge_mock_data(roster),
    }
    for ti, spec in enumerate(_TENDERS):
        _seed_tender(db, spec, users, roster[ti], stats)
    if decisions:
        _record_decisions(db, users, stats)
    if reports:
        _seed_reports(db, users, stats)
    return _final_report(db, stats)


def main() -> None:
    import time
    from app.database.base import Base
    from app.database.session import SessionLocal, engine

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        started = time.time()
        report = seed_bulk_demo(db)
        report["elapsed_seconds"] = round(time.time() - started, 1)
        print(json.dumps(report, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
