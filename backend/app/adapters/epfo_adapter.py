"""Mock EPFO (Employees' Provident Fund Organisation) verification adapter."""

from app.adapters.base import GovernmentVerificationAdapter


class EPFOAdapter(GovernmentVerificationAdapter):
    source = "EPFO"
    _data_file = "epfo.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_epfo(identifier)

    def verify_epfo(self, epfo_code: str) -> dict:
        code = self._normalize(epfo_code)
        record = self._load_json(self._data_file).get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
