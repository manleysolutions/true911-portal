"""Provisioning suggestion engine — rules-based matching for unlinked infrastructure.

Scans SIMs, devices, and lines not yet assigned to a site, creates queue items
with suggested linkages.  SuperAdmin scans all tenants; tenant admins scan their own.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.line import Line
from app.models.provisioning_queue import ProvisioningQueueItem
from app.models.sim import Sim
from app.models.site import Site

logger = logging.getLogger("true911.provisioning")


async def scan_and_enqueue(
    db: AsyncSession,
    tenant_id: str | None,
    initiated_by: str,
    is_superadmin: bool = False,
) -> dict:
    """Scan for unlinked SIMs/devices/lines and create queue items.

    If is_superadmin=True, scans ALL tenants. Otherwise scopes to tenant_id.
    """
    created = 0
    skipped = 0

    # Load existing queue keys to avoid duplicates
    eq = select(ProvisioningQueueItem.item_type, ProvisioningQueueItem.item_id).where(
        ProvisioningQueueItem.status.in_(["new", "suggested", "needs_review"]),
    )
    if not is_superadmin:
        eq = eq.where(ProvisioningQueueItem.tenant_id == tenant_id)
    existing_q = await db.execute(eq)
    existing_keys = {(r[0], r[1]) for r in existing_q.all()}

    # Load ALL sites (grouped by tenant for suggestion matching)
    sq = select(Site)
    if not is_superadmin:
        sq = sq.where(Site.tenant_id == tenant_id)
    site_result = await db.execute(sq)
    all_sites = site_result.scalars().all()
    sites_by_tenant: dict[str, list[Site]] = {}
    for s in all_sites:
        sites_by_tenant.setdefault(s.tenant_id, []).append(s)

    # ── Unlinked SIMs ────────────────────────────────────────────
    sim_q = select(Sim).where(
        Sim.site_id.is_(None),
        Sim.status.notin_(["terminated", "deactivated"]),
    )
    if not is_superadmin:
        sim_q = sim_q.where(Sim.tenant_id == tenant_id)
    sim_result = await db.execute(sim_q)
    for sim in sim_result.scalars().all():
        if ("sim", sim.id) in existing_keys:
            skipped += 1
            continue
        tenant_sites = sites_by_tenant.get(sim.tenant_id, [])
        suggestion = _suggest(sim.carrier, tenant_sites)
        item = ProvisioningQueueItem(
            tenant_id=sim.tenant_id,
            item_type="sim",
            item_id=sim.id,
            external_ref=sim.iccid,
            source_provider=sim.carrier if sim.data_source == "carrier_sync" else "manual",
            current_site_id=sim.site_id,
            current_device_id=sim.device_id,
            missing_customer=not bool(sim.tenant_id),
            **suggestion,
        )
        db.add(item)
        created += 1

    # ── Unlinked Devices ─────────────────────────────────────────
    dev_q = select(Device).where(
        Device.site_id.is_(None),
        Device.status.notin_(["decommissioned"]),
    )
    if not is_superadmin:
        dev_q = dev_q.where(Device.tenant_id == tenant_id)
    dev_result = await db.execute(dev_q)
    for dev in dev_result.scalars().all():
        if ("device", dev.id) in existing_keys:
            skipped += 1
            continue
        tenant_sites = sites_by_tenant.get(dev.tenant_id, [])
        suggestion = _suggest(dev.carrier, tenant_sites)
        item = ProvisioningQueueItem(
            tenant_id=dev.tenant_id,
            item_type="device",
            item_id=dev.id,
            external_ref=dev.device_id,
            source_provider=dev.carrier or "manual",
            current_site_id=dev.site_id,
            **suggestion,
        )
        db.add(item)
        created += 1

    # ── Unlinked Lines ───────────────────────────────────────────
    line_q = select(Line).where(
        Line.site_id.is_(None),
        Line.status.notin_(["disconnected"]),
    )
    if not is_superadmin:
        line_q = line_q.where(Line.tenant_id == tenant_id)
    line_result = await db.execute(line_q)
    for line in line_result.scalars().all():
        if ("line", line.id) in existing_keys:
            skipped += 1
            continue
        tenant_sites = sites_by_tenant.get(line.tenant_id, [])
        suggestion = _suggest(line.provider, tenant_sites)
        item = ProvisioningQueueItem(
            tenant_id=line.tenant_id,
            item_type="line",
            item_id=line.id,
            external_ref=line.did or line.line_id,
            source_provider=line.provider or "manual",
            current_site_id=line.site_id,
            current_device_id=line.device_id,
            **suggestion,
        )
        db.add(item)
        created += 1

    await db.commit()
    logger.info("Provisioning scan: created=%d skipped=%d by=%s", created, skipped, initiated_by)
    return {"created": created, "skipped": skipped}


def _suggest(carrier: str | None, sites: list[Site]) -> dict:
    """Generate suggestion fields based on available sites.

    Only suggests a specific site when there's exactly one site in the tenant.
    Multiple sites → needs_review so the operator picks the right one.
    """
    flags = {"missing_site": True, "missing_e911": True}

    if not sites:
        return {**flags, "status": "needs_review", "suggestion_confidence": None,
                "suggestion_reason": "No sites in tenant — create a site first"}

    if len(sites) == 1:
        s = sites[0]
        has_e911 = bool(s.e911_street and s.e911_city)
        return {
            **flags,
            "status": "suggested",
            "suggested_site_id": s.site_id,
            "suggested_site_name": s.site_name,
            "suggested_tenant_id": s.tenant_id,
            "suggestion_confidence": 0.8,
            "suggestion_reason": f"Only site in account — {s.site_name}",
            "missing_e911": not has_e911,
        }

    # Multiple sites → don't guess, let the operator decide
    site_names = ", ".join(s.site_name for s in sites[:3])
    suffix = f" + {len(sites) - 3} more" if len(sites) > 3 else ""
    return {
        **flags,
        "status": "needs_review",
        "suggestion_confidence": None,
        "suggestion_reason": f"{len(sites)} sites in account ({site_names}{suffix}) — select the correct site",
    }
