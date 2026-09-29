"""Format validators for Indian business identifiers (CONTRACT.md §9 patterns).

Pure functions, no DB access. These check structural format only — they do not
verify that an identifier is genuinely registered (that is the adapters' job).
"""
import re

_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
_CIN_RE = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$")


def _clean(value: object) -> str:
    return value.strip().upper() if isinstance(value, str) else ""


def is_valid_pan_format(value: object) -> bool:
    """PAN: 5 letters, 4 digits, 1 letter (e.g. AAFCA1234E)."""
    return bool(_PAN_RE.fullmatch(_clean(value)))


def is_valid_gstin_format(value: object) -> bool:
    """GSTIN: 2-digit state code + 10-char PAN + entity code + 'Z' + checksum.

    Also sanity-checks that the state code is within 01-38.
    """
    v = _clean(value)
    if not _GSTIN_RE.fullmatch(v):
        return False
    state_code = int(v[:2])
    return 1 <= state_code <= 38


def is_valid_udyam_format(value: object) -> bool:
    """Udyam registration number: UDYAM-XX-00-0000000 (e.g. UDYAM-MH-19-0012345)."""
    return bool(_UDYAM_RE.fullmatch(_clean(value)))


def is_valid_cin_format(value: object) -> bool:
    """CIN: listing status (L/U) + 5 digits + 2-letter state + 4-digit year
    + 3-letter ownership + 6-digit registration number."""
    return bool(_CIN_RE.fullmatch(_clean(value)))
