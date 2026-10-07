"""Deterministic regex extraction with canonical normalization (CONTRACT §9 step 4).

Confidence is fixed per pattern family: 0.95–0.99 (never 1.0 — honest
mocking: regex is strong but not infallible).
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- patterns
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
UDYAM_RE = re.compile(r"\bUDYAM-[A-Z]{2}-\d{2}-\d{7}\b")
CIN_RE = re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+91[\s\-]?)?[6-9]\d{9}(?!\d)")

_MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?"
)
DATE_RE = re.compile(
    r"\b(?P<iso>\d{4}-\d{1,2}-\d{1,2})"
    r"|\b(?P<dmy>\d{1,2}[-/]\d{1,2}[-/]\d{4})"
    rf"|\b(?P<mdy>\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}})\b",
    re.IGNORECASE,
)
AMOUNT_RE = re.compile(
    r"(?:₹|Rs\.?|INR)\s*\d[\d,]*(?:\.\d+)?\s*(?:crores?|lakhs?|lacs?)?",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percents?\b)", re.IGNORECASE)
# Experience duration: "Experience: 5 years" (labeled line) or
# "5 years of experience" (prose). Captures the numeric value only.
EXPERIENCE_RE = re.compile(
    r"\bexperience\s*:\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b"
    r"|\b(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\s+of\s+experience\b",
    re.IGNORECASE,
)
# EPFO establishment code: "MH/123456/001" (state / establishment / extension).
EPFO_RE = re.compile(r"\b[A-Z]{2}/\d{4,7}/\d{2,4}\b")
# ESIC employer/IP code: 17 digits. Context-gated (too generic alone).
ESIC_RE = re.compile(r"(?<!\d)\d{17}(?!\d)")
# Labeled-line extractors for the new demo evidence templates.
# "Financial Year: 2023-24" (ITR document only — the balance sheet uses its
# own "Balance Sheet Year" label so the two facts never merge).
ITR_FY_RE = re.compile(
    r"(?im)^[ \t]*Financial Year[ \t]*:[ \t]*(\d{4}\s*[-\u2013]\s*\d{2,4})[ \t]*$"
)
# "Balance Sheet Year: 2023-24".
BS_YEAR_RE = re.compile(
    r"(?im)^[ \t]*Balance Sheet Year[ \t]*:[ \t]*(\d{4}\s*[-\u2013]\s*\d{2,4})[ \t]*$"
)
# "ISO Certificate Number: ISO-2024-88412".
ISO_CERT_NO_RE = re.compile(
    r"(?im)^[ \t]*ISO Certificate Number[ \t]*:[ \t]*([A-Za-z0-9][\w\-.]*?)[ \t]*$"
)
# "ISO Valid Until: 31-03-2027" (DD-MM-YYYY) or "ISO Valid Until: 2027-03-31"
# (YYYY-MM-DD, as written by the demo seed) via the existing date normalizer.
ISO_VALID_UNTIL_RE = re.compile(
    r"(?im)^[ \t]*ISO Valid Until[ \t]*:[ \t]*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})"
)

PATTERNS: dict[str, re.Pattern] = {
    "pan": PAN_RE,
    "gstin": GSTIN_RE,
    "udyam": UDYAM_RE,
    "cin": CIN_RE,
    "email": EMAIL_RE,
    "phone": PHONE_RE,
    "date": DATE_RE,
    "amount": AMOUNT_RE,
    "percent": PERCENT_RE,
    "experience": EXPERIENCE_RE,
    "epfo": EPFO_RE,
    "esic": ESIC_RE,
    "itr_fy": ITR_FY_RE,
    "bs_year": BS_YEAR_RE,
    "iso_cert_no": ISO_CERT_NO_RE,
    "iso_valid_until": ISO_VALID_UNTIL_RE,
}

# Canonical field names for identifier patterns (no context needed).
_DIRECT_FIELDS = {
    "pan": ("pan", 0.99),
    "gstin": ("gstin", 0.99),
    "udyam": ("udyam_number", 0.99),
    "cin": ("cin", 0.99),
    "email": ("email", 0.98),
    "phone": ("phone", 0.97),
    "epfo": ("epfo_code", 0.97),
}

_CONTEXT_CHARS = 40  # how far back we look for disambiguating keywords


def _context(text: str, start: int) -> str:
    return text[max(0, start - _CONTEXT_CHARS) : start].lower()


# Document-aware fallback labels for values whose surrounding context does
# not disambiguate them. A bare date/amount on an EMD receipt is not the
# same semantic field as a bare date/amount on a GST certificate — the
# fallback keeps them document-scoped so they are never falsely compared
# across documents. Only used when no contextual label matches.
_DOC_DATE_FALLBACK = {
    "GST_CERTIFICATE": "registration_date",
    "PAN_CERTIFICATE": "issue_date",
    "UDYAM_CERTIFICATE": "registration_date",
    "EMD_RECEIPT": "receipt_date",
    "EMD_PAYMENT": "receipt_date",
    "ISO_9001_CERTIFICATE": "issue_date",
    "BALANCE_SHEET": "reporting_date",
    "ITR_DOCUMENT": "filing_date",
    "MCA21_CERTIFICATE": "incorporation_date",
    "EPFO_CERTIFICATE": "registration_date",
    "ESIC_CERTIFICATE": "registration_date",
}

_DOC_AMOUNT_FALLBACK = {
    "EMD_RECEIPT": "emd_amount_inr",
    "EMD_PAYMENT": "emd_amount_inr",
    "BALANCE_SHEET": "turnover_inr",
    "TURNOVER_CERTIFICATE": "turnover_inr",
}


def _classify_date(ctx: str, doc_type: str | None = None) -> tuple[str, float]:
    # Specific contextual labels first (highest confidence).
    if "valid" in ctx:
        return "valid_until", 0.97
    if "incorporat" in ctx:
        return "incorporation_date", 0.97
    if "regist" in ctx:
        return "registration_date", 0.97
    if "receipt" in ctx or "payment date" in ctx:
        return "receipt_date", 0.97
    if "expir" in ctx:
        return "expiry_date", 0.97
    if "issue" in ctx and "reissue" not in ctx:
        return "issue_date", 0.96
    if "report" in ctx:
        return "reporting_date", 0.96
    if "birth" in ctx or "dob" in ctx:
        return "date_of_birth", 0.96
    if "filing" in ctx or "filed" in ctx:
        return "filing_date", 0.96
    # Document-aware fallback — never a bare generic "date".
    if doc_type and doc_type in _DOC_DATE_FALLBACK:
        return _DOC_DATE_FALLBACK[doc_type], 0.90
    return "date", 0.90


def _classify_amount(ctx: str, doc_type: str | None = None) -> tuple[str, float]:
    if "emd" in ctx:
        return "emd_amount_inr", 0.97
    if "turnover" in ctx:
        return "turnover_inr", 0.97
    if "net worth" in ctx or "networth" in ctx:
        return "net_worth_inr", 0.96
    if doc_type and doc_type in _DOC_AMOUNT_FALLBACK:
        return _DOC_AMOUNT_FALLBACK[doc_type], 0.90
    return "amount_inr", 0.90


def _classify_percent(ctx: str, doc_type: str | None = None) -> tuple[str, float]:
    if "past performance" in ctx:
        return "past_performance_pct", 0.97
    if "local content" in ctx:
        return "local_content_pct", 0.97
    # Percentages without a clear label stay generic but document-scoped at
    # the semantic layer; keep the raw name stable for compatibility.
    return "percent", 0.90


def normalize_amount(raw: str) -> int | None:
    """'₹12.4 crore' / 'Rs 1,24,00,000' / 'INR 50 lakh' -> int INR."""
    if not raw:
        return None
    # drop parenthetical remarks like "(approx)" before parsing
    raw = re.sub(r"\([^)]*\)", "", raw)
    lowered = raw.lower()
    multiplier = 1
    if "crore" in lowered:
        multiplier = 10_000_000
    elif "lakh" in lowered or "lac" in lowered:
        multiplier = 100_000
    cleaned = re.sub(r"[₹,\s]", "", raw)
    cleaned = re.sub(r"(?i)^(rs\.?|inr)", "", cleaned)
    cleaned = re.sub(r"(?i)(crores?|lakhs?|lacs?)$", "", cleaned)
    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return None


def normalize_date(raw: str) -> str | None:
    """Any supported date spelling -> 'YYYY-MM-DD' ISO. None if unparseable."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        from dateutil import parser as date_parser

        if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", raw):
            # ISO already: parse without dayfirst so month/day are not swapped
            return date_parser.parse(raw).strftime("%Y-%m-%d")
        return date_parser.parse(raw, dayfirst=True).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def normalize_percent(raw: str) -> float | None:
    """'62%' / '62 percent' -> 62.0. None if unparseable."""
    if not raw:
        return None
    m = re.search(r"\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _normalize(field_name: str, raw: str) -> str:
    if field_name in ("pan", "gstin", "cin", "udyam_number"):
        return raw.strip().upper()
    if field_name == "email":
        return raw.strip().lower()
    if field_name == "phone":
        digits = re.sub(r"\D", "", raw)
        return digits[-10:] if len(digits) >= 10 else digits
    if field_name in (
        "valid_until", "incorporation_date", "iso_valid_until", "date",
        "registration_date", "receipt_date", "expiry_date", "issue_date",
        "reporting_date", "date_of_birth", "filing_date",
    ):
        return normalize_date(raw) or raw.strip()
    if field_name in ("turnover_inr", "amount_inr", "emd_amount_inr", "net_worth_inr"):
        amount = normalize_amount(raw)
        return str(amount) if amount is not None else raw.strip()
    if field_name in ("local_content_pct", "past_performance_pct", "percent"):
        pct = normalize_percent(raw)
        return str(pct) if pct is not None else raw.strip()
    if field_name == "experience_years":
        try:
            return str(float(raw.strip()))
        except ValueError:
            return raw.strip()
    return raw.strip()


def extract_all(
    text: str,
    page_number: int | None = None,
    doc_type: str | None = None,
) -> list[dict]:
    """Run every pattern over *text*.

    Returns a list of dicts: {field_name, field_value (raw match),
    normalized_value (str), confidence, method="REGEX", page_number}.
    Exact duplicate (field, raw, page) hits are collapsed.

    ``doc_type`` (e.g. "GST_CERTIFICATE") makes the date/amount/percent
    fallbacks document-aware so a bare date on an EMD receipt never gets
    the same semantic field name as a bare date on a GST certificate.
    """
    results: list[dict] = []
    seen: set[tuple[str, str, int | None]] = set()
    if not text:
        return results

    for key, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            if not raw:
                continue
            ctx = _context(text, match.start())
            if key in _DIRECT_FIELDS:
                field_name, confidence = _DIRECT_FIELDS[key]
            elif key == "date":
                field_name, confidence = _classify_date(ctx, doc_type)
            elif key == "amount":
                field_name, confidence = _classify_amount(ctx, doc_type)
            elif key == "percent":
                field_name, confidence = _classify_percent(ctx, doc_type)
            elif key == "experience":
                # Capture groups 1/2 hold the numeric value; the surrounding
                # wording ("Experience:" / "years of experience") is the gate.
                num = match.group(1) or match.group(2)
                if not num:
                    continue
                raw = num
                field_name, confidence = "experience_years", 0.96
            elif key == "esic":
                # 17 digits is too generic to trust without ESIC context.
                if "esic" not in ctx and "insurance" not in ctx:
                    continue
                field_name, confidence = "esic_code", 0.96
            elif key == "itr_fy":
                # Labeled line only; group(1) is the "2023-24" value.
                raw = match.group(1)
                field_name, confidence = "itr_financial_year", 0.96
            elif key == "bs_year":
                raw = match.group(1)
                field_name, confidence = "financial_year", 0.96
            elif key == "iso_cert_no":
                raw = match.group(1)
                field_name, confidence = "iso_certificate_number", 0.96
            elif key == "iso_valid_until":
                raw = match.group(1)
                field_name, confidence = "iso_valid_until", 0.96
            else:  # pragma: no cover - defensive
                continue
            dedupe_key = (field_name, raw, page_number)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            results.append(
                {
                    "field_name": field_name,
                    "field_value": raw,
                    "normalized_value": _normalize(field_name, raw),
                    "confidence": confidence,
                    "method": "REGEX",
                    "page_number": page_number,
                }
            )
    return results
