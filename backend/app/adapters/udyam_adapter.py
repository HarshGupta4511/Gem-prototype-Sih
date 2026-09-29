"""Mock Udyam (MSME registration) verification adapter."""

from app.adapters.base import GovernmentVerificationAdapter


class UdyamAdapter(GovernmentVerificationAdapter):
    source = "UDYAM"
    _data_file = "udyam.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_udyam(identifier)

    def verify_udyam(self, udyam_number: str) -> dict:
        code = self._normalize(udyam_number)
        record = self._load_json(self._data_file).get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
