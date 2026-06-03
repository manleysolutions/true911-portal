"""Vola Cloud status adapter.

Looks a device up in the Vola device list by serial number first, then by IMEI
as a fallback, and normalizes online/offline + firmware + last heartbeat.

All Vola-specific code lives here; the generic core never imports the Vola
client.  Raw payload is returned for safe persistence in IntegrationPayload.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.services.device_health.adapters.base import StatusProbeAdapter
from app.services.device_health.models import VendorStatus
from app.services.device_health.reason_codes import ReasonCode
from app.services.device_health.status import NormalizedStatus

logger = logging.getLogger("true911.device_health.vola")

# Vola's device-list "lastUpdateTime" is a vendor-formatted value.  Its exact
# format must be CONFIRMED against production (run the sync with
# DEVICE_HEALTH_DEBUG=true to print the raw value — see
# docs/VOLA_TELEMETRY_RELIABILITY.md).  This parser handles the realistic set
# of shapes (ISO-8601, several human string layouts, and epoch seconds/ms) and
# returns None when it cannot trust the value — it NEVER invents a timestamp.
_VOLA_TS_FORMATS = (
    "%b %d %Y %H:%M",        # "Jun 01 2026 09:00"
    "%b %d %Y %H:%M:%S",     # "Jun 01 2026 09:00:00"
    "%Y-%m-%d %H:%M:%S",     # "2026-06-01 09:00:00"
    "%Y-%m-%d %H:%M",        # "2026-06-01 09:00"
    "%Y/%m/%d %H:%M:%S",     # "2026/06/01 09:00:00"
    "%m/%d/%Y %H:%M:%S",     # "06/01/2026 09:00:00"
    "%b %d, %Y %H:%M:%S",    # "Jun 01, 2026 09:00:00"
    "%d %b %Y %H:%M:%S",     # "01 Jun 2026 09:00:00"
)

# Candidate keys that may carry the device's last-contact time, in priority
# order.  The Vola device-list documents ``lastUpdateTime``; the alternates are
# defensive in case a model/firmware reports under a different key.
HEARTBEAT_TIME_KEYS = (
    "lastUpdateTime", "last_update", "lastActiveTime",
    "lastOnlineTime", "lastSeen", "updateTime", "heartbeatTime",
)


def _parse_vola_timestamp(raw):
    """Best-effort parse of a Vola last-contact value → aware UTC datetime.

    Accepts ISO-8601, the human string layouts in ``_VOLA_TS_FORMATS``, and
    epoch seconds or milliseconds (int / float / numeric string).  Returns
    ``None`` for anything it cannot trust — never fabricates a value.
    """
    from datetime import datetime, timezone

    if raw is None:
        return None

    # Epoch — int/float, or a purely-numeric string.
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().lstrip("-").isdigit()):
        try:
            num = float(raw)
        except (TypeError, ValueError):
            return None
        # Heuristic: values too large for plausible seconds are milliseconds.
        seconds = num / 1000.0 if abs(num) >= 1e12 else num
        try:
            ts = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return ts if 2000 <= ts.year <= 2100 else None

    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None

    try:
        ts = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in _VOLA_TS_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def heartbeat_debug_fields(raw: dict) -> dict:
    """Return the SAFE, named heartbeat-relevant fields from a raw Vola device
    item, for operator debugging.  No secrets exist in the Vola device list, and
    this never returns the whole payload — only the named diagnostic keys plus
    the parsed last-seen result and which key supplied it.
    """
    if not isinstance(raw, dict):
        return {}
    named = (
        "deviceSN", "sn", "status", "deviceModel", "softwareVersion",
        "firmwareVersion", "version", "ip", "lanIp",
        "rssi", "signal", "signalStrength", "signal_dbm",
    ) + HEARTBEAT_TIME_KEYS
    out = {k: raw.get(k) for k in named if k in raw}
    chosen_key, chosen_val = _select_heartbeat_value(raw)
    out["_heartbeat_key_used"] = chosen_key
    parsed = _parse_vola_timestamp(chosen_val)
    out["_parsed_last_seen"] = parsed.isoformat() if parsed else None
    return out


def _select_heartbeat_value(raw: dict):
    """First non-empty heartbeat-time value across the candidate keys."""
    for key in HEARTBEAT_TIME_KEYS:
        val = raw.get(key)
        if val not in (None, ""):
            return key, val
    return None, None


class VolaCloudAdapter(StatusProbeAdapter):
    vendor = "vola"

    def __init__(self, client=None):
        # client injectable for tests; built lazily from env otherwise.
        self._client = client

    @property
    def is_configured(self) -> bool:
        return bool(settings.VOLA_EMAIL and settings.VOLA_PASSWORD)

    def _get_client(self):
        if self._client is not None:
            return self._client
        from app.services.vola_service import get_vola_client
        return get_vola_client()

    async def probe(
        self,
        *,
        serial: Optional[str] = None,
        imei: Optional[str] = None,
        iccid: Optional[str] = None,
        msisdn: Optional[str] = None,
    ) -> VendorStatus:
        ident = serial or imei or ""
        vs = VendorStatus(vendor=self.vendor, device_identifier=ident,
                          connection_type="cellular")

        if not self.is_configured:
            vs.available = False
            vs.reason_codes = [ReasonCode.MISSING_CREDENTIALS]
            vs.error = "VOLA_EMAIL / VOLA_PASSWORD not configured"
            logger.info("Vola probe skipped — credentials missing")
            return vs

        from app.integrations.vola import extract_device_list

        try:
            client = self._get_client()
            data = await client.get_device_list("inUse")
        except Exception as exc:  # auth / network / config
            vs.available = False
            vs.reason_codes = [ReasonCode.VENDOR_API_UNAVAILABLE]
            vs.error = f"{type(exc).__name__}: {exc}"
            logger.warning("Vola device-list failed: %s", vs.error)
            return vs

        raw_list = extract_device_list(data) or []
        match = None
        for item in raw_list:
            sn = item.get("deviceSN") or item.get("sn")
            if serial and sn == serial:
                match = item
                break
        if match is None and imei:
            # IMEI fallback — Vola device list may carry an imei/IMEI key.
            for item in raw_list:
                if (item.get("imei") or item.get("IMEI")) == imei:
                    match = item
                    break

        if match is None:
            vs.normalized_status = NormalizedStatus.UNKNOWN
            vs.reason_codes = [ReasonCode.DEVICE_NOT_FOUND]
            vs.error = "device not present in Vola device list"
            logger.info("Vola: %s not found in device list", ident)
            return vs

        raw_status = str(match.get("status") or "").strip()
        online = raw_status.lower() == "online"
        vs.raw_status = raw_status
        vs.normalized_status = (
            NormalizedStatus.ONLINE if online else NormalizedStatus.OFFLINE)
        vs.firmware = (match.get("softwareVersion") or match.get("firmwareVersion")
                       or match.get("version"))
        vs.static_ip = match.get("ip") or match.get("lanIp")
        # Vola reports a signal/RSSI on some models; capture if present.
        for key in ("rssi", "signal", "signalStrength", "signal_dbm"):
            if match.get(key) not in (None, ""):
                try:
                    vs.signal_strength = float(match[key])
                except (TypeError, ValueError):
                    pass
                break
        # Last heartbeat: the device's last-contact time.  Pick the first
        # populated candidate key (lastUpdateTime + alternates), keep the raw
        # value in raw_payload, and best-effort parse to a UTC datetime.  Never
        # fabricate a value we can't parse (last_seen stays None).
        _hb_key, _hb_val = _select_heartbeat_value(match)
        vs.last_seen = _parse_vola_timestamp(_hb_val)
        vs.raw_payload = match
        vs.reason_codes = [ReasonCode.OK] if online else [ReasonCode.DEVICE_OFFLINE]
        return vs
