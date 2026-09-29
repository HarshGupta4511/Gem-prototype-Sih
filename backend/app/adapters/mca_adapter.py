"""Mock MCA21 (Ministry of Corporate Affairs) verification adapter."""

from app.adapters.base import GovernmentVerificationAdapter


class MCAAdapter(GovernmentVerificationAdapter):
    source = "MCA21"
    _data_file = "mca21.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_mca(identifier)

    def verify_mca(self, cin: str) -> dict:
        code = self._normalize(cin)
        record = self._load_json(self._data_file).get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
