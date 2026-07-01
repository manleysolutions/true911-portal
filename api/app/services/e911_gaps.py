"""Internal E911 gap worklist — surfaces missing / unverified emergency data
for correction by operations.

This is an INTERNAL surface (never customer-facing).  It exists so that while
the customer OPERATIONAL axis may be shown green in preview (see
``services.customer.preview``), the E911 axis stays honest end-to-end: any
location whose emergency record is incomplete or unverified is listed here so an
operator can fix it before verification.  It reads real stored data and writes
nothing.

Gap taxonomy (per site):
  * ``service_address``   — one of e911_street/city/state/zip is missing.
  * ``e911_verification`` — the stored ``e911_status`` is not verified/validated
                            (E911 "verified" must only be true when actually
                            verified — this is the worklist of the not-yet-true).
  * per emergency endpoint (ServiceUnit): ``service_type`` (no unit_type),
    ``location`` (no floor and no location_description), ``callback_number``
    (no linked line/device number).
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.line import Line
from app.models.service_unit import ServiceUnit
from app.models.site import Site

_E911_VERIFIED = {"validated", "verified"}


def compute_site_e911_gaps(site, units_with_callbacks: Iterable[tuple]) -> Optional[dict]:
    """Pure gap computation for one site.  ``units_with_callbacks`` is an
    iterable of ``(ServiceUnit, callback_number|None)``.  Returns a gap record,
    or ``None`` when the site's E911 data is complete AND verified (nothing to
    correct)."""
    address_present = all([site.e911_street, site.e911_city, site.e911_state, site.e911_zip])
    verified = (site.e911_status or "").lower() in _E911_VERIFIED

    site_missing: list[str] = []
    if not address_present:
        site_missing.append("service_address")
    if not verified:
        site_missing.append("e911_verification")

    endpoint_gaps: list[dict] = []
    for unit, callback in units_with_callbacks:
        miss: list[str] = []
        if not unit.unit_type:
            miss.append("service_type")
        if not (unit.floor or unit.location_description):
            miss.append("location")
        if not callback:
            miss.append("callback_number")
        if miss:
            endpoint_gaps.append({
                "unit_id": unit.unit_id,
                "unit_name": unit.unit_name,
                "missing": miss,
            })

    if not site_missing and not endpoint_gaps:
        return None
    return {
        "site_id": site.site_id,
        "site_name": site.site_name,
        "e911_verified": verified,
        "missing": site_missing,
        "endpoint_gaps": endpoint_gaps,
    }


async def _callback_for_unit(db: AsyncSession, tenant_id: str, unit) -> Optional[str]:
    """Resolve a unit's callback number from its linked line/device (tenant-
    scoped, real stored data)."""
    if unit.line_id:
        did = (await db.execute(
            select(Line.did).where(Line.line_id == unit.line_id, Line.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if did:
            return did
    if unit.device_id:
        return (await db.execute(
            select(Device.msisdn).where(
                Device.device_id == unit.device_id, Device.tenant_id == tenant_id
            )
        )).scalar_one_or_none()
    return None


async def list_e911_gaps(db: AsyncSession, tenant_id: str) -> list[dict]:
    """Return the E911 correction worklist for a tenant — every site with
    missing or unverified emergency data (complete+verified sites are omitted).
    Read-only; tenant-scoped."""
    sites = (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id).order_by(Site.site_name)
    )).scalars().all()
    out: list[dict] = []
    for site in sites:
        units = (await db.execute(
            select(ServiceUnit).where(
                ServiceUnit.tenant_id == tenant_id, ServiceUnit.site_id == site.site_id
            )
        )).scalars().all()
        units_with_callbacks = [
            (unit, await _callback_for_unit(db, tenant_id, unit)) for unit in units
        ]
        gap = compute_site_e911_gaps(site, units_with_callbacks)
        if gap is not None:
            out.append(gap)
    return out
