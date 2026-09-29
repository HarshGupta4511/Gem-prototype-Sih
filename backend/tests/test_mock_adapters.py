"""Tests for the mock government verification adapters (CONTRACT §10).

Every response must carry ``is_mock: True`` — nothing here implies live
government access.
"""
from app.adapters.blacklist_adapter import BlacklistAdapter
from app.adapters.esic_adapter import ESICAdapter
from app.adapters.gst_adapter import GSTNAdapter
from app.adapters.udyam_adapter import UdyamAdapter


def test_gstn_hit():
    r = GSTNAdapter().verify("27AAFCA1234E1Z5")
    assert r["status"] == "VERIFIED"
    assert r["is_mock"] is True
    assert r["data"]["legal_name"] == "Apex Flow Systems Private Limited"
    assert r["data"]["status"] == "ACTIVE"


def test_gstn_unknown_identifier_not_found():
    r = GSTNAdapter().verify("27ZZZZZ9999Z9Z9Z9")
    assert r["status"] == "NOT_FOUND"
    assert r["is_mock"] is True


def test_udyam_expired():
    # Seed scenario E: Udyam record expired -> EXPIRED check status.
    r = UdyamAdapter().verify("UDYAM-MH-19-0056789")
    assert r["status"] == "EXPIRED"
    assert r["data"]["status"] == "EXPIRED"


def test_esic_unavailable_simulated_downtime():
    # Seed scenario A: ESIC portal simulated as unavailable.
    r = ESICAdapter().verify("11000012345678901")
    assert r["status"] == "UNAVAILABLE"
    assert r["is_mock"] is True


def test_esic_unknown_not_found():
    r = ESICAdapter().verify("11000567890123456")
    assert r["status"] == "NOT_FOUND"


def test_blacklist_hit_debarred():
    # Seed scenario D.
    r = BlacklistAdapter().verify("Deccan Industrial Traders")
    assert r["status"] == "VERIFIED"
    assert r["is_mock"] is True
    assert r["data"]["debarred"] is True
    assert r["data"]["authority"] == "CPCL"


def test_blacklist_clean_company():
    r = BlacklistAdapter().verify("Some Nonexistent Company Xyz")
    assert r["status"] == "VERIFIED"
    assert r["data"]["blacklisted"] is False
    assert r["data"]["debarred"] is False


def test_identifier_normalization_lowercase():
    r = GSTNAdapter().verify("27aafca1234e1z5")
    assert r["status"] == "VERIFIED"
    assert r["data"]["gstin"] == "27AAFCA1234E1Z5"
