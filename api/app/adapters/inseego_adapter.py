"""Inseego FW3100 device adapter.

Maps vendor-specific heartbeat keys into canonical field names.
The FW3100 is a cellular router — heartbeat payloads may include
modem/signal fields if the device firmware supports them.

Example plausible FW3100 heartbeat payload::

    {
        "device_id": "INSG-001",
        "rssi": -75,
        "rsrp": -95,
        "sinr": 8.5,
        "wan_ip": "100.72.3.14",
        "connection_status": "connected",
        "network_type": "LTE",
        "uptime": 172800,
        "fw_version": "1.12.3"
    }

Normalized output::

    {
        "signal_dbm": -95,
        "ip_address": "100.72.3.14",
        "uptime_seconds": 172800,
        "firmware_version": "1.12.3",
    }

Note: No Inseego API client exists in this repo.  Telemetry comes
exclusively through device heartbeats posted to POST /api/heartbeat.
"""

from __future__ import annotations

from app.adapters.base import DeviceAdapter

# Inseego FW3100 key → canonical key
_KEY_MAP: dict[str, str] = {
    # signal — prefer RSRP over RSSI for health scoring
    "rsrp": "signal_dbm",
    "rsrp_dbm": "signal_dbm",
    "rssi": "signal_rssi",
    "sinr": "signal_sinr",
    "signal_dbm": "signal_dbm",
    # firmware
    "fw_version": "firmware_version",
    "fw_ver": "firmware_version",
    "firmware_version": "firmware_version",
    # IP / WAN
    "wan_ip": "ip_address",
    "public_ip": "ip_address",
    "ip_address": "ip_address",
    # uptime
    "uptime": "uptime_seconds",
    "uptime_sec": "uptime_seconds",
    "uptime_seconds": "uptime_seconds",
    # connection / network (stored in metadata, used by telemetry bridge)
    "connection_status": "connection_status",
    "network_type": "network_type",
}


class InsegoAdapter(DeviceAdapter):
    """Normalize an Inseego FW3100 heartbeat payload."""

    def normalize_heartbeat(self, payload: dict) -> dict:
        out: dict = {}
        for raw_key, value in payload.items():
            canonical = _KEY_MAP.get(raw_key)
            if canonical is not None and value is not None:
                out[canonical] = value
        # If we have RSSI but no RSRP, fall back to RSSI for signal_dbm
        if "signal_dbm" not in out and "signal_rssi" in out:
            out["signal_dbm"] = out["signal_rssi"]
        return out
