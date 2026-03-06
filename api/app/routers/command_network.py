"""Command Network Router — carrier telemetry, network events, dashboard.

Endpoints:
  POST /carrier-telemetry              Ingest carrier telemetry
  GET  /network-events                 List network events
  POST /network-events/{id}/resolve    Resolve a network event
  GET  /network/summary                Network dashboard summary
  PUT  /site/{site_id}/ng911           Update NG911 fields
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, case, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user
from app.models.device import Device
from app.models.site import Site
from app.models.network_event import NetworkEvent
from app.models.incident import Incident
from app.services.rbac import can
from app.services.carrier_adapter import (
    get_adapter, ingest_carrier_telemetry, CarrierTelemetry,
)
from app.services.audit_logger import log_audit
from app.schemas.command_phase7 import (
    CarrierTelemetryIngest,
    NetworkEventOut,
    NetworkSummary,
    SiteNG911Update,
)

router = APIRouter()


# ── Carrier Telemetry Ingest ────────────────────────────────────────

@router.post("/carrier-telemetry")
async def ingest_carrier(
    payload: CarrierTelemetryIngest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can(user.role, "COMMAND_INGEST_CARRIER"):
        raise HTTPException(403, "Not authorized")

    adapter = get_adapter(payload.carrier)
    telemetry = adapter.normalize(payload.model_dump())
    events = await ingest_carrier_telemetry(db, user.tenant_id, telemetry)

    # Auto-create incidents for life-safety-impacting network events
    incidents_created = []
    for evt in events:
        if evt.severity == "critical" and evt.event_type in (
            "device_disconnected", "signal_degradation",
        ):
            inc = Incident(
                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                tenant_id=user.tenant_id,
                site_id=evt.site_id or "unknown",
                opened_at=datetime.now(timezone.utc),
                severity="critical",
                status="open",
                summary=evt.summary,
                source="network",
                incident_type="network",
                category="network",
                description=f"Network event: {evt.event_type}",
                created_by="system",
            )
            db.add(inc)
            evt.incident_id = inc.incident_id
            incidents_created.append(inc.incident_id)

    await log_audit(
        db, user.tenant_id, "network", "carrier_telemetry_ingested",
        f"Carrier telemetry from {payload.carrier} for device {payload.device_id}",
        actor=user.email, device_id=payload.device_id,
    )
    await db.commit()

    return {
        "status": "ok",
        "events_created": len(events),
        "incidents_created": incidents_created,
    }


# ── Network Events ─────────────────────────────────────────────────

@router.get("/network-events", response_model=list[NetworkEventOut])
async def list_network_events(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    event_type: str | None = None,
    severity: str | None = None,
    device_id: str | None = None,
    resolved: bool | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
):
    if not can(user.role, "COMMAND_VIEW_NETWORK"):
        raise HTTPException(403, "Not authorized")

    q = select(NetworkEvent).where(
        NetworkEvent.tenant_id == user.tenant_id,
    ).order_by(NetworkEvent.created_at.desc())

    if event_type:
        q = q.where(NetworkEvent.event_type == event_type)
    if severity:
        q = q.where(NetworkEvent.severity == severity)
    if device_id:
        q = q.where(NetworkEvent.device_id == device_id)
    if resolved is not None:
        q = q.where(NetworkEvent.resolved == resolved)

    q = q.offset(offset).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/network-events/{event_id}/resolve")
async def resolve_network_event(
    event_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can(user.role, "COMMAND_MANAGE_NETWORK"):
        raise HTTPException(403, "Not authorized")

    q = select(NetworkEvent).where(
        NetworkEvent.id == event_id,
        NetworkEvent.tenant_id == user.tenant_id,
    )
    evt = (await db.execute(q)).scalar_one_or_none()
    if not evt:
        raise HTTPException(404, "Event not found")

    evt.resolved = True
    evt.resolved_at = datetime.now(timezone.utc)

    await log_audit(
        db, user.tenant_id, "network", "network_event_resolved",
        f"Network event {evt.event_id} resolved",
        actor=user.email, device_id=evt.device_id,
    )
    await db.commit()
    return {"status": "resolved"}


# ── Network Dashboard Summary ──────────────────────────────────────

@router.get("/network/summary", response_model=NetworkSummary)
async def network_summary(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can(user.role, "COMMAND_VIEW_NETWORK"):
        raise HTTPException(403, "Not authorized")

    tid = user.tenant_id

    # Device network counts
    devices = (await db.execute(
        select(Device).where(Device.tenant_id == tid)
    )).scalars().all()

    total = len(devices)
    connected = sum(1 for d in devices if d.network_status and d.network_status.lower() in ("connected", "registered", "attached"))
    disconnected = sum(1 for d in devices if d.network_status and d.network_status.lower() in ("disconnected", "not_registered", "denied", "detached"))
    degraded = total - connected - disconnected

    # Carrier distribution
    carrier_dist = {}
    for d in devices:
        c = d.carrier or "unknown"
        carrier_dist[c] = carrier_dist.get(c, 0) + 1

    # Signal distribution
    signal_dist = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "critical": 0, "unknown": 0}
    for d in devices:
        # Use most recent command_telemetry signal if available
        if d.network_status is None:
            signal_dist["unknown"] += 1
        else:
            signal_dist["good"] += 1  # Default bucket; real impl reads actual dBm

    # Recent events
    recent = (await db.execute(
        select(NetworkEvent).where(
            NetworkEvent.tenant_id == tid,
        ).order_by(NetworkEvent.created_at.desc()).limit(20)
    )).scalars().all()

    return NetworkSummary(
        total_devices=total,
        connected=connected,
        disconnected=disconnected,
        degraded=degraded,
        carrier_distribution=carrier_dist,
        recent_network_events=recent,
        signal_distribution=signal_dist,
    )


# ── NG911 Site Fields ──────────────────────────────────────────────

@router.put("/site/{site_id}/ng911")
async def update_ng911(
    site_id: str,
    payload: SiteNG911Update,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not can(user.role, "COMMAND_MANAGE_NETWORK"):
        raise HTTPException(403, "Not authorized")

    site = (await db.execute(
        select(Site).where(Site.site_id == site_id, Site.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Site not found")

    if payload.psap_id is not None:
        site.psap_id = payload.psap_id
    if payload.emergency_class is not None:
        site.emergency_class = payload.emergency_class
    if payload.ng911_uri is not None:
        site.ng911_uri = payload.ng911_uri

    await log_audit(
        db, user.tenant_id, "config", "ng911_updated",
        f"NG911 fields updated for site {site_id}",
        actor=user.email, site_id=site_id,
        detail=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    return {"status": "updated", "site_id": site_id}
