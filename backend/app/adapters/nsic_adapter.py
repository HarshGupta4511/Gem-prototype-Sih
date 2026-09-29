"""Mock NSIC (National Small Industries Corporation) verification adapter.

The demo mock database is intentionally empty, so every lookup returns
NOT_FOUND (honest: no record, not a silent pass).
"""

from app.adapters.base import GovernmentVerificationAdapter


class NSICAdapter(GovernmentVerificationAdapter):
    source = "NSIC"
    _data_file = "nsic.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_nsic(identifier)

    def verify_nsic(self, certificate_no: str) -> dict:
        code = self._normalize(certificate_no)
        record = self._load_json(self._data_file).get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
