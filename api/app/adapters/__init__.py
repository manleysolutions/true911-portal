"""Vendor adapter layer — normalizes device heartbeat payloads.

Usage::

    from app.adapters import get_adapter

    adapter = get_adapter(device.device_type, device.model)
    normalized = adapter.normalize_heartbeat(raw_payload)
"""

from app.adapters.registry import get_adapter

__all__ = ["get_adapter"]
