"""Server-side CAPTCHA for the officer login form.

Generates short, human-readable security codes rendered as SVG images and
validates them on login. Pure standard library — no extra dependency, no
external service, no network call.

Design notes (kept honest):
- This is a *demo-grade* CAPTCHA: it stops casual bots and proves the login
  form has a human-verification step for the SIH demo. It is NOT hardened
  against a determined OCR attacker.
- Challenges live in process memory with a short TTL and are single-use.
  That is correct for the single-worker deployment (Render runs
  WEB_CONCURRENCY=1); a multi-worker setup would need a shared store.
"""
from __future__ import annotations

import secrets
import time
import uuid
from urllib.parse import quote

# Ambiguous glyphs (0/O, 1/I/L) are excluded so officers never mistype.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6
TTL_SECONDS = 300

# captcha_id -> (solution, expires_at_epoch)
_STORE: dict[str, tuple[str, float]] = {}


def _purge_expired(now: float | None = None) -> None:
    now = time.time() if now is None else now
    expired = [cid for cid, (_, exp) in _STORE.items() if exp <= now]
    for cid in expired:
        del _STORE[cid]


def _random_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))


def _render_svg(code: str) -> str:
    """Render the code as a noisy SVG image (170x64)."""
    rng = secrets.SystemRandom()
    width, height = 170, 64
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#eef2f7"/>',
    ]
    # Wavy interference lines.
    for _ in range(3):
        y0 = rng.randint(8, height - 8)
        amp = rng.randint(4, 10)
        color = rng.choice(["#94a3b8", "#64748b", "#38bdf8"])
        d = f"M -5 {y0} "
        x = -5
        while x < width + 5:
            x += rng.randint(12, 26)
            d += f"Q {x - 8} {y0 + rng.choice([-amp, amp])} {x} {y0 + rng.randint(-4, 4)} "
        parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.4" opacity="0.7"/>'
        )
    # Random speckle dots.
    for _ in range(28):
        cx = rng.randint(0, width)
        cy = rng.randint(0, height)
        r = rng.uniform(0.8, 2.2)
        color = rng.choice(["#94a3b8", "#64748b", "#1e40af"])
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="{color}" opacity="0.55"/>'
        )
    # The code itself: one rotated glyph at a time.
    colors = ["#1e3a8a", "#0f172a", "#1d4ed8", "#334155", "#0c4a6e"]
    slot = width / CODE_LENGTH
    for i, ch in enumerate(code):
        x = slot * i + slot / 2 + rng.uniform(-6, 6)
        y = height / 2 + rng.uniform(-4, 8)
        rot = rng.uniform(-22, 22)
        size = rng.randint(26, 32)
        color = rng.choice(colors)
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="Georgia, serif" '
            f'font-size="{size}" font-weight="bold" fill="{color}" '
            f'text-anchor="middle" transform="rotate({rot:.1f} {x:.1f} {y:.1f})">{ch}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def generate() -> tuple[str, str]:
    """Create a challenge.

    Returns ``(captcha_id, image_data_uri)``. The data URI can be used
    directly as an ``<img src>``.
    """
    _purge_expired()
    code = _random_code()
    captcha_id = uuid.uuid4().hex
    _STORE[captcha_id] = (code, time.time() + TTL_SECONDS)
    svg = _render_svg(code)
    return captcha_id, "data:image/svg+xml," + quote(svg)


def verify(captcha_id: str | None, text: str | None) -> bool:
    """Validate a solution. Challenges are single-use and time-bound."""
    _purge_expired()
    if not captcha_id or not text:
        return False
    entry = _STORE.pop(captcha_id, None)
    if entry is None:
        return False
    solution, _ = entry
    return solution == text.strip().upper()


def _test_reset() -> None:
    """Clear the store. Test-only hook."""
    _STORE.clear()
