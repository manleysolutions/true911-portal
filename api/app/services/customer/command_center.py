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
from app.services.customer import contributions as contrib
from app.services.customer import serialize as cs
from app.services.customer import service_inference as si
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


async def load_services_summary(db: AsyncSession, tenant_id: str, now) -> dict:
    """Portfolio Life-Safety service inventory (Phase 6): totals + protected /
    attention + a by-type breakdown.  Service counts are building/service-derived
    (not a raw device count) — Phase 5."""
    summary = await load_portfolio_summary(db, tenant_id, now)
    rows = (await db.execute(
        select(ServiceUnit.unit_type, func.count())
        .where(ServiceUnit.tenant_id == tenant_id)
        .group_by(ServiceUnit.unit_type))).all()
    by_type: dict = {}
    for ut, n in rows:
        label = cs.enterprise_service_label(ut)
        by_type[label] = by_type.get(label, 0) + int(n)
    total = summary["life_safety_services"]
    protected = summary["protected_services"]
    return {
        "as_of": now.isoformat(),
        "total_services": total,
        "protected_services": protected,
        "attention_services": max(total - protected, 0),
        "inventory": [{"service": k, "count": v} for k, v in sorted(by_type.items())],
    }


async def load_e911_history_all(db: AsyncSession, tenant_id: str):
    from app.models.e911_change_log import E911ChangeLog
    return (await db.execute(
        select(E911ChangeLog)
        .where(E911ChangeLog.tenant_id == tenant_id)
        .order_by(E911ChangeLog.requested_at.desc()))).scalars().all()


# ── Service intelligence: inferred Life-Safety services (Phase 1-7) ──
async def load_overrides(db: AsyncSession, tenant_id: str, site_id: str) -> dict:
    """Current manual service-classification overrides for a site — read from the
    append-only ActionAudit log (latest per device wins).  {device_id: service_type}."""
    import json

    from app.models.action_audit import ActionAudit
    rows = (await db.execute(
        select(ActionAudit).where(
            ActionAudit.tenant_id == tenant_id,
            ActionAudit.site_id == site_id,
            ActionAudit.action_type == si.OVERRIDE_ACTION,
        ).order_by(ActionAudit.id.desc()))).scalars().all()
    out: dict = {}
    for r in rows:
        try:
            d = json.loads(r.details or "{}")
        except Exception:
            continue
        did, st = d.get("device_id"), d.get("service_type")
        if did and st and did not in out:   # desc order -> first seen is latest
            out[did] = st
    return out


def _service_status(svc: dict, preview: bool, now) -> dict:
    """Service health (Phase 3) derived from the service's supporting equipment
    (never a raw device count).  Preview greens the operational axis."""
    if preview:
        return preview_protection(now)
    statuses = [_protection_from_device_assurance(it.get("_da"), now)
                for it in svc["equipment"] if it.get("_da")]
    as_of = now.isoformat()
    if not statuses:
        return cs.status_object("Unknown", as_of=as_of, reason="No monitored equipment yet")
    labels = [s["status"] for s in statuses]
    if "Critical" in labels:
        return cs.status_object("Critical", as_of=as_of, reason="This service needs attention.")
    if "Attention Needed" in labels:
        return cs.status_object("Attention Needed", as_of=as_of, reason="We're reviewing an item for this service.")
    if all(lbl == "Protected" for lbl in labels):
        ev = next((s.get("evidence") for s in statuses if s.get("evidence")), None)
        return cs.status_object("Protected", as_of=as_of, evidence=ev)
    return cs.status_object("Unknown", as_of=as_of, reason="We're confirming this service's status.")


async def _build_location_services(db, tenant_id, site, now) -> list[dict]:
    """Infer + assemble the Life-Safety Service cards for a site (service-first)."""
    preview = preview_enabled(tenant_id)
    device_by_id = {}
    if not preview:
        signals = await load_site_assurance_signals(db, tenant_id, site.site_id)
        if signals is not None:
            device_by_id = {d.device_id: d for d in compute_site_assurance(signals, now=now).devices}

    units = (await db.execute(
        select(ServiceUnit).where(
            ServiceUnit.tenant_id == tenant_id, ServiceUnit.site_id == site.site_id))).scalars().all()
    devices = (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id, Device.site_id == site.site_id))).scalars().all()
    lines = (await db.execute(
        select(Line).where(Line.tenant_id == tenant_id, Line.site_id == site.site_id))).scalars().all()
    overrides = await load_overrides(db, tenant_id, site.site_id)

    unit_by_device = {u.device_id: u for u in units if u.device_id}
    line_by_device = {ln.device_id: ln for ln in lines if ln.device_id}
    line_did_by_id = {ln.line_id: ln.did for ln in lines}

    present = set()
    items = []
    for d in devices:
        present.add(d.device_id)
        u = unit_by_device.get(d.device_id)
        ln = line_by_device.get(d.device_id)
        phone = ((line_did_by_id.get(u.line_id) if (u and u.line_id) else None)
                 or (ln.did if ln else None) or getattr(d, "msisdn", None))
        items.append({
            "device_id": d.device_id, "model": d.model, "device_type": d.device_type,
            "manufacturer": getattr(d, "manufacturer", None), "carrier": getattr(d, "carrier", None),
            "notes": getattr(d, "notes", None),
            "line_label": (f"{ln.provider} {ln.did or ''}".strip() if ln else None),
            "unit_type": u.unit_type if u else None, "unit_name": u.unit_name if u else None,
            "where": (u.location_description if u else None), "floor": (u.floor if u else None),
            "phone_number": phone, "_device": d, "_da": device_by_id.get(d.device_id), "_unit": u,
        })
    empty_units = [{"unit_type": u.unit_type, "unit_name": u.unit_name,
                    "where": u.location_description, "floor": u.floor}
                   for u in units if (not u.device_id or u.device_id not in present)]

    inferred = si.infer_services(items, overrides=overrides, empty_units=empty_units)

    out = []
    for svc in inferred:
        status = _service_status(svc, preview, now)
        equip_cards = []
        for it in svc["equipment"]:
            dstatus = preview_protection(now) if preview else _protection_from_device_assurance(it.get("_da"), now)
            equip_cards.append(cs.location_device(
                it["_device"], protection=dstatus, preview=preview, identifier=it.get("phone_number")))
        anchor = next((it["_unit"] for it in svc["equipment"] if it.get("_unit")), None)
        carrier = next((it.get("carrier") for it in svc["equipment"] if it.get("carrier")), None)
        ref = cs.encode_ref("svc", anchor.id) if anchor is not None else cs.encode_ref("svc", "i:" + svc["key"])
        attention = [status["reason"]] if (status.get("status") not in ("Protected", "Inactive")
                                           and status.get("reason")) else []
        out.append(cs.service_card(
            service_ref=ref, service_type=svc["service_type"], status=status,
            name=(anchor.unit_name if anchor is not None else None),
            where=svc["where"], floor=svc["floor"], equipment=equip_cards,
            confidence=svc["confidence"], carrier=carrier, phone_numbers=svc["phone_numbers"],
            attention_items=attention))
    return out


async def load_location_services(db: AsyncSession, tenant_id: str, location_ref: str, now):
    """Life-Safety Services for a location — inferred from equipment, each with
    the equipment that supports it grouped beneath (service-first, Phase 6/7).
    Returns None when the location is unknown/cross-tenant."""
    site = await resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None
    return {"location": site.site_name, "services": await _build_location_services(db, tenant_id, site, now)}


# ── Digital Twin location sub-resources (Phase 3/5/7) ────────────────
async def load_location_documents(db: AsyncSession, tenant_id: str, location_ref: str):
    site = await resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None
    return {"location": site.site_name, **cs.documents_placeholder()}


async def load_location_photos(db: AsyncSession, tenant_id: str, location_ref: str):
    site = await resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None
    return {"location": site.site_name, **cs.photos_placeholder()}


async def load_location_contacts(db: AsyncSession, tenant_id: str, location_ref: str):
    site = await resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None
    return {"location": site.site_name, **cs.location_contacts(site)}


async def load_location_inspections(db: AsyncSession, tenant_id: str, location_ref: str):
    site = await resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None
    # No inspection data source yet -> honest empty (real-only).
    return {"location": site.site_name, **cs.inspections_placeholder(items=[])}


async def load_location_health(db: AsyncSession, tenant_id: str, location_ref: str, now):
    """Digital Twin building health for ONE location — real signals only; unknown
    inputs lower confidence (never fabricated).  Reuses ``serialize.health_score``."""
    site = await resolve_site(db, tenant_id, location_ref)
    if site is None:
        return None

    # Location health derives from SERVICE health (Phase 4), NOT raw equipment
    # health: protected share of the location's inferred Life-Safety services.
    services = await _build_location_services(db, tenant_id, site, now)
    if services:
        protected = sum(1 for s in services if s["status"]["status"] == "Protected")
        operational = cs._pct(protected, len(services))
    else:
        operational = None

    devices = (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id, Device.site_id == site.site_id))).scalars().all()

    verified = (site.e911_status or "").lower() in cs._E911_VERIFIED
    address_present = all([site.e911_street, site.e911_city, site.e911_state, site.e911_zip])
    e911_val = (100.0 if verified else 0.0) if address_present else None

    reporting = sum(1 for d in devices if getattr(d, "last_heartbeat", None) is not None)
    # offline-equipment signal: share of devices reporting (unknown if none report).
    offline_val = cs._pct(reporting, len(devices)) if reporting else None

    health = cs.health_score({
        "e911_verified": e911_val,
        "service_coverage": operational,   # operational services
        "telemetry": offline_val,          # offline equipment inverse (reporting share)
        "alarm_testing": None,             # inspection/alarm-test freshness -> unknown
        "carrier": None,                   # carrier health -> unknown
    })

    # ── Building Workspace: separated health + Digital-Twin maturity (Phase 4/7).
    # Customer-contributed signals raise Digital-Twin completeness / documentation
    # and the maturity tier — the collaborative-workspace incentive.
    counts = await contrib.contribution_counts(db, tenant_id, site.site_id)
    has_docs = counts.get("document", 0) > 0
    has_photos = counts.get("photo", 0) > 0
    has_procedures = counts.get("procedure", 0) > 0
    has_inspection = counts.get("inspection", 0) > 0
    has_contacts = bool(getattr(site, "poc_name", None) or counts.get("contact", 0) > 0)

    # Digital-Twin completeness: how much of the twin is populated (real signals).
    completeness = cs._pct(
        sum([bool(services), bool(devices), bool(address_present), bool(has_contacts)]), 4)
    # Documentation: share of the three document artefact types present.
    documentation = cs._pct(sum([has_docs, has_photos, has_procedures]), 3)

    separated = cs.separated_health(
        operational=operational, completeness=completeness,
        compliance=None,               # no reliable per-site compliance signal yet -> unknown
        documentation=documentation)
    maturity = cs.building_maturity({
        "documentation": has_docs, "contacts": has_contacts, "procedures": has_procedures,
        "testing": has_inspection, "compliance": False, "photos": has_photos,
        "e911": verified})

    return {"location": site.site_name, "as_of": now.isoformat(), "health": health,
            "building_health": separated, "maturity": maturity}


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
