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
}

# Canonical field names for identifier patterns (no context needed).
_DIRECT_FIELDS = {
    "pan": ("pan", 0.99),
    "gstin": ("gstin", 0.99),
    "udyam": ("udyam_number", 0.99),
    "cin": ("cin", 0.99),
    "email": ("email", 0.98),
    "phone": ("phone", 0.97),
}

_CONTEXT_CHARS = 40  # how far back we look for disambiguating keywords


def _context(text: str, start: int) -> str:
    return text[max(0, start - _CONTEXT_CHARS) : start].lower()


def _classify_date(ctx: str) -> tuple[str, float]:
    if "valid" in ctx:
        return "valid_until", 0.97
    if "incorporat" in ctx:
        return "incorporation_date", 0.97
    return "date", 0.95


def _classify_amount(ctx: str) -> tuple[str, float]:
    if "emd" in ctx:
        return "emd_amount_inr", 0.97
    if "turnover" in ctx:
        return "turnover_inr", 0.97
    return "amount_inr", 0.96


def _classify_percent(ctx: str) -> tuple[str, float]:
    if "past performance" in ctx:
        return "past_performance_pct", 0.97
    if "local content" in ctx:
        return "local_content_pct", 0.97
    return "percent", 0.96


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
    if field_name in ("valid_until", "incorporation_date", "date"):
        return normalize_date(raw) or raw.strip()
    if field_name in ("turnover_inr", "amount_inr", "emd_amount_inr"):
        amount = normalize_amount(raw)
        return str(amount) if amount is not None else raw.strip()
    if field_name in ("local_content_pct", "past_performance_pct", "percent"):
        pct = normalize_percent(raw)
        return str(pct) if pct is not None else raw.strip()
    return raw.strip()


def extract_all(text: str, page_number: int | None = None) -> list[dict]:
    """Run every pattern over *text*.

    Returns a list of dicts: {field_name, field_value (raw match),
    normalized_value (str), confidence, method="REGEX", page_number}.
    Exact duplicate (field, raw, page) hits are collapsed.
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
                field_name, confidence = _classify_date(ctx)
            elif key == "amount":
                field_name, confidence = _classify_amount(ctx)
            elif key == "percent":
                field_name, confidence = _classify_percent(ctx)
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
