"""Gemini LLM + vision OCR provider selection (no network calls).

Covers: default stays mock, gemini selected only when configured,
graceful fallback without a key, and OCR availability reporting.
"""
from app.core.config import settings
from app.services import extraction_service, llm_service


def _patch(monkeypatch, **kwargs):
    for k, v in kwargs.items():
        monkeypatch.setattr(settings, k, v)


def test_default_is_mock(monkeypatch):
    _patch(monkeypatch, LLM_PROVIDER="mock", GEMINI_API_KEY="", OCR_PROVIDER="paddle")
    assert llm_service.get_llm_provider().name == "mock-llm-demo"


def test_gemini_selected_when_configured(monkeypatch):
    _patch(monkeypatch, LLM_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    p = llm_service.get_llm_provider()
    assert isinstance(p, llm_service.GeminiProvider)
    assert p.name == "gemini"
    assert "generativelanguage.googleapis.com" in p.endpoint
    assert p.model == settings.GEMINI_MODEL


def test_gemini_falls_back_to_mock_without_key(monkeypatch):
    _patch(monkeypatch, LLM_PROVIDER="gemini", GEMINI_API_KEY="")
    assert llm_service.get_llm_provider().name == "mock-llm-demo"


def test_openai_still_works(monkeypatch):
    _patch(
        monkeypatch,
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="test-key",
        GEMINI_API_KEY="",
    )
    p = llm_service.get_llm_provider()
    assert isinstance(p, llm_service.OpenAIProvider)
    assert not isinstance(p, llm_service.GeminiProvider)
    assert p.endpoint == "https://api.openai.com/v1/chat/completions"


def test_gemini_ocr_availability(monkeypatch):
    _patch(monkeypatch, OCR_PROVIDER="gemini", GEMINI_API_KEY="")
    assert extraction_service.ocr_available() is False
    _patch(monkeypatch, GEMINI_API_KEY="test-key")
    assert extraction_service.ocr_available() is True


def test_gemini_ocr_no_key_returns_unavailable(monkeypatch):
    _patch(monkeypatch, GEMINI_API_KEY="")
    text, err = extraction_service.run_ocr_gemini("/nonexistent.pdf")
    assert text is None
    assert err == "OCR_UNAVAILABLE"
