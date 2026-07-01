"""Customer Command Center aggregation (Phase 1/4/6/8) — READ-ONLY.

Aggregates a tenant's life-safety portfolio into the executive summary + health
score, the service-first location detail (services with equipment grouped
beneath them), the activity timeline, and enterprise search.

Composes ONLY through the customer serializers (``serialize.py``) so no raw
operational field can leak.  Respects Preview Mode for the OPERATIONAL axis
(green), and holds E911 to the truth.  Never writes; never fabricates (missing
signals become "unknown", which lowers health confidence).
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.line import Line
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.services.assurance import compute_site_assurance
from app.services.assurance.loader import load_site_assurance_signals
from app.services.customer import serialize as cs
from app.services.customer.preview import preview_enabled, preview_protection
from app.services.customer.portfolio import (
    _protection_from_device_assurance,
    _service_protection,
    company_name,
    load_e911_history,
    load_portfolio,
    resolve_site,
)

_ACTIVITY_MAX = 8
_SEARCH_MAX = 25


# ── Portfolio summary + health (Phase 1 + 6) ─────────────────────────
async def load_portfolio_summary(db: AsyncSession, tenant_id: str, now) -> dict:
    portfolio = await load_portfolio(db, tenant_id, now)
    counts = cs.portfolio_counts([p["status"] for _s, p in portfolio])
    company = await company_name(db, tenant_id)
    protected_site_ids = {s.site_id for s, p in portfolio if p["status"] == "Protected"}

    units = (await db.execute(
        select(ServiceUnit.site_id, ServiceUnit.device_id)
        .where(ServiceUnit.tenant_id == tenant_id))).all()
    services_total = len(units)
    units_with_device = sum(1 for _sid, did in units if did)
    protected_services = sum(1 for sid, _did in units if sid in protected_site_ids)

    devices_total = int((await db.execute(
        select(func.count()).select_from(Device).where(Device.tenant_id == tenant_id))).scalar() or 0)
    devices_reporting = int((await db.execute(
        select(func.count()).select_from(Device).where(
            Device.tenant_id == tenant_id, Device.last_heartbeat.isnot(None)))).scalar() or 0)

    numbers = set()
    for (did,) in (await db.execute(
        select(Line.did).where(Line.tenant_id == tenant_id, Line.did.isnot(None)))).all():
        if did:
            numbers.add(did.strip())
    for (msisdn,) in (await db.execute(
        select(Device.msisdn).where(Device.tenant_id == tenant_id, Device.msisdn.isnot(None)))).all():
        if msisdn:
            numbers.add(msisdn.strip())

    e911_with_address = sum(1 for s, _p in portfolio
                            if all([s.e911_street, s.e911_city, s.e911_state, s.e911_zip]))
    e911_verified = sum(1 for s, _p in portfolio
                        if (s.e911_status or "").lower() in cs._E911_VERIFIED)

    # Health: honest signals only; unknowns -> lower confidence (never fabricated).
    telemetry_val = cs._pct(devices_reporting, devices_total) if devices_reporting else None
    health = cs.health_score({
        "e911_verified": cs._pct(e911_verified, e911_with_address),
        "service_coverage": cs._pct(units_with_device, services_total),
        "telemetry": telemetry_val,
        "alarm_testing": None,   # no data source yet -> unknown
        "carrier": None,         # no data source yet -> unknown
    })

    logs = (await load_e911_history_all(db, tenant_id))[:_ACTIVITY_MAX]
    recent_activity = [cs.timeline_item(lg) for lg in logs]

    return cs.portfolio_summary(
        company=company, counts=counts, services=services_total,
        protected_services=protected_services, devices=devices_total,
        phone_numbers=len(numbers), e911_verified=e911_verified,
        e911_with_address=e911_with_address, health=health,
        recent_activity=recent_activity, upcoming_maintenance=[],
        as_of=now.isoformat())


async def load_portfolio_health(db: AsyncSession, tenant_id: str, now) -> dict:
    """The health score on its own (Phase 6 endpoint)."""
    summary = await load_portfolio_summary(db, tenant_id, now)
    return {"as_of": now.isoformat(), "health": summary["monthly_health_score"]}


async def load_e911_history_all(db: AsyncSession, tenant_id: str):
    from app.models.e911_change_log import E911ChangeLog
    return (await db.execute(
        select(E911ChangeLog)
        .where(E911ChangeLog.tenant_id == tenant_id)
        .order_by(E911ChangeLog.requested_at.desc()))).scalars().all()


# ── Service-first location detail (Phase 4) ──────────────────────────
async def load_location_services(db: AsyncSession, tenant_id: str, location_ref: str, now):
    """Life-Safety Services for a location, each with the equipment that supports
    it grouped beneath.  Returns None when the location is unknown/cross-tenant."""
    site = await resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None
    preview = preview_enabled(tenant_id)
    device_by_id = {}
    if not preview:
        signals = await load_site_assurance_signals(db, tenant_id, site.site_id)
        if signals is not None:
            device_by_id = {d.device_id: d for d in compute_site_assurance(signals, now=now).devices}

    units = (await db.execute(
        select(ServiceUnit).where(
            ServiceUnit.tenant_id == tenant_id, ServiceUnit.site_id == site.site_id))).scalars().all()

    # devices for the site (one query) + line DIDs for callback identifiers.
    device_rows = {d.device_id: d for d in (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id, Device.site_id == site.site_id))).scalars().all()}
    line_did = {r.line_id: r.did for r in (await db.execute(
        select(Line).where(Line.tenant_id == tenant_id, Line.site_id == site.site_id))).scalars().all()}

    services = []
    for u in units:
        da = device_by_id.get(u.device_id) if u.device_id else None
        status = preview_protection(now) if preview else _service_protection(u, da, now)
        equip = []
        dev = device_rows.get(u.device_id) if u.device_id else None
        if dev is not None:
            identifier = (line_did.get(u.line_id) if u.line_id else None) or getattr(dev, "msisdn", None)
            dev_status = preview_protection(now) if preview else _protection_from_device_assurance(da, now)
            equip.append(cs.location_device(dev, protection=dev_status, preview=preview, identifier=identifier))
        services.append(cs.service_with_equipment(u, status=status, equipment=equip))
    return {"location": site.site_name, "services": services}


async def load_location_timeline(db: AsyncSession, tenant_id: str, location_ref: str):
    """Customer-safe activity timeline for a location (real E911-log data only)."""
    site = await resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None
    logs = await load_e911_history(db, tenant_id, site.site_id)
    return {"location": site.site_name, "timeline": [cs.timeline_item(lg) for lg in logs]}


# ── Enterprise search (Phase 3 + 8) ──────────────────────────────────
async def search_portfolio(db: AsyncSession, tenant_id: str, q: str, now):
    """Search a tenant's portfolio by store name/number, city, state, phone
    number, service type, and equipment/service label — returns matching
    LOCATIONS (customer-safe).  Tenant-scoped; empty query -> empty."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "results": []}
    like = f"%{q.lower()}%"
    site_ids: set[str] = set()

    # Sites by name / city / state / store id
    for (sid,) in (await db.execute(
        select(Site.site_id).where(
            Site.tenant_id == tenant_id,
            or_(func.lower(Site.site_name).like(like),
                func.lower(Site.e911_city).like(like),
                func.lower(Site.e911_state).like(like),
                func.lower(Site.site_id).like(like))))).all():
        site_ids.add(sid)
    # Service units by type / name / where
    for (sid,) in (await db.execute(
        select(ServiceUnit.site_id).where(
            ServiceUnit.tenant_id == tenant_id,
            or_(func.lower(ServiceUnit.unit_type).like(like),
                func.lower(ServiceUnit.unit_name).like(like),
                func.lower(ServiceUnit.location_description).like(like))))).all():
        if sid:
            site_ids.add(sid)
    # Devices by phone number (msisdn)
    for (sid,) in (await db.execute(
        select(Device.site_id).where(
            Device.tenant_id == tenant_id, func.lower(Device.msisdn).like(like)))).all():
        if sid:
            site_ids.add(sid)
    # Lines by DID (phone number)
    for (sid,) in (await db.execute(
        select(Line.site_id).where(
            Line.tenant_id == tenant_id, func.lower(Line.did).like(like)))).all():
        if sid:
            site_ids.add(sid)

    if not site_ids:
        return {"query": q, "results": []}
    sites = (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id, Site.site_id.in_(site_ids))
        .order_by(Site.site_name).limit(_SEARCH_MAX))).scalars().all()
    results = [{
        "location_ref": cs.encode_ref("loc", s.id),
        "location": s.site_name,
        "city": s.e911_city,
        "state": s.e911_state,
        "emergency_address_state": cs.e911_state_label(s),
        "map_point": cs._map_point(s),
    } for s in sites]
    return {"query": q, "results": results}
