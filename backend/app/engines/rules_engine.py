"""Rules engine — the ONLY decider of PASS/FAIL (§6 of CONTRACT.md).

Deterministic evaluation of tender requirements against a per-bid context.
Statuses: PASS, FAIL, MISSING, EXPIRED, MISMATCH, REVIEW_REQUIRED.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

try:  # Built by a sibling agent; fallback keeps the engine testable standalone.
    from app.engines.entity_resolution import names_match as _names_match
except Exception:  # pragma: no cover - fallback only
    from difflib import SequenceMatcher

    def _names_match(a, b, threshold=85):  # type: ignore[misc]
        ratio = SequenceMatcher(None, str(a).strip().upper(), str(b).strip().upper()).ratio()
        return ratio * 100 >= threshold


LOW_CONFIDENCE_THRESHOLD = 0.70
DEFAULT_CONFIDENCE = 0.95
STATUSES = ("PASS", "FAIL", "MISSING", "EXPIRED", "MISMATCH", "REVIEW_REQUIRED", "NOT_APPLICABLE")
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
                 "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y")


def _get(req, key, default=None):
    """Accept both attribute-style (ORM) and dict-style requirement objects."""
    return req.get(key, default) if isinstance(req, dict) else getattr(req, key, default)


def _short_field(vs: str) -> str:
    return vs.split(".")[-1] if isinstance(vs, str) else str(vs)


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return isinstance(value, (list, dict)) and len(value) == 0


def _to_number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^0-9.\-]", "", str(value).replace(",", ""))
    try:
        return float(s) if s not in ("", ".", "-", "-.") else None
    except ValueError:
        return None


def _fmt_num(x) -> str:
    f = float(x)
    return str(int(f)) if f.is_integer() else str(f)


def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ("true", "yes", "y", "1"):
        return True
    return False if s in ("false", "no", "n", "0") else None


def resolve_value_source(value_source: str, context: dict):
    """Resolve ``extracted.<f>`` | ``bidder.<f>`` | ``verification.<SRC>.<path>``.

    Returns (value, evidence_list)."""
    if not isinstance(value_source, str) or not value_source:
        return None, []
    extracted, bidder = context.get("extracted") or {}, context.get("bidder") or {}
    verification, evidence_index = context.get("verification") or {}, context.get("evidence_index") or {}

    if value_source.startswith("extracted."):
        field = value_source[len("extracted."):]
        return extracted.get(field), [dict(e) for e in evidence_index.get(field, [])]
    if value_source.startswith("bidder."):
        field = value_source[len("bidder."):]
        value = bidder.get(field)
        return value, [{"field": field, "value": value, "source": "bidder declaration"}]
    if value_source.startswith("verification."):
        parts = value_source.split(".")
        if len(parts) < 3:
            return None, []
        source, path = parts[1], parts[2:]
        check = verification.get(source)
        if not check:
            return None, []
        value = check.get("data") or {}
        # Tolerate an explicit leading "data." segment: the path is into response data.
        if path and path[0] == "data":
            path = path[1:]
        for p in path:
            value = value.get(p) if isinstance(value, dict) else None
            if value is None:
                break
        ev = [{"source": f"verification:{source}", "field": ".".join(path), "value": value,
               "check_id": check.get("check_id"), "confidence": check.get("confidence")}]
        return value, ev
    return None, []


def _present_doc_types(documents) -> set:
    return {d.get("document_type") if isinstance(d, dict) else d for d in documents or []}


class RulesEngine:
    """Evaluates tender requirements. The ONLY decider of PASS/FAIL."""

    def evaluate(self, requirement, context: dict) -> dict:
        rule_type = str(_get(requirement, "rule_type") or "").upper()
        config = _get(requirement, "rule_config") or {}
        if isinstance(config, str):
            try:
                import json
                config = json.loads(config)
            except Exception:
                config = {}
        try:
            weight = float(_get(requirement, "weight", 0.0) or 0.0)
        except (TypeError, ValueError):
            weight = 0.0

        handler = getattr(self, f"_rule_{rule_type.lower()}", None)
        raw = handler(config, context) if handler else (
            "REVIEW_REQUIRED",
            f"REVIEW_REQUIRED — unknown rule type '{rule_type}'; officer review required.",
            f"unknown rule type {rule_type}", [])
        # REGISTRATION_STATUS appends a reg_check dict as a 5th element.
        reg_check = raw[4] if len(raw) == 5 else None
        status, explanation, rule_applied, evidence = raw[0], raw[1], raw[2], raw[3]

        # Confidence rule (§6) considers EXTRACTION confidence only — verification
        # check confidences (source "verification:*") are not extraction confidences
        # and must not trigger the low-confidence downgrade/signal.
        confs = [float(e["confidence"]) for e in evidence
                 if isinstance(e.get("confidence"), (int, float))
                 and not str(e.get("source") or "").startswith("verification:")]
        min_conf = min(confs) if confs else DEFAULT_CONFIDENCE
        low_confidence = min_conf < LOW_CONFIDENCE_THRESHOLD

        # Confidence rule (§6): downgrade PASS on weak extraction only.
        if status == "PASS" and low_confidence:
            status = "REVIEW_REQUIRED"
            if explanation.startswith("PASS because "):
                explanation = "REVIEW_REQUIRED — " + explanation[len("PASS because "):]
            explanation = explanation.rstrip() + " Low extraction confidence — officer review required."

        result = {"status": status, "explanation": explanation, "rule_applied": rule_applied,
                  "evidence": evidence, "confidence": round(min_conf, 4), "weight": weight,
                  "low_confidence": low_confidence, "rule_type": rule_type,
                  "mandatory": bool(_get(requirement, "mandatory", False))}
        for key in ("category", "verification_source"):
            val = _get(requirement, key)
            if val is not None:
                result[key] = val
        if reg_check is not None:
            result["reg_check"] = reg_check
        return result

    def evaluate_all(self, requirements, context: dict) -> list[dict]:
        out = []
        for req in requirements:
            r = self.evaluate(req, context)
            r["requirement_id"] = _get(req, "id")
            r["requirement_name"] = _get(req, "requirement_name")
            out.append(r)
        return out

    # ------------------------------------------------------------------ rules

    def _rule_existence(self, config, context):
        vs, field = config.get("value_source"), _short_field(config.get("value_source"))
        value, evidence = resolve_value_source(vs, context)
        applied = f"{field} is present"
        if _is_missing(value):
            return ("MISSING", f"MISSING — {field} was not found in the submitted documents or declaration.",
                    applied, evidence)
        return ("PASS", f"PASS because {field} is present (value: '{value}').", applied, evidence)

    def _rule_document_required(self, config, context):
        wanted = config.get("document_types") or []
        hits = [t for t in wanted if t in _present_doc_types(context.get("documents"))]
        doc_index, evidence = context.get("document_index") or {}, []
        for t in hits:
            for e in doc_index.get(t) or [{}]:
                evidence.append({"document_type": t, "document_id": e.get("document_id"),
                                 "filename": e.get("filename"), "value": "present"})
        if hits:
            return ("PASS", f"PASS because required document found: {', '.join(hits)}.",
                    f"document present: {', '.join(hits)} (required one of {wanted})", evidence)
        return ("MISSING", f"MISSING — none of the required documents {wanted} was submitted "
                "(only PROCESSED documents count).", f"document required: one of {wanted}", evidence)

    def _rule_equality(self, config, context):
        vs, expected = config.get("value_source"), config.get("expected")
        field = _short_field(vs)
        value, evidence = resolve_value_source(vs, context)
        applied = f"{field} == {expected}"
        if _is_missing(value):
            return ("MISSING", f"MISSING — {field} was not found; cannot compare with expected '{expected}'.",
                    applied, evidence)
        match = (value.strip().lower() == str(expected).strip().lower()
                 if isinstance(value, str) and isinstance(expected, str) else value == expected)
        if match:
            return ("PASS", f"PASS because {field} = '{value}' matches expected '{expected}'.", applied, evidence)
        return ("FAIL", f"FAIL — {field} = '{value}' does not match expected '{expected}'.", applied, evidence)

    def _rule_match(self, config, context):
        vs, pattern = config.get("value_source"), config.get("pattern", "")
        field = _short_field(vs)
        value, evidence = resolve_value_source(vs, context)
        applied = f"{field} matches /{pattern}/"
        if _is_missing(value):
            return ("MISSING", f"MISSING — {field} was not found; cannot apply pattern '{pattern}'.",
                    applied, evidence)
        try:
            hit = re.search(pattern, str(value))
        except re.error as exc:
            return ("REVIEW_REQUIRED", f"REVIEW_REQUIRED — invalid regex pattern '{pattern}': {exc}.",
                    applied, evidence)
        if hit:
            return ("PASS", f"PASS because {field} = '{value}' matches pattern '{pattern}'.", applied, evidence)
        return ("FAIL", f"FAIL — {field} = '{value}' does not match pattern '{pattern}'.", applied, evidence)

    def _rule_minimum(self, config, context):
        return self._minmax(config, context, ">=")

    def _rule_maximum(self, config, context):
        return self._minmax(config, context, "<=")

    def _minmax(self, config, context, operator):
        vs = config.get("value_source")
        target, field = config.get("value"), _short_field(vs)
        value, evidence = resolve_value_source(vs, context)
        actual = _to_number(value)
        applied = f"{field} {_fmt_num(actual) if actual is not None else '?'} {operator} " \
                  f"{_fmt_num(target) if target is not None else '?'}"
        if actual is None:
            return ("MISSING", f"MISSING — {field} is missing or non-numeric ('{value}'); "
                    f"cannot compare with {operator} {_fmt_num(target)}.", applied, evidence)
        ok = actual >= float(target) if operator == ">=" else actual <= float(target)
        if ok:
            return ("PASS", f"PASS because {field} {_fmt_num(actual)} {operator} {_fmt_num(target)}.",
                    applied, evidence)
        return ("FAIL", f"FAIL — {field} {_fmt_num(actual)} does not satisfy {operator} {_fmt_num(target)}.",
                applied, evidence)

    def _rule_date_validity(self, config, context):
        vs, field = config.get("value_source"), _short_field(config.get("value_source"))
        value, evidence = resolve_value_source(vs, context)
        today = _parse_date(context.get("today")) or datetime.now(timezone.utc).date()
        applied = f"{field} must be after {today.isoformat()}"
        d = _parse_date(value)
        if d is None:
            return ("MISSING", f"MISSING — no usable date found for {field} ('{value}').", applied, evidence)
        if d < today:
            return ("EXPIRED", f"EXPIRED — {field} date {d.isoformat()} is before {today.isoformat()}.",
                    applied, evidence)
        return ("PASS", f"PASS because {field} date {d.isoformat()} is on/after {today.isoformat()}.",
                applied, evidence)

    def _rule_date_range(self, config, context):
        vs, field = config.get("value_source"), _short_field(config.get("value_source"))
        lo, hi = _parse_date(config.get("min")), _parse_date(config.get("max"))
        value, evidence = resolve_value_source(vs, context)
        applied = f"{field} within {lo.isoformat() if lo else '?'}..{hi.isoformat() if hi else '?'}"
        d = _parse_date(value)
        if d is None:
            return ("MISSING", f"MISSING — no usable date found for {field} ('{value}').", applied, evidence)
        if (lo and d < lo) or (hi and d > hi):
            return ("FAIL", f"FAIL — {field} date {d.isoformat()} is outside "
                    f"{lo.isoformat() if lo else '…'}..{hi.isoformat() if hi else '…'}." , applied, evidence)
        return ("PASS", f"PASS because {field} date {d.isoformat()} is within the allowed range.",
                applied, evidence)

    def _rule_contains(self, config, context):
        vs, substring = config.get("value_source"), str(config.get("substring", ""))
        field = _short_field(vs)
        value, evidence = resolve_value_source(vs, context)
        applied = f"{field} contains '{substring}'"
        if _is_missing(value):
            return ("MISSING", f"MISSING — {field} was not found; cannot check for '{substring}'.",
                    applied, evidence)
        if substring.lower() in str(value).lower():
            return ("PASS", f"PASS because {field} contains '{substring}'.", applied, evidence)
        return ("FAIL", f"FAIL — {field} = '{value}' does not contain '{substring}'.", applied, evidence)

    def _rule_boolean(self, config, context):
        vs, expected = config.get("value_source"), config.get("expected")
        field = _short_field(vs)
        value, evidence = resolve_value_source(vs, context)
        applied = f"{field} == {expected}"
        actual = _to_bool(value)
        if actual is None:
            return ("MISSING", f"MISSING — {field} is missing or not interpretable as boolean ('{value}').",
                    applied, evidence)
        if actual == bool(expected):
            return ("PASS", f"PASS because {field} = {actual} matches expected {bool(expected)}.",
                    applied, evidence)
        return ("FAIL", f"FAIL — {field} = {actual} does not match expected {bool(expected)}.", applied, evidence)

    def _rule_registration_status(self, config, context):
        source = config.get("source")
        identifier_field = config.get("identifier_field")
        require_status = config.get("require_status", "ACTIVE")
        not_found_status = config.get("not_found_status", "FAIL")
        verification = context.get("verification") or {}
        identifier = None
        if identifier_field:
            identifier, _ = resolve_value_source(f"bidder.{identifier_field}", context)
            if _is_missing(identifier):
                identifier, _ = resolve_value_source(f"extracted.{identifier_field}", context)
        applied = f"{source} registration status == {require_status}"
        reg_check = {"source": source, "check_status": None, "data_status": None}

        check = verification.get(source)
        if not check:
            return ("REVIEW_REQUIRED",
                    f"REVIEW_REQUIRED — no verification performed for source {source}; "
                    f"cannot confirm {identifier_field} = '{identifier}'.", applied, [], reg_check)
        check_status = check.get("status")
        reg_check["check_status"] = check_status
        data = check.get("data") or {}
        data_status = data.get("status")
        reg_check["data_status"] = data_status
        evidence = [{"source": f"verification:{source}", "field": "status",
                     "value": data_status if check_status == "VERIFIED" else check_status,
                     "check_id": check.get("check_id"), "confidence": check.get("confidence"),
                     "identifier": identifier}]
        required = f"(required {require_status})"
        if check_status == "VERIFIED":
            if data_status == require_status:
                return ("PASS", f"PASS because {source} verification returned status '{data_status}' "
                        f"for {identifier_field} '{identifier}'.",
                        f"{source} status {data_status} {required}", evidence, reg_check)
            if data_status == "EXPIRED":
                return ("EXPIRED", f"EXPIRED — {source} reports status '{data_status}' for "
                        f"{identifier_field} '{identifier}'.",
                        f"{source} status {data_status} {required}", evidence, reg_check)
            return ("MISMATCH", f"MISMATCH — {source} reports status '{data_status}' for "
                    f"{identifier_field} '{identifier}', required '{require_status}'.",
                    f"{source} status {data_status} {required}", evidence, reg_check)
        if check_status == "MISMATCH":
            return ("MISMATCH", f"MISMATCH — {source} portal data does not match the declared "
                    f"{identifier_field} '{identifier}'.", applied, evidence, reg_check)
        if check_status == "NOT_FOUND":
            return (not_found_status, f"{not_found_status} — {source} has no record for "
                    f"{identifier_field} '{identifier}'.", applied, evidence, reg_check)
        if check_status == "EXPIRED":
            return ("EXPIRED", f"EXPIRED — {source} registration for {identifier_field} "
                    f"'{identifier}' has expired.", applied, evidence, reg_check)
        # UNAVAILABLE / REVIEW_REQUIRED from the adapter: never PASS/FAIL.
        return ("REVIEW_REQUIRED", f"REVIEW_REQUIRED — {source} verification is {check_status}; "
                f"cannot verify {identifier_field} '{identifier}'.", applied, evidence, reg_check)

    def _rule_identity_match(self, config, context):
        fields = config.get("fields") or ["legal_name"]
        bidder, extracted_by_doc = context.get("bidder") or {}, context.get("extracted_by_doc") or {}
        evidence, mismatches, checked = [], [], 0
        for field in fields:
            bidder_val = bidder.get(field)
            for doc_type, doc_fields in extracted_by_doc.items():
                doc_val = (doc_fields or {}).get(field)
                if _is_missing(bidder_val) or _is_missing(doc_val):
                    continue
                checked += 1
                evidence.append({"document_type": doc_type, "field": field,
                                 "bidder_value": bidder_val, "document_value": doc_val})
                sa, sb = str(bidder_val).strip(), str(doc_val).strip()
                if not (sa.lower() == sb.lower() or _names_match(sa, sb, threshold=85)):
                    mismatches.append((doc_type, field, bidder_val, doc_val))
        applied = f"identity match on {fields} vs documents (threshold 85)"
        if mismatches:
            details = "; ".join(f"bidder {f} '{bv}' vs {dt} '{dv}'" for dt, f, bv, dv in mismatches)
            return ("MISMATCH", f"MISMATCH — identity mismatch: {details}.", applied, evidence)
        if checked == 0:
            return ("REVIEW_REQUIRED", f"REVIEW_REQUIRED — no comparable {fields} values found across "
                    "bidder declaration and documents.", applied, evidence)
        return ("PASS", f"PASS because bidder identity ({', '.join(fields)}) matches all submitted "
                f"documents ({checked} comparison(s), threshold 85).", applied, evidence)

    def _rule_custom_rule(self, config, context):
        expression = config.get("expression", "")
        applied = f"custom rule: {expression}"
        # Restricted eval: no builtins except a small safe numeric/string allowlist
        # (no I/O, no imports, no attribute access beyond the expression itself).
        safe_builtins = {"int": int, "float": float, "str": str, "bool": bool,
                         "len": len, "min": min, "max": max, "abs": abs, "round": round}
        try:
            outcome = eval(expression, {"__builtins__": safe_builtins},
                           {"ctx": context, "context": context})
        except Exception as exc:
            return ("REVIEW_REQUIRED", f"REVIEW_REQUIRED — custom rule evaluation error: {exc}.",
                    applied, [])
        if isinstance(outcome, str) and outcome in STATUSES:
            status = outcome
        elif outcome is True:
            status = "PASS"
        elif outcome is False:
            status = "FAIL"
        else:
            return ("REVIEW_REQUIRED", "REVIEW_REQUIRED — custom rule did not return a bool or "
                    f"status (got {outcome!r}).", applied, [])
        verb = {"PASS": "passed", "FAIL": "failed"}.get(status, f"evaluated to {status}")
        return (status, f"{status} — custom rule {verb}: {expression}.", applied, [])
