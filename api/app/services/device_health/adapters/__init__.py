"""Vendor status-probe adapters.

Each adapter knows how to ask ONE vendor "what is the live status of this
device/line?" and returns a normalized :class:`VendorStatus`.  All
vendor-specific logic is confined here — the generic health core never imports
a vendor SDK.

Adapters are used by the sync command (``app.sync_device_health``), not by the
per-request read APIs (those read persisted DB fields so a page load never
blocks on a vendor call).
"""

from app.services.device_health.adapters.base import StatusProbeAdapter
from app.services.device_health.adapters.registry import (
    get_status_adapter,
    adapter_status_summary,
    ALL_VENDORS,
)

__all__ = [
    "StatusProbeAdapter",
    "get_status_adapter",
    "adapter_status_summary",
    "ALL_VENDORS",
]
