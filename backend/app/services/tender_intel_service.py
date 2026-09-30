"""Tender intelligence — deterministic tender-text → requirement drafts.

Parses free-form tender text with keyword/clause regexes into structured
requirement drafts (mirroring the tender_requirements fields). The officer
confirms before saving; nothing here decides PASS/FAIL.
"""

from __future__ import annotations

import re


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;\n])\s+", text or "") if s.strip()]


_AMOUNT_RE = re.compile(
    r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(crore|cr|lakh|lac|lacs)?",
    re.IGNORECASE,
)
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b", re.IGNORECASE)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _inr_to_int(num_str: str, unit: str | None) -> int:
    n = float(num_str.replace(",", ""))
    u = (unit or "").lower()
    if u in ("crore", "cr"):
        n *= 10_000_000
    elif u in ("lakh", "lac", "lacs"):
        n *= 100_000
    return int(n)


def _inr_display(amount: int) -> str:
    if amount % 10_000_000 == 0:
        return f"₹{amount // 10_000_000} crore"
    if amount % 100_000 == 0:
        return f"₹{amount // 100_000} lakh"
    return f"₹{amount:,}"


def _draft(
    name,
    category,
    description,
    mandatory,
    rule_type,
    rule_config,
    threshold,
    expected_value,
    verification_source,
    weight,
):
    return {
        "requirement_name": name,
        "category": category,
        "description": description,
        "mandatory": mandatory,
        "rule_type": rule_type,
        "rule_config": rule_config,
        "threshold": threshold,
        "expected_value": expected_value,
        "verification_source": verification_source,
        "weight": weight,
        "policy_reference": None,
    }


def analyze_tender_text(text: str) -> dict:
    """Parse tender text into requirement drafts. Returns {"requirements": [...]}."""
    text = text or ""
    lower = text.lower()
    sentences = _sentences(text)
    drafts: list[dict] = []

    def has(pattern: str) -> bool:
        return re.search(pattern, lower) is not None

    # --- Statutory registrations -------------------------------------------
    if has(r"\bgst\b|goods and services tax"):
        drafts.append(
            _draft(
                "GST Registration",
                "STATUTORY",
                "Bidder must hold an active GST registration, verified against the GSTN portal.",
                True,
                "REGISTRATION_STATUS",
                {"source": "GSTN", "identifier_field": "gstin", "require_status": "ACTIVE"},
                "Active GST registration",
                "ACTIVE",
                "GSTN",
                15,
            )
        )
    if has(r"\bpan\b|permanent account number"):
        drafts.append(
            _draft(
                "PAN Verification",
                "STATUTORY",
                "Bidder PAN must be active as per the income-tax (PAN_IT) portal.",
                True,
                "REGISTRATION_STATUS",
                {"source": "PAN_IT", "identifier_field": "pan", "require_status": "ACTIVE"},
                "Active PAN",
                "ACTIVE",
                "PAN_IT",
                10,
            )
        )
    if has(r"udyam|\bmsme\b|micro.{0,20}small.{0,20}medium"):
        drafts.append(
            _draft(
                "Udyam/MSME Registration",
                "REGISTRATION",
                "Bidder should hold an active Udyam/MSME registration.",
                True,
                "REGISTRATION_STATUS",
                {"source": "UDYAM", "identifier_field": "udyam", "require_status": "ACTIVE"},
                "Active Udyam registration",
                "ACTIVE",
                "UDYAM",
                10,
            )
        )

    # --- Financial: turnover -------------------------------------------------
    for s in sentences:
        if "turnover" in s.lower():
            m = _AMOUNT_RE.search(s)
            if m:
                amount = _inr_to_int(m.group(1), m.group(2))
                label = _inr_display(amount)
                drafts.append(
                    _draft(
                        f"Minimum Turnover {label}",
                        "FINANCIAL",
                        f"Bidder must demonstrate minimum turnover of {label} "
                        f"(detected clause: '{s[:120]}').",
                        True,
                        "MINIMUM",
                        {
                            "value_source": "extracted.turnover_inr",
                            "operator": ">=",
                            "value": amount,
                        },
                        f"≥ {label}",
                        str(amount),
                        None,
                        15,
                    )
                )
                break

    # --- Experience: years ----------------------------------------------------
    for s in sentences:
        if "experience" in s.lower():
            m = _YEARS_RE.search(s)
            if m:
                years = float(m.group(1))
                drafts.append(
                    _draft(
                        f"Minimum {years:g} Years Experience",
                        "EXPERIENCE",
                        f"Bidder must have at least {years:g} years of relevant experience "
                        f"(detected clause: '{s[:120]}').",
                        True,
                        "MINIMUM",
                        {
                            "value_source": "extracted.experience_years",
                            "operator": ">=",
                            "value": years,
                        },
                        f"≥ {years:g} years",
                        str(years),
                        None,
                        10,
                    )
                )
                break

    # --- Local content ---------------------------------------------------------
    for s in sentences:
        if "local content" in s.lower():
            m = _PCT_RE.search(s)
            if m:
                pct = float(m.group(1))
                drafts.append(
                    _draft(
                        f"Make in India Local Content ≥ {pct:g}%",
                        "LOCAL_CONTENT",
                        f"Bidder must declare at least {pct:g}% local content "
                        f"(detected clause: '{s[:120]}').",
                        True,
                        "MINIMUM",
                        {
                            "value_source": "extracted.local_content_pct",
                            "operator": ">=",
                            "value": pct,
                        },
                        f"≥ {pct:g}%",
                        str(pct),
                        None,
                        10,
                    )
                )
                break

    # --- OEM -------------------------------------------------------------------
    if has(r"\boem\b|original equipment manufacturer"):
        drafts.append(
            _draft(
                "OEM Authorization",
                "OEM",
                "Bidder must submit a valid OEM authorization certificate.",
                True,
                "DOCUMENT_REQUIRED",
                {"document_types": ["OEM_AUTHORIZATION"]},
                "OEM authorization certificate submitted",
                "OEM_AUTHORIZATION",
                None,
                10,
            )
        )

    # --- EPFO / ESIC -------------------------------------------------------------
    if has(r"\bepfo\b|employees' provident fund|provident fund"):
        drafts.append(
            _draft(
                "EPFO Registration",
                "STATUTORY",
                "Bidder must hold an active EPFO registration.",
                True,
                "REGISTRATION_STATUS",
                {"source": "EPFO", "identifier_field": "epfo_code", "require_status": "ACTIVE"},
                "Active EPFO registration",
                "ACTIVE",
                "EPFO",
                5,
            )
        )
    if has(r"\besic\b|employees' state insurance|state insurance"):
        drafts.append(
            _draft(
                "ESIC Registration",
                "STATUTORY",
                "Bidder must hold an active ESIC registration.",
                True,
                "REGISTRATION_STATUS",
                {"source": "ESIC", "identifier_field": "esic_code", "require_status": "ACTIVE"},
                "Active ESIC registration",
                "ACTIVE",
                "ESIC",
                5,
            )
        )

    # --- Income tax --------------------------------------------------------------
    if has(r"\bitr\b|income[\s-]?tax return"):
        drafts.append(
            _draft(
                "Income Tax Compliance",
                "STATUTORY",
                "Bidder must have filed income tax returns (verified via PAN_IT itr_filed_upto).",
                True,
                "EXISTENCE",
                {"value_source": "verification.PAN_IT.itr_filed_upto"},
                "ITR filed",
                "present",
                "PAN_IT",
                5,
            )
        )

    # --- Integrity: blacklist / debarment -----------------------------------------
    if has(r"blacklist|debar"):
        drafts.append(
            _draft(
                "Blacklisting / Debarment Check",
                "INTEGRITY",
                "Bidder must not be blacklisted or debarred by any government authority.",
                True,
                "CUSTOM_RULE",
                {
                    "expression": "ctx.get('verification', {}).get('BLACKLIST', {})"
                    ".get('data', {}).get('blacklisted', False) == False"
                },
                "Not blacklisted/debarred",
                "blacklisted == False",
                "BLACKLIST",
                5,
            )
        )

    # --- Startup -------------------------------------------------------------------
    if has(r"startup"):
        drafts.append(
            _draft(
                "Startup India Recognition",
                "REGISTRATION",
                "Startup bidders should submit a valid Startup India recognition certificate.",
                False,
                "DOCUMENT_REQUIRED",
                {"document_types": ["STARTUP_INDIA_CERTIFICATE"]},
                "Startup India certificate submitted",
                "STARTUP_INDIA_CERTIFICATE",
                None,
                5,
            )
        )

    # Deduplicate by requirement name, preserving order.
    seen = set()
    unique = []
    for d in drafts:
        if d["requirement_name"] not in seen:
            seen.add(d["requirement_name"])
            unique.append(d)
    return {"requirements": unique}


# --- Internal-field inference for the tender wizard ---------------------------
# The wizard UI no longer asks the Procurement Officer for rule_type /
# verification_source / rule_config — those are implementation-level fields.
# When a requirement is saved WITHOUT a rule_config (e.g. typed manually in
# Step 2), this deterministic keyword inference fills those internal fields in
# so the compliance engine keeps working unchanged. Requirements that already
# carry a rule_config (analyze-draft output, standard template) are left alone.


def _parse_threshold_number(threshold: str | None):
    """Best-effort numeric parse of a free-text threshold.

    Handles ₹/Rs/INR amounts with lakh/crore units, year counts, percentages
    and plain numbers. Returns None when nothing parseable is found.
    """
    t = (threshold or "").strip()
    if not t:
        return None
    m = _AMOUNT_RE.search(t)
    if m:
        return _inr_to_int(m.group(1), m.group(2))
    m = _YEARS_RE.search(t)
    if m:
        return float(m.group(1))
    m = _PCT_RE.search(t)
    if m:
        return float(m.group(1))
    m = re.search(r"[\d,]+(?:\.\d+)?", t)
    if m:
        try:
            return float(m.group(0).replace(",", ""))
        except ValueError:
            return None
    return None


def infer_requirement_metadata(name: str, threshold: str | None = None) -> dict:
    """Infer internal requirement fields from the requirement name.

    Returns a dict with ``rule_type``, ``verification_source``, ``category``
    and ``rule_config``. The mappings mirror :func:`analyze_tender_text` so a
    manually typed requirement (e.g. "GST Registration") gets the same internal
    wiring as its extracted counterpart.

    Unrecognized names fall back to a safe EXISTENCE check with an empty
    config — the engine then reports MISSING (officer review) instead of
    crashing. A MINIMUM whose threshold has no parseable number also falls
    back to EXISTENCE for the same reason.
    """
    n = (name or "").lower()

    def _registration(source: str, identifier_field: str, category: str = "STATUTORY") -> dict:
        return {
            "rule_type": "REGISTRATION_STATUS",
            "verification_source": source,
            "category": category,
            "rule_config": {
                "source": source,
                "identifier_field": identifier_field,
                "require_status": "ACTIVE",
            },
        }

    def _minimum(value_source: str, category: str, threshold: str | None) -> dict:
        value = _parse_threshold_number(threshold)
        if value is None:
            return {
                "rule_type": "EXISTENCE",
                "verification_source": None,
                "category": category,
                "rule_config": {},
            }
        return {
            "rule_type": "MINIMUM",
            "verification_source": None,
            "category": category,
            "rule_config": {
                "value_source": value_source,
                "operator": ">=",
                "value": value,
            },
        }

    if re.search(r"\bgst\b", n):
        return _registration("GSTN", "gstin")
    if re.search(r"\bpan\b", n):
        return _registration("PAN_IT", "pan")
    if re.search(r"udyam|msme", n):
        return _registration("UDYAM", "udyam", "REGISTRATION")
    if re.search(r"epfo|provident fund", n):
        return _registration("EPFO", "epfo_code")
    if re.search(r"esic|state insurance", n):
        return _registration("ESIC", "esic_code")
    if re.search(r"\bitr\b|income[-\s]?tax", n):
        return {
            "rule_type": "EXISTENCE",
            "verification_source": "PAN_IT",
            "category": "STATUTORY",
            "rule_config": {"value_source": "verification.PAN_IT.itr_filed_upto"},
        }
    if re.search(r"blacklist|debar", n):
        return {
            "rule_type": "CUSTOM_RULE",
            "verification_source": "BLACKLIST",
            "category": "INTEGRITY",
            "rule_config": {
                "expression": "ctx.get('verification', {}).get('BLACKLIST', {})"
                              ".get('data', {}).get('blacklisted', False) == False"
            },
        }
    if re.search(r"\boem\b", n):
        return {
            "rule_type": "BOOLEAN",
            "verification_source": None,
            "category": "OEM",
            "rule_config": {
                "value_source": "extracted.oem_authorization_valid",
                "expected": True,
            },
        }
    if re.search(r"turnover", n):
        return _minimum("extracted.turnover_inr", "FINANCIAL", threshold)
    if re.search(r"past performance", n):
        return _minimum("extracted.past_performance_pct", "EXPERIENCE", threshold)
    if re.search(r"experience", n):
        return _minimum("extracted.experience_years", "EXPERIENCE", threshold)
    if re.search(r"local content|\bmii\b|make in india", n):
        return _minimum("extracted.local_content_pct", "LOCAL_CONTENT", threshold)
    if re.search(r"\bemd\b|earnest", n):
        return _minimum("extracted.emd_amount_inr", "FINANCIAL", threshold)
    if re.search(r"startup", n):
        return {
            "rule_type": "DOCUMENT_REQUIRED",
            "verification_source": None,
            "category": "REGISTRATION",
            "rule_config": {"document_types": ["STARTUP_INDIA_CERTIFICATE"]},
        }
    if re.search(r"document|dossier|certificate", n):
        return {
            "rule_type": "DOCUMENT_REQUIRED",
            "verification_source": None,
            "category": "DOCUMENT",
            "rule_config": {"document_types": ["BID_DOSSIER"]},
        }
    return {
        "rule_type": "EXISTENCE",
        "verification_source": None,
        "category": "TECHNICAL",
        "rule_config": {},
    }
