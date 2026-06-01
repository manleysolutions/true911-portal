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
        vs.raw_payload = match
        vs.reason_codes = [ReasonCode.OK] if online else [ReasonCode.DEVICE_OFFLINE]
        # last heartbeat is a vendor-formatted string; keep it raw in payload —
        # we do not invent a parsed datetime we cannot trust.
        return vs
