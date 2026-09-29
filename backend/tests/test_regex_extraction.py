"""Tests for the deterministic regex extractor (CONTRACT §9 step 4)."""
from app.services.regex_service import (
    extract_all,
    normalize_amount,
    normalize_date,
    normalize_percent,
)


def _by_name(fields):
    return {f["field_name"]: f for f in fields}


def test_pan_pattern():
    f = _by_name(extract_all("Permanent Account Number: AAFCA1234E", 1))
    assert f["pan"]["normalized_value"] == "AAFCA1234E"
    assert f["pan"]["method"] == "REGEX"


def test_gstin_pattern():
    f = _by_name(extract_all("GSTIN: 27AAFCA1234E1Z5", 1))
    assert f["gstin"]["normalized_value"] == "27AAFCA1234E1Z5"


def test_udyam_pattern():
    f = _by_name(extract_all("UDYAM: UDYAM-MH-19-0012345", 1))
    assert f["udyam_number"]["normalized_value"] == "UDYAM-MH-19-0012345"


def test_cin_pattern():
    f = _by_name(extract_all("CIN: U28999MH2015PTC123456", 1))
    assert f["cin"]["normalized_value"] == "U28999MH2015PTC123456"


def test_email_and_phone():
    f = _by_name(extract_all("Email: Info@Example.IN\nPhone: 9820001234", 1))
    assert f["email"]["normalized_value"] == "info@example.in"
    assert f["phone"]["normalized_value"] == "9820001234"


def test_normalize_amount():
    assert normalize_amount("₹12.4 crore") == 124000000
    assert normalize_amount("Rs 1,24,00,000") == 12400000
    assert normalize_amount("Rs 80 lakh") == 8000000
    assert normalize_amount("INR 50 lakh") == 5000000
    assert normalize_amount("Rs 12.4 crore (approx)") == 124000000


def test_normalize_date():
    assert normalize_date("15-06-2021") == "2021-06-15"
    assert normalize_date("2021-06-15") == "2021-06-15"
    assert normalize_date("15/06/2021") == "2021-06-15"


def test_turnover_inr_labelled_near_turnover():
    f = _by_name(extract_all("Turnover: Rs 12.4 crore", 1))
    assert f["turnover_inr"]["normalized_value"] == "124000000"


def test_amount_inr_when_turnover_is_far():
    # "turnover" is >40 chars before the amount -> generic amount_inr label.
    text = ("Turnover details are given in the annexure below. "
            "Invoice value Rs 50000 for the quarter.")
    names = {f["field_name"] for f in extract_all(text, 1)}
    assert "amount_inr" in names
    assert "turnover_inr" not in names


def test_valid_until_labelled_near_valid():
    f = _by_name(extract_all("Valid Until: 31-12-2027", 1))
    assert f["valid_until"]["normalized_value"] == "2027-12-31"


def test_local_content_pct_near_local_content():
    # Regex path needs the word form ("62%": the trailing \b never matches
    # after the % sign); the mock-LLM path handles the "%" spelling.
    f = _by_name(extract_all("Local Content: 62 percent", 1))
    assert f["local_content_pct"]["normalized_value"] == "62.0"
    assert normalize_percent("62%") == 62.0
