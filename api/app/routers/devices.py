import json
import secrets
import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.command_telemetry import CommandTelemetry
from app.models.device import Device
from app.models.device_sim import DeviceSim
from app.models.event import Event
from app.models.sim import Sim
from app.models.site import Site
from app.models.user import User
from sqlalchemy import func as sa_func

from app.routers.helpers import apply_sort
from app.schemas.device import (
    DeviceCreate,
    DeviceCreateOut,
    DeviceHeartbeatRequest,
    DeviceKeyOut,
    DeviceOut,
    DeviceUpdate,
)
from app.schemas.sim import SimOut
from app.services.continuity import compute_device_computed_status
from app.services.health_scoring import compute_device_health

router = APIRouter()

_KEY_PREFIX = "t91_"

_CONSTRAINT_MESSAGES = {
    "uq_devices_imei": "A device with this IMEI already exists",
    "uq_devices_serial_number": "A device with this serial number already exists",
    "uq_devices_msisdn": "A device with this MSISDN already exists",
    "devices_device_id_key": "A device with this device ID already exists",
}


def _parse_device_conflict(e: IntegrityError) -> str:
    msg = str(e.orig) if e.orig else str(e)
    for constraint, detail in _CONSTRAINT_MESSAGES.items():
        if constraint in msg:
            return detail
    return "Duplicate value: a device with one of these identifiers already exists"


def _generate_device_key() -> tuple[str, str]:
    """Return (raw_key, bcrypt_hash)."""
    raw = _KEY_PREFIX + secrets.token_urlsafe(32)
    hashed = bcrypt.hashpw(raw.encode("utf-8")[:72], bcrypt.gensalt()).decode()
    return raw, hashed


class _TelemetrySnapshot:
    """Latest telemetry values for a device, extracted from CommandTelemetry."""
    __slots__ = ("signal_dbm", "sip_status", "source")

    def __init__(self, signal_dbm: float | None = None, sip_status: str | None = None, source: str | None = None):
        self.signal_dbm = signal_dbm
        self.sip_status = sip_status
        self.source = source


def _device_out(device: Device, snap: _TelemetrySnapshot | None = None) -> DeviceOut:
    """Build DeviceOut with computed_status, health_status, and has_api_key."""
    snap = snap or _TelemetrySnapshot()
    out = DeviceOut.model_validate(device)
    out.computed_status = compute_device_computed_status(
        device.last_heartbeat, device.heartbeat_interval,
    )
    out.has_api_key = device.api_key_hash is not None
    out.health_status = compute_device_health(
        last_heartbeat=device.last_heartbeat,
        heartbeat_interval=device.heartbeat_interval,
        network_status=device.network_status,
        signal_dbm=snap.signal_dbm,
        last_network_event=device.last_network_event,
        device_status=device.status,
        sip_status=snap.sip_status,
    )
    out.signal_dbm = snap.signal_dbm
    out.telemetry_source = device.telemetry_source or snap.source
    return out


async def _latest_telemetry(
    db: AsyncSession, tenant_id: str, device_ids: list[str],
) -> dict[str, _TelemetrySnapshot]:
    """Return {device_id: TelemetrySnapshot} from the most recent command_telemetry."""
    if not device_ids:
        return {}
    # Subquery: max recorded_at per device
    sub = (
        select(
            CommandTelemetry.device_id,
            sa_func.max(CommandTelemetry.recorded_at).label("max_ts"),
        )
        .where(
            CommandTelemetry.tenant_id == tenant_id,
            CommandTelemetry.device_id.in_(device_ids),
        )
        .group_by(CommandTelemetry.device_id)
        .subquery()
    )
    q = (
        select(
            CommandTelemetry.device_id,
            CommandTelemetry.signal_strength,
            CommandTelemetry.metadata_json,
        )
        .join(sub, (CommandTelemetry.device_id == sub.c.device_id) & (CommandTelemetry.recorded_at == sub.c.max_ts))
        .where(CommandTelemetry.tenant_id == tenant_id)
    )
    result = await db.execute(q)
    out: dict[str, _TelemetrySnapshot] = {}
    for row in result.all():
        meta = {}
        if row.metadata_json:
            try:
                meta = json.loads(row.metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass
        out[row.device_id] = _TelemetrySnapshot(
            signal_dbm=row.signal_strength,
            sip_status=meta.get("sip_status"),
            source=meta.get("source"),
        )
    return out


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    device_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Device).where(Device.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(Device.site_id == site_id)
    if status_filter:
        q = q.where(Device.status == status_filter)
    if device_type:
        q = q.where(Device.device_type == device_type)
    q = apply_sort(q, Device, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    devices = result.scalars().all()

    # Batch-load latest telemetry from command_telemetry
    telem_map = await _latest_telemetry(db, current_user.tenant_id, [d.device_id for d in devices])

    return [_device_out(d, telem_map.get(d.device_id)) for d in devices]


@router.get("/health-summary")
async def device_health_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return health status counts across all tenant devices."""
    result = await db.execute(
        select(Device).where(Device.tenant_id == current_user.tenant_id)
    )
    devices = result.scalars().all()
    telem_map = await _latest_telemetry(db, current_user.tenant_id, [d.device_id for d in devices])

    counts = {"healthy": 0, "warning": 0, "critical": 0, "unknown": 0}
    for d in devices:
        snap = telem_map.get(d.device_id) or _TelemetrySnapshot()
        h = compute_device_health(
            last_heartbeat=d.last_heartbeat,
            heartbeat_interval=d.heartbeat_interval,
            network_status=d.network_status,
            signal_dbm=snap.signal_dbm,
            last_network_event=d.last_network_event,
            device_status=d.status,
            sip_status=snap.sip_status,
        )
        counts[h] = counts.get(h, 0) + 1

    return {"total": len(devices), **counts}


@router.get("/{device_pk}", response_model=DeviceOut)
async def get_device(
    device_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Device).where(Device.id == device_pk, Device.tenant_id == current_user.tenant_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    telem_map = await _latest_telemetry(db, current_user.tenant_id, [device.device_id])
    return _device_out(device, telem_map.get(device.device_id))


@router.post("", response_model=DeviceCreateOut, status_code=201)
async def create_device(
    body: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_key, key_hash = _generate_device_key()
    device = Device(
        **body.model_dump(),
        tenant_id=current_user.tenant_id,
        api_key_hash=key_hash,
        claimed_at=datetime.now(timezone.utc),
        claimed_by=current_user.email,
    )
    db.add(device)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        detail = _parse_device_conflict(e)
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail)
    await db.commit()
    await db.refresh(device)

    out = DeviceCreateOut.model_validate(device)
    out.computed_status = compute_device_computed_status(
        device.last_heartbeat, device.heartbeat_interval,
    )
    out.has_api_key = True
    out.api_key = raw_key
    return out


@router.patch("/{device_pk}", response_model=DeviceOut)
async def update_device(
    device_pk: int,
    body: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Device).where(Device.id == device_pk, Device.tenant_id == current_user.tenant_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        detail = _parse_device_conflict(e)
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail)
    await db.commit()
    await db.refresh(device)
    return _device_out(device)


@router.delete("/{device_pk}", response_model=DeviceOut)
async def delete_device(
    device_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: sets status to 'decommissioned'."""
    result = await db.execute(
        select(Device).where(Device.id == device_pk, Device.tenant_id == current_user.tenant_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    device.status = "decommissioned"
    await db.commit()
    await db.refresh(device)
    return _device_out(device)


@router.post(
    "/{device_pk}/rotate-key",
    response_model=DeviceKeyOut,
    dependencies=[Depends(require_permission("ROTATE_DEVICE_KEY"))],
)
async def rotate_device_key(
    device_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a new API key for a device. Admin-only. Returns key once."""
    result = await db.execute(
        select(Device).where(Device.id == device_pk, Device.tenant_id == current_user.tenant_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    raw_key, key_hash = _generate_device_key()
    device.api_key_hash = key_hash
    await db.commit()
    return DeviceKeyOut(device_id=device.device_id, api_key=raw_key)


@router.post("/{device_pk}/heartbeat", response_model=DeviceOut)
async def device_heartbeat(
    device_pk: int,
    body: DeviceHeartbeatRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Device).where(Device.id == device_pk, Device.tenant_id == current_user.tenant_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    now = datetime.now(timezone.utc)
    device.last_heartbeat = now
    if body:
        if body.firmware_version:
            device.firmware_version = body.firmware_version
        if body.container_version:
            device.container_version = body.container_version

    # Propagate heartbeat timestamp to parent site
    if device.site_id:
        site_result = await db.execute(
            select(Site).where(
                Site.site_id == device.site_id,
                Site.tenant_id == current_user.tenant_id,
            )
        )
        site = site_result.scalar_one_or_none()
        if site:
            site.last_device_heartbeat = now

    # Emit a device.heartbeat event
    db.add(Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        tenant_id=current_user.tenant_id,
        event_type="device.heartbeat",
        site_id=device.site_id,
        device_id=device.device_id,
        severity="info",
        message=f"Heartbeat received from {device.device_id}",
    ))

    await db.commit()
    await db.refresh(device)
    return _device_out(device)


@router.get("/{device_pk}/sims", response_model=list[SimOut])
async def list_device_sims(
    device_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List active SIMs assigned to a device."""
    result = await db.execute(
        select(Device).where(
            Device.id == device_pk, Device.tenant_id == current_user.tenant_id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    sim_result = await db.execute(
        select(Sim)
        .join(DeviceSim, DeviceSim.sim_id == Sim.id)
        .where(
            DeviceSim.device_id == device_pk,
            DeviceSim.active == True,
        )
    )
    return [SimOut.model_validate(s) for s in sim_result.scalars().all()]


# ── Bulk Site Assignment ──────────────────────────────────────────

from pydantic import BaseModel as _BaseModel


class DeviceBulkSiteAssign(_BaseModel):
    device_ids: list[int]
    site_id: str


@router.post(
    "/bulk-assign-site",
    response_model=dict,
    dependencies=[Depends(require_permission("MANAGE_DEVICES"))],
)
async def bulk_assign_devices_to_site(
    body: DeviceBulkSiteAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign multiple devices to a site in one operation."""
    # Verify site exists and is accessible
    site_q = select(Site).where(Site.site_id == body.site_id)
    if current_user.role != "SuperAdmin":
        site_q = site_q.where(Site.tenant_id == current_user.tenant_id)
    site_result = await db.execute(site_q)
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    # Fetch devices
    dev_result = await db.execute(
        select(Device).where(Device.id.in_(body.device_ids))
    )
    devices = dev_result.scalars().all()

    assigned = 0
    skipped = 0
    for device in devices:
        if current_user.role != "SuperAdmin" and device.tenant_id != current_user.tenant_id:
            skipped += 1
            continue
        device.site_id = body.site_id
        if device.tenant_id != site.tenant_id:
            device.tenant_id = site.tenant_id
        assigned += 1

    await db.commit()
    return {"assigned": assigned, "skipped": skipped, "site_id": body.site_id}
