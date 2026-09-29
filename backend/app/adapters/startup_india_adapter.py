"""Mock Startup India (DPIIT recognition) verification adapter."""

from app.adapters.base import GovernmentVerificationAdapter


class StartupIndiaAdapter(GovernmentVerificationAdapter):
    source = "STARTUP_INDIA"
    _data_file = "startup_india.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_startup(identifier)

    def verify_startup(self, certificate_no: str) -> dict:
        code = self._normalize(certificate_no)
        record = self._load_json(self._data_file).get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
