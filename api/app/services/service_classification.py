"""Internal Operations — Life-Safety service classification (Phase 8).

Lets Operations review the inferred service classification for a site and
**approve / override / merge / split** it.  Every override is an append-only
``ActionAudit`` record — persistence and logging in one (no new table/migration).
The customer inference engine (``services.customer.service_inference`` +
``command_center.load_overrides``) reads the latest override per device and
applies it, so an operator correction immediately reshapes what the customer sees.

INTERNAL only — guarded by ``MANAGE_SERVICE_CLASSIFICATION`` (never a customer
role).  This module never returns anything to the customer plane.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_audit import ActionAudit
from app.models.device import Device
from app.models.line import Line
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.services.customer import service_inference as si


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


async def _site(db: AsyncSession, tenant_id: str, site_id: str):
    return (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id, Site.site_id == site_id))).scalar_one_or_none()


async def load_overrides(db: AsyncSession, tenant_id: str, site_id: str) -> dict:
    """{device_id: service_type} from the latest override audit records."""
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
        if did and st and did not in out:
            out[did] = st
    return out


async def infer_site_classification(db: AsyncSession, tenant_id: str, site_id: str) -> dict | None:
    """Internal review view of a site's inferred services (with device detail +
    current overrides).  Returns None if the site is unknown for this tenant."""
    site = await _site(db, tenant_id, site_id)
    if site is None:
        return None
    units = (await db.execute(select(ServiceUnit).where(
        ServiceUnit.tenant_id == tenant_id, ServiceUnit.site_id == site_id))).scalars().all()
    devices = (await db.execute(select(Device).where(
        Device.tenant_id == tenant_id, Device.site_id == site_id))).scalars().all()
    lines = (await db.execute(select(Line).where(
        Line.tenant_id == tenant_id, Line.site_id == site_id))).scalars().all()
    overrides = await load_overrides(db, tenant_id, site_id)

    unit_by_device = {u.device_id: u for u in units if u.device_id}
    line_by_device = {ln.device_id: ln for ln in lines if ln.device_id}
    present = set()
    items = []
    for d in devices:
        present.add(d.device_id)
        u = unit_by_device.get(d.device_id)
        ln = line_by_device.get(d.device_id)
        items.append({
            "device_id": d.device_id, "model": d.model, "device_type": d.device_type,
            "manufacturer": d.manufacturer, "carrier": d.carrier, "notes": d.notes,
            "line_label": (f"{ln.provider} {ln.did or ''}".strip() if ln else None),
            "unit_type": u.unit_type if u else None, "unit_name": u.unit_name if u else None,
            "where": (u.location_description if u else None), "floor": (u.floor if u else None),
        })
    empty_units = [{"unit_type": u.unit_type, "unit_name": u.unit_name,
                    "where": u.location_description, "floor": u.floor}
                   for u in units if (not u.device_id or u.device_id not in present)]

    inferred = si.infer_services(items, overrides=overrides, empty_units=empty_units)
    services = [{
        "service_type": s["service_type"], "confidence": s["confidence"], "source": s["source"],
        "where": s["where"], "floor": s["floor"],
        "devices": [{
            "device_id": it["device_id"], "model": it.get("model"),
            "device_type": it.get("device_type"),
            "overridden": it["device_id"] in overrides,
        } for it in s["equipment"]],
    } for s in inferred]
    return {"site_id": site_id, "site_name": site.site_name,
            "override_count": len(overrides), "services": services}


async def record_override(db: AsyncSession, user, *, site_id: str, service_type: str,
                          device_ids: list[str], operation: str, reason: str = "") -> dict:
    """Record a classification override for one or more devices as append-only
    ActionAudit records (one per device — every override is logged).  Returns a
    summary.  ``operation`` ∈ approve|override|merge|split."""
    op = operation if operation in si.OVERRIDE_OPERATIONS else "override"
    if service_type not in si.SERVICE_TYPES:
        raise ValueError(f"Unknown service_type '{service_type}'")
    now = datetime.now(timezone.utc)
    original_tid = getattr(user, "_original_tenant_id", user.tenant_id)
    written = []
    for did in device_ids:
        details = json.dumps({"device_id": did, "service_type": service_type,
                              "operation": op, "reason": reason or ""})
        db.add(ActionAudit(
            audit_id=_uid("AUD"), request_id=_uid("REQ"), tenant_id=user.tenant_id,
            user_email=user.email, requester_name=getattr(user, "name", None), role=user.role,
            action_type=si.OVERRIDE_ACTION, site_id=site_id, timestamp=now, result="ok",
            details=details, original_tenant_id=original_tid,
            acting_as_tenant_id=(user.tenant_id if user.tenant_id != original_tid else None)))
        written.append(did)
    await db.commit()
    return {"site_id": site_id, "operation": op, "service_type": service_type,
            "devices": written, "logged": len(written)}


async def list_overrides(db: AsyncSession, tenant_id: str, site_id: str) -> dict:
    """Override history for a site (the audit trail — every override, newest first)."""
    rows = (await db.execute(
        select(ActionAudit).where(
            ActionAudit.tenant_id == tenant_id, ActionAudit.site_id == site_id,
            ActionAudit.action_type == si.OVERRIDE_ACTION,
        ).order_by(ActionAudit.id.desc()))).scalars().all()
    history = []
    for r in rows:
        try:
            d = json.loads(r.details or "{}")
        except Exception:
            d = {}
        history.append({
            "when": r.timestamp.isoformat() if r.timestamp else None,
            "by": r.requester_name or r.user_email, "role": r.role,
            "operation": d.get("operation"), "device_id": d.get("device_id"),
            "service_type": d.get("service_type"), "reason": d.get("reason") or None,
        })
    return {"site_id": site_id, "count": len(history), "history": history}
