"""Variety demonstration dataset seeder — DEMO DATA, fully synthetic.

A *separate* multi-tender demo dataset that exercises the existing BIDWISE
architecture end-to-end with naturally varied outcomes:

- 6 tenders (``VAR-DEMO-2026-01`` … ``VAR-DEMO-2026-06``), 7 bidders each,
  drawn from 15 fictional companies. Several companies bid in multiple
  tenders; recurring pairs co-participate repeatedly.
- Different requirement subsets / weights per tender (weights always total
  100), built from the existing 10-document catalogue and the existing rule
  types (``REGISTRATION_STATUS``, ``MINIMUM``, ``MATCH``, ``DATE_VALIDITY``,
  ``CUSTOM_RULE``). No new requirement system, no engine changes.
- Real generated PDF evidence documents through the shared
  ``generate_dossier_pdf`` template path (every page carries the
  ``SAMPLE — FOR DEMONSTRATION ONLY`` footer). Intentional mismatch
  scenarios put the actual conflicting values inside the documents.
- Additive mock registry fixtures (``pan_it.json`` / ``gstn.json`` /
  ``udyam.json`` / ``mca21.json`` / ``epfo.json`` / ``blacklist.json``)
  keyed by fresh fictional identifiers that collide with nothing real and
  nothing used by the other demo datasets.

Nothing is hardcoded: compliance scores come from
:func:`app.services.compliance_service.evaluate_bid`, risk levels from the
risk engine inside that same call, recommendations from
:func:`app.services.recommendation_service.generate_recommendation`, and
integrity findings from the existing integrity detectors (run by the
officer from the Integrity page, as with the other datasets).

The dataset is engineered so the existing engines naturally produce:

- varied compliance scores (a fully compliant bidder per tender reaches
  ~100; threshold failures subtract the failed requirement's weight),
- varied risk levels (clean → LOW; mismatches/expiry → MEDIUM;
  blacklist / multiple serious issues → HIGH),
- varied recommendations (comparative per tender),
- integrity signals: RECURRING_BIDDER_COHORT (several pairs),
  REPEATED_PARTICIPATION, DOCUMENT_IDENTITY_RELATIONSHIP (shared PAN),
  CROSS_BID_DOCUMENT_SIMILARITY (near-identical experience certificates),
  REPEATED_HISTORICAL_ANOMALIES.

Isolation: tender numbers use the ``VAR-DEMO-`` prefix, company legal
names / identifiers are distinct from the Apex / Vertex / Nova / PrimeTech
demo profiles, the GeM demo tender and the ``INT-DEMO-*`` integrity
dataset. :func:`reset_variety_demo_dataset` deletes only the six
``VAR-DEMO-*`` tenders (via ``delete_tender``, which cascades) plus any
integrity findings referencing them. Mock fixture records added here are
left in place on reset (same documented behaviour as the integrity demo
dataset): they are additive and keyed by fictional identifiers.

Idempotency: :func:`load_variety_demo_dataset` is a no-op when the six
tenders already exist.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import date
from pathlib import Path

# Guards against concurrent dataset loads (double-clicks / retries). Only one
# load runs at a time per process; a second concurrent call gets
# {"already_running": True} instead of racing the idempotency check.
_LOAD_LOCK = threading.Lock()

VARIETY_TENDER_NUMBERS = [
    "VAR-DEMO-2026-01",
    "VAR-DEMO-2026-02",
    "VAR-DEMO-2026-03",
    "VAR-DEMO-2026-04",
    "VAR-DEMO-2026-05",
    "VAR-DEMO-2026-06",
]

MOCK_DATA_DIR = Path(__file__).resolve().parent.parent / "adapters" / "mock_data"

# ---------------------------------------------------------------------------
# Fictional companies. Every identifier is structurally valid but invented.
# Contact details are unique per company so the shared-contact detector
# stays silent; only the engineered signals fire.
#
# Fixture-level fates (per company — the mock registry cannot vary by
# tender, so scenarios are designed around one fate per company):
# - aarohan:  GSTIN fixture CANCELLED (GST -> EXPIRED); PAN absent (NOT_FOUND)
# - narmada:  GSTIN fixture CANCELLED (GST -> EXPIRED);
#             MCA21 fixture carries a different company name (-> MISMATCH)
# - tapi:     UDYAM fixture carries a different enterprise name (-> MISMATCH)
# - mahanadi: EPFO fixture SUSPENDED (-> REVIEW_REQUIRED)
# - brightline: EPFO fixture SUSPENDED (-> REVIEW_REQUIRED)
# - crestline: dual-PAN evidence (PAN card shows X, GST certificate shows Y)
# - nimbus_a / nimbus_b: share one PAN under different legal names
# ---------------------------------------------------------------------------

SHARED_NIMBUS_PAN = "NNHHF5505N"
CRESTLINE_PAN_X = "CCCLL7707C"   # bidder row + PAN certificate
CRESTLINE_PAN_Y = "CCDDY8808D"   # GST certificate
CRESTLINE_GSTIN_Y = "27CCDDY8808D1Z5"
GODAVARI_PAN_Y = "GGDDY9919D"    # Tender-1-only GST-certificate PAN (override)
GODAVARI_GSTIN_Y = "27GGDDY9919D1Z5"
KESTREL_PAN_Y = "KKEEY3313Y"     # Tender-6-only GST-certificate PAN (override)
KESTREL_GSTIN_Y = "27KKEEY3313Y1Z5"


def _gstin(pan: str) -> str:
    return f"27{pan}1Z5"


COMPANIES: dict[str, dict] = {
    "aarohan": {
        "legal_name": "Aarohan Industries",
        "pan": "AAIIN1101A",
        "gstin": _gstin("AAIIN1101A"),
        "udyam": "UDYAM-MH-27-0001101",
        "cin": "U28999MH2019PTC000101",
        "epfo_code": "MH/900101/001",
        "address": "Plot 8, MIDC Industrial Area, Waluj, Aurangabad - 431136",
        "email": "bids@aarohan-industries-demo.in",
        "phone": "+91 98220 51001",
        "contact_name": "D. Joshi",
        "incorporation_date": "09-05-2019",
        "auditor": "Waluj Audit Associates",
        "iso_no": "ISO-2021-11011",
        "iso_valid_from": "2021-04-01",
        "iso_valid_until": "2028-03-31",
        "iso_scope": "Design, fabrication and supply of process skids and structural steelwork for chemical plants",
        "experience": (
            "7 years of experience supplying process skids and fabrication "
            "work to chemical plants. Executed 14 orders worth Rs 3.1 crore."
        ),
    },
    "meridian": {
        "legal_name": "Meridian Systems",
        "pan": "MMDDS2202M",
        "gstin": _gstin("MMDDS2202M"),
        "udyam": "UDYAM-MH-27-0002202",
        "cin": "U29299MH2017PTC000202",
        "epfo_code": "MH/900202/002",
        "address": "Gala 4, MIDC Bhosari, Pune - 411026",
        "email": "tenders@meridian-systems-demo.in",
        "phone": "+91 98220 51002",
        "contact_name": "S. Kulkarni",
        "incorporation_date": "22-08-2017",
        "auditor": "Bhosari Audit Circle",
        "iso_no": "ISO-2021-22022",
        "iso_valid_from": "2021-04-01",
        "iso_valid_until": "2027-09-30",
        "iso_scope": "Design, manufacture and supply of industrial automation panels and control systems",
        "experience": (
            "8 years of experience in industrial automation panels and "
            "control systems. Executed 21 orders worth Rs 4.6 crore."
        ),
    },
    "kestrel": {
        "legal_name": "Kestrel Enterprises",
        "pan": "KKEEN3303K",
        "gstin": _gstin("KKEEN3303K"),
        "udyam": "UDYAM-MH-27-0003303",
        "cin": "U29199MH2016PTC000303",
        "epfo_code": "MH/900303/003",
        "address": "Plot 17, MIDC Chakan Phase II, Pune - 410501",
        "email": "contracts@kestrel-enterprises-demo.in",
        "phone": "+91 98220 51003",
        "contact_name": "R. Deshmukh",
        "incorporation_date": "11-03-2016",
        "auditor": "Chakan Financial Auditors",
        "iso_no": "ISO-2021-33033",
        "iso_valid_from": "2021-04-01",
        "iso_valid_until": "2028-12-31",
        "iso_scope": "Manufacture and supply of pumps, valves and flow control equipment",
        "experience": (
            "12 years of experience manufacturing pumps, valves and flow "
            "control assemblies. Executed 38 orders worth Rs 9.2 crore."
        ),
    },
    "vardaan": {
        "legal_name": "Vardaan Technologies",
        "pan": "VVTTN4404V",
        "gstin": _gstin("VVTTN4404V"),
        "udyam": "UDYAM-MH-27-0004404",
        "cin": "U29399MH2018PTC000404",
        "epfo_code": "MH/900404/004",
        "address": "Shop 12, APMC Market Yard, Navi Mumbai - 400705",
        "email": "sales@vardaan-technologies-demo.in",
        "phone": "+91 98220 51004",
        "contact_name": "P. Shah",
        "incorporation_date": "14-07-2018",
        "auditor": "Vashi Audit Associates",
        "iso_no": "ISO-2021-44044",
        "iso_valid_from": "2021-04-01",
        "iso_valid_until": "2029-02-28",
        "iso_scope": "Trading of industrial valves, fittings and pipeline accessories",
        "experience": (
            "9 years of experience trading industrial valves and fittings. "
            "Executed 26 orders worth Rs 5.4 crore."
        ),
    },
    "nimbus_a": {
        # Shares SHARED_NIMBUS_PAN with nimbus_b under a different legal
        # name -> DOCUMENT_IDENTITY_RELATIONSHIP.
        "legal_name": "Nimbus Heavy Fab Pvt. Ltd.",
        "pan": SHARED_NIMBUS_PAN,
        "gstin": "27" + SHARED_NIMBUS_PAN + "1Z5",
        "udyam": "UDYAM-MH-27-0005505",
        "cin": "U28999MH2020PTC000505",
        "epfo_code": "MH/900505/005",
        "address": "Plot 29, MIDC Ranjangaon, Pune - 412220",
        "email": "hello@nimbus-heavyfab-demo.in",
        "phone": "+91 98220 51005",
        "contact_name": "A. Pawar",
        "incorporation_date": "05-02-2020",
        "auditor": "Ranjangaon Audit Group",
        "iso_no": "ISO-2022-55055",
        "iso_valid_from": "2022-04-01",
        "iso_valid_until": "2028-03-31",
        "iso_scope": "Heavy fabrication of pressure vessels and structural steel assemblies",
        "experience": (
            "6 years of experience in heavy fabrication of pressure vessels. "
            "Executed 11 orders worth Rs 2.8 crore."
        ),
    },
    "nimbus_b": {
        "legal_name": "Nimbus Fabrication Works",
        "pan": SHARED_NIMBUS_PAN,
        "gstin": "29" + SHARED_NIMBUS_PAN + "1Z5",
        "udyam": "UDYAM-KA-29-0005506",
        "cin": "U28999KA2021PTC000506",
        "epfo_code": "MH/900506/006",
        "address": "Plot 3, KIADB Industrial Area, Bengaluru - 562157",
        "email": "contact@nimbus-fabworks-demo.in",
        "phone": "+91 98220 51006",
        "contact_name": "K. Rao",
        "incorporation_date": "19-06-2021",
        "auditor": "Bengaluru Audit Circle",
        "iso_no": "ISO-2022-55056",
        "iso_valid_from": "2022-04-01",
        "iso_valid_until": "2027-06-30",
        "iso_scope": "Fabrication of structural steel and industrial sheet-metal assemblies",
        "experience": (
            "5 years of experience in structural fabrication for warehouses. "
            "Executed 9 orders worth Rs 1.9 crore."
        ),
    },
    "brightline": {
        "legal_name": "Brightline Tools Co.",
        "pan": "BBLLE6606B",
        "gstin": _gstin("BBLLE6606B"),
        "udyam": "UDYAM-MH-27-0006606",
        "cin": "U28999MH2019PTC000606",
        "epfo_code": "MH/900606/007",
        "address": "Gala 9, MIDC Andheri East, Mumbai - 400093",
        "email": "hello@brightline-tools-demo.in",
        "phone": "+91 98220 51007",
        "contact_name": "N. Mehta",
        "incorporation_date": "17-02-2019",
        "auditor": "Andheri Audit Associates",
        "iso_no": "ISO-2021-66066",
        "iso_valid_from": "2021-04-01",
        "iso_valid_until": "2028-03-31",
        "iso_scope": "Supply of cutting tools and machine tool accessories",
        "experience": (
            "7 years of experience supplying cutting tools and machine "
            "accessories. Executed 19 orders worth Rs 3.8 crore."
        ),
    },
    "crestline": {
        # Dual-PAN evidence: the PAN certificate shows CRESTLINE_PAN_X
        # (also the bidder-row PAN) while the GST certificate shows
        # CRESTLINE_PAN_Y. Both are valid fictional PANs with ACTIVE mock
        # records, so verification passes but the cross-document mismatch
        # is genuine and visible.
        "legal_name": "Crestline Valves Ltd.",
        "pan": CRESTLINE_PAN_X,
        "gstin": CRESTLINE_GSTIN_Y,
        "udyam": "UDYAM-MH-27-0007707",
        "cin": "U29199MH2018PTC000707",
        "epfo_code": "MH/900707/008",
        "address": "Plot 44, MIDC Waluj, Aurangabad - 431136",
        "email": "bids@crestline-valves-demo.in",
        "phone": "+91 98220 51008",
        "contact_name": "V. Patil",
        "incorporation_date": "28-09-2018",
        "auditor": "Waluj Audit Associates",
        "iso_no": "ISO-2021-77077",
        "iso_valid_from": "2021-04-01",
        "iso_valid_until": "2027-12-31",
        "iso_scope": "Manufacture and supply of industrial valves for water utilities",
        "experience": (
            "3 years of experience supplying industrial valves to water "
            "utilities. Executed 6 orders worth Rs 1.1 crore."
        ),
    },
    "godavari": {
        "legal_name": "Godavari Forge Pvt. Ltd.",
        "pan": "GGDDR9909G",
        "gstin": _gstin("GGDDR9909G"),
        "udyam": "UDYAM-MH-27-0009909",
        "cin": "U28999MH2017PTC000909",
        "epfo_code": "MH/900909/009",
        "address": "Plot 61, MIDC Shendra, Aurangabad - 431154",
        "email": "tenders@godavari-forge-demo.in",
        "phone": "+91 98220 51009",
        "contact_name": "S. Reddy",
        "incorporation_date": "03-12-2017",
        "auditor": "Shendra Audit Circle",
        "iso_no": "ISO-2021-99099",
        "iso_valid_from": "2021-04-01",
        "iso_valid_until": "2028-03-31",
        "iso_scope": "Manufacture and supply of forged flanges and pipe fittings",
        "experience": (
            "6 years of experience in forged flanges and fittings. "
            "Executed 13 orders worth Rs 2.6 crore."
        ),
    },
    "kaveri": {
        "legal_name": "Kaveri Pumps Ltd.",
        "pan": "KKAAV1010K",
        "gstin": _gstin("KKAAV1010K"),
        "udyam": "UDYAM-MH-27-0010101",
        "cin": "U29199MH2019PTC001001",
        "epfo_code": "MH/901010/010",
        "address": "Plot 12, MIDC Malegaon, Sinnar, Nashik - 422113",
        "email": "contracts@kaveri-pumps-demo.in",
        "phone": "+91 98220 51010",
        "contact_name": "M. Nair",
        "incorporation_date": "25-04-2019",
        "auditor": "Nashik Audit Associates",
        "iso_no": "ISO-2022-10101",
        "iso_valid_from": "2022-04-01",
        "iso_valid_until": "2029-01-15",
        "iso_scope": "Manufacture and supply of industrial pumps and pumping systems",
        "experience": (
            "5 years of experience manufacturing centrifugal pumps. "
            "Executed 10 orders worth Rs 2.2 crore."
        ),
    },
    "narmada": {
        "legal_name": "Narmada Systems Pvt. Ltd.",
        "pan": "NNRMM2020N",
        "gstin": _gstin("NNRMM2020N"),
        "udyam": "UDYAM-MH-27-0020202",
        "cin": "U29299MH2020PTC002002",
        "epfo_code": "MH/902020/011",
        "address": "Plot 5, MIDC Satpur, Nashik - 422007",
        "email": "bids@narmada-systems-demo.in",
        "phone": "+91 98220 51011",
        "contact_name": "J. Singh",
        "incorporation_date": "16-01-2020",
        "auditor": "Satpur Audit Group",
        "iso_no": "ISO-2022-20202",
        "iso_valid_from": "2022-04-01",
        "iso_valid_until": "2028-03-31",
        "iso_scope": "Design and supply of water treatment skids and systems",
        "experience": (
            "6 years of experience in water treatment skids. "
            "Executed 12 orders worth Rs 2.9 crore."
        ),
    },
    "tapi": {
        "legal_name": "Tapi Engineering Works",
        "pan": "TTAAP3030T",
        "gstin": _gstin("TTAAP3030T"),
        "udyam": "UDYAM-MH-27-0030303",
        "cin": "U28999MH2021PTC003003",
        "epfo_code": "MH/903030/012",
        "address": "Plot 77, MIDC Bhusawal, Jalgaon - 425201",
        "email": "hello@tapi-engg-demo.in",
        "phone": "+91 98220 51012",
        "contact_name": "R. Khan",
        "incorporation_date": "08-08-2021",
        "auditor": "Jalgaon Audit Circle",
        "iso_no": "ISO-2022-30303",
        "iso_valid_from": "2022-04-01",
        "iso_valid_until": "2027-09-30",
        "iso_scope": "Fabrication of storage tanks and structural steelwork",
        "experience": (
            "4 years of experience in fabrication of storage tanks. "
            "Executed 8 orders worth Rs 1.6 crore."
        ),
    },
    "sabarmati": {
        "legal_name": "Sabarmati Industrial Co.",
        "pan": "SSBBM4040S",
        "gstin": _gstin("SSBBM4040S"),
        "udyam": "UDYAM-GJ-24-0040404",
        "cin": "U28999GJ2018PTC004004",
        "epfo_code": "MH/904040/013",
        "address": "Plot 90, GIDC Vatva Phase II, Ahmedabad - 382445",
        "email": "tenders@sabarmati-industrial-demo.in",
        "phone": "+91 98220 51013",
        "contact_name": "H. Patel",
        "incorporation_date": "30-06-2018",
        "auditor": "Vatva Audit Associates",
        "iso_no": "ISO-2021-40404",
        "iso_valid_from": "2021-04-01",
        "iso_valid_until": "2028-06-30",
        "iso_scope": "Supply of material handling equipment and industrial components",
        "experience": (
            "9 years of experience supplying material handling equipment. "
            "Executed 22 orders worth Rs 4.1 crore."
        ),
    },
    "mahanadi": {
        "legal_name": "Mahanadi Equipments Pvt. Ltd.",
        "pan": "MMHHN5050M",
        "gstin": _gstin("MMHHN5050M"),
        "udyam": "UDYAM-OD-21-0050505",
        "cin": "U29399OD2019PTC005005",
        "epfo_code": "MH/905050/014",
        "address": "Plot 23, Industrial Estate, Rourkela - 769004",
        "email": "bids@mahanadi-equipments-demo.in",
        "phone": "+91 98220 51014",
        "contact_name": "B. Das",
        "incorporation_date": "12-11-2019",
        "auditor": "Rourkela Audit Circle",
        "iso_no": "ISO-2022-50505",
        "iso_valid_from": "2022-04-01",
        "iso_valid_until": "2028-03-31",
        "iso_scope": "Supply of mining equipment spares and earthmoving components",
        "experience": (
            "3 years of experience supplying mining equipment spares. "
            "Executed 5 orders worth Rs 0.9 crore."
        ),
    },
    "brahmani": {
        "legal_name": "Brahmani Traders",
        "pan": "BBRRH6060B",
        "gstin": _gstin("BBRRH6060B"),
        "udyam": "UDYAM-OD-21-0060606",
        "cin": "U51999OD2020PTC006006",
        "epfo_code": "MH/906060/015",
        "address": "Shop 7, Industrial Market, Sambalpur - 768001",
        "email": "hello@brahmani-traders-demo.in",
        "phone": "+91 98220 51015",
        "contact_name": "P. Mishra",
        "incorporation_date": "21-05-2020",
        "auditor": "Sambalpur Audit Group",
        "iso_no": "ISO-2022-60606",
        "iso_valid_from": "2022-04-01",
        "iso_valid_until": "2027-11-30",
        "iso_scope": "Trading of industrial consumables and general engineering goods",
        "experience": (
            "7 years of experience trading industrial consumables. "
            "Executed 15 orders worth Rs 2.4 crore."
        ),
    },
}

def _inr(amount: int) -> str:
    """Format an int amount with Indian digit grouping: 8500000 -> Rs 85,00,000."""
    digits = str(amount)
    if len(digits) <= 3:
        return f"Rs {digits}"
    tail, head = digits[-3:], digits[:-3]
    parts = []
    while len(head) > 2:
        parts.append(head[-2:])
        head = head[:-2]
    if head:
        parts.append(head)
    return f"Rs {','.join(reversed(parts))},{tail}"


# ---------------------------------------------------------------------------
# Requirement builders (existing rule types only)
# ---------------------------------------------------------------------------

def _req(name, category, rule_type, rule_config, weight, mandatory=True,
         threshold=None):
    return (name, category, rule_type, rule_config, weight, mandatory,
            threshold)


def _r_gst(w):
    return _req("GST Registration", "STATUTORY", "REGISTRATION_STATUS",
                {"source": "GSTN", "identifier_field": "gstin",
                 "require_status": "ACTIVE"}, w,
                threshold="Valid and active GST registration")


def _r_pan(w):
    return _req("PAN Verification", "STATUTORY", "REGISTRATION_STATUS",
                {"source": "PAN_IT", "identifier_field": "pan",
                 "require_status": "ACTIVE"}, w,
                threshold="Valid PAN matching bidder identity")


def _r_udyam(w):
    return _req("Udyam Registration", "REGISTRATION", "REGISTRATION_STATUS",
                {"source": "UDYAM", "identifier_field": "udyam_number",
                 "require_status": "ACTIVE"}, w,
                threshold="Valid Udyam registration")


def _r_mca21(w):
    return _req("MCA21 Incorporation", "STATUTORY", "REGISTRATION_STATUS",
                {"source": "MCA21", "identifier_field": "cin",
                 "require_status": "ACTIVE"}, w,
                threshold="Valid MCA21 incorporation record")


def _r_epfo(w):
    return _req("EPFO Registration", "STATUTORY", "REGISTRATION_STATUS",
                {"source": "EPFO", "identifier_field": "epfo_code",
                 "require_status": "ACTIVE"}, w,
                threshold="Valid EPFO registration")


def _r_itr(w):
    return _req("ITR FY 2023-24", "STATUTORY", "MATCH",
                {"value_source": "extracted.itr_financial_year",
                 "pattern": "2023-24"}, w,
                threshold="ITR filed for FY 2023-24")


def _r_turnover(w, threshold):
    return _req("Balance Sheet Turnover", "FINANCIAL", "MINIMUM",
                {"value_source": "extracted.turnover_inr", "operator": ">=",
                 "value": threshold}, w, threshold=_inr(threshold))


def _r_experience(w, years):
    return _req("Work Experience", "EXPERIENCE", "MINIMUM",
                {"value_source": "extracted.experience_years", "operator": ">=",
                 "value": years}, w, threshold=f"{years} years")


def _r_iso(w):
    return _req("ISO 9001 Validity", "TECHNICAL", "DATE_VALIDITY",
                {"value_source": "extracted.iso_valid_until",
                 "document_type": "ISO_9001_CERTIFICATE"}, w,
                threshold="ISO 9001 certificate must be valid (not expired) "
                          "as on the date of evaluation")


def _r_emd(w, amount):
    return _req("EMD Amount", "FINANCIAL", "MINIMUM",
                {"value_source": "extracted.emd_amount_inr", "operator": ">=",
                 "value": amount}, w, threshold=_inr(amount))


def _r_blacklist(w):
    return _req(
        "Blacklist / Debarment Check", "INTEGRITY", "CUSTOM_RULE",
        {"expression":
         "('REVIEW_REQUIRED' if ctx.get('verification', {}).get('BLACKLIST') is None "
         "else ('FAIL' if ctx['verification']['BLACKLIST'].get('data', {})"
         ".get('blacklisted', False) else 'PASS'))"},
        w, threshold="Bidder must not be blacklisted/debarred")


# ---------------------------------------------------------------------------
# Tender specifications.
#
# Each bidder entry: (company_key, scenario) where scenario overrides any of:
#   turnover        — "Rs ..." string for the balance sheet (default 95L)
#   turnover_alt    — adds a TURNOVER_CERTIFICATE with a conflicting value
#                     (>10% different -> genuine inconsistency evidence)
#   total_income    — ITR "Total Income" line (default 60L)
#   experience      — Experience line; first number = years (default company)
#   emd_amount      — "Rs ..." string (default = tender EMD requirement)
#   emd_ref         — payment reference override
#   iso_valid_until — default "2028-03-31"; expired -> "2023-06-30"
#   itr_fy          — default "2023-24"
#   gst_cert_pan    — PAN shown on the GST certificate (default company pan;
#                     crestline's default differs — see COMPANIES)
#   gstin           — GSTIN shown on the GST certificate
#   skip_docs       — template types to NOT generate (genuine MISSING)
# ---------------------------------------------------------------------------

T1_REQS = [_r_gst(15), _r_pan(10), _r_udyam(10), _r_itr(10), _r_mca21(10),
           _r_turnover(15, 5_000_000), _r_experience(10, 5), _r_iso(5),
           _r_emd(5, 200_000), _r_epfo(10)]
T2_REQS = [_r_itr(10), _r_turnover(20, 10_000_000), _r_experience(20, 8),
           _r_gst(15), _r_pan(10), _r_emd(15, 500_000), _r_mca21(10)]
T3_REQS = [_r_gst(20), _r_pan(15), _r_udyam(15), _r_mca21(10), _r_epfo(10),
           _r_iso(10), _r_emd(10, 100_000), _r_itr(10)]
T4_REQS = [_r_gst(15), _r_pan(10), _r_turnover(15, 7_500_000),
           _r_experience(15, 5), _r_itr(10), _r_iso(10), _r_emd(10, 200_000),
           _r_udyam(10), _r_epfo(5)]
T5_REQS = [_r_gst(15), _r_pan(15), _r_turnover(15, 6_000_000),
           _r_experience(15, 5), _r_itr(10), _r_emd(10, 200_000), _r_iso(10),
           _r_epfo(10)]
T6_REQS = [_r_gst(10), _r_pan(10), _r_udyam(10), _r_turnover(15, 8_000_000),
           _r_itr(10), _r_experience(10, 6), _r_iso(10), _r_emd(10, 300_000),
           _r_blacklist(10), _r_epfo(5)]

for _rs in (T1_REQS, T2_REQS, T3_REQS, T4_REQS, T5_REQS, T6_REQS):
    assert sum(r[4] for r in _rs) == 100, "requirement weights must total 100"

# Near-identical experience text for the Tender-5 document-similarity pair
# (kestrel + vardaan): only the legal name on each document differs.
_SHARED_EXPERIENCE_TEXT = (
    "9 years — design, manufacture, supply, installation supervision and "
    "commissioning support for industrial pumping equipment including "
    "centrifugal pumps, valves and flow control assemblies for municipal "
    "water supply augmentation projects. Contract value Rs 2.4 crore. "
    "Completed 15-03-2024 with satisfactory performance and no penalty "
    "levied; completion certified after successful trial operation."
)

TENDERS: list[dict] = [
    {
        "tender_number": "VAR-DEMO-2026-01",
        "title": "DEMO DATA — Variety: general industrial goods procurement (baseline)",
        "issue_date": date(2026, 1, 12),
        "closing_date": date(2026, 3, 12),
        "requirements": T1_REQS,
        "estimated_value_inr": 85000000,
        "emd_default": 200000,
        "bidders": [
            # A — fully compliant
            ("meridian", {"turnover": _inr(8_500_000)}),
            # B — single substantive failure: turnover below threshold
            ("brightline", {"turnover": _inr(4_000_000)}),
            # C — two failures: turnover + experience below thresholds
            ("crestline", {"turnover": _inr(3_800_000),
                           "experience": "3 years of experience supplying "
                           "industrial valves to water utilities. Executed 6 "
                           "orders worth Rs 1.1 crore."}),
            # D — identity mismatch between documents (PAN card vs GST cert)
            ("godavari", {"gst_cert_pan": GODAVARI_PAN_Y,
                          "gstin": GODAVARI_GSTIN_Y}),
            # E — expired ISO certificate
            ("mahanadi", {"iso_valid_until": "2023-06-30",
                         "experience": "9 years of experience supplying "
                         "mining equipment spares. Executed 18 orders worth "
                         "Rs 2.7 crore."}),
            # F — EMD below required amount
            ("sabarmati", {"emd_amount": _inr(100_000)}),
            # G — multiple serious issues: GST source inactive + turnover
            #     below threshold + expired ISO
            ("aarohan", {"turnover": _inr(4_200_000),
                         "iso_valid_until": "2023-06-30"}),
        ],
    },
    {
        "tender_number": "VAR-DEMO-2026-02",
        "title": "DEMO DATA — Variety: financial & experience emphasis",
        "issue_date": date(2026, 2, 9),
        "closing_date": date(2026, 4, 9),
        "requirements": T2_REQS,
        "estimated_value_inr": 120000000,
        "emd_default": 500000,
        "bidders": [
            # A — strongest: financials + experience + clean statutory
            ("kestrel", {"turnover": _inr(25_000_000),
                         "emd_amount": _inr(500_000)}),
            # B — turnover below threshold
            ("vardaan", {"turnover": _inr(6_000_000)}),
            # C — genuine inconsistency: balance sheet vs turnover
            #     certificate differ well beyond tolerance; ITR total income
            #     agrees with neither
            ("godavari", {"turnover": _inr(18_000_000),
                          "turnover_alt": _inr(11_000_000),
                          "total_income": _inr(9_500_000),
                          "experience": "10 years of experience in forged "
                          "flanges and fittings. Executed 24 orders worth "
                          "Rs 5.2 crore."}),
            # D — ITR for the wrong financial year
            ("tapi", {"itr_fy": "2022-23",
                      "turnover": _inr(15_000_000),
                      "experience": "8 years of experience in fabrication of "
                      "storage tanks. Executed 16 orders worth Rs 3.4 crore."}),
            # E — experience below threshold
            ("kaveri", {"turnover": _inr(12_000_000)}),
            # F — EMD below required amount
            ("sabarmati", {"emd_amount": _inr(200_000),
                           "turnover": _inr(11_000_000)}),
            # G — multiple financial/experience problems
            ("meridian", {"turnover": _inr(7_000_000),
                          "experience": "4 years of experience in industrial "
                          "automation panels and control systems. Executed 9 "
                          "orders worth Rs 1.2 crore.",
                          "emd_amount": _inr(200_000)}),
        ],
    },
    {
        "tender_number": "VAR-DEMO-2026-03",
        "title": "DEMO DATA — Variety: statutory verification emphasis",
        "issue_date": date(2026, 3, 16),
        "closing_date": date(2026, 5, 16),
        "requirements": T3_REQS,
        "estimated_value_inr": 67500000,
        "emd_default": 100000,
        "bidders": [
            # A — all statutory identifiers valid and matching
            ("kaveri", {}),
            # B — GST document valid but the mock registry shows the GSTIN
            #     as cancelled -> EXPIRED (plus the company's MCA21 name
            #     mismatch -> MISMATCH)
            ("narmada", {}),
            # C — PAN card shows one valid PAN, the GST certificate shows a
            #     different valid PAN (both with ACTIVE mock records)
            ("crestline", {}),
            # D — Udyam enterprise name does not match the registered legal
            #     name in the mock registry; ISO valid but close to expiry
            #     (still PASS at evaluation — boundary demonstration)
            ("tapi", {"iso_valid_until": "2026-12-31"}),
            # E — EPFO verification source suspended -> REVIEW_REQUIRED
            ("mahanadi", {}),
            # F — expired ISO certificate, other statutory evidence valid
            ("kestrel", {"iso_valid_until": "2023-06-30"}),
            # G — multiple statutory failures: GST cancelled, PAN not found
            ("aarohan", {}),
        ],
    },
    {
        "tender_number": "VAR-DEMO-2026-04",
        "title": "DEMO DATA — Variety: mixed realistic scenarios",
        "issue_date": date(2026, 4, 20),
        "closing_date": date(2026, 6, 20),
        "requirements": T4_REQS,
        "estimated_value_inr": 185000000,
        "emd_default": 200000,
        "bidders": [
            # A — clean, all requirements satisfied
            ("vardaan", {"turnover": _inr(14_000_000)}),
            # B — clean, all requirements satisfied (ISO present and valid)
            ("kaveri", {"turnover": _inr(11_000_000)}),
            # C — statutory identifier mismatch + threshold failure
            ("narmada", {"turnover": _inr(5_000_000)}),
            # D — expired certificate, no missing evidence
            ("brightline", {"turnover": _inr(9_500_000),
                            "iso_valid_until": "2024-01-31"}),
            # E — financial inconsistency (ITR vs balance sheet vs turnover
            #     certificate), other requirements valid
            ("sabarmati", {"turnover": _inr(12_000_000),
                           "turnover_alt": _inr(8_000_000),
                           "total_income": _inr(6_000_000)}),
            # F — EMD issue + experience failure
            ("mahanadi", {"turnover": _inr(8_800_000),
                          "emd_amount": _inr(100_000)}),
            # G — several serious failures
            ("meridian", {"turnover": _inr(5_500_000),
                          "emd_amount": _inr(100_000),
                          "experience": "3 years of experience in industrial "
                          "automation panels. Executed 6 orders worth "
                          "Rs 0.8 crore."}),
        ],
    },
    {
        "tender_number": "VAR-DEMO-2026-05",
        "title": "DEMO DATA — Variety: repeated participation + integrity",
        "issue_date": date(2026, 5, 11),
        "closing_date": date(2026, 7, 11),
        "requirements": T5_REQS,
        "estimated_value_inr": 92500000,
        "emd_default": 200000,
        "bidders": [
            # A — ISO certificate names a different company than the
            #     registered bidder (identity mismatch on the ISO doc)
            ("aarohan", {"turnover": _inr(9_000_000),
                        "iso_legal_name": "Aarohan Industrial Works"}),
            ("meridian", {"turnover": _inr(11_000_000)}),
            # Document-similarity pair: near-identical experience text
            ("kestrel", {"turnover": _inr(13_000_000),
                         "experience": _SHARED_EXPERIENCE_TEXT}),
            ("vardaan", {"turnover": _inr(10_000_000),
                         "experience": _SHARED_EXPERIENCE_TEXT}),
            # Shared-PAN identity pair
            ("nimbus_a", {"turnover": _inr(7_500_000)}),
            ("nimbus_b", {"turnover": _inr(7_000_000)}),
            # G — ISO certificate does not state an expiry date ("Not
            #     stated") -> no usable date -> MISSING via the engine
            #     (document itself is present)
            ("tapi", {"turnover": _inr(8_500_000),
                     "iso_valid_until": "Not stated"}),
        ],
    },
    {
        "tender_number": "VAR-DEMO-2026-06",
        "title": "DEMO DATA — Variety: historical anomaly + blacklist",
        "issue_date": date(2026, 6, 8),
        "closing_date": date(2026, 8, 8),
        "requirements": T6_REQS,
        "estimated_value_inr": 150000000,
        "emd_default": 300000,
        "bidders": [
            # A — fully compliant, all mandatory PASS
            ("godavari", {"turnover": _inr(16_000_000),
                          "experience": "10 years of experience in forged "
                          "flanges and fittings. Executed 24 orders worth "
                          "Rs 5.2 crore."}),
            # B — one threshold failure (turnover); ISO certificate names
            #     a different company than the registered bidder
            ("narmada", {"turnover": _inr(6_500_000),
                       "iso_legal_name": "Narmada Systems and Controls"}),
            # C — document-specific mismatch (GST certificate shows a
            #     different valid PAN than the PAN card, Tender-6 only)
            ("kestrel", {"gst_cert_pan": KESTREL_PAN_Y,
                         "gstin": KESTREL_GSTIN_Y,
                         "turnover": _inr(12_000_000)}),
            # D — EPFO verification source requires review
            ("brightline", {"turnover": _inr(10_000_000)}),
            # E — expired ISO + turnover below threshold
            ("crestline", {"turnover": _inr(7_000_000),
                           "iso_valid_until": "2023-06-30"}),
            # F — blacklisted in the mock registry; documents otherwise valid
            ("brahmani", {"turnover": _inr(9_500_000),
                          "emd_amount": _inr(300_000)}),
            # G — repeated historical anomaly: genuine FAILs here after
            #     FAIL/MISMATCH in earlier tenders (T2 ITR, T3 Udyam)
            ("tapi", {"turnover": _inr(5_500_000),
                      "emd_amount": _inr(150_000),
                      "experience": "4 years of experience in fabrication of "
                      "storage tanks. Executed 8 orders worth Rs 1.6 crore."}),
        ],
    },
]

# Requirement name -> standalone document template (None = no document).
_REQ_DOC_TEMPLATES = {
    "GST Registration": "GST_CERTIFICATE",
    "PAN Verification": "PAN_CERTIFICATE",
    "Udyam Registration": "UDYAM_CERTIFICATE",
    "MCA21 Incorporation": "MCA21_CERTIFICATE",
    "EPFO Registration": "EPFO_CERTIFICATE",
    "ITR FY 2023-24": "ITR_DOCUMENT",
    "Balance Sheet Turnover": "BALANCE_SHEET",
    "Work Experience": "EXPERIENCE_CERTIFICATE",
    "ISO 9001 Validity": "ISO_9001_CERTIFICATE",
    "EMD Amount": "EMD_RECEIPT",
    "Blacklist / Debarment Check": None,
}

_DEMO_SUBTITLE = "DEMO DATA — synthetic record for variety demonstration only"


# ---------------------------------------------------------------------------
# Mock fixtures (additive, idempotent)
# ---------------------------------------------------------------------------

def _fixture_name_overrides() -> dict[str, dict[str, str]]:
    """identifier -> fixture record name (differs from the legal name)."""
    return {
        # GSTIN fixtures keyed by gstin
        "gstn": {
            COMPANIES["narmada"]["gstin"]: "Narmada Trading Co.",
        },
        # UDYAM fixtures keyed by udyam number
        "udyam": {
            COMPANIES["tapi"]["udyam"]: "Tapi Engineering Corporation",
        },
        # MCA21 fixtures keyed by CIN
        "mca21": {
            COMPANIES["narmada"]["cin"]: "Narmada Trading Co.",
        },
        # PAN fixtures keyed by PAN: the shared PAN is anchored to nimbus_a's
        # legal name; nimbus_b's divergent name is what the name cross-check
        # and the identity-relationship detector flag.
        "pan_name": {
            SHARED_NIMBUS_PAN: COMPANIES["nimbus_a"]["legal_name"],
        },
    }


def _write_fixtures() -> int:
    """Add mock registry records for the fictional identifiers.

    Records are only added when absent (idempotent); existing records are
    never modified. Fixture statuses encode the engineered scenarios:
    CANCELLED GSTINs, SUSPENDED EPFO codes, divergent registry names, and
    the blacklist entry.
    """
    added = 0
    overrides = _fixture_name_overrides()

    def _load(name: str) -> tuple[dict, Path]:
        path = MOCK_DATA_DIR / name
        return json.loads(path.read_text(encoding="utf-8")), path

    def _save(name: str, data: dict, path: Path) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    pan_data, pan_path = _load("pan_it.json")
    gstn_data, gstn_path = _load("gstn.json")
    udyam_data, udyam_path = _load("udyam.json")
    mca21_data, mca21_path = _load("mca21.json")
    epfo_data, epfo_path = _load("epfo.json")
    blacklist_data, blacklist_path = _load("blacklist.json")

    for key, c in COMPANIES.items():
        legal = c["legal_name"]

        # PAN fixtures. Aarohan's PAN is deliberately absent -> NOT_FOUND.
        if key != "aarohan" and c["pan"] not in pan_data:
            pan_data[c["pan"]] = {
                "pan": c["pan"],
                "name": overrides["pan_name"].get(c["pan"], legal),
                "legal_name": overrides["pan_name"].get(c["pan"], legal),
                "status": "ACTIVE",
                "itr_filed_upto": 2025,
            }
            added += 1
        # Crestline's GST-certificate PAN also needs a mock record.
        if key == "crestline" and CRESTLINE_PAN_Y not in pan_data:
            pan_data[CRESTLINE_PAN_Y] = {
                "pan": CRESTLINE_PAN_Y,
                "name": legal,
                "legal_name": legal,
                "status": "ACTIVE",
                "itr_filed_upto": 2025,
            }
            added += 1

        # GSTIN fixtures. Aarohan + Narmada are CANCELLED -> EXPIRED checks.
        gstin = c["gstin"]
        if gstin not in gstn_data:
            cancelled = key in ("aarohan", "narmada")
            gstn_data[gstin] = {
                "gstin": gstin,
                "legal_name": overrides["gstn"].get(gstin, legal),
                "registration_date": "2021-06-15",
                "state": "Maharashtra",
                "status": "CANCELLED" if cancelled else "ACTIVE",
            }
            added += 1
        # UDYAM fixtures.
        if c["udyam"] not in udyam_data:
            udyam_data[c["udyam"]] = {
                "udyam_number": c["udyam"],
                "enterprise_name": overrides["udyam"].get(c["udyam"], legal),
                "registration_date": "2021-07-02",
                "category": "MEDIUM",
                "status": "ACTIVE",
            }
            added += 1

        # MCA21 fixtures.
        if c["cin"] not in mca21_data:
            mca21_data[c["cin"]] = {
                "cin": c["cin"],
                "company_name": overrides["mca21"].get(c["cin"], legal),
                "incorporation_date": c["incorporation_date"],
                "status": "ACTIVE",
            }
            added += 1

        # EPFO fixtures. Mahanadi + Brightline are SUSPENDED ->
        # REVIEW_REQUIRED checks.
        if c["epfo_code"] not in epfo_data:
            epfo_data[c["epfo_code"]] = {
                "epfo_code": c["epfo_code"],
                "employer_name": legal,
                "status": "SUSPENDED" if key in ("mahanadi", "brightline")
                else "ACTIVE",
            }
            added += 1

    # Per-tender override GSTINs/PANs (doc-level scenarios) also resolve in
    # the mock registry. One record each (outside the company loop).
    for extra_gstin, owner in (("27CCDDY8808D1Z5", "crestline"),
                               ("27GGDDY9919D1Z5", "godavari"),
                               ("27KKEEY3313Y1Z5", "kestrel")):
        if extra_gstin not in gstn_data:
            gstn_data[extra_gstin] = {
                "gstin": extra_gstin,
                "legal_name": COMPANIES[owner]["legal_name"],
                "registration_date": "2021-06-15",
                "state": "Maharashtra",
                "status": "ACTIVE",
            }
            added += 1
    for extra_pan, owner in ((GODAVARI_PAN_Y, "godavari"),
                             (KESTREL_PAN_Y, "kestrel")):
        if extra_pan not in pan_data:
            pan_data[extra_pan] = {
                "pan": extra_pan,
                "name": COMPANIES[owner]["legal_name"],
                "legal_name": COMPANIES[owner]["legal_name"],
                "status": "ACTIVE",
                "itr_filed_upto": 2025,
            }
            added += 1

    # Blacklist fixture for Brahmani Traders (Tender-6 F scenario).
    brahmani_name = COMPANIES["brahmani"]["legal_name"]
    if not any(r.get("company_name") == brahmani_name for r in blacklist_data):
        blacklist_data.append({
            "company_name": brahmani_name,
            "blacklisted": True,
            "debarred": False,
            "authority": "CPCL",
            "reason": ("Blacklisted for submission of forged turnover "
                       "certificates in tender CPCL-2024-118 "
                       "(fictional demo record)"),
            "period": "2025-03-01 to 2028-02-29",
            "is_mock": True,
        })
        added += 1

    if added:
        _save("pan_it.json", pan_data, pan_path)
        _save("gstn.json", gstn_data, gstn_path)
        _save("udyam.json", udyam_data, udyam_path)
        _save("mca21.json", mca21_data, mca21_path)
        _save("epfo.json", epfo_data, epfo_path)
        _save("blacklist.json", blacklist_data, blacklist_path)
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

def _section_data(company: dict, scenario: dict, template_type: str,
                  tender_number: str, company_key: str,
                  emd_default: int) -> dict:
    """Build the template data dict for one standalone evidence document."""
    legal = company["legal_name"]
    gst_cert_pan = scenario.get("gst_cert_pan", company["pan"])
    # Crestline's company-level dual-PAN evidence: its GST certificate
    # always shows CRESTLINE_PAN_Y (unless a scenario overrides it).
    if company_key == "crestline" and "gst_cert_pan" not in scenario:
        gst_cert_pan = CRESTLINE_PAN_Y
    if template_type == "PAN_CERTIFICATE":
        return {
            "legal_name": legal,
            "pan": company["pan"],
            "incorporation_date": company["incorporation_date"],
            "address": company["address"],
            "email": company["email"],
            "phone": company["phone"],
        }
    if template_type == "GST_CERTIFICATE":
        return {
            "legal_name": legal,
            "trade_name": legal,
            "gstin": scenario.get("gstin", company["gstin"]),
            "pan": gst_cert_pan,
            "registration_date": "15-06-2021",
            "address": company["address"],
        }
    if template_type == "UDYAM_CERTIFICATE":
        return {
            "legal_name": legal,
            "udyam": company["udyam"],
            "valid_until": "2028-06-30",
            "address": company["address"],
        }
    if template_type == "MCA21_CERTIFICATE":
        return {
            "legal_name": legal,
            "cin": company["cin"],
            "incorporation_date": company["incorporation_date"],
            "company_status": "Active",
        }
    if template_type == "EPFO_CERTIFICATE":
        return {
            "legal_name": legal,
            "epfo_code": company["epfo_code"],
            "address": company["address"],
        }
    if template_type == "ITR_DOCUMENT":
        return {
            "legal_name": legal,
            "pan": company["pan"],
            "itr_financial_year": scenario.get("itr_fy", "2023-24"),
            "assessment_year": "2024-25",
            "total_income": scenario.get("total_income", _inr(6_000_000)),
        }
    if template_type == "BALANCE_SHEET":
        return {
            "legal_name": legal,
            "financial_year": "2023-24",
            "turnover": scenario.get("turnover", _inr(9_500_000)),
            "auditor_name": company["auditor"],
        }
    if template_type == "TURNOVER_CERTIFICATE":
        return {
            "legal_name": legal,
            "turnover": scenario["turnover_alt"],
            "turnover_period": "FY 2023-24",
        }
    if template_type == "EXPERIENCE_CERTIFICATE":
        return {
            "legal_name": legal,
            "experience": scenario.get("experience", company["experience"]),
        }
    if template_type == "ISO_9001_CERTIFICATE":
        return {
            # iso_legal_name override lets a scenario put a different
            # company name on the certificate (identity-mismatch scenario).
            "legal_name": scenario.get("iso_legal_name", legal),
            "iso_certificate_number": company["iso_no"],
            "iso_valid_from": scenario.get(
                "iso_valid_from", company.get("iso_valid_from", "2021-04-01")),
            "iso_valid_until": scenario.get(
                "iso_valid_until", company.get("iso_valid_until", "2028-03-31")),
            "iso_scope": company.get("iso_scope", ""),
        }
    if template_type == "EMD_RECEIPT":
        tender_short = tender_number.replace("VAR-DEMO-", "VAR")
        return {
            "legal_name": legal,
            "emd_amount": scenario.get("emd_amount", _inr(emd_default)),
            "emd_reference": scenario.get(
                "emd_ref", f"NEFT/{tender_short}/{company_key.upper()}/2026"),
            "emd_date": "2026-02-20",
            "emd_beneficiary": "CPCL",
        }
    raise ValueError(f"Unsupported variety demo template {template_type}")


def _doc_templates_for(requirements: list[tuple], scenario: dict) -> list[str]:
    """Which standalone documents a bid gets (requirement-driven)."""
    templates = []
    for req in requirements:
        tpl = _REQ_DOC_TEMPLATES.get(req[0])
        if tpl and tpl not in templates:
            templates.append(tpl)
    skip = set(scenario.get("skip_docs", ()))
    templates = [t for t in templates if t not in skip]
    if scenario.get("turnover_alt"):
        templates.append("TURNOVER_CERTIFICATE")
    return templates


def _persist_document(db, bid, tender_number: str, company_key: str,
                      template_type: str, scenario: dict, emd_default: int,
                      user_id: int | None) -> dict:
    """Generate one standalone PDF, persist it, run the real pipeline."""
    from app.core.config import ensure_upload_dir
    from app.models.models import Document
    from app.seed.demo_docs import generate_dossier_pdf
    from app.seed.demo_bidder_profiles import demo_banner
    from app.services.pipeline_service import process_document

    company = COMPANIES[company_key]
    section_data = _section_data(company, scenario, template_type,
                                 tender_number, company_key, emd_default)
    pdf = generate_dossier_pdf(
        company["legal_name"],
        [(template_type, section_data)],
        banner=demo_banner(),
        title=f"{template_type.replace('_', ' ').title()} — DEMO DATA",
        subtitle=_DEMO_SUBTITLE,
    )
    filename = (
        f"vardemo_{bid.tender_id}_{company_key}_{template_type.lower()}.pdf"
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

def variety_demo_dataset_status(db) -> dict:
    """Report whether the variety demo dataset is loaded."""
    from app.models.models import Tender

    tenders = []
    for number in VARIETY_TENDER_NUMBERS:
        tender = db.query(Tender).filter_by(tender_number=number).first()
        if tender is not None:
            tenders.append({"id": tender.id, "tender_number": number})
    return {"loaded": len(tenders) == len(VARIETY_TENDER_NUMBERS),
            "tenders": tenders}


def _refresh_variety_metadata(db) -> dict:
    """Backfill tender metadata + requirement criteria on existing rows.

    Idempotent: rewrites the same spec values every time, so re-running
    load on an already-seeded dataset converges instead of duplicating.
    Touches ONLY the six VAR-DEMO tenders and their requirements.
    Also backfills ``document_type`` into DATE_VALIDITY rule_configs so the
    rule engine can distinguish missing documents from unclear dates.
    """
    from app.models.models import Tender, TenderRequirement

    updated = {"tenders": 0, "requirements": 0, "rule_configs": 0}
    for spec in TENDERS:
        tender = (db.query(Tender)
                  .filter_by(tender_number=spec["tender_number"]).one_or_none())
        if tender is None:
            continue
        if tender.estimated_value_inr != spec["estimated_value_inr"]:
            tender.estimated_value_inr = spec["estimated_value_inr"]
            updated["tenders"] += 1
        # Match requirements by name; rewrite the criteria text from spec.
        wanted = {name: (threshold, rule_config)
                  for (name, _cat, _rt, rule_config, _w, _m,
                       threshold) in spec["requirements"]}
        for req in (db.query(TenderRequirement)
                    .filter_by(tender_id=tender.id).all()):
            want = wanted.get(req.requirement_name)
            if want is None:
                continue
            threshold, rule_config = want
            if req.threshold != threshold:
                req.threshold = threshold
                updated["requirements"] += 1
            # Backfill document_type for DATE_VALIDITY rules.
            if req.rule_type == "DATE_VALIDITY" and isinstance(rule_config, dict):
                want_doc = rule_config.get("document_type")
                if want_doc:
                    current = dict(req.rule_config or {})
                    if current.get("document_type") != want_doc:
                        current["document_type"] = want_doc
                        req.rule_config = current
                        updated["rule_configs"] += 1
    db.commit()
    return updated


def load_variety_demo_dataset(db, user_id: int | None = None) -> dict:
    """Create the variety demo dataset (idempotent).

    Builds 6 tenders x 7 bids with real PDF evidence, writes mock fixtures,
    then runs verification + compliance + recommendation per bid through the
    real engines. A second call is a no-op. Concurrent calls are serialized;
    a call arriving while a load is in progress returns
    ``{"already_running": True}``.
    """
    if not _LOAD_LOCK.acquire(blocking=False):
        return {"already_running": True, "already_loaded": False,
                "reason": "load already in progress"}
    try:
        return _load_variety_demo_dataset_locked(db, user_id=user_id)
    finally:
        _LOAD_LOCK.release()


def _load_variety_demo_dataset_locked(db, user_id: int | None = None) -> dict:
    from app.models.models import Bidder, BidSubmission, Tender, TenderRequirement
    from app.services import audit_service
    from app.services.compliance_service import evaluate_bid
    from app.services.recommendation_service import generate_recommendation
    from app.services.verification_service import run_verification

    if variety_demo_dataset_status(db)["loaded"]:
        refreshed = _refresh_variety_metadata(db)
        return {"already_loaded": True, "loaded": False,
                "reason": "already loaded",
                "metadata_refreshed": refreshed}

    _write_fixtures()

    counts = {"tenders": 0, "bidders": 0, "bids": 0, "documents": 0}
    for spec in TENDERS:
        tender = Tender(
            tender_number=spec["tender_number"],
            title=spec["title"],
            organization="DEMO DATA — Variety demonstration",
            department="Procurement (demo)",
            description=(
                "DEMO DATA — synthetic tender created solely for multi-tender "
                "variety demonstrations. All companies, identifiers, documents "
                "and outcomes are fictional; every score and finding is "
                "computed by the real engines from the generated evidence."
            ),
            issue_date=spec["issue_date"],
            closing_date=spec["closing_date"],
            estimated_value_inr=spec["estimated_value_inr"],
            status="OPEN",
            is_demo_history=False,
        )
        db.add(tender)
        db.flush()
        counts["tenders"] += 1

        for (name, category, rule_type, rule_config, weight, mandatory,
             threshold) in spec["requirements"]:
            db.add(TenderRequirement(
                tender_id=tender.id,
                requirement_name=name,
                category=category,
                rule_type=rule_type,
                rule_config=dict(rule_config),
                threshold=threshold,
                description=f"DEMO DATA variety requirement: {name}.",
                weight=weight,
                mandatory=mandatory,
            ))
        db.commit()

        tender_bids: list = []
        for company_key, scenario in spec["bidders"]:
            company = COMPANIES[company_key]
            bidder = Bidder(
                tender_id=tender.id,
                legal_name=company["legal_name"],
                pan=company["pan"],
                gstin=scenario.get("gstin", company["gstin"]),
                udyam=company.get("udyam"),
                cin=company.get("cin"),
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
            tender_bids.append(bid)

            for template_type in _doc_templates_for(spec["requirements"],
                                                    scenario):
                _persist_document(db, bid, spec["tender_number"], company_key,
                                  template_type, scenario,
                                  spec["emd_default"], user_id)
                counts["documents"] += 1

            # Real verification + compliance + risk per bid.
            run_verification(db, bid.id, user_id=user_id)
            evaluate_bid(db, bid.id, user_id=user_id)

        # Comparative recommendation across the tender's bids.
        if tender_bids:
            generate_recommendation(db, tender_bids[0].id, user_id=user_id)

    audit_service.append_audit(
        db,
        user_id=user_id,
        action="VARIETY_DEMO_DATASET_LOADED",
        entity_type="tender",
        entity_id="VAR-DEMO-2026",
        metadata={"counts": counts, "tenders": VARIETY_TENDER_NUMBERS},
    )
    db.commit()
    return {"loaded": True, "already_loaded": False, **counts}


def reset_variety_demo_dataset(db, user_id: int | None = None) -> dict:
    """Delete only the VAR-DEMO tenders and findings referencing them.

    Findings are removed before their tenders so the operation is safe on
    databases that enforce the integrity_findings.tender_id FK. Mock fixture
    records are left in place (documented behaviour — additive entries keyed
    by fictional identifiers).
    """
    from app.models.models import Bidder, BidSubmission, IntegrityFinding, Tender
    from app.services import audit_service
    from app.services.delete_service import delete_tender

    wanted = set(VARIETY_TENDER_NUMBERS)
    removed = {"tenders": 0, "findings": 0}

    demo_tender_ids: set[int] = set()
    for number in VARIETY_TENDER_NUMBERS:
        tender = db.query(Tender).filter_by(tender_number=number).first()
        if tender is not None:
            demo_tender_ids.add(tender.id)

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

    for finding in db.query(IntegrityFinding).all():
        if _is_demo_finding(finding):
            db.delete(finding)
            removed["findings"] += 1
    db.flush()

    for tender_id in demo_tender_ids:
        delete_tender(db, tender_id, user_id=user_id)
        removed["tenders"] += 1

    # Safety net: collapse any duplicate non-closed findings that may have
    # accumulated (e.g. from concurrent analysis runs before the run lock).
    from app.services.integrity_service import dedupe_existing_findings
    dedupe_result = dedupe_existing_findings(db)
    removed["duplicate_findings_removed"] = dedupe_result["removed_duplicates"]

    audit_service.append_audit(
        db,
        user_id=user_id,
        action="VARIETY_DEMO_DATASET_RESET",
        entity_type="tender",
        entity_id="VAR-DEMO-2026",
        metadata={"removed": removed, "tenders": VARIETY_TENDER_NUMBERS},
    )
    db.commit()
    return {"reset": True, **removed}
