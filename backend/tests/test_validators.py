"""Tests for the Indian identifier format validators."""
from app.utils.validators import (
    is_valid_cin_format,
    is_valid_gstin_format,
    is_valid_pan_format,
    is_valid_udyam_format,
)


def test_pan_valid():
    assert is_valid_pan_format("AAFCA1234E")
    assert is_valid_pan_format("aafca1234e")  # cleaned + uppercased


def test_pan_invalid():
    assert not is_valid_pan_format("ABCDE1234")
    assert not is_valid_pan_format("AAFCA12345")
    assert not is_valid_pan_format("")
    assert not is_valid_pan_format(None)


def test_gstin_valid():
    assert is_valid_gstin_format("27AAFCA1234E1Z5")


def test_gstin_bad_state_code():
    # State code 99 is outside the valid 01-38 range.
    assert not is_valid_gstin_format("99AAFCA1234E1Z5")


def test_gstin_bad_format():
    assert not is_valid_gstin_format("27AAFCA1234E1Z")
    assert not is_valid_gstin_format("not-a-gstin")


def test_udyam_valid():
    assert is_valid_udyam_format("UDYAM-MH-19-0012345")


def test_udyam_invalid():
    assert not is_valid_udyam_format("UDYAM-MH-1-123")
    assert not is_valid_udyam_format("MH-19-0012345")


def test_cin_valid():
    assert is_valid_cin_format("U28999MH2015PTC123456")
    assert is_valid_cin_format("L12345AB1990XYZ654321")


def test_cin_invalid():
    assert not is_valid_cin_format("X123")
    assert not is_valid_cin_format("28999MH2015PTC123456")
