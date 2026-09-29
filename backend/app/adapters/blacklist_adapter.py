"""Mock blacklist / debarment verification adapter.

Looks up the (normalized) company name against the mock blacklist. A hit
returns status ``VERIFIED`` with the ``blacklisted``/``debarred`` flags in
``data`` — the rules/risk engines interpret those flags (a hit is evidence,
not an automatic disqualification). No hit returns ``VERIFIED`` with
``blacklisted: False, debarred: False`` ("verified clean").
"""

from app.adapters.base import GovernmentVerificationAdapter


class BlacklistAdapter(GovernmentVerificationAdapter):
    source = "BLACKLIST"
    _data_file = "blacklist.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_blacklist(identifier)

    def verify_blacklist(self, company_name: str) -> dict:
        name = (company_name or "").strip()
        records = self._load_json(self._data_file)
        hit = next(
            (rec for rec in records if self._names_equal(rec.get("company_name", ""), name)),
            None,
        )
        if hit is not None:
            return {
                "source": self.source,
                "status": "VERIFIED",
                "data": dict(hit),
                "timestamp": self._now_iso(),
                "is_mock": True,
                "confidence": 0.95,
            }
        # Verified clean: the name was checked against the mock list, no hit.
        return {
            "source": self.source,
            "status": "VERIFIED",
            "data": {
                "company_name": name,
                "blacklisted": False,
                "debarred": False,
            },
            "timestamp": self._now_iso(),
            "is_mock": True,
            "confidence": 0.95,
        }

    @staticmethod
    def _names_equal(a: str, b: str) -> bool:
        """Normalized-name equality using the entity-resolution helper."""
        try:
            from app.engines.entity_resolution import normalize_name

            return normalize_name(a) == normalize_name(b)
        except (ImportError, AttributeError):
            # entity_resolution not available (parallel build); crude fallback.
            return a.strip().upper() == b.strip().upper()
