"""Unauthenticated device-token heartbeat endpoint.

Devices call POST /api/heartbeat with header ``X-Device-Key`` and a JSON
body containing their ``device_id``.  No JWT or user session is required.
"""

import json
import uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import get_adapter
from app.adapters.base import DEVICE_WRITABLE_FIELDS
from app.dependencies import get_db
from app.models.device import Device
from app.models.event import Event
from app.models.site import Site
from app.models.telemetry_event import TelemetryEvent
from app.schemas.device import DeviceTokenHeartbeatRequest, DeviceTokenHeartbeatResponse
from app.services.continuity import DEFAULT_HEARTBEAT_INTERVAL

router = APIRouter()

_GENERIC_AUTH_ERROR = "Invalid device credentials"


async def _authenticate_device(
    device_id: str,
    raw_key: str,
    db: AsyncSession,
) -> Device:
    """Lookup device by device_id and verify raw_key against stored hash.

    Returns the Device ORM object on success.
    Raises 403 with a generic message on any failure — intentionally does
    not distinguish between "device not found" and "wrong key" to prevent
    enumeration.
    """
    result = await db.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device or not device.api_key_hash:
        raise HTTPException(status.HTTP_403_FORBIDDEN, _GENERIC_AUTH_ERROR)

    if not bcrypt.checkpw(raw_key.encode("utf-8")[:72], device.api_key_hash.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, _GENERIC_AUTH_ERROR)

    return device


@router.post("", response_model=DeviceTokenHeartbeatResponse)
async def device_token_heartbeat(
    body: DeviceTokenHeartbeatRequest,
    x_device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    device = await _authenticate_device(body.device_id, x_device_key, db)

    now = datetime.now(timezone.utc)
    device.last_heartbeat = now

    # ── Adapter layer: normalize vendor-specific payload ──────────
    # Build raw payload from the request body (includes Pydantic extras)
    raw_payload = body.model_dump(exclude_none=True)
    raw_payload.pop("device_id", None)  # not a telemetry field

    adapter = get_adapter(device.device_type, device.model)
    normalized = adapter.normalize_heartbeat(raw_payload)

    # Apply only allowlisted writable fields to the Device row
    for field in DEVICE_WRITABLE_FIELDS:
        value = normalized.get(field)
        if value is not None:
            setattr(device, field, value)

    # Propagate heartbeat timestamp to parent site
    if device.site_id:
        site_result = await db.execute(
            select(Site).where(
                Site.site_id == device.site_id,
                Site.tenant_id == device.tenant_id,
            )
        )
        site = site_result.scalar_one_or_none()
        if site:
            site.last_device_heartbeat = now

    # ── Telemetry: store raw payload for audit / replay ───────────
    db.add(TelemetryEvent(
        event_id=f"tel-{uuid.uuid4().hex[:12]}",
        site_id=device.site_id or "",
        tenant_id=device.tenant_id,
        timestamp=now,
        category="device.heartbeat.raw",
        severity="info",
        message=f"Raw heartbeat from {device.device_id}",
        raw_json=json.dumps(raw_payload) if raw_payload else None,
    ))

    # ── Event: standard heartbeat event with normalized metadata ──
    db.add(Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        tenant_id=device.tenant_id,
        event_type="device.heartbeat",
        site_id=device.site_id,
        device_id=device.device_id,
        severity="info",
        message=f"Heartbeat received from {device.device_id}",
        metadata_json=normalized or None,
    ))

    await db.commit()

    interval = device.heartbeat_interval or DEFAULT_HEARTBEAT_INTERVAL
    return DeviceTokenHeartbeatResponse(
        device_id=device.device_id,
        next_heartbeat_seconds=interval,
    )
