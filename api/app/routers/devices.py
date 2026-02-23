from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.device import Device
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.device import DeviceCreate, DeviceHeartbeatRequest, DeviceOut, DeviceUpdate

router = APIRouter()


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
    return [DeviceOut.model_validate(r) for r in result.scalars().all()]


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
    return DeviceOut.model_validate(device)


@router.post("", response_model=DeviceOut, status_code=201)
async def create_device(
    body: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    device = Device(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return DeviceOut.model_validate(device)


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
    await db.commit()
    await db.refresh(device)
    return DeviceOut.model_validate(device)


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

    device.last_heartbeat = datetime.now(timezone.utc)
    if body:
        if body.firmware_version:
            device.firmware_version = body.firmware_version
        if body.container_version:
            device.container_version = body.container_version
    await db.commit()
    await db.refresh(device)
    return DeviceOut.model_validate(device)
