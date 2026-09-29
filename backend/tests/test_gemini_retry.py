"""Retry behavior for Gemini LLM calls (no network calls).

Covers: 429/503 are retried with backoff and eventually succeed, a
permanent error (400) is not retried, and repeated transient failures
raise after exhausting attempts.
"""
import io
import json
import urllib.error

import pytest

from app.services.llm_service import GeminiProvider, LLMError, post_json_with_retry


class _FakeHeaders(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.test", code=code, msg="boom",
        hdrs=_FakeHeaders(), fp=io.BytesIO(b"{}"),
    )


def _ok_payload() -> dict:
    return {
        "choices": [{
            "message": {"content": json.dumps({"pan": "ABCDE1234F"})}
        }]
    }


def test_retries_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return _FakeResp(_ok_payload())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    out = post_json_with_retry(object(), timeout=5, name="gemini")
    assert out["choices"][0]["message"]["content"]
    assert calls["n"] == 3


def test_503_retry_then_extract_fields_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(503)
        return _FakeResp(_ok_payload())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    p = GeminiProvider(model="gemini-flash-latest", api_key="k")
    out = p.extract_fields("BID_DOSSIER", "some text", "d.pdf")
    assert out["pan"] == "ABCDE1234F"
    assert calls["n"] == 2


def test_400_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(400)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(LLMError):
        GeminiProvider(model="m", api_key="k").extract_fields("X", "t", "f.pdf")
    assert calls["n"] == 1


def test_exhausted_retries_raise(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise _http_error(429)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(LLMError):
        GeminiProvider(model="m", api_key="k").extract_fields("X", "t", "f.pdf")
    assert calls["n"] == 4
