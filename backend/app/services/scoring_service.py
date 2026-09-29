"""Compliance score — transparent, inspectable (§7 of CONTRACT.md).

score = 100 * Σ(weight × factor) / Σ(weight)
factor: PASS=1.0, REVIEW_REQUIRED=0.5, FAIL/MISSING/EXPIRED/MISMATCH=0.

Weight-0 and NOT_APPLICABLE requirements are excluded from the denominator
but still shown (weighted_contribution = 0).
"""

from __future__ import annotations

FACTOR = {
    "PASS": 1.0,
    "REVIEW_REQUIRED": 0.5,
    "FAIL": 0.0,
    "MISSING": 0.0,
    "EXPIRED": 0.0,
    "MISMATCH": 0.0,
    "NOT_APPLICABLE": None,
}


def _applicable(result: dict) -> bool:
    weight = result.get("weight", 0.0) or 0.0
    return result.get("status") != "NOT_APPLICABLE" and weight > 0


def compute_score(results: list[dict]) -> tuple[float, list[dict]]:
    """Compute the compliance score and set each result's weighted_contribution.

    Mutates ``results`` in place (adds ``weighted_contribution``) and returns
    ``(score, results)``. Score is rounded to 2 decimals.
    """
    denom = sum((r.get("weight", 0.0) or 0.0) for r in results if _applicable(r))

    total = 0.0
    for r in results:
        weight = r.get("weight", 0.0) or 0.0
        if not _applicable(r) or denom == 0:
            r["weighted_contribution"] = 0.0
            continue
        factor = FACTOR.get(r.get("status"), 0.0) or 0.0
        contribution = 100.0 * weight * factor / denom
        r["weighted_contribution"] = round(contribution, 2)
        total += weight * factor

    score = round(100.0 * total / denom, 2) if denom else 0.0
    return score, results
