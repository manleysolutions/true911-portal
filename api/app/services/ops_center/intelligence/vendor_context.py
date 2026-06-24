"""Carrier / VendorContext — normalized service output (Phase 1.5 stub).

Produces a single, normalized view of the carrier + hardware-vendor context
for a device so triage/handoff can present "who provides this line and on what
hardware" without each consumer re-deriving it.  This is a SERVICE OUTPUT (a
read-only dataclass) — it adds NO columns to the Device/Sim tables.  It
degrades gracefully when the device is unknown or fields are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device

# Coarse hardware-vendor inference from the existing manufacturer/model/type
# fields.  Intentionally conservative; returns "unknown" rather than guess.
_VENDOR_HINTS = {
    "napco": "napco",
    "starlink": "starlink",
    "telnyx": "telnyx",
    "inseego": "inseego",
    "cisco": "cisco",
    "flyingvoice": "flyingvoice",
    "vola": "vola",
    "lm150": "flyingvoice",
}


@dataclass
class VendorContext:
    device_id: Optional[str] = None
    available: bool = False
    carrier: Optional[str] = None
    vendor: Optional[str] = None
    transport: Optional[str] = None        # cellular | ata | starlink | unknown
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    firmware_version: Optional[str] = None
    iccid: Optional[str] = None
    msisdn: Optional[str] = None
    starlink_id: Optional[str] = None
    last_network_event_at: Optional[datetime] = None
    notes: Optional[str] = None


def _infer_vendor(device: Device) -> Optional[str]:
    haystack = " ".join(
        str(getattr(device, f, "") or "")
        for f in ("manufacturer", "model", "device_type")
    ).lower()
    for hint, vendor in _VENDOR_HINTS.items():
        if hint in haystack:
            return vendor
    return None


def context_from_device(device: Device) -> VendorContext:
    """Build a :class:`VendorContext` from an already-loaded Device."""
    return VendorContext(
        device_id=getattr(device, "device_id", None),
        available=True,
        carrier=getattr(device, "carrier", None),
        vendor=_infer_vendor(device),
        transport=getattr(device, "identifier_type", None) or "unknown",
        model=getattr(device, "model", None),
        manufacturer=getattr(device, "manufacturer", None),
        firmware_version=getattr(device, "firmware_version", None),
        iccid=getattr(device, "iccid", None),
        msisdn=getattr(device, "msisdn", None),
        starlink_id=getattr(device, "starlink_id", None),
        last_network_event_at=getattr(device, "last_network_event", None),
    )


async def build_vendor_context(
    db: AsyncSession, *, device_id: Optional[str], tenant_id: str
) -> VendorContext:
    """Load *device_id* within *tenant_id* and return its VendorContext.

    Tenant-scoped.  Returns an ``available=False`` context (not an error) when
    the device is missing or no device_id is supplied — graceful degradation.
    """
    if not device_id:
        return VendorContext(available=False, notes="No device linked to this session.")
    device = (
        await db.execute(
            select(Device).where(Device.device_id == device_id, Device.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if device is None:
        return VendorContext(device_id=device_id, available=False, notes="Device not found in tenant.")
    return context_from_device(device)
