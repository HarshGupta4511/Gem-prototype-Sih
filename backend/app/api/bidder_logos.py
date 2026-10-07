"""Bidder logo endpoints — display-only company images.

Design constraint: NO database schema change. Logos live on disk at
``{UPLOAD_DIR}/bidder_logos/{bidder_id}.png`` — every upload is normalized
to PNG via Pillow. The file's existence IS the record: no column, no table,
no migration.

Logos are purely cosmetic. Nothing in the verification, compliance, risk,
integrity or recommendation pipeline reads this directory, so a logo can
never influence a score or finding.
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import ensure_upload_dir
from app.core.deps import get_current_user, get_db, require_officer
from app.models.models import Bidder, User

router = APIRouter(prefix="/api/bidders", tags=["bidder-logos"])

_OFFICER = require_officer()

log = logging.getLogger(__name__)

MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_MAGIC_PREFIXES = {
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
    ".webp": b"RIFF",  # full check also requires b"WEBP" at offset 8
}


def logo_dir() -> Path:
    """Directory holding bidder logos; created on demand."""
    d = ensure_upload_dir() / "bidder_logos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logo_path(bidder_id: int) -> Path:
    """Deterministic on-disk path for a bidder's logo (always PNG)."""
    return logo_dir() / f"{int(bidder_id)}.png"


def validate_and_normalize_logo(filename: str | None, content: bytes) -> bytes:
    """Validate an uploaded logo and return normalized PNG bytes.

    Raises ``ValueError`` with a human-readable message when invalid:
    unsupported extension, over the 2 MB limit, magic-byte mismatch, or
    unreadable image data.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported image type '{ext or '(none)'}'. "
            f"Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}."
        )
    if len(content) > MAX_LOGO_BYTES:
        raise ValueError(
            f"Image too large: {len(content)} bytes exceeds the "
            f"{MAX_LOGO_BYTES // (1024 * 1024)} MB limit."
        )
    if not content.startswith(_MAGIC_PREFIXES[ext]):
        raise ValueError(
            f"File content does not match its '{ext}' extension "
            f"(magic bytes mismatch). The file may be corrupt or renamed."
        )
    if ext == ".webp" and b"WEBP" not in content[:16]:
        raise ValueError("File is not a valid WebP image.")
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
        # Re-open after verify() (verify leaves the image unusable).
        with Image.open(io.BytesIO(content)) as img:
            rgb = img.convert("RGB")
            buf = io.BytesIO()
            rgb.save(buf, format="PNG")
            return buf.getvalue()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("File is not a readable image.") from exc


@router.post("/{bidder_id}/logo")
async def upload_bidder_logo(
    bidder_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Upload or replace a bidder's display-only logo (officer only).

    Accepts JPG/JPEG/PNG/WebP (≤ 2 MB, magic-byte checked); the image is
    normalized to PNG and stored at ``bidder_logos/{bidder_id}.png``.
    """
    bidder = db.get(Bidder, bidder_id)
    if bidder is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bidder not found"
        )
    content = await file.read()
    try:
        png = validate_and_normalize_logo(file.filename, content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None
    path = logo_path(bidder_id)
    path.write_bytes(png)
    log.info("Bidder %s logo uploaded (%d bytes PNG)", bidder_id, len(png))
    return {
        "bidder_id": bidder_id,
        "logo_url": f"/api/bidders/{bidder_id}/logo",
        "size_bytes": len(png),
    }


@router.get("/{bidder_id}/logo")
def get_bidder_logo(
    bidder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Serve a bidder's logo (any authenticated officer). 404 when absent."""
    path = logo_path(bidder_id)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No logo for this bidder"
        )
    return FileResponse(
        path, media_type="image/png", filename=f"bidder-{bidder_id}-logo.png"
    )


@router.delete("/{bidder_id}/logo", status_code=status.HTTP_204_NO_CONTENT)
def delete_bidder_logo(
    bidder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_OFFICER),
):
    """Remove a bidder's logo (officer only). Idempotent: always 204."""
    path = logo_path(bidder_id)
    if path.exists():
        path.unlink()
        log.info("Bidder %s logo removed", bidder_id)
    return None
