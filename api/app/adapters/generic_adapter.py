"""Generic adapter — passes through recognised keys as-is."""

from __future__ import annotations

from app.adapters.base import DEVICE_WRITABLE_FIELDS, METADATA_KEYS, DeviceAdapter

_ALLOWED = DEVICE_WRITABLE_FIELDS | METADATA_KEYS


class GenericAdapter(DeviceAdapter):
    """No vendor-specific mapping; just allowlist the known keys."""

    def normalize_heartbeat(self, payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k in _ALLOWED and v is not None}
