"""T-Mobile carrier status adapter (TAAP SubscriberInquiry).

The real TAAP client (``app.integrations.tmobile_taap``) implements the
OAuth2 + PoP flow.  This adapter wraps it for the health pipeline.

Known vendor constraints (logged, not invented):
  * SubscriberInquiry is MSISDN-primary.  ICCID / IMEI reverse lookup is not
    confirmed available — those identifiers return DEVICE_NOT_FOUND with a note
    rather than a fabricated result.
  * VoLTE status / static IP / usage are not in the SubscriberInquiry response
    schema we have; we attempt query_network best-effort and leave fields None
    when the vendor does not return them.
  * Credentials (TMOBILE_CONSUMER_KEY/SECRET + RSA key) are not yet provisioned
    in any environment — until then this returns MISSING_CREDENTIALS and the
    live callback ingest remains the primary T-Mobile signal.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.services.device_health.adapters.base import StatusProbeAdapter
from app.services.device_health.models import VendorStatus
from app.services.device_health.reason_codes import ReasonCode
from app.services.device_health.status import NormalizedStatus

logger = logging.getLogger("true911.device_health.tmobile")

# T-Mobile subscriber status strings that mean the line is not carrying service.
_INACTIVE = frozenset({"suspended", "deactivated", "cancelled", "canceled", "inactive"})


class TMobileAdapter(StatusProbeAdapter):
    vendor = "tmobile"

    def __init__(self, client=None):
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        from app.integrations.tmobile_taap import TMobileTAAPClient
        return TMobileTAAPClient()

    @property
    def is_configured(self) -> bool:
        try:
            return bool(self._get_client().is_configured)
        except Exception:
            return False

    async def probe(
        self,
        *,
        serial: Optional[str] = None,
        imei: Optional[str] = None,
        iccid: Optional[str] = None,
        msisdn: Optional[str] = None,
    ) -> VendorStatus:
        ident = msisdn or iccid or imei or ""
        vs = VendorStatus(vendor=self.vendor, device_identifier=ident,
                          connection_type="cellular")

        if not self.is_configured:
            vs.available = False
            vs.reason_codes = [ReasonCode.MISSING_CREDENTIALS]
            vs.error = ("TMOBILE_CONSUMER_KEY/SECRET + RSA key not configured; "
                        "relying on callback ingest")
            logger.info("T-Mobile probe skipped — credentials missing")
            return vs

        if not msisdn:
            # SubscriberInquiry is MSISDN-primary; do not fabricate a lookup.
            vs.normalized_status = NormalizedStatus.UNKNOWN
            vs.reason_codes = [ReasonCode.DEVICE_NOT_FOUND]
            vs.error = ("T-Mobile SubscriberInquiry requires MSISDN; ICCID/IMEI "
                        "reverse lookup not available")
            logger.info("T-Mobile: no MSISDN for %s — lookup unsupported", iccid or imei)
            return vs

        client = self._get_client()
        try:
            data = await client.subscriber_inquiry(msisdn)
        except Exception as exc:
            vs.available = False
            vs.reason_codes = [ReasonCode.VENDOR_API_UNAVAILABLE]
            vs.error = f"{type(exc).__name__}: {exc}"
            logger.warning("T-Mobile SubscriberInquiry failed: %s", vs.error)
            return vs

        raw_status = str(data.get("status") or "").strip()
        vs.raw_status = raw_status
        vs.sim_status = raw_status or None
        vs.raw_payload = data
        status_l = raw_status.lower()
        if status_l == "active":
            vs.normalized_status = NormalizedStatus.ONLINE
            vs.reason_codes = [ReasonCode.OK]
        elif status_l in _INACTIVE:
            vs.normalized_status = NormalizedStatus.OFFLINE
            vs.reason_codes = [ReasonCode.SIM_INACTIVE]
        else:
            vs.normalized_status = NormalizedStatus.UNKNOWN

        # Best-effort enrichment — tolerate missing fields, never invent them.
        for key in ("staticIp", "static_ip", "ipAddress"):
            if data.get(key):
                vs.static_ip = data[key]
                break
        for key in ("volte", "volteStatus", "volte_status"):
            if key in data:
                vs.volte_status = str(data[key])
                break
        return vs
