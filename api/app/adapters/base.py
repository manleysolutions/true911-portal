"""Abstract base class for vendor device adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


# Fields that an adapter may write to a Device row.
# Anything outside this set is silently dropped during apply.
DEVICE_WRITABLE_FIELDS: frozenset[str] = frozenset({
    "firmware_version",
    "container_version",
})

# Keys that the normalized dict may contain beyond the writable fields.
# These end up in Event.metadata_json / TelemetryEvent.raw_json only.
METADATA_KEYS: frozenset[str] = frozenset({
    "signal_dbm",
    "ip_address",
    "uptime_seconds",
})


class DeviceAdapter(ABC):
    """Normalize a vendor-specific heartbeat payload into a common dict.

    Subclasses implement :meth:`normalize_heartbeat` to map vendor keys
    into the canonical key names listed in ``DEVICE_WRITABLE_FIELDS`` and
    ``METADATA_KEYS``.
    """

    @abstractmethod
    def normalize_heartbeat(self, payload: dict) -> dict:
        """Return a dict with only recognised canonical keys.

        The caller uses ``DEVICE_WRITABLE_FIELDS`` to decide which keys
        are written to the Device row; everything else is stored as
        event metadata.
        """
        ...
