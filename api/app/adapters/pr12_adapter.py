"""PR12 / CSA device adapter.

Maps vendor-specific heartbeat keys into canonical field names.

Example raw PR12 heartbeat payload::

    {
        "device_id": "PR12-001",
        "fw_ver": "2.4.1",
        "ctr_ver": "1.8.0",
        "rsrp": -82,
        "public_ip": "203.0.113.44",
        "uptime": 86400,
        "board_temp_c": 42,
        "carrier_id": "310260"
    }

Normalized output::

    {
        "firmware_version": "2.4.1",
        "container_version": "1.8.0",
        "signal_dbm": -82,
        "ip_address": "203.0.113.44",
        "uptime_seconds": 86400,
    }
"""

from __future__ import annotations

from app.adapters.base import DeviceAdapter

# PR12-specific key → canonical key
_KEY_MAP: dict[str, str] = {
    # firmware
    "fw_ver": "firmware_version",
    "fw_version": "firmware_version",
    "firmware_version": "firmware_version",
    # container
    "ctr_ver": "container_version",
    "ctr_version": "container_version",
    "container_version": "container_version",
    # signal strength — PR12 reports RSRP; map to our generic signal_dbm
    "rsrp": "signal_dbm",
    "rsrp_dbm": "signal_dbm",
    "signal_dbm": "signal_dbm",
    # IP
    "public_ip": "ip_address",
    "ip_address": "ip_address",
    "wan_ip": "ip_address",
    # uptime
    "uptime": "uptime_seconds",
    "uptime_sec": "uptime_seconds",
    "uptime_seconds": "uptime_seconds",
}


class PR12Adapter(DeviceAdapter):
    """Normalize a PR12/CSA heartbeat payload."""

    def normalize_heartbeat(self, payload: dict) -> dict:
        out: dict = {}
        for raw_key, value in payload.items():
            canonical = _KEY_MAP.get(raw_key)
            if canonical is not None and value is not None:
                out[canonical] = value
        return out
