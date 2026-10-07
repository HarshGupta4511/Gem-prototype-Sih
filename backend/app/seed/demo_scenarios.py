"""Mismatch-focused demo scenario generator for BIDWISE.

Replaces the old "same fixed scenario per bidder" model. A *scenario* is a
named, reproducible mutation plan applied to a fictional bidder identity:

- Document-side mutations (names, amounts, dates, financial years on the
  generated PDFs).
- Fixture-side mutations (mock registry records keyed by the scenario's
  fictional identifiers).

Every outcome (MISMATCH / FAIL / EXPIRED / MISSING / PASS) then *emerges*
from the real pipeline — extraction -> mock verification -> deterministic
rules engine. Nothing is hardcoded and no score is randomized.

Reproducibility: ``plan_scenario(identity, scenario_id, seed)`` derives a
``random.Random`` stream from ``(identity, scenario_id, seed)``; the same
triple always yields the same identifiers, PDFs, fixtures and therefore the
same compliance outcomes. ``seed=None`` means "pick a fresh random seed"
(the seed is returned so the officer can replay it).

Idempotency: seeded files use the prefix
``demo_{identity}_{scenario}_{seed}_`` so re-loading never duplicates
documents; fixture records are added only when the identifier key is absent.
"""
from __future__ import annotations

import json
import random
import string
from dataclasses import dataclass, field
from pathlib import Path

# ------------------------------------------------------------------ catalog
SCENARIOS: dict[str, dict] = {
    "clean": {
        "title": "Fully Compliant",
        "description": "All evidence valid and consistent with mock registries.",
    },
    "gst_name_mismatch": {
        "title": "GST Name Mismatch",
        "description": "GST certificate is genuine but the mock GSTN registry carries a different legal name.",
    },
    "gst_status_conflict": {
        "title": "GST Status Conflict",
        "description": "Certificate claims ACTIVE registration; the mock GSTN registry reports INACTIVE.",
    },
    "pan_name_mismatch": {
        "title": "PAN Name Mismatch",
        "description": "PAN card is genuine but the mock PAN registry carries a different holder name.",
    },
    "mca21_name_mismatch": {
        "title": "MCA21 Name Mismatch",
        "description": "Incorporation certificate is genuine but the mock MCA21 registry carries a different company name.",
    },
    "itr_fy_mismatch": {
        "title": "ITR Financial-Year Mismatch",
        "description": "The ITR document is for FY 2022–23 while the tender requires FY 2023–24.",
    },
    "turnover_shortfall": {
        "title": "Turnover Below Threshold",
        "description": "The balance sheet is genuine but the turnover is below the required minimum.",
    },
    "udyam_entity_mismatch": {
        "title": "Udyam Entity Mismatch",
        "description": "Udyam certificate belongs to a differently named entity in the mock registry.",
    },
    "experience_conflict": {
        "title": "Experience Certificate Conflict",
        "description": "The experience certificate names a different entity than the rest of the dossier (cross-document inconsistency).",
    },
    "iso_expired": {
        "title": "ISO 9001 Expired",
        "description": "The ISO 9001 certificate's validity has lapsed.",
    },
    "emd_wrong_amount": {
        "title": "EMD Amount Short",
        "description": "The EMD receipt shows an amount below the required bid security.",
    },
    "emd_wrong_beneficiary": {
        "title": "EMD Wrong Beneficiary",
        "description": "The EMD receipt names a beneficiary that is not the tendering authority (visible in extracted fields for officer review).",
    },
    "epfo_conflict": {
        "title": "EPFO Record Conflict",
        "description": "EPFO certificate is genuine but the mock EPFO registry reports the establishment INACTIVE.",
    },
    "missing_evidence": {
        "title": "Missing Evidence",
        "description": "Only balance sheet and experience evidence are present; everything else is deliberately absent.",
    },
    "debarred": {
        "title": "Debarred Entity",
        "description": "Full valid evidence, but the mock debarment registry lists the bidder — risk goes CRITICAL while the score stays independent.",
    },
}
SCENARIO_IDS = tuple(SCENARIOS)

# Classic profile keys map to scenarios (backward compatibility for the
# Stage-3 modal's historic behaviour).
CLASSIC_SCENARIO = {
    "apex": "clean",
    "vertex": "missing_evidence",
    "nova": "pan_name_mismatch",
    "primetech": "debarred",
}

MOCK_DATA_DIR = Path(__file__).resolve().parent.parent / "adapters" / "mock_data"


@dataclass
class ScenarioPlan:
    identity_key: str
    scenario_id: str
    seed: int
    legal_name: str
    identifiers: dict = field(default_factory=dict)
    # template_type -> {field: value} overrides on generated PDF sections
    doc_mutations: dict = field(default_factory=dict)
    # per-template legal_name override (cross-document inconsistency)
    doc_name_overrides: dict = field(default_factory=dict)
    # mock source -> {field: value} overrides on the fixture record
    fixture_mutations: dict = field(default_factory=dict)
    # blacklist record to append (or None)
    blacklist_record: dict | None = None
    # template types to NOT generate (missing-evidence scenarios)
    omit_templates: set = field(default_factory=set)


def _rng(identity_key: str, scenario_id: str, seed: int) -> random.Random:
    return random.Random(f"bidwise-demo:{identity_key}:{scenario_id}:{seed}")


def _gen_identifiers(rng: random.Random) -> dict:
    pan = (
        "".join(rng.choices(string.ascii_uppercase, k=5))
        + "".join(rng.choices(string.digits, k=4))
        + rng.choice(string.ascii_uppercase)
    )
    return {
        "pan": pan,
        "gstin": f"27{pan}1Z5",
        "udyam": f"UDYAM-MH-{rng.randint(10, 99)}-{rng.randint(1000000, 9999999):07d}",
        "cin": (
            f"U{rng.randint(10000, 99999)}MH{rng.randint(2000, 2024)}"
            f"PTC{rng.randint(100000, 999999)}"
        ),
        "epfo_code": f"MH/{rng.randint(100000, 999999)}/{rng.randint(100, 999):03d}",
    }


def _alt_name(rng: random.Random, legal_name: str) -> str:
    """A plausibly-different fictional entity name (never the real one)."""
    prefixes = ["Shree", "National", "United", "Supreme", "Global"]
    cores = ["Mech Works", "Infra Projects", "Trading Co", "Engineering",
             "Industrial Enterprises", "Fabricators"]
    suffixes = ["Pvt. Ltd.", "LLP", "Enterprises"]
    for _ in range(10):
        cand = f"{rng.choice(prefixes)} {rng.choice(cores)} {rng.choice(suffixes)}"
        if cand != legal_name:
            return cand
    return f"{legal_name} (Alternate)"


def plan_scenario(identity_key: str, scenario_id: str, seed: int | None,
                  legal_name: str) -> ScenarioPlan:
    """Build a reproducible mutation plan. ``seed=None`` picks a fresh seed."""
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario_id}'")
    if seed is None:
        seed = random.randint(1, 999_999)
    rng = _rng(identity_key, scenario_id, seed)
    plan = ScenarioPlan(identity_key=identity_key, scenario_id=scenario_id,
                        seed=seed, legal_name=legal_name)
    plan.identifiers = _gen_identifiers(rng)
    alt = _alt_name(rng, legal_name)

    if scenario_id == "gst_name_mismatch":
        plan.fixture_mutations["GSTN"] = {"legal_name": alt}
    elif scenario_id == "gst_status_conflict":
        plan.fixture_mutations["GSTN"] = {"status": "INACTIVE"}
    elif scenario_id == "pan_name_mismatch":
        plan.fixture_mutations["PAN_IT"] = {"legal_name": alt, "name": alt}
    elif scenario_id == "mca21_name_mismatch":
        plan.fixture_mutations["MCA21"] = {"company_name": alt}
    elif scenario_id == "itr_fy_mismatch":
        plan.doc_mutations["ITR_DOCUMENT"] = {
            "itr_financial_year": "2022-23", "assessment_year": "2023-24",
        }
    elif scenario_id == "turnover_shortfall":
        plan.doc_mutations["BALANCE_SHEET"] = {"_turnover_below_threshold": True}
    elif scenario_id == "udyam_entity_mismatch":
        plan.fixture_mutations["UDYAM"] = {"enterprise_name": alt}
    elif scenario_id == "experience_conflict":
        plan.doc_name_overrides["EXPERIENCE_CERTIFICATE"] = alt
    elif scenario_id == "iso_expired":
        plan.doc_mutations["ISO_9001_CERTIFICATE"] = {"iso_valid_until": "31-03-2022"}
    elif scenario_id == "emd_wrong_amount":
        plan.doc_mutations["EMD_RECEIPT"] = {"_emd_below_threshold": True}
    elif scenario_id == "emd_wrong_beneficiary":
        plan.doc_mutations["EMD_RECEIPT"] = {"emd_beneficiary": alt}
    elif scenario_id == "epfo_conflict":
        plan.fixture_mutations["EPFO"] = {"status": "INACTIVE"}
    elif scenario_id == "missing_evidence":
        plan.omit_templates = {
            "GST_CERTIFICATE", "PAN_CERTIFICATE", "UDYAM_CERTIFICATE",
            "ITR_DOCUMENT", "MCA21_CERTIFICATE", "ISO_9001_CERTIFICATE",
            "EMD_RECEIPT", "EPFO_CERTIFICATE",
        }
    elif scenario_id == "debarred":
        plan.blacklist_record = {
            "company_name": legal_name,
            "blacklisted": True,
            "debarred": False,
            "authority": "CPCL",
            "period": "2025-01-01 to 2028-12-31",
            "reason": ("Blacklisted (demo record) for submission of forged "
                       "turnover certificates in tender CPCL-2024-207"),
        }
    # "clean": no mutations
    return plan


# ------------------------------------------------------------- fixtures
def _fixture_path(source: str) -> Path:
    return MOCK_DATA_DIR / {
        "GSTN": "gstn.json", "PAN_IT": "pan_it.json", "UDYAM": "udyam.json",
        "MCA21": "mca21.json", "EPFO": "epfo.json",
    }[source]


def _id_key(source: str, identifiers: dict) -> str:
    return {
        "GSTN": identifiers["gstin"], "PAN_IT": identifiers["pan"],
        "UDYAM": identifiers["udyam"], "MCA21": identifiers["cin"],
        "EPFO": identifiers["epfo_code"],
    }[source]


def _base_fixture(source: str, identifiers: dict, legal_name: str) -> dict:
    idk = _ident_key(source, identifiers)
    if source == "GSTN":
        return {"gstin": idk, "legal_name": legal_name,
                "registration_date": "2021-06-15", "state": "Maharashtra",
                "status": "ACTIVE"}
    if source == "PAN_IT":
        return {"pan": idk, "name": legal_name, "legal_name": legal_name,
                "status": "ACTIVE", "itr_filed_upto": 2025}
    if source == "UDYAM":
        return {"udyam_number": idk, "enterprise_name": legal_name,
                "category": "MEDIUM", "registration_date": "2021-07-02",
                "status": "ACTIVE"}
    if source == "MCA21":
        return {"cin": idk, "company_name": legal_name,
                "incorporation_date": "2015-03-12", "status": "ACTIVE"}
    if source == "EPFO":
        return {"epfo_code": idk, "employer_name": legal_name, "status": "ACTIVE"}
    raise ValueError(source)


def _ident_key(source: str, identifiers: dict) -> str:
    return _id_key(source, identifiers)


def ensure_scenario_fixtures(plan: ScenarioPlan) -> int:
    """Additively write mock registry records for the plan's identifiers.

    Records are keyed by the scenario's fictional identifiers and are only
    added when absent (idempotent). Returns the number of records added.
    """
    added = 0
    for source in ("GSTN", "PAN_IT", "UDYAM", "MCA21", "EPFO"):
        path = _fixture_path(source)
        data = json.loads(path.read_text())
        key = _id_key(source, plan.identifiers)
        if key not in data:
            rec = _base_fixture(source, plan.identifiers, plan.legal_name)
            rec.update(plan.fixture_mutations.get(source, {}))
            data[key] = rec
            path.write_text(json.dumps(data, indent=2))
            added += 1
    if plan.blacklist_record:
        path = MOCK_DATA_DIR / "blacklist.json"
        data = json.loads(path.read_text())
        names = {r.get("company_name") for r in data}
        if plan.blacklist_record["company_name"] not in names:
            data.append(plan.blacklist_record)
            path.write_text(json.dumps(data, indent=2))
            added += 1
    if added:
        # The mock adapters cache fixture JSON in memory; invalidate so the
        # freshly written scenario records are visible to verification runs
        # in this process.
        try:
            from app.adapters.base import _mock_data_cache
            _mock_data_cache.clear()
        except ImportError:
            pass
    return added
