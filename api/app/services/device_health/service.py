"""DB-backed assembly of :class:`DeviceHealth` for a tenant or a site.

Reads only — never writes.  Every query is tenant-scoped (the single tenancy
guarantee).  Uses a small fixed number of bulk queries (O(1) round-trips
regardless of fleet size), mirroring ``app.services.health.signals_loader``.

The per-request read APIs call this; it does NOT make live vendor calls (those
happen in the sync command and persist to Device columns), so a page load
never blocks on a vendor API.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord
from app.models.command_telemetry import CommandTelemetry
from app.models.device import Device
from app.models.service_unit import ServiceUnit
from app.models.sim import Sim
from app.models.site import Site
from app.services.device_health.classifier import classify
from app.services.device_health.models import DeviceHealth
from app.services.device_health.recommended_action import recommend
from app.services.device_health.scoring import DeviceContext, score
from app.services.health.signals import HealthSignals

logger = logging.getLogger("true911.device_health.service")


def _sip_from_metadata(metadata_json: Optional[str]) -> Optional[str]:
    if not metadata_json:
        return None
    try:
        data = json.loads(metadata_json)
    except (ValueError, TypeError):
        return None
    if isinstance(data, dict):
        val = data.get("sip_status") or data.get("sipStatus")
        return str(val) if val is not None else None
    return None


async def _latest_telemetry_by_device(
    db: AsyncSession, tenant_id: str, device_ids: list[str]
) -> dict[str, CommandTelemetry]:
    """Most recent CommandTelemetry row per device (DISTINCT ON)."""
    if not device_ids:
        return {}
    q = (
        select(CommandTelemetry)
        .where(CommandTelemetry.tenant_id == tenant_id)
        .where(CommandTelemetry.device_id.in_(device_ids))
        .order_by(CommandTelemetry.device_id, CommandTelemetry.recorded_at.desc())
        .distinct(CommandTelemetry.device_id)
    )
    rows = (await db.execute(q)).scalars().all()
    return {r.device_id: r for r in rows}


async def _last_call_by_device(
    db: AsyncSession, tenant_id: str, device_ids: list[str]
) -> dict[str, datetime]:
    if not device_ids:
        return {}
    q = (
        select(CallRecord.device_id, func.max(CallRecord.started_at).label("last_call"))
        .where(CallRecord.tenant_id == tenant_id)
        .where(CallRecord.device_id.in_(device_ids))
        .where(CallRecord.started_at.is_not(None))
        .group_by(CallRecord.device_id)
    )
    return {row.device_id: row.last_call for row in (await db.execute(q)).all()}


async def build_device_health(
    db: AsyncSession,
    tenant_id: str,
    *,
    site_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[DeviceHealth]:
    """Return DeviceHealth for every device in ``tenant_id`` (optionally one site).

    Tenant isolation is the FIRST clause on every query; an attacker-controlled
    ``site_id`` from another tenant simply yields an empty list.
    """
    devices_q = select(Device).where(Device.tenant_id == tenant_id)
    if site_id is not None:
        devices_q = devices_q.where(Device.site_id == site_id)
    devices = (await db.execute(devices_q)).scalars().all()
    if not devices:
        return []

    device_ids = [d.device_id for d in devices]

    # Context tables (all tenant-scoped, bulk).
    units = (await db.execute(
        select(ServiceUnit).where(ServiceUnit.tenant_id == tenant_id))).scalars().all()
    unit_by_device = {u.device_id: u for u in units if u.device_id}

    sites = (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id))).scalars().all()
    site_name_by_id = {s.site_id: s.site_name for s in sites}

    sims = (await db.execute(
        select(Sim).where(Sim.tenant_id == tenant_id))).scalars().all()
    sim_by_device = {s.device_id: s for s in sims if s.device_id}
    sim_by_iccid = {s.iccid: s for s in sims if s.iccid}

    telemetry = await _latest_telemetry_by_device(db, tenant_id, device_ids)
    last_call = await _last_call_by_device(db, tenant_id, device_ids)

    results: list[DeviceHealth] = []
    for d in devices:
        unit = unit_by_device.get(d.device_id)
        sim = sim_by_device.get(d.device_id) or (
            sim_by_iccid.get(d.iccid) if d.iccid else None)
        tel = telemetry.get(d.device_id)

        signal_dbm = getattr(tel, "signal_strength", None) if tel else None
        sip_status = _sip_from_metadata(getattr(tel, "metadata_json", None)) if tel else None

        cls = classify(
            model=d.model, device_type=d.device_type,
            hardware_model_id=d.hardware_model_id, manufacturer=d.manufacturer,
            carrier=d.carrier,
        )

        signals = HealthSignals(
            last_heartbeat_at=d.last_heartbeat,
            last_carrier_event_at=getattr(d, "last_network_event", None),
            last_call_event_at=last_call.get(d.device_id),
            last_vola_sync_at=getattr(d, "vola_last_sync", None),
            network_status=d.network_status,
            signal_dbm=signal_dbm,
            sip_status=sip_status,
            heartbeat_interval_seconds=d.heartbeat_interval,
            device_lifecycle=d.status or "active",
        )

        volte_enabled = None
        sim_status = None
        if sim is not None:
            sim_status = sim.status
            meta = sim.meta or {}
            if "volte_enabled" in meta:
                volte_enabled = bool(meta.get("volte_enabled"))

        ctx = DeviceContext(
            voice_type=cls.voice_type,
            sim_status=sim_status,
            volte_enabled=volte_enabled,
            has_call_history=d.device_id in last_call,
        )

        scored = score(signals, ctx, now=now)

        dh = DeviceHealth(
            tenant_id=tenant_id,
            device_id=d.device_id,
            device_name=(unit.unit_name if unit else (d.model or d.device_id)),
            model=d.model,
            device_type=d.device_type,
            manufacturer=d.manufacturer,
            serial_number=d.serial_number,
            imei=d.imei,
            iccid=d.iccid,
            msisdn=d.msisdn,
            carrier=d.carrier,
            site_id=d.site_id,
            site_name=site_name_by_id.get(d.site_id),
            service_unit_id=(unit.unit_id if unit else None),
            service_unit_name=(unit.unit_name if unit else None),
            connection_type=cls.connection_type,
            voice_type=cls.voice_type,
            canonical_state=scored.canonical.value,
            status=scored.status,
            reason_codes=scored.reasons,
            recommended_action=recommend(scored.reasons),
            last_check_in=signals.last_observed_at(),
            last_call_activity=last_call.get(d.device_id),
            last_callback_received=getattr(d, "last_network_event", None),
            last_sync_time=getattr(d, "vola_last_sync", None),
            firmware=d.firmware_version,
            signal_dbm=signal_dbm,
            sim_status=sim_status,
            sip_status=sip_status,
            volte_status=("enabled" if volte_enabled else
                          ("disabled" if volte_enabled is False else None)),
            static_ip=d.wan_ip,
            vendor_links={
                "vola_org_id": getattr(d, "vola_org_id", None),
                "telemetry_source": getattr(d, "telemetry_source", None),
            },
        )
        results.append(dh)

    return results
