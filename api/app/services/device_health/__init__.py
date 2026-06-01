"""Hardware-agnostic device-health layer.

This package fuses the True911 DB record with vendor-cloud / carrier / SIP
signals into ONE normalized health view per device, regardless of hardware.

Core principle: vendor-specific logic lives only in
``app.services.device_health.adapters``.  Everything in this package's top
level is generic — it must read the same for a Vola LM150, an MS130v4, an
Inseego+Cisco ATA, or a future Teltonika endpoint.

Reuses the existing canonical normalizer (``app.services.health``) for the
liveness/degradation state machine; this layer adds reason codes, a
customer-facing 4-value status, and a recommended action on top.
"""

from app.services.device_health.status import NormalizedStatus, from_canonical
from app.services.device_health.reason_codes import ReasonCode
from app.services.device_health.classifier import (
    DeviceClassification,
    classify,
)
from app.services.device_health.recommended_action import recommend
from app.services.device_health.models import VendorStatus, DeviceHealth

__all__ = [
    "NormalizedStatus",
    "from_canonical",
    "ReasonCode",
    "DeviceClassification",
    "classify",
    "recommend",
    "VendorStatus",
    "DeviceHealth",
]
