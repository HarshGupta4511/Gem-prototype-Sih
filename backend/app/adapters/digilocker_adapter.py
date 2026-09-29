"""Mock DigiLocker document verification adapter.

The demo mock database is intentionally empty, so every lookup returns
NOT_FOUND (honest: no record, not a silent pass).
"""

from app.adapters.base import GovernmentVerificationAdapter


class DigiLockerAdapter(GovernmentVerificationAdapter):
    source = "DIGILOCKER"
    _data_file = "digilocker.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_digilocker(identifier)

    def verify_digilocker(self, document_id: str) -> dict:
        code = self._normalize(document_id)
        record = self._load_json(self._data_file).get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
