"""Registry of all mock government verification adapters (singletons)."""

from app.adapters.base import GovernmentVerificationAdapter
from app.adapters.blacklist_adapter import BlacklistAdapter
from app.adapters.digilocker_adapter import DigiLockerAdapter
from app.adapters.epfo_adapter import EPFOAdapter
from app.adapters.esic_adapter import ESICAdapter
from app.adapters.gst_adapter import GSTNAdapter
from app.adapters.mca_adapter import MCAAdapter
from app.adapters.nsic_adapter import NSICAdapter
from app.adapters.pan_adapter import PANAdapter
from app.adapters.startup_india_adapter import StartupIndiaAdapter
from app.adapters.udyam_adapter import UdyamAdapter

ADAPTERS: dict[str, GovernmentVerificationAdapter] = {
    "GSTN": GSTNAdapter(),
    "UDYAM": UdyamAdapter(),
    "PAN_IT": PANAdapter(),
    "MCA21": MCAAdapter(),
    "EPFO": EPFOAdapter(),
    "ESIC": ESICAdapter(),
    "STARTUP_INDIA": StartupIndiaAdapter(),
    "NSIC": NSICAdapter(),
    "DIGILOCKER": DigiLockerAdapter(),
    "BLACKLIST": BlacklistAdapter(),
}


def get_adapter(source: str) -> GovernmentVerificationAdapter | None:
    """Return the singleton adapter for an AdapterSource value, or None."""
    return ADAPTERS.get((source or "").strip().upper())
