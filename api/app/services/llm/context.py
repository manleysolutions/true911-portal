"""Tenant-isolated context loader for LLLM summaries.

This is the SINGLE point where a SQL query is issued for an AI Health
Summary.  Every other module in :mod:`app.services.llm` operates on
the :class:`SummaryContext` this module returns — never the raw ORM —
so a code-review rule is enforceable:

    grep "select(" app/services/llm/**.py | grep -v context.py
    → must be empty.

The factory takes the resolved ``current_user`` (already
tenant-impersonation-aware via :func:`app.dependencies.get_current_user`)
and uses ``user.tenant_id`` as the filter on every query.  No callsite
gets to pass a tenant_id by hand.

``sources_used`` on the returned context is the structured evidence
trail the audit row and response will surface — every value comes from
a real lookup, not a guess.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.incident import Incident
from app.models.site import Site
from app.models.user import User
from app.services.llm.deterministic import (
    FleetSnapshot,
    IncidentSnapshot,
    SiteSnapshot,
    SummaryContext,
)

logger = logging.getLogger("true911.llm.context")


# A device is "stale" when its last_heartbeat is older than this.  Phase
# 1 keeps this as a simple wall-clock threshold; future phases may read
# Device.heartbeat_interval for a per-device check.
STALE_DEVICE_SECONDS = 300

# Incident statuses that mean "currently open" — matches the convention
# used by app.routers.command and the existing UI dashboards.
_OPEN_STATUSES = ("open", "acknowledged", "in_progress", "new")


class LLLMContext:
    """Factory that builds a :class:`SummaryContext` for one summary call.

    Instances are short-lived (per-request).  Tenant isolation is
    enforced by always filtering on ``self.tenant_id`` — set once from
    the authenticated user and never mutated.
    """

    def __init__(self, user: User, db: AsyncSession):
        self.user = user
        self.db = db
        # ``user.tenant_id`` is the EFFECTIVE tenant (post-impersonation)
        # — exactly the value every other tenant-scoped query in the
        # codebase uses.  Store it once so a typo or future refactor
        # can't accidentally widen the scope.
        self.tenant_id: str = user.tenant_id

    # ─── Public loaders ────────────────────────────────────────────

    async def load_fleet(self) -> SummaryContext:
        """Build a fleet-scope context from existing structured fields."""
        fleet = await self._build_fleet_snapshot()
        incidents = await self._load_open_incidents(site_id=None, limit=10)

        sources_used: List[str] = [
            f"sites:tenant={self.tenant_id}",
            f"devices:tenant={self.tenant_id}",
            f"incidents:tenant={self.tenant_id}:open",
        ]
        return SummaryContext(
            scope="fleet",
            scope_id=None,
            tenant_id=self.tenant_id,
            fleet=fleet,
            incidents=incidents,
            sources_used=sources_used,
        )

    async def load_site(self, site_id: str) -> SummaryContext:
        """Build a single-site-scope context.

        Returns a context whose ``site`` is None when the requested
        site does not belong to the caller's tenant — the deterministic
        builder converts that into a 'site not found' message rather
        than leaking existence across tenants.
        """
        site_snapshot = await self._build_site_snapshot(site_id)
        incidents = await self._load_open_incidents(site_id=site_id, limit=10)

        sources_used: List[str] = [
            f"sites:site_id={site_id}",
            f"devices:site_id={site_id}",
            f"incidents:site_id={site_id}:open",
        ]
        return SummaryContext(
            scope="site",
            scope_id=site_id,
            tenant_id=self.tenant_id,
            site=site_snapshot,
            incidents=incidents,
            sources_used=sources_used,
        )

    # ─── Builders ──────────────────────────────────────────────────

    async def _build_fleet_snapshot(self) -> FleetSnapshot:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_DEVICE_SECONDS)

        # Total sites for tenant
        total_sites_q = select(func.count(Site.id)).where(
            Site.tenant_id == self.tenant_id
        )
        total_sites = int((await self.db.execute(total_sites_q)).scalar() or 0)

        # "Connected" — sites whose most recent device heartbeat is fresh.
        # Phase 1 approximates with: any device on the site with
        # last_heartbeat >= cutoff.
        connected_sites_q = (
            select(func.count(func.distinct(Device.site_id)))
            .where(Device.tenant_id == self.tenant_id)
            .where(Device.last_heartbeat >= cutoff)
        )
        connected_sites = int((await self.db.execute(connected_sites_q)).scalar() or 0)

        # Stale devices — active devices with no fresh heartbeat
        stale_devices_q = (
            select(func.count(Device.id))
            .where(Device.tenant_id == self.tenant_id)
            .where(Device.status == "active")
            .where(
                (Device.last_heartbeat.is_(None))  # never reported
                | (Device.last_heartbeat < cutoff)  # reported but stale
            )
        )
        stale_devices = int((await self.db.execute(stale_devices_q)).scalar() or 0)

        # Open incidents — total and critical
        active_incidents_q = (
            select(func.count(Incident.id))
            .where(Incident.tenant_id == self.tenant_id)
            .where(Incident.status.in_(_OPEN_STATUSES))
        )
        active_incidents = int((await self.db.execute(active_incidents_q)).scalar() or 0)

        critical_incidents_q = active_incidents_q.where(
            Incident.severity == "critical"
        )
        critical_incidents = int((await self.db.execute(critical_incidents_q)).scalar() or 0)

        # "Needs attention" = sites with at least one open incident.
        # Cheap approximation; UI does a richer derivation.
        sites_needing_attention_q = (
            select(func.count(func.distinct(Incident.site_id)))
            .where(Incident.tenant_id == self.tenant_id)
            .where(Incident.status.in_(_OPEN_STATUSES))
        )
        sites_needing_attention = int(
            (await self.db.execute(sites_needing_attention_q)).scalar() or 0
        )

        return FleetSnapshot(
            total_sites=total_sites,
            connected_sites=connected_sites,
            sites_needing_attention=sites_needing_attention,
            active_incidents=active_incidents,
            critical_incidents=critical_incidents,
            stale_devices=stale_devices,
        )

    async def _build_site_snapshot(self, site_id: str) -> Optional[SiteSnapshot]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_DEVICE_SECONDS)

        # Tenant-scoped lookup — returns None if the site belongs to a
        # different tenant.  This is the core isolation guarantee.
        site_q = select(Site).where(
            Site.site_id == site_id,
            Site.tenant_id == self.tenant_id,
        )
        site_row: Optional[Site] = (await self.db.execute(site_q)).scalar_one_or_none()
        if site_row is None:
            return None

        # Last heartbeat across any device at this site
        last_hb_q = (
            select(func.max(Device.last_heartbeat))
            .where(Device.tenant_id == self.tenant_id)
            .where(Device.site_id == site_id)
        )
        last_hb: Optional[datetime] = (await self.db.execute(last_hb_q)).scalar_one_or_none()
        last_hb_seconds_ago: Optional[int]
        if last_hb is None:
            last_hb_seconds_ago = None
        else:
            if last_hb.tzinfo is None:
                last_hb = last_hb.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - last_hb
            last_hb_seconds_ago = max(0, int(delta.total_seconds()))

        stale_devices_q = (
            select(func.count(Device.id))
            .where(Device.tenant_id == self.tenant_id)
            .where(Device.site_id == site_id)
            .where(Device.status == "active")
            .where(
                (Device.last_heartbeat.is_(None))
                | (Device.last_heartbeat < cutoff)
            )
        )
        stale_devices = int((await self.db.execute(stale_devices_q)).scalar() or 0)

        active_incidents_q = (
            select(func.count(Incident.id))
            .where(Incident.tenant_id == self.tenant_id)
            .where(Incident.site_id == site_id)
            .where(Incident.status.in_(_OPEN_STATUSES))
        )
        active_incidents = int((await self.db.execute(active_incidents_q)).scalar() or 0)

        critical_incidents_q = active_incidents_q.where(
            Incident.severity == "critical"
        )
        critical_incidents = int(
            (await self.db.execute(critical_incidents_q)).scalar() or 0
        )

        connection_status = "stale" if last_hb_seconds_ago is None or last_hb_seconds_ago > STALE_DEVICE_SECONDS else "connected"

        needs_attention = bool(
            critical_incidents
            or active_incidents
            or stale_devices
            or last_hb_seconds_ago is None
            or last_hb_seconds_ago > STALE_DEVICE_SECONDS
        )

        return SiteSnapshot(
            site_id=site_row.site_id,
            site_name=site_row.site_name,
            needs_attention=needs_attention,
            active_incidents=active_incidents,
            critical_incidents=critical_incidents,
            stale_devices=stale_devices,
            overdue_tasks=0,  # not modeled in Phase 1
            last_heartbeat_seconds_ago=last_hb_seconds_ago,
            connection_status=connection_status,
        )

    async def _load_open_incidents(
        self, *, site_id: Optional[str], limit: int = 10
    ) -> List[IncidentSnapshot]:
        """Load open incidents, optionally site-scoped."""
        now = datetime.now(timezone.utc)
        q = (
            select(Incident)
            .where(Incident.tenant_id == self.tenant_id)
            .where(Incident.status.in_(_OPEN_STATUSES))
            .order_by(Incident.opened_at.desc())
            .limit(limit)
        )
        if site_id is not None:
            q = q.where(Incident.site_id == site_id)
        rows = (await self.db.execute(q)).scalars().all()

        out: List[IncidentSnapshot] = []
        for r in rows:
            opened = r.opened_at
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
            minutes = max(0, int((now - opened).total_seconds() // 60))
            # We deliberately store r.summary unchanged here — the
            # validator scans for injection markers BEFORE the text is
            # included in any prompt, so this snapshot represents what
            # the operator already sees in the existing Incidents UI.
            out.append(
                IncidentSnapshot(
                    incident_id=r.incident_id,
                    severity=r.severity or "info",
                    summary=r.summary or "",
                    opened_minutes_ago=minutes,
                    site_id=r.site_id,
                )
            )
        return out


def fingerprint_inputs_for_fleet(ctx: SummaryContext) -> dict:
    """Stable dict for the cache fingerprint, fleet scope.

    Lives in the context module because both the orchestrator (when
    computing the cache key) and tests (when asserting fingerprint
    stability) need it.
    """
    return {
        "scope": "fleet",
        "tenant_id": ctx.tenant_id,
        "fleet": {
            "total_sites": ctx.fleet.total_sites,
            "connected_sites": ctx.fleet.connected_sites,
            "stale_devices": ctx.fleet.stale_devices,
            "active_incidents": ctx.fleet.active_incidents,
            "critical_incidents": ctx.fleet.critical_incidents,
            "sites_needing_attention": ctx.fleet.sites_needing_attention,
        },
        "open_incident_ids": sorted(i.incident_id for i in ctx.incidents),
    }


def fingerprint_inputs_for_site(ctx: SummaryContext) -> dict:
    """Stable dict for the cache fingerprint, site scope."""
    site = ctx.site
    return {
        "scope": "site",
        "tenant_id": ctx.tenant_id,
        "scope_id": ctx.scope_id,
        "site_present": site is not None,
        "site": (
            {
                "site_id": site.site_id,
                "needs_attention": site.needs_attention,
                "active_incidents": site.active_incidents,
                "critical_incidents": site.critical_incidents,
                "stale_devices": site.stale_devices,
                # Round seconds to the nearest 30s bucket so jitter in
                # the heartbeat timestamp doesn't bust the cache every
                # second.
                "last_heartbeat_bucket": (
                    None
                    if site.last_heartbeat_seconds_ago is None
                    else (site.last_heartbeat_seconds_ago // 30) * 30
                ),
                "connection_status": site.connection_status,
            }
            if site is not None
            else None
        ),
        "open_incident_ids": sorted(i.incident_id for i in ctx.incidents),
    }
