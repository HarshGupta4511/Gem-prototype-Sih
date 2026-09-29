"""Tests for entity resolution (CONTRACT §6 IDENTITY_MATCH)."""
from app.engines.entity_resolution import names_match, normalize_name


def test_normalize_name_strips_pvt_ltd():
    assert normalize_name("Apex Flow Systems Pvt Ltd") == "APEX FLOW SYSTEMS"


def test_normalize_name_strips_private_limited_and_llp():
    assert normalize_name("Apex Flow Systems Private Limited") == "APEX FLOW SYSTEMS"
    assert normalize_name("Fusion Petro Equipment LLP") == "FUSION PETRO EQUIPMENT"


def test_names_match_equivalent_legal_forms():
    assert names_match("Apex Flow Systems Pvt Ltd",
                       "Apex Flow Systems Private Limited")


def test_names_match_crestline_mismatch_case():
    # Seed scenario C: docs say "Crestline Pumps Pvt Ltd" but the mock portal
    # returns "Crestline Trading Co" -> must NOT match.
    assert not names_match("Crestline Pumps Pvt Ltd", "Crestline Trading Co")


def test_names_match_identical():
    assert names_match("Bharat Mech Works", "Bharat Mech Works")
