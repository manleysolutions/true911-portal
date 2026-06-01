"""Status-adapter registry — map a vendor key to its adapter instance.

The classifier decides which vendor keys apply to a device
(``DeviceClassification.probe_vendors``); this registry resolves those keys to
adapter instances.  Unknown keys fall through to ``FutureDeviceAdapter`` so a
newly-seen device class degrades gracefully instead of raising.
"""

from __future__ import annotations

from typing import Optional

from app.services.device_health.adapters.base import StatusProbeAdapter
from app.services.device_health.adapters.tmobile import TMobileAdapter
from app.services.device_health.adapters.vola import VolaCloudAdapter
from app.services.device_health.adapters.stubs import (
    CiscoAtaAdapter,
    FutureDeviceAdapter,
    InseegoAdapter,
    MS130Adapter,
    TelnyxAdapter,
)

# Singleton instances (stateless / cheap).
_REGISTRY: dict[str, StatusProbeAdapter] = {
    "vola": VolaCloudAdapter(),
    "tmobile": TMobileAdapter(),
    "telnyx": TelnyxAdapter(),
    "inseego": InseegoAdapter(),
    "cisco_ata": CiscoAtaAdapter(),
    "ms130": MS130Adapter(),
    "future": FutureDeviceAdapter(),
}

ALL_VENDORS: tuple[str, ...] = tuple(_REGISTRY.keys())

_FUTURE = _REGISTRY["future"]


def get_status_adapter(vendor: Optional[str]) -> StatusProbeAdapter:
    """Return the adapter for a vendor key (FutureDeviceAdapter if unknown)."""
    if not vendor:
        return _FUTURE
    return _REGISTRY.get(vendor.lower().strip(), _FUTURE)


def adapter_status_summary() -> list[dict]:
    """Safe, no-secret summary of every registered adapter (for the API)."""
    return [a.config_summary() for a in _REGISTRY.values()]
