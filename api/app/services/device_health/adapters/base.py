"""Abstract base for vendor status-probe adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.services.device_health.models import VendorStatus


class StatusProbeAdapter(ABC):
    """Ask one vendor for the live status of one device/line.

    Implementations MUST be defensive: a missing-credential or network error
    returns a :class:`VendorStatus` with ``available=False`` and an
    appropriate reason code — it never raises.  This keeps the sync command's
    per-device loop resilient across a mixed fleet.
    """

    vendor: str = ""

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """True when credentials / endpoints are present for live calls."""
        ...

    @abstractmethod
    async def probe(
        self,
        *,
        serial: Optional[str] = None,
        imei: Optional[str] = None,
        iccid: Optional[str] = None,
        msisdn: Optional[str] = None,
    ) -> VendorStatus:
        """Return a normalized status for the given identifiers."""
        ...

    def config_summary(self) -> dict:
        """Safe (no-secret) summary for the adapter-status API."""
        return {"vendor": self.vendor, "configured": self.is_configured}
