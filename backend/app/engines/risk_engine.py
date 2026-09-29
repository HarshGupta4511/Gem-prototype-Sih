"""Risk engine — independent of the compliance score (§8 of CONTRACT.md).

Builds weighted risk signals from verification outcomes, compliance results
and extraction quality. Level: any critical signal → CRITICAL; else
Σ weights ≥ 50 → HIGH, ≥ 25 → MEDIUM, else LOW.
"""

from __future__ import annotations

import re

# code -> (severity, weight). Severity strings per §8: critical|high|medium|low.
SIGNAL_WEIGHTS = {
    "BLACKLISTED": ("critical", 100),
    "DEBARRED": ("critical", 100),
    "PAN_MISMATCH": ("high", 40),
    "GST_NAME_MISMATCH": ("high", 40),
    "CIN_MISMATCH": ("high", 40),
    "MISSING_MANDATORY_DOC": ("high", 30),
    "EXPIRED_CERTIFICATE": ("high", 30),
    "FAILED_MANDATORY_REQUIREMENT": ("high", 25),
    "UNVERIFIED_SOURCE": ("medium", 15),
    "LOW_CONFIDENCE_EXTRACTION": ("medium", 10),
    "LARGE_VALUE_DISCREPANCY": ("medium", 15),
}

# Per-code caps applied when summing signal weights into the risk score.
SIGNAL_CAPS = {
    "MISSING_MANDATORY_DOC": 60,  # 30 per requirement, capped at 60
}

_PAN_RE = re.compile(r"\bPAN\b")
_GST_RE = re.compile(r"\bGST\b")


def _to_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^0-9.\-]", "", str(value).replace(",", ""))
    try:
        return float(s)
    except ValueError:
        return None


def assess(context: dict, results: list[dict], verification: dict | None = None) -> dict:
    """Assess bid risk. Returns {risk_level, risk_score, signals, risk_reasons, explanation}."""
    verification = verification or (context.get("verification") or {})
    bidder = context.get("bidder") or {}
    extracted = context.get("extracted") or {}

    signals: list[dict] = []

    def add(code: str, message: str):
        severity, weight = SIGNAL_WEIGHTS[code]
        signals.append(
            {"code": code, "message": message, "severity": severity, "weight": weight}
        )

    # --- Blacklist / debarment ------------------------------------------------
    blk = verification.get("BLACKLIST") or {}
    blk_data = blk.get("data") or {}
    if blk_data.get("blacklisted"):
        add(
            "BLACKLISTED",
            "Blacklisted by "
            f"{blk_data.get('authority', 'the blacklisting authority')}"
            f" — {blk_data.get('reason', 'listed as blacklisted')}"
            f" (period: {blk_data.get('period', 'unspecified')}).",
        )
    if blk_data.get("debarred"):
        add(
            "DEBARRED",
            "Debarred by "
            f"{blk_data.get('authority', 'the debarring authority')}"
            f" — {blk_data.get('reason', 'listed as debarred')}"
            f" (period: {blk_data.get('period', 'unspecified')}).",
        )

    # --- Per-result signals ----------------------------------------------------
    for r in results:
        name = r.get("requirement_name") or ""
        name_u = name.upper()
        vsrc = (r.get("verification_source") or "").upper()
        status = r.get("status")
        mandatory = bool(r.get("mandatory"))
        rule_type = (r.get("rule_type") or "").upper()
        expl = (r.get("explanation") or "").strip()

        if status == "MISMATCH":
            if _GST_RE.search(name_u) or vsrc == "GSTN":
                add(
                    "GST_NAME_MISMATCH",
                    f"GST identity mismatch on '{name}': {expl}",
                )
            elif _PAN_RE.search(name_u) or vsrc == "PAN_IT":
                add(
                    "PAN_MISMATCH",
                    f"PAN identity mismatch on '{name}': {expl}",
                )

        if status == "MISSING" and mandatory and rule_type in ("DOCUMENT_REQUIRED", "EXISTENCE"):
            add("MISSING_MANDATORY_DOC", f"Mandatory information/document missing for '{name}': {expl}")

        if status == "EXPIRED" and mandatory:
            add("EXPIRED_CERTIFICATE", f"Expired certificate for '{name}': {expl}")

        if status == "FAIL" and mandatory:
            add(
                "FAILED_MANDATORY_REQUIREMENT",
                f"Mandatory requirement failed for '{name}': {expl}",
            )

        if status == "REVIEW_REQUIRED" and rule_type == "REGISTRATION_STATUS":
            reg_check = r.get("reg_check") or {}
            check_status = reg_check.get("check_status")
            if check_status in (None, "UNAVAILABLE", "NOT_FOUND"):
                add(
                    "UNVERIFIED_SOURCE",
                    f"Registration status for '{name}' could not be verified "
                    f"(portal check: {check_status or 'not performed'}); officer review required.",
                )

        if r.get("low_confidence"):
            add(
                "LOW_CONFIDENCE_EXTRACTION",
                f"Low extraction confidence behind '{name}' "
                f"(confidence {r.get('confidence')}); officer review required.",
            )

    # --- MCA21 name mismatch ---------------------------------------------------
    mca = verification.get("MCA21") or {}
    if mca.get("status") == "MISMATCH":
        add(
            "CIN_MISMATCH",
            "MCA21 portal data does not match the declared company identity "
            f"({(mca.get('data') or {}).get('company_name', 'see verification check')}).",
        )

    # --- Declared vs extracted value discrepancy --------------------------------
    declared_turnover = _to_number(bidder.get("turnover_inr"))
    extracted_turnover = _to_number(extracted.get("turnover_inr"))
    if declared_turnover and extracted_turnover:
        denom = max(declared_turnover, extracted_turnover)
        if denom > 0 and abs(declared_turnover - extracted_turnover) / denom > 0.25:
            add(
                "LARGE_VALUE_DISCREPANCY",
                f"Declared turnover ({int(declared_turnover):,}) differs from extracted "
                f"turnover ({int(extracted_turnover):,}) by more than 25%.",
            )

    # --- Level -----------------------------------------------------------------
    code_totals: dict[str, float] = {}
    for s in signals:
        code_totals[s["code"]] = code_totals.get(s["code"], 0) + s["weight"]
    total = sum(
        min(t, SIGNAL_CAPS.get(code, t)) for code, t in code_totals.items()
    )

    if any(s["severity"] == "critical" for s in signals):
        level = "CRITICAL"
    elif total >= 50:
        level = "HIGH"
    elif total >= 25:
        level = "MEDIUM"
    else:
        level = "LOW"
    risk_score = round(min(100, total), 2)

    risk_reasons = [s["message"] for s in signals] or ["No risk signals detected."]
    top = ", ".join(s["code"] for s in signals[:3])
    explanation = (
        f"Risk assessment over {len(results)} compliance result(s) produced "
        f"{len(signals)} signal(s) with total weight {total:g} → risk level {level}."
    )
    if any(s["severity"] == "critical" for s in signals):
        explanation += f" Critical signal(s) present: {top}."
    elif signals:
        explanation += f" Top signals: {top}."
    explanation += " Risk is computed independently of the compliance score."

    return {
        "risk_level": level,
        "risk_score": risk_score,
        "signals": signals,
        "risk_reasons": risk_reasons,
        "explanation": explanation,
    }
