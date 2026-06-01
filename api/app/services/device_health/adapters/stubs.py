"""Interface stubs for vendors whose live status integration is not built yet.

Each is a real, correctly-shaped adapter so the registry, classifier, sync
command, and tests all treat it uniformly today.  Filling one in later means
implementing ``probe`` — no change to the generic core.

  * TelnyxAdapter   — SIP / CDR voice path (call records already ingested;
                      live registration probe TBD)
  * InseegoAdapter  — cellular modem / static IP (TR-069 / vendor API TBD)
  * CiscoAtaAdapter — analog FXS / SIP ATA (provisioning server probe TBD)
  * MS130Adapter    — Manley/True911 MS130v4 line (SIP or VoLTE per config)
  * FutureDeviceAdapter — catch-all for newly certified endpoints
"""

from __future__ import annotations

from typing import Optional

from app.services.device_health.adapters.base import StatusProbeAdapter
from app.services.device_health.models import VendorStatus
from app.services.device_health.reason_codes import ReasonCode
from app.services.device_health.status import NormalizedStatus


class _NotYetLiveAdapter(StatusProbeAdapter):
    """Shared behaviour for adapters whose live probe is not implemented."""

    vendor = ""
    _note = "live status integration not implemented yet"

    @property
    def is_configured(self) -> bool:
        return False

    async def probe(
        self,
        *,
        serial: Optional[str] = None,
        imei: Optional[str] = None,
        iccid: Optional[str] = None,
        msisdn: Optional[str] = None,
    ) -> VendorStatus:
        return VendorStatus(
            vendor=self.vendor,
            device_identifier=(serial or imei or iccid or msisdn or ""),
            normalized_status=NormalizedStatus.UNKNOWN,
            available=False,
            reason_codes=[ReasonCode.MISSING_CREDENTIALS],
            error=self._note,
        )

    def config_summary(self) -> dict:
        return {"vendor": self.vendor, "configured": False, "note": self._note}


class TelnyxAdapter(_NotYetLiveAdapter):
    vendor = "telnyx"
    _note = "Telnyx SIP/CDR live registration probe not implemented (CDR liveness comes from call_records)"


class InseegoAdapter(_NotYetLiveAdapter):
    vendor = "inseego"
    _note = "Inseego modem/static-IP live probe not implemented"


class CiscoAtaAdapter(_NotYetLiveAdapter):
    vendor = "cisco_ata"
    _note = "Cisco ATA SIP registration probe not implemented"


class MS130Adapter(_NotYetLiveAdapter):
    vendor = "ms130"
    _note = "MS130v4 line status probe not implemented"


class FutureDeviceAdapter(_NotYetLiveAdapter):
    vendor = "future"
    _note = "no adapter registered for this device class"
