from .base import CarrierProvider, CarrierSyncResult
from .verizon import VerizonProvider
from .tmobile import TMobileProvider
from .att import ATTProvider

PROVIDERS: dict[str, type[CarrierProvider]] = {
    "verizon": VerizonProvider,
    "tmobile": TMobileProvider,
    "att": ATTProvider,
}


def get_provider(carrier: str) -> CarrierProvider:
    """Return a carrier provider instance, or raise KeyError."""
    cls = PROVIDERS.get(carrier.lower())
    if not cls:
        raise KeyError(f"Unknown carrier: {carrier}")
    return cls()
