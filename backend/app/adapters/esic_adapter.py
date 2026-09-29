"""Mock ESIC (Employees' State Insurance Corporation) verification adapter.

Honors the ``"_simulate_unavailable"`` key in ``esic.json``: identifiers listed
there return ``UNAVAILABLE`` (simulated portal downtime). Per contract §6/§10,
UNAVAILABLE must surface as REVIEW_REQUIRED downstream — never a silent
PASS/FAIL.
"""

from app.adapters.base import GovernmentVerificationAdapter


class ESICAdapter(GovernmentVerificationAdapter):
    source = "ESIC"
    _data_file = "esic.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_esic(identifier)

    def verify_esic(self, esic_code: str) -> dict:
        code = self._normalize(esic_code)
        db = self._load_json(self._data_file)
        if code in db.get("_simulate_unavailable", []):
            return self._unavailable(
                code,
                "MOCK GOVERNMENT VERIFICATION — ESIC portal simulated as unavailable "
                "(demo downtime scenario). Treat as REVIEW_REQUIRED, not PASS/FAIL.",
            )
        record = db.get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
