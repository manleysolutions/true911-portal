"""Promote a CONFIRMED-mapped Zoho lifecycle_state onto sites.lifecycle_status.

This is the ONLY Zoho code path that writes a production row, and it writes ONLY
the additive lifecycle columns — never the operational ``sites.status``, and
never a delete.  It acts solely on records whose ``external_record_map`` is
``map_status == "confirmed"`` with a ``site_id`` link, and only when the staged
record has a non-null normalized ``lifecycle_state``.

Apply is gated by ``FEATURE_ZOHO_LIFECYCLE_PROMOTION`` (default off); the planner
(dry run) is always safe to call and never writes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.external_record_map import ExternalRecordMap
from app.models.site import Site
from app.models.zoho_subscription_record import ZohoSubscriptionRecord

logger = logging.getLogger("true911.zoho_lifecycle_promotion")

LIFECYCLE_SOURCE = "zoho_crm"


def promotion_enabled() -> bool:
    return str(settings.FEATURE_ZOHO_LIFECYCLE_PROMOTION).strip().lower() == "true"


def _plan_item(rec: ZohoSubscriptionRecord, site: Site) -> dict[str, Any]:
    proposed = rec.lifecycle_state
    current = site.lifecycle_status
    return {
        "subscription_mgmt_id": rec.subscription_mgmt_id,
        "site_id": site.site_id,
        "current_lifecycle_status": current,
        "proposed_lifecycle_status": proposed,
        "would_change": current != proposed,
        # Operational status shown for context only — it is NEVER modified here.
        "operational_status": site.status,
    }


async def _confirmed_rows(db: AsyncSession, org_id: str):
    """(record, map, site) for confirmed, site-linked, normalized records — tenant-scoped."""
    q = (
        select(ZohoSubscriptionRecord, ExternalRecordMap, Site)
        .join(ExternalRecordMap, ZohoSubscriptionRecord.external_record_map_id == ExternalRecordMap.id)
        .join(Site, ExternalRecordMap.site_id == Site.site_id)
        .where(
            ZohoSubscriptionRecord.org_id == org_id,
            ExternalRecordMap.map_status == "confirmed",
            ExternalRecordMap.site_id.isnot(None),
            ZohoSubscriptionRecord.lifecycle_state.isnot(None),
            Site.tenant_id == org_id,
        )
    )
    return (await db.execute(q)).all()


async def plan_site_promotion(db: AsyncSession, org_id: str) -> list[dict[str, Any]]:
    """Compute what promotion WOULD write — no DB writes."""
    return [_plan_item(rec, site) for rec, _rec_map, site in await _confirmed_rows(db, org_id)]


async def apply_site_promotion(db: AsyncSession, org_id: str) -> dict[str, Any]:
    """Write proposed lifecycle_status to confirmed-mapped sites (additive only).

    Gated: raises RuntimeError when FEATURE_ZOHO_LIFECYCLE_PROMOTION is off.
    Writes only lifecycle_status / lifecycle_source / lifecycle_synced_at, and
    only when the value actually changes (idempotent).  Never touches
    site.status; never deletes.
    """
    if not promotion_enabled():
        raise RuntimeError(
            "Zoho lifecycle promotion is disabled. Set "
            "FEATURE_ZOHO_LIFECYCLE_PROMOTION=true to apply."
        )

    now = datetime.now(timezone.utc)
    applied: list[dict[str, Any]] = []
    for rec, _rec_map, site in await _confirmed_rows(db, org_id):
        if site.lifecycle_status != rec.lifecycle_state:
            before = site.lifecycle_status
            site.lifecycle_status = rec.lifecycle_state
            site.lifecycle_source = LIFECYCLE_SOURCE
            site.lifecycle_synced_at = now
            applied.append({
                "site_id": site.site_id,
                "subscription_mgmt_id": rec.subscription_mgmt_id,
                "from": before,
                "to": rec.lifecycle_state,
            })

    if applied:
        await db.flush()
    logger.info(
        "Zoho lifecycle promotion applied org_id=%s changed=%d", org_id, len(applied)
    )
    return {"applied": applied, "applied_count": len(applied)}
