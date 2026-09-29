"""Mock PAN / Income Tax verification adapter."""

from app.adapters.base import GovernmentVerificationAdapter


class PANAdapter(GovernmentVerificationAdapter):
    source = "PAN_IT"
    _data_file = "pan_it.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_pan(identifier)

    def verify_pan(self, pan: str) -> dict:
        code = self._normalize(pan)
        record = self._load_json(self._data_file).get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
