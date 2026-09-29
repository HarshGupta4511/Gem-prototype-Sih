"""Tests for the transparent compliance score math (CONTRACT §7)."""
from app.services.scoring_service import compute_score


def _r(status, weight):
    return {"status": status, "weight": weight}


def test_score_math():
    score, out = compute_score([_r("PASS", 50), _r("FAIL", 50)])
    assert score == 50.0
    assert out[0]["weighted_contribution"] == 50.0
    assert out[1]["weighted_contribution"] == 0.0


def test_review_required_factor_half():
    score, _ = compute_score([_r("PASS", 50), _r("REVIEW_REQUIRED", 50)])
    assert score == 75.0


def test_weight_zero_excluded_from_denominator():
    score, out = compute_score([_r("PASS", 100), _r("MISSING", 0)])
    assert score == 100.0
    assert out[1]["weighted_contribution"] == 0.0


def test_full_example():
    # 15 PASS, 10 PASS, 10 REVIEW, 5 FAIL -> (15+10+5)/40*100 = 75
    score, _ = compute_score([_r("PASS", 15), _r("PASS", 10),
                              _r("REVIEW_REQUIRED", 10), _r("FAIL", 5)])
    assert score == 75.0


def test_empty_results():
    score, _ = compute_score([])
    assert score == 0.0
