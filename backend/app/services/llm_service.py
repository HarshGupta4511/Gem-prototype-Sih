"""Pluggable LLM extraction (CONTRACT §9 step 5).

- ``MockLLMProvider`` (default): deterministic heuristics over labeled lines
  (``Label: value``) that the demo PDFs contain. Clearly labeled
  ``"provider": "mock-llm-demo"``.
- ``OpenAIProvider``: used only when ``settings.LLM_PROVIDER == "openai"``
  and ``OPENAI_API_KEY`` is set. Output keys are validated against the allowed
  schema; ANY failure raises ``LLMError`` (the pipeline records it and moves
  on — it never crashes the pipeline).
- ``GeminiProvider``: same chat-completions protocol via Google's
  OpenAI-compatible endpoint (``settings.LLM_PROVIDER == "gemini"`` and
  ``GEMINI_API_KEY`` set). Free tier via Google AI Studio — no extra deps.
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


def post_json_with_retry(req, timeout: int, name: str) -> dict:
    """POST a JSON request with retries on transient errors.

    Google's free tier rate-limits bursts (HTTP 429) and occasionally
    returns 503 under load — e.g. during demo seeding when many documents
    are extracted back-to-back. Retry with exponential backoff so one
    busy minute doesn't silently drop every LLM call to the regex
    fallback. Non-transient errors raise immediately.
    """
    import time
    import json
    import urllib.error
    import urllib.request

    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in (429, 500, 502, 503):
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            wait = float(retry_after) if retry_after else 2.0 * (2 ** attempt)
            log.warning("%s: transient HTTP %s (attempt %d/4); retrying in %.1fs",
                        name, exc.code, attempt + 1, wait)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc

ALLOWED_KEYS = {
    "legal_name",
    "trade_name",
    "turnover_inr",
    "turnover_period",
    "experience_years",
    "past_performance_pct",
    "local_content_pct",
    "emd_amount_inr",
    "oem_name",
    "oem_authorization_valid",
    "valid_until",
    "incorporation_date",
    "address",
    "email",
    "phone",
    "epfo_code",
    "esic_code",
    "udyam_number",
    "cin",
    "itr",
    "pan",
    "gstin",
    "startup_certificate_number",
    "debarment_declaration",
    "payment_reference",
    "payment_date",
    "beneficiary",
    "client_name",
    "dpiit_recognition",
    "registration_date",
    "confidence",
    "provider",
}


class LLMError(Exception):
    """Raised when an LLM provider cannot produce schema-valid output."""


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def extract_fields(
        self, document_type: str, text: str, filename: str
    ) -> dict:
        """Return a dict of allowed keys (+ 'provider', 'confidence')."""

    def suggest_requirements(self, tender_context: dict) -> list[dict]:
        """Suggest tender compliance requirements from tender context.

        Returns a list of dicts with keys: requirement_name, threshold,
        mandatory (bool), weight (number), description. Suggestions are
        ADVISORY — the officer reviews and confirms them before the tender
        is created. Base implementation raises: providers that cannot do
        genuine generation must say so explicitly.
        """
        raise LLMError(f"{self.name}: requirement suggestions not supported")


class MockLLMProvider(LLMProvider):
    """Deterministic heuristic extraction from ``Label: value`` lines."""

    name = "mock-llm-demo"

    # (label, canonical field, value transform) — longest labels first so
    # "Turnover Period" wins over "Turnover" on its own line.
    _LABELS: tuple[tuple[str, str, str], ...] = (
        ("Acknowledgement Number", "itr", "str"),
        ("ITR Acknowledgement", "itr", "str"),
        ("Legal Name", "legal_name", "str"),
        ("Trade Name", "trade_name", "str"),
        ("Turnover Period", "turnover_period", "str"),
        ("Turnover", "turnover_inr", "amount"),
        ("Experience", "experience_years", "experience"),
        ("Past Performance", "past_performance_pct", "percent"),
        ("Local Content", "local_content_pct", "percent"),
        ("EMD Amount", "emd_amount_inr", "amount"),
        ("OEM Name", "oem_name", "str"),
        ("OEM Authorization", "oem_authorization_valid", "bool"),
        ("Valid Until", "valid_until", "date"),
        ("Incorporation Date", "incorporation_date", "date"),
        ("Address", "address", "str"),
        ("Email", "email", "str"),
        ("Phone", "phone", "str"),
        ("EPFO Code", "epfo_code", "str"),
        ("ESIC Code", "esic_code", "str"),
        ("UDYAM", "udyam_number", "str"),
        ("CIN", "cin", "str"),
        ("PAN", "pan", "str"),
        ("GSTIN", "gstin", "str"),
        ("Certificate Number", "startup_certificate_number", "str"),
        ("DPIIT Recognition", "dpiit_recognition", "str"),
        ("Debarment Declaration", "debarment_declaration", "str"),
        ("Payment Reference", "payment_reference", "str"),
        ("Payment Date", "payment_date", "date"),
        ("Beneficiary", "beneficiary", "str"),
        ("Client", "client_name", "str"),
        ("Registration Date", "registration_date", "date"),
        ("ISO Certificate Number", "iso_certificate_number", "str"),
        ("ISO Valid From", "iso_valid_from", "date"),
        ("ISO Valid Until", "iso_valid_until", "date"),
        ("Financial Year", "itr_financial_year", "str"),
        ("Balance Sheet Year", "financial_year", "str"),
        ("Assessment Year", "assessment_year", "str"),
        ("Total Income", "total_income", "amount"),
        ("Auditor Name", "auditor_name", "str"),
        ("Company Status", "company_status", "str"),
    )

    def extract_fields(self, document_type: str, text: str, filename: str) -> dict:
        from app.services import regex_service

        out: dict = {}
        confidences: list[float] = []
        for label, field, kind in self._LABELS:
            # NOTE: horizontal whitespace only ([ \t]). The earlier \s*
            # form let an empty label swallow the next non-empty line
            # (e.g. "Client:" with no value consumed the next paragraph),
            # producing a false-positive extraction. Values stay single-line.
            pattern = re.compile(
                r"(?im)^[ \t]*" + re.escape(label)
                + r"(?:[ \t]+(?:number|registration|no\.?))?[ \t]*:[ \t]*([^\n]+?)[ \t]*$"
            )
            m = pattern.search(text or "")
            if not m:
                continue
            raw_line = m.group(0)
            raw_value = m.group(1).strip()
            value = self._transform(kind, raw_value, regex_service)
            if value is None:
                continue
            out[field] = value
            confidences.append(0.62 if "approx" in raw_line.lower() else 0.9)

        out["provider"] = self.name
        out["confidence"] = (
            sum(confidences) / len(confidences) if confidences else 0.9
        )
        return out

    @staticmethod
    def _transform(kind: str, raw: str, regex_service):
        if kind == "str":
            return raw or None
        if kind == "amount":
            return regex_service.normalize_amount(raw)
        if kind == "percent":
            return regex_service.normalize_percent(raw)
        if kind == "date":
            return regex_service.normalize_date(raw)
        if kind == "experience":
            m = re.search(r"\d+(?:\.\d+)?", raw)
            return float(m.group(0)) if m else None
        if kind == "bool":
            # Negation wins: "Invalid" contains "valid", so affirmative
            # substrings must never be tested first. Word boundaries keep
            # "no" from matching inside words like "notarized".
            lowered = raw.lower()
            if re.search(r"\b(no|not|invalid|unauthorized|false|rejected|denied)\b", lowered):
                return False
            if re.search(r"\b(yes|valid|true|authorized|approved)\b", lowered):
                return True
            return None
        return raw or None  # pragma: no cover


class OpenAIProvider(LLMProvider):
    """OpenAI chat-completions provider (stdlib urllib, no extra deps).

    ``endpoint`` is overridable so OpenAI-compatible APIs (e.g. Gemini's
    ``.../v1beta/openai/`` endpoint) can reuse the whole protocol.
    """

    name = "openai"
    _ENDPOINT = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        endpoint: str | None = None,
    ):
        from app.core.config import settings

        self.model = model or getattr(settings, "LLM_MODEL", "gpt-4o-mini")
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.endpoint = endpoint or self._ENDPOINT

    def _missing_key_error(self) -> LLMError:
        return LLMError(f"{self.name}: API key is not set")

    def _post_with_retry(self, req, timeout: int = 90) -> dict:
        return post_json_with_retry(req, timeout=timeout, name=self.name)

    def _chat_json(self, system: str, prompt: str, timeout: int = 90) -> object:
        """POST a chat-completion request and parse the JSON content."""
        import json
        import urllib.request

        if not self.api_key:
            raise self._missing_key_error()
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode()
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            payload = self._post_with_retry(req, timeout=timeout)
        except Exception as exc:
            raise LLMError(f"{self.name} request failed: {exc}") from exc
        try:
            return json.loads(payload["choices"][0]["message"]["content"])
        except Exception as exc:
            raise LLMError(f"Unparseable {self.name} response: {exc}") from exc

    def suggest_requirements(self, tender_context: dict) -> list[dict]:
        """Suggest compliance requirements for a tender (ADVISORY only).

        Never decides PASS/FAIL — the deterministic rules engine does that
        later. The officer reviews/edits every suggestion before creation.
        """
        ctx = "\n".join(
            f"{k}: {v}" for k, v in tender_context.items() if v not in (None, "")
        )
        prompt = (
            "You are a GeM (Government e-Marketplace, India) procurement expert. "
            "Suggest compliance requirements for the tender described below. "
            "Return ONLY a JSON object of the form "
            '{"requirements": [{"requirement_name": str, "threshold": str, '
            '"mandatory": bool, "weight": number, "description": str}]}. '
            "Rules: 6-10 requirements; requirement_name short and formal "
            '(e.g. "GST Registration", "Minimum Turnover", "OEM Authorization"); '
            'threshold as a human-readable criterion (e.g. "Minimum ₹10 lakh", '
            '"Valid registration required") or empty string if none; '
            "mandatory true for legal/statutory must-haves; weights are relative "
            "importance numbers (they will be normalized to sum 100 later — use "
            "roughly 5-25 per item); description one short sentence. "
            "Include statutory basics (GST, PAN) plus tender-specific ones "
            "(turnover, experience, OEM authorization, Make in India / local "
            "content, EMD where relevant).\n\n"
            f"TENDER:\n{ctx[:4000]}"
        )
        data = self._chat_json(
            "Suggest GeM tender compliance requirements as JSON.", prompt
        )
        if not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
            raise LLMError(f"{self.name}: response missing 'requirements' list")
        out: list[dict] = []
        for item in data["requirements"][:12]:
            if not isinstance(item, dict) or not item.get("requirement_name"):
                continue
            try:
                weight = float(item.get("weight") or 0)
            except (TypeError, ValueError):
                weight = 0
            out.append(
                {
                    "requirement_name": str(item["requirement_name"])[:120],
                    "threshold": str(item.get("threshold") or "")[:200],
                    "mandatory": bool(item.get("mandatory", True)),
                    "weight": max(0.0, weight),
                    "description": str(item.get("description") or "")[:300],
                }
            )
        if not out:
            raise LLMError(f"{self.name}: no usable requirements suggested")
        return out

    def extract_fields(self, document_type: str, text: str, filename: str) -> dict:
        import json
        import urllib.request

        if not self.api_key:
            raise self._missing_key_error()
        schema = ", ".join(sorted(ALLOWED_KEYS - {"provider", "confidence"}))
        prompt = (
            f"You extract structured fields from a {document_type} document "
            f"(file: {filename}). Return ONLY a JSON object with any of these keys: "
            f"{schema}. Dates as YYYY-MM-DD, amounts as integer INR, percents as "
            f"numbers, booleans as true/false. Omit keys you cannot find.\n\n"
            f"DOCUMENT TEXT:\n{text[:12000]}"
        )
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "Extract document fields as JSON."},
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode()
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            payload = self._post_with_retry(req)
        except Exception as exc:
            raise LLMError(f"{self.name} request failed: {exc}") from exc
        try:
            data = json.loads(payload["choices"][0]["message"]["content"])
        except Exception as exc:
            raise LLMError(f"Unparseable {self.name} response: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError(f"{self.name} response was not a JSON object")
        unknown = set(data) - ALLOWED_KEYS
        if unknown:
            raise LLMError(f"Unexpected keys from {self.name}: {sorted(unknown)}")
        data["provider"] = self.name
        return data


class GeminiProvider(OpenAIProvider):
    """Gemini via Google's OpenAI-compatible endpoint (free AI Studio tier).

    Same protocol as :class:`OpenAIProvider`; only the endpoint, model and
    key differ. One GEMINI_API_KEY also powers Gemini vision OCR
    (see ``extraction_service.run_ocr_gemini``).
    """

    name = "gemini"
    _ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        from app.core.config import settings

        super().__init__(
            model=model or settings.GEMINI_MODEL,
            api_key=api_key or settings.GEMINI_API_KEY,
            endpoint=self._ENDPOINT,
        )


def get_llm_provider() -> LLMProvider:
    """Return the configured provider (CONTRACT §1: default is the mock)."""
    from app.core.config import settings

    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return OpenAIProvider()
    if settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        return GeminiProvider()
    return MockLLMProvider()
