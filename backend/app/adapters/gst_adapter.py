"""Mock GSTN (Goods and Services Tax Network) verification adapter."""

from app.adapters.base import GovernmentVerificationAdapter


class GSTNAdapter(GovernmentVerificationAdapter):
    source = "GSTN"
    _data_file = "gstn.json"

    def verify(self, identifier: str) -> dict:
        return self.verify_gst(identifier)

    def verify_gst(self, gstin: str) -> dict:
        code = self._normalize(gstin)
        record = self._load_json(self._data_file).get(code)
        if record is None:
            return self._not_found(code)
        return self._hit(record)
