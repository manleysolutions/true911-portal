"""CSAS (CSA-Software) edge runtime adapter.

Maps the CSAS heartbeat payload into canonical field names.

Example raw CSAS heartbeat payload::

    {
        "device_id": "CSAS-001",
        "status": "running",
        "uptime": 86400,
        "timestamp": "2026-03-23T12:00:00Z",
        "version": "3.1.0",
        "sip_status": "registered",
        "signal_dbm": -78
    }

Normalized output::

    {
        "firmware_version": "3.1.0",
        "uptime_seconds": 86400,
        "csas_status": "running",
        "csas_timestamp": "2026-03-23T12:00:00Z",
        "sip_status": "registered",
        "signal_dbm": -78,
    }
"""

from __future__ import annotations

from app.adapters.base import DeviceAdapter

# CSAS-specific key -> canonical key
_KEY_MAP: dict[str, str] = {
    # version -> firmware_version
    "version": "firmware_version",
    "fw_ver": "firmware_version",
    "firmware_version": "firmware_version",
    # container
    "ctr_ver": "container_version",
    "container_version": "container_version",
    # uptime
    "uptime": "uptime_seconds",
    "uptime_sec": "uptime_seconds",
    "uptime_seconds": "uptime_seconds",
    # CSAS runtime state (stored in metadata, never overwrites device.status)
    "status": "csas_status",
    "csas_status": "csas_status",
    # Client-reported timestamp (informational; server uses its own clock)
    "timestamp": "csas_timestamp",
    "csas_timestamp": "csas_timestamp",
    # Signal / network passthrough
    "signal_dbm": "signal_dbm",
    "rsrp": "signal_dbm",
    "rssi": "signal_rssi",
    "sinr": "signal_sinr",
    "rsrq": "signal_rsrq",
    "ip_address": "ip_address",
    "public_ip": "ip_address",
    "wan_ip": "ip_address",
    "sip_status": "sip_status",
    "sip_registered": "sip_status",
    "carrier_id": "carrier_id",
    "network_type": "network_type",
    "connection_status": "connection_status",
    "board_temp_c": "board_temp_c",
    "temperature_c": "board_temp_c",
}


class CSASAdapter(DeviceAdapter):
    """Normalize a CSAS edge-runtime heartbeat payload."""

    def normalize_heartbeat(self, payload: dict) -> dict:
        out: dict = {}
        for raw_key, value in payload.items():
            canonical = _KEY_MAP.get(raw_key)
            if canonical is not None and value is not None:
                out[canonical] = value
        return out
