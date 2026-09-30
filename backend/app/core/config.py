"""Application configuration (pydantic-settings).

Values come from environment variables / a `.env` file at the backend root,
falling back to the defaults below. Import `settings` anywhere config is needed.
"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_upload_dir() -> Path:
    # backend/app/core/config.py -> parents[2] == backend/
    return Path(__file__).resolve().parents[2] / "uploads"


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./bidverify.db"
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    UPLOAD_DIR: Path = Field(default_factory=_default_upload_dir)
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024
    LLM_PROVIDER: str = "mock"
    OPENAI_API_KEY: str | None = None
    # Gemini (free tier via Google AI Studio): one key powers BOTH the LLM
    # extraction provider (LLM_PROVIDER=gemini) and vision OCR
    # (OCR_PROVIDER=gemini). Never commit a real key — use a local .env.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"  # Lite models get a separate, larger free-quota bucket (~500/day)
    # OCR engine for scanned PDFs: "paddle" (local PaddleOCR) or "gemini"
    # (Gemini vision API — needs GEMINI_API_KEY).
    OCR_PROVIDER: str = "paddle"
    # Auto-run the demo seed on startup when the tenders table is empty.
    # Disable in production via AUTO_SEED=false.
    AUTO_SEED: bool = True
    # Extra CORS origins (comma-separated) for hosted frontends, e.g.
    # CORS_ORIGINS=https://bidverify-frontend.onrender.com
    CORS_ORIGINS: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def is_dev_secret() -> bool:
    """True when JWT_SECRET is still the insecure development default."""
    return settings.JWT_SECRET == "dev-secret-change-me"


def ensure_upload_dir() -> Path:
    """Create the upload directory on demand and return its path."""
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return settings.UPLOAD_DIR
