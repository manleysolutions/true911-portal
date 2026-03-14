"""Provisioning suggestion engine — rules-based matching for unlinked infrastructure.

Scans SIMs, devices, and lines that are not yet assigned to a site and generates
queue items with suggested linkages based on:
  - tenant ownership (same tenant = likely match)
  - carrier/provider matching
  - naming conventions
  - prior assignments on related records
  - missing data flags

This is a first-pass rules engine.  Future versions can incorporate AI/ML
for more sophisticated matching.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.line import Line
from app.models.provisioning_queue import ProvisioningQueueItem
from app.models.sim import Sim
from app.models.site import Site

logger = logging.getLogger("true911.provisioning")


async def scan_and_enqueue(
    db: AsyncSession,
    tenant_id: str,
    initiated_by: str,
) -> dict:
    """Scan for unlinked SIMs/devices/lines and create queue items with suggestions.

    Returns a summary of items created/updated.
    """
    created = 0
    skipped = 0

    # Load existing queue item_ids to avoid duplicates
    existing_q = await db.execute(
        select(ProvisioningQueueItem.item_type, ProvisioningQueueItem.item_id).where(
            ProvisioningQueueItem.tenant_id == tenant_id,
            ProvisioningQueueItem.status.in_(["new", "suggested", "needs_review"]),
        )
    )
    existing_keys = {(r[0], r[1]) for r in existing_q.all()}

    # Load all sites for this tenant (for suggestion matching)
    site_result = await db.execute(
        select(Site).where(Site.tenant_id == tenant_id)
    )
    tenant_sites = site_result.scalars().all()
    sites_by_id = {s.site_id: s for s in tenant_sites}

    # ── Unlinked SIMs ────────────────────────────────────────────
    sim_result = await db.execute(
        select(Sim).where(
            Sim.tenant_id == tenant_id,
            Sim.site_id.is_(None),
            Sim.status.notin_(["terminated", "deactivated"]),
        )
    )
    for sim in sim_result.scalars().all():
        if ("sim", sim.id) in existing_keys:
            skipped += 1
            continue

        suggestion = _suggest_for_sim(sim, tenant_sites)
        item = ProvisioningQueueItem(
            tenant_id=tenant_id,
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
    dev_result = await db.execute(
        select(Device).where(
            Device.tenant_id == tenant_id,
            Device.site_id.is_(None),
            Device.status.notin_(["decommissioned"]),
        )
    )
    for dev in dev_result.scalars().all():
        if ("device", dev.id) in existing_keys:
            skipped += 1
            continue

        suggestion = _suggest_for_device(dev, tenant_sites)
        item = ProvisioningQueueItem(
            tenant_id=tenant_id,
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
    line_result = await db.execute(
        select(Line).where(
            Line.tenant_id == tenant_id,
            Line.site_id.is_(None),
            Line.status.notin_(["disconnected"]),
        )
    )
    for line in line_result.scalars().all():
        if ("line", line.id) in existing_keys:
            skipped += 1
            continue

        suggestion = _suggest_for_line(line, tenant_sites)
        item = ProvisioningQueueItem(
            tenant_id=tenant_id,
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

    logger.info(
        "Provisioning scan: tenant=%s created=%d skipped=%d by=%s",
        tenant_id, created, skipped, initiated_by,
    )
    return {"created": created, "skipped": skipped, "tenant_id": tenant_id}


def _base_flags() -> dict:
    """Default flags for a new queue item (unlinked = missing site and E911)."""
    return {"missing_site": True, "missing_e911": True}


def _suggest_for_sim(sim: Sim, sites: list[Site]) -> dict:
    """Generate suggestion fields for an unlinked SIM."""
    flags = _base_flags()
    if not sites:
        return {**flags, "status": "new", "suggestion_confidence": None}

    if len(sites) == 1:
        s = sites[0]
        has_e911 = bool(s.e911_street and s.e911_city)
        return {
            **flags,
            "status": "suggested",
            "suggested_site_id": s.site_id,
            "suggested_site_name": s.site_name,
            "suggested_tenant_id": s.tenant_id,
            "suggested_unit_type": "elevator_phone",
            "suggestion_confidence": 0.7,
            "suggestion_reason": f"Only site in tenant — {s.site_name}",
            "missing_e911": not has_e911,
            "needs_compliance_review": True,
        }

    if sim.carrier:
        carrier_match = [s for s in sites if (s.carrier or "").lower() == sim.carrier.lower()]
        if len(carrier_match) == 1:
            s = carrier_match[0]
            has_e911 = bool(s.e911_street and s.e911_city)
            return {
                **flags,
                "status": "suggested",
                "suggested_site_id": s.site_id,
                "suggested_site_name": s.site_name,
                "suggested_tenant_id": s.tenant_id,
                "suggestion_confidence": 0.5,
                "suggestion_reason": f"Carrier match ({sim.carrier}) — {s.site_name}",
                "missing_e911": not has_e911,
                "needs_compliance_review": True,
            }

    return {
        **flags,
        "status": "needs_review",
        "suggestion_confidence": None,
        "suggestion_reason": f"{len(sites)} sites available — manual assignment needed",
        "needs_compliance_review": True,
    }


def _suggest_for_device(dev: Device, sites: list[Site]) -> dict:
    """Generate suggestion fields for an unlinked device."""
    flags = _base_flags()
    if not sites:
        return {**flags, "status": "new", "suggestion_confidence": None}

    if len(sites) == 1:
        s = sites[0]
        has_e911 = bool(s.e911_street and s.e911_city)
        return {
            **flags,
            "status": "suggested",
            "suggested_site_id": s.site_id,
            "suggested_site_name": s.site_name,
            "suggested_tenant_id": s.tenant_id,
            "suggestion_confidence": 0.7,
            "suggestion_reason": f"Only site in tenant — {s.site_name}",
            "missing_e911": not has_e911,
        }

    return {
        **flags,
        "status": "needs_review",
        "suggestion_confidence": None,
        "suggestion_reason": f"{len(sites)} sites available — manual assignment needed",
    }


def _suggest_for_line(line: Line, sites: list[Site]) -> dict:
    """Generate suggestion fields for an unlinked line."""
    flags = _base_flags()
    if not sites:
        return {**flags, "status": "new", "suggestion_confidence": None}

    if len(sites) == 1:
        s = sites[0]
        has_e911 = bool(s.e911_street and s.e911_city)
        return {
            **flags,
            "status": "suggested",
            "suggested_site_id": s.site_id,
            "suggested_site_name": s.site_name,
            "suggested_tenant_id": s.tenant_id,
            "suggestion_confidence": 0.7,
            "suggestion_reason": f"Only site in tenant — {s.site_name}",
            "missing_e911": not has_e911,
        }

    return {
        **flags,
        "status": "needs_review",
        "suggestion_confidence": None,
        "suggestion_reason": f"{len(sites)} sites available — manual assignment needed",
    }
