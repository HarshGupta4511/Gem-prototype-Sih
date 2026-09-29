"""Base class for (mock) government verification adapters.

Every adapter response carries ``is_mock: True`` — these adapters NEVER imply
live government access. All portal data is fictional demo data loaded from
``app/adapters/mock_data/*.json``.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Record-level mock statuses -> VerificationStatus values (contract §3).
# Unknown mock statuses degrade to REVIEW_REQUIRED: never a silent PASS/FAIL.
_RECORD_STATUS_TO_CHECK_STATUS = {
    "ACTIVE": "VERIFIED",
    "RECOGNIZED": "VERIFIED",
    "EXPIRED": "EXPIRED",
    "CANCELLED": "EXPIRED",
    "SUSPENDED": "REVIEW_REQUIRED",
}

_mock_data_cache: dict[str, Any] = {}


class GovernmentVerificationAdapter(ABC):
    """Common interface for all (mock) government verification adapters."""

    source: str  # AdapterSource value, e.g. "GSTN"

    @abstractmethod
    def verify(self, identifier: str) -> dict:
        """Return ``{"source", "status", "data", "timestamp", "is_mock": True, "confidence"}``."""

    # ------------------------------------------------------------------ #
    # helpers                                                             #
    # ------------------------------------------------------------------ #

    def _load_json(self, name: str) -> Any:
        """Load a mock-data JSON file (cached) from ``app/adapters/mock_data/``."""
        if name not in _mock_data_cache:
            path = Path(__file__).parent / "mock_data" / name
            with open(path, "r", encoding="utf-8") as fh:
                _mock_data_cache[name] = json.load(fh)
        return _mock_data_cache[name]

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize(identifier: str) -> str:
        """Normalize an identifier (strip + upper-case) before lookup."""
        return (identifier or "").strip().upper()

    def _not_found(self, identifier: str) -> dict:
        return {
            "source": self.source,
            "status": "NOT_FOUND",
            "data": {},
            "timestamp": self._now_iso(),
            "is_mock": True,
            "confidence": 0.9,
        }

    def _unavailable(self, identifier: str, note: str) -> dict:
        """Simulated portal downtime -> UNAVAILABLE (never a silent PASS/FAIL)."""
        return {
            "source": self.source,
            "status": "UNAVAILABLE",
            "data": {"identifier": self._normalize(identifier), "note": note},
            "timestamp": self._now_iso(),
            "is_mock": True,
            "confidence": 0.5,
        }

    def _hit(self, record: dict) -> dict:
        record_status = str(record.get("status", "")).upper()
        status = _RECORD_STATUS_TO_CHECK_STATUS.get(record_status, "REVIEW_REQUIRED")
        return {
            "source": self.source,
            "status": status,
            "data": dict(record),
            "timestamp": self._now_iso(),
            "is_mock": True,
            "confidence": 0.95,
        }
