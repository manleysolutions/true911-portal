import secrets
import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.device import Device
from app.models.event import Event
from app.models.site import Site
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.device import (
    DeviceCreate,
    DeviceCreateOut,
    DeviceHeartbeatRequest,
    DeviceKeyOut,
    DeviceOut,
    DeviceUpdate,
)
from app.services.continuity import compute_device_computed_status

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


def _device_out(device: Device) -> DeviceOut:
    """Build DeviceOut with computed_status and has_api_key injected."""
    out = DeviceOut.model_validate(device)
    out.computed_status = compute_device_computed_status(
        device.last_heartbeat, device.heartbeat_interval,
    )
    out.has_api_key = device.api_key_hash is not None
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
    return [_device_out(r) for r in result.scalars().all()]


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
    return _device_out(device)


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
