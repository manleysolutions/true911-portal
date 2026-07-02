"""Customer portfolio orchestration (PR-C2).

Composition layer between the read-only Assurance engine and the customer
serializer.  It loads tenant sites, runs ``compute_site_assurance`` per site,
and maps each engine result to a customer ``StatusObject`` using ONLY PR-C1
serializer primitives (``status_object`` / ``evidence_object``).  It emits no
raw model fields — all customer-facing shaping happens in ``serialize.py``.

Reused by GET /api/customer/dashboard and /locations[/{ref}].

NOTE (perf): assurance is computed per site via ``load_site_assurance_signals``
(~6 bounded queries/site).  At RH scale (42 sites) a portfolio read is ~250
queries.  A batched loader / assurance snapshot is the planned optimization
(docs/ASSURANCE_ENGINE.md) — out of scope for PR-C2.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.device import Device
from app.models.e911_change_log import E911ChangeLog
from app.models.line import Line
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.models.tenant import Tenant
from app.services.assurance import compute_site_assurance, reason_codes as rc
from app.services.assurance.loader import load_site_assurance_signals
from app.services.assurance.signals import AssuranceLabel
from app.services.customer.preview import preview_enabled, preview_protection
from app.services.customer.refs import decode_ref
from app.services.customer.serialize import (
    e911_endpoint_item,
    evidence_object,
    location_device,
    service_preview,
    status_object,
)

# Engine label -> customer six-label vocabulary (serialize.SIX_LABELS).
# Explicit so a vocabulary change in either layer fails a drift test rather
# than silently producing "Unknown".  (Engine INACTIVE value is
# "Inactive / Deactivated"; the customer label is "Inactive".)
_LABEL_MAP = {
    AssuranceLabel.PROTECTED: "Protected",
    AssuranceLabel.ATTENTION: "Attention Needed",
    AssuranceLabel.CRITICAL: "Critical",
    AssuranceLabel.PENDING_INSTALL: "Pending Install",
    AssuranceLabel.INACTIVE: "Inactive",
    AssuranceLabel.UNKNOWN: "Unknown",
}


def _evidence(result, signals, as_of: str):
    """Build an EvidenceObject for a Protected site, or None.  When None, the
    no-false-green rule in ``status_object`` recodes the label to Unknown."""
    signals_out = []
    online = sum(1 for d in result.devices if getattr(d, "last_heartbeat_at", None) is not None)
    if online:
        signals_out.append(f"{online} device{'s' if online != 1 else ''} reporting")
    lt = getattr(signals, "last_test", None)
    if lt is not None and (getattr(lt, "result", "") or "").lower() == "pass":
        signals_out.append(f"test passed {lt.at.date().isoformat()}")
    return evidence_object(as_of, signals_out) if signals_out else None


def _reason_from_codes(codes):
    for code in codes or ():
        meta = rc.ALL.get(code)
        if meta is not None and getattr(meta, "customer_message", None):
            return meta.customer_message
    return None


def _reason(result):
    return _reason_from_codes(result.reason_codes)


def _protection_from_result(result, signals, now) -> dict:
    """Map a computed AssuranceResult to a customer StatusObject (site level)."""
    label = _LABEL_MAP.get(result.label, "Unknown")
    as_of = now.isoformat()
    if label == "Protected":
        # status_object downgrades to Unknown if evidence is empty (no false green)
        return status_object("Protected", as_of=as_of, evidence=_evidence(result, signals, as_of))
    return status_object(label, as_of=as_of, reason=_reason(result))


def protection_from_assurance(signals, now) -> dict:
    """Map an Assurance engine result for one site to a customer StatusObject."""
    return _protection_from_result(compute_site_assurance(signals, now=now), signals, now)


# ── Device / service composition (PR-C3) ─────────────────────────────
def _protection_from_device_assurance(da, now) -> dict:
    """Equipment protection from the engine's per-device label (consistent
    with the site assurance).  None device -> Unknown empty state."""
    as_of = now.isoformat()
    if da is None:
        return status_object("Unknown", as_of=as_of, reason="No monitored equipment yet")
    label = _LABEL_MAP.get(da.label, "Unknown")
    if label == "Protected":
        ev = evidence_object(as_of, ["device reporting"]) if getattr(da, "last_heartbeat_at", None) else None
        return status_object("Protected", as_of=as_of, evidence=ev)
    return status_object(label, as_of=as_of, reason=_reason_from_codes(getattr(da, "reason_codes", ())))


def _service_reason(da, comp):
    if comp == "non_compliant":
        return "A compliance item needs attention."
    if comp in ("review_required", "partially_compliant"):
        return "A compliance review is in progress."
    return _reason_from_codes(getattr(da, "reason_codes", ())) if da is not None else None


def _service_protection(unit, da, now) -> dict:
    """Compose the service's StatusObject from the engine device label +
    service status + compliance (deterministic, six-label vocabulary)."""
    as_of = now.isoformat()
    ustatus = (unit.status or "").lower()
    if ustatus == "pending_install":
        return status_object("Pending Install", as_of=as_of, reason="This service is being set up.")
    if ustatus in ("inactive", "decommissioned"):
        return status_object("Inactive", as_of=as_of, reason="This service is not currently active.")
    comp = (unit.compliance_status or "").lower()
    dev_label = _LABEL_MAP.get(da.label, "Unknown") if da is not None else "Unknown"
    if comp == "non_compliant" or dev_label == "Critical":
        return status_object("Critical", as_of=as_of, reason=_service_reason(da, comp) or "This service needs attention.")
    if comp in ("review_required", "partially_compliant") or dev_label == "Attention Needed":
        return status_object("Attention Needed", as_of=as_of, reason=_service_reason(da, comp) or "We're reviewing an item for this service.")
    if dev_label == "Protected":
        ev = evidence_object(as_of, ["device reporting"]) if (da is not None and getattr(da, "last_heartbeat_at", None)) else None
        return status_object("Protected", as_of=as_of, evidence=ev)
    return status_object("Unknown", as_of=as_of, reason="We're confirming this service's status.")


def _unknown(now) -> dict:
    return status_object("Unknown", as_of=now.isoformat(), reason="Status cannot be confirmed yet")


async def load_portfolio(db: AsyncSession, tenant_id: str, now) -> list[tuple[Site, dict]]:
    """Return (Site, protection StatusObject) for every site in the tenant.

    When preview is enabled for the tenant (RH go-live login preview), the
    operational protection is forced to Active/Protected — see
    ``services.customer.preview``.  The E911 axis is untouched (its own
    endpoint reads real stored data)."""
    preview = preview_enabled(tenant_id)
    sites = (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id)
    )).scalars().all()
    out: list[tuple[Site, dict]] = []
    for site in sites:
        if preview:
            out.append((site, preview_protection(now)))
            continue
        signals = await load_site_assurance_signals(db, tenant_id, site.site_id)
        protection = protection_from_assurance(signals, now) if signals is not None else _unknown(now)
        out.append((site, protection))
    return out


async def resolve_location(db: AsyncSession, tenant_id: str, location_ref: str, now):
    """Resolve an opaque location_ref to (Site, site_protection,
    services_preview[]) within the caller's tenant, or None (unknown / forged /
    cross-tenant ref).  The services preview reuses the site assurance result
    (computed once) — no extra per-service queries."""
    raw = decode_ref("loc", location_ref)
    if raw is None:
        return None
    try:
        site_pk = int(raw)
    except (TypeError, ValueError):
        return None
    site = (await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if site is None:
        return None
    preview = preview_enabled(tenant_id)
    if preview:
        site_protection = preview_protection(now)
        device_by_id = {}
    else:
        signals = await load_site_assurance_signals(db, tenant_id, site.site_id)
        if signals is not None:
            result = compute_site_assurance(signals, now=now)
            site_protection = _protection_from_result(result, signals, now)
            device_by_id = {d.device_id: d for d in result.devices}
        else:
            site_protection = _unknown(now)
            device_by_id = {}
    units = (await db.execute(
        select(ServiceUnit).where(
            ServiceUnit.tenant_id == tenant_id, ServiceUnit.site_id == site.site_id
        )
    )).scalars().all()
    previews = [
        service_preview(
            u,
            protection=preview_protection(now) if preview else _service_protection(
                u, device_by_id.get(u.device_id) if u.device_id else None, now
            ),
        )
        for u in units
    ]
    devices = await _location_devices(db, tenant_id, site.site_id, units,
                                      device_by_id, preview, now)
    return site, site_protection, previews, devices


async def _location_devices(db, tenant_id, site_id, units, device_by_id, preview, now):
    """Customer-safe device list for a location.  Resolves each device's
    line/callback identifier from a linked line (``Line.did``) else its own
    number (``Device.msisdn``) — tenant-scoped, real data only."""
    device_rows = (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id, Device.site_id == site_id)
    )).scalars().all()
    if not device_rows:
        return []
    # line DID per device (one query for the site), falling back to msisdn.
    line_did = {
        line_id: did
        for line_id, did, dev_id in (
            (r.line_id, r.did, r.device_id) for r in (await db.execute(
                select(Line).where(Line.tenant_id == tenant_id, Line.site_id == site_id)
            )).scalars().all()
        )
    }
    unit_line_by_device = {u.device_id: u.line_id for u in units if u.device_id and u.line_id}
    out = []
    for d in device_rows:
        line_id = unit_line_by_device.get(d.device_id)
        identifier = (line_did.get(line_id) if line_id else None) or getattr(d, "msisdn", None)
        if preview:
            protection = preview_protection(now)
        else:
            protection = _protection_from_device_assurance(device_by_id.get(d.device_id), now)
        out.append(location_device(d, protection=protection, preview=preview, identifier=identifier))
    return out


async def resolve_service(db: AsyncSession, tenant_id: str, service_ref: str, now):
    """Resolve a svc ref to (ServiceUnit, Device|None, service_protection,
    equipment_protection) within the caller's tenant, or None.  Equipment
    protection uses the engine's per-device label (single source of truth)."""
    raw = decode_ref("svc", service_ref)
    if raw is None:
        return None
    try:
        unit_pk = int(raw)
    except (TypeError, ValueError):
        return None
    unit = (await db.execute(
        select(ServiceUnit).where(ServiceUnit.id == unit_pk, ServiceUnit.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if unit is None:
        return None
    preview = preview_enabled(tenant_id)
    da = None
    device_row = None
    if unit.site_id and unit.device_id:
        if not preview:
            signals = await load_site_assurance_signals(db, tenant_id, unit.site_id)
            if signals is not None:
                result = compute_site_assurance(signals, now=now)
                da = next((d for d in result.devices if d.device_id == unit.device_id), None)
        device_row = (await db.execute(
            select(Device).where(Device.device_id == unit.device_id, Device.tenant_id == tenant_id)
        )).scalar_one_or_none()
    if preview:
        # Preview forces both axes to Active/Protected; the raw device row is
        # still returned unchanged so the serializer reads real (non-jargon)
        # fields — only the derived health string is overridden downstream.
        return unit, device_row, preview_protection(now), preview_protection(now)
    return unit, device_row, _service_protection(unit, da, now), _protection_from_device_assurance(da, now)


async def load_e911_endpoints(db: AsyncSession, tenant_id: str, site_id: str) -> list[dict]:
    """Per-service emergency-endpoint detail for a site's E911 record — real
    stored data only.  Each entry carries the service type, where it is
    (unit/suite/floor), and the callback number / BTN / line identifier
    resolved from the linked line (``Line.did``) or device (``Device.msisdn``).

    Tenant-scoped.  A unit with no linked, in-tenant line/device simply has no
    callback number ("where applicable") — nothing is fabricated.  This is the
    ONE customer surface where the emergency callback number is intentionally
    shown (a life-safety field the customer must be able to verify), unlike the
    equipment-health view where the raw number stays hidden (§7)."""
    units = (await db.execute(
        select(ServiceUnit).where(
            ServiceUnit.tenant_id == tenant_id, ServiceUnit.site_id == site_id
        )
    )).scalars().all()
    out: list[dict] = []
    for unit in units:
        callback = None
        if unit.line_id:
            callback = (await db.execute(
                select(Line.did).where(
                    Line.line_id == unit.line_id, Line.tenant_id == tenant_id
                )
            )).scalar_one_or_none()
        if not callback and unit.device_id:
            callback = (await db.execute(
                select(Device.msisdn).where(
                    Device.device_id == unit.device_id, Device.tenant_id == tenant_id
                )
            )).scalar_one_or_none()
        out.append(e911_endpoint_item(unit, callback_number=callback))
    return out


async def resolve_site(db: AsyncSession, tenant_id: str, location_ref: str):
    """Lightweight loc-ref -> Site resolver (no assurance) for the E911 axis.

    Also accepts a registry ``bldg`` ref (when registry mode is enabled): it
    resolves the canonical building to its PRIMARY linked Site, so the secondary
    site-based endpoints (E911 / timeline / contacts / contributions) keep working
    with building refs.  Read-only; tenant-scoped."""
    raw = decode_ref("loc", location_ref)
    if raw is not None:
        try:
            site_pk = int(raw)
        except (TypeError, ValueError):
            return None
        return (await db.execute(
            select(Site).where(Site.id == site_pk, Site.tenant_id == tenant_id)
        )).scalar_one_or_none()
    # registry building ref → primary linked site (only when registry mode is on)
    return await _resolve_building_primary_site(db, tenant_id, location_ref)


async def _resolve_building_primary_site(db: AsyncSession, tenant_id: str, building_ref: str):
    from app.services.customer import portfolio_registry_view as prv
    if not prv.registry_mode_enabled(tenant_id):
        return None
    raw = decode_ref("bldg", building_ref)
    if raw is None:
        return None
    try:
        bid = int(raw)
    except (TypeError, ValueError):
        return None
    from app.models.portfolio_registry import PortfolioBuilding
    b = (await db.execute(select(PortfolioBuilding).where(
        PortfolioBuilding.id == bid, PortfolioBuilding.tenant_id == tenant_id))).scalar_one_or_none()
    if b is None or not (b.approved or prv._include_pending(tenant_id)):
        return None
    sites = (await db.execute(select(Site).where(Site.tenant_id == tenant_id))).scalars().all()
    # reuse the read-model linkage (no assurance needed here — just identity)
    _si, by_store, by_addr, dev_site = await prv._link_indexes(db, tenant_id, [(s, None) for s in sites])
    site_ids = prv._resolve_building_site_ids(b, by_store, by_addr, dev_site)
    for site in sites:
        if site.site_id in site_ids:
            return site
    return None


async def load_e911_history(db: AsyncSession, tenant_id: str, site_id: str):
    """E911 change-log rows for a site (tenant-scoped, newest first)."""
    return (await db.execute(
        select(E911ChangeLog)
        .where(E911ChangeLog.tenant_id == tenant_id, E911ChangeLog.site_id == site_id)
        .order_by(E911ChangeLog.requested_at.desc())
    )).scalars().all()


async def company_name(db: AsyncSession, tenant_id: str, *, resolved_customer=None) -> str:
    """Customer-facing display name for the dashboard, generic across single-
    and multi-customer tenants:

      1. a resolved Customer (from the authenticated customer context) -> its name
         — forward hook; inert today (User has no Customer link). See EPIC-GEN-001.
      2. tenant has EXACTLY ONE Customer -> that Customer.name (the RH path).
      3. zero or many Customers -> the tenant org name (display_name or name).
      4. neither resolvable -> a neutral "Your Portfolio".

    Never picks an arbitrary Customer via LIMIT 1, and never exposes the raw
    tenant_id slug as a customer-facing string.
    """
    if resolved_customer is not None:
        return resolved_customer.name
    # Probe up to 2 to distinguish "exactly one" from "more than one".
    names = (await db.execute(
        select(Customer.name).where(Customer.tenant_id == tenant_id)
        .order_by(Customer.id).limit(2)
    )).scalars().all()
    if len(names) == 1:
        return names[0]
    tenant = (await db.execute(
        select(Tenant.display_name, Tenant.name).where(Tenant.tenant_id == tenant_id)
    )).first()
    if tenant:
        return tenant.display_name or tenant.name or "Your Portfolio"
    return "Your Portfolio"
