"""Upload validation and storage (CONTRACT §5 documents endpoint).

validate_upload raises ValueError on: bad extension, oversize file,
or magic-byte mismatch. save_upload stores bytes under
UPLOAD_DIR / <bid_id> / "<uuid>_<safe filename>" and returns
(file_path, sha256_hex, size_bytes).
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from app.core.config import settings

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

MAGIC: dict[str, bytes] = {
    ".pdf": b"%PDF",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG",
}

_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def validate_upload(filename: str, content: bytes) -> None:
    """Raise ValueError with a clear message when the upload is invalid."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext or '(none)'}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if len(content) > settings.MAX_UPLOAD_BYTES:
        limit_mb = settings.MAX_UPLOAD_BYTES / (1024 * 1024)
        raise ValueError(
            f"File too large: {len(content)} bytes exceeds the "
            f"{limit_mb:.0f} MB limit."
        )
    magic = MAGIC[ext]
    if not content.startswith(magic):
        raise ValueError(
            f"File content does not match its '{ext}' extension "
            f"(magic bytes mismatch). The file may be corrupt or renamed."
        )


def mime_for(filename: str) -> str:
    return _MIME_BY_EXT.get(os.path.splitext(filename or "")[1].lower(),
                            "application/octet-stream")


def save_upload(content: bytes, filename: str, bid_id: int) -> tuple[str, str, int]:
    """Persist bytes; return (file_path, sha256_hex, size_bytes)."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(filename or "upload"))
    safe = (safe or "upload")[:100]
    digest = hashlib.sha256(content).hexdigest()
    dest_dir = Path(settings.UPLOAD_DIR) / str(bid_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{uuid.uuid4().hex}_{safe}"
    path.write_bytes(content)
    return str(path), digest, len(content)
