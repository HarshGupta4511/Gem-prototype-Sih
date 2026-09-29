"""Text extraction: PyMuPDF first, OCR fallback for scanned pages.

OCR engines (``settings.OCR_PROVIDER``):
- ``"paddle"`` (default): local PaddleOCR, no key needed.
- ``"gemini"``: Gemini vision API via Google's OpenAI-compatible endpoint —
  needs ``GEMINI_API_KEY`` (free tier via Google AI Studio). One page image
  per request; transcription prompt keeps reading order.

Both heavy imports are lazy so the service module is importable without the
optional dependencies installed. Nothing here ever raises for OCR problems —
callers get (None, error) instead.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PAGE_MARKER = "\n--- PAGE {n} ---\n"
GEMINI_OCR_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
)
GEMINI_OCR_DPI = 150  # vision models don't need 200dpi; keeps payloads small


def extract_text_pymupdf(file_path: str) -> tuple[str, int]:
    """Return (full_text, page_count).

    Pages are joined with ``\\n--- PAGE n ---\\n`` markers so callers can
    split per-page text back out for page_number attribution.
    """
    import fitz  # lazy: PyMuPDF is required for the pipeline, not the import

    doc = fitz.open(file_path)
    try:
        chunks: list[str] = []
        for i, page in enumerate(doc):
            chunks.append(PAGE_MARKER.format(n=i + 1))
            chunks.append(page.get_text() or "")
        return "".join(chunks), len(doc)
    finally:
        doc.close()


def split_pages(full_text: str) -> list[tuple[int, str]]:
    """Inverse of the PAGE_MARKER joining: [(page_number, text), ...]."""
    import re

    parts = re.split(r"\n--- PAGE (\d+) ---\n", full_text or "")
    pages: list[tuple[int, str]] = []
    # parts = ['', '1', text1, '2', text2, ...]
    for i in range(1, len(parts), 2):
        try:
            pages.append((int(parts[i]), parts[i + 1]))
        except (IndexError, ValueError):
            continue
    return pages


def ocr_available() -> bool:
    """True when the configured OCR engine can run."""
    from app.core.config import settings

    if settings.OCR_PROVIDER == "gemini":
        return bool(settings.GEMINI_API_KEY)
    try:
        import paddleocr  # noqa: F401

        return True
    except ImportError:
        return False


def run_ocr(file_path: str) -> tuple[str | None, str | None]:
    """OCR every page. Returns (text, error); never raises.

    Dispatches to the configured engine (``settings.OCR_PROVIDER``).
    The returned text uses the same PAGE markers as extract_text_pymupdf.
    """
    from app.core.config import settings

    if settings.OCR_PROVIDER == "gemini":
        return run_ocr_gemini(file_path)
    return run_ocr_paddle(file_path)


def run_ocr_gemini(file_path: str) -> tuple[str | None, str | None]:
    """OCR via Gemini vision (one page image per request). Never raises."""
    from app.core.config import settings

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return None, "OCR_UNAVAILABLE"
    try:
        import fitz

        doc = fitz.open(file_path)
        try:
            chunks: list[str] = []
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=GEMINI_OCR_DPI)
                img_b64 = _pixmap_to_b64_png(pix)
                page_text = _gemini_transcribe_page(
                    img_b64, api_key, settings.GEMINI_MODEL
                )
                chunks.append(PAGE_MARKER.format(n=i + 1))
                chunks.append(page_text)
            text = "".join(chunks)
            if len(text.strip()) < 10:
                return None, "OCR_FAILED: no text recognized"
            return text, None
        finally:
            doc.close()
    except Exception as exc:  # never propagate — pipeline depends on this
        log.warning("Gemini OCR failed for %s: %s", file_path, exc)
        return None, f"OCR_FAILED: {exc}"


def _pixmap_to_b64_png(pix) -> str:
    """Encode a fitz Pixmap as base64 PNG."""
    import base64

    return base64.b64encode(pix.tobytes("png")).decode()


def _gemini_transcribe_page(img_b64: str, api_key: str, model: str) -> str:
    """Transcribe one page image with Gemini vision. Raises on failure."""
    import json
    import urllib.request

    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Transcribe all text visible in this document page "
                                "image. Return only the transcribed text, preserving "
                                "reading order and line breaks. If no text is visible, "
                                "return an empty string."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}"
                            },
                        },
                    ],
                }
            ],
        }
    ).encode()
    req = urllib.request.Request(
        GEMINI_OCR_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    from app.services.llm_service import post_json_with_retry

    payload = post_json_with_retry(req, timeout=120, name="gemini-ocr")
    return payload["choices"][0]["message"]["content"] or ""


def run_ocr_paddle(file_path: str) -> tuple[str | None, str | None]:
    """OCR every page image at 200 dpi with local PaddleOCR. Never raises."""
    try:
        import paddleocr  # noqa: F401
    except ImportError:
        return None, "OCR_UNAVAILABLE"

    try:
        import fitz
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(lang="en", show_log=False)
        doc = fitz.open(file_path)
        try:
            chunks: list[str] = []
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=200)
                lines = _ocr_pixmap(ocr, pix)
                chunks.append(PAGE_MARKER.format(n=i + 1))
                chunks.append("\n".join(lines))
            text = "".join(chunks)
            if len(text.strip()) < 10:
                return None, "OCR_FAILED: no text recognized"
            return text, None
        finally:
            doc.close()
    except Exception as exc:  # never propagate — pipeline depends on this
        log.warning("OCR failed for %s: %s", file_path, exc)
        return None, f"OCR_FAILED: {exc}"


def _ocr_pixmap(ocr, pix) -> list[str]:
    """Run one PaddleOCR pass over a fitz Pixmap, tolerating API variance."""
    lines: list[str] = []
    result = None
    try:
        import numpy as np

        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        if pix.n == 4:  # drop alpha for the OCR model
            img = img[:, :, :3]
        result = ocr.ocr(img)
    except ImportError:
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            pix.save(tmp.name)
            tmp_path = tmp.name
        try:
            result = ocr.ocr(tmp_path)
        finally:
            os.unlink(tmp_path)
    for block in result or []:
        for line in block or []:
            try:
                text = line[1][0]
            except (TypeError, IndexError):
                continue
            if text:
                lines.append(str(text))
    return lines
