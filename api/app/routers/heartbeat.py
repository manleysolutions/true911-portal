"""Unauthenticated device-token heartbeat endpoint.

Devices call POST /api/heartbeat with header ``X-Device-Key`` and a JSON
body containing their ``device_id``.  No JWT or user session is required.
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import get_adapter
from app.adapters.base import DEVICE_WRITABLE_FIELDS
from app.dependencies import authenticate_device, get_db
from app.models.command_telemetry import CommandTelemetry
from app.models.event import Event
from app.models.site import Site
from app.models.telemetry_event import TelemetryEvent
from app.schemas.device import DeviceTokenHeartbeatRequest, DeviceTokenHeartbeatResponse
from app.services.continuity import DEFAULT_HEARTBEAT_INTERVAL

router = APIRouter()


@router.post("", response_model=DeviceTokenHeartbeatResponse)
async def device_token_heartbeat(
    body: DeviceTokenHeartbeatRequest,
    x_device_key: str = Header(..., alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    device = await authenticate_device(body.device_id, x_device_key, db)

    now = datetime.now(timezone.utc)
    device.last_heartbeat = now

    # ── Adapter layer: normalize vendor-specific payload ──────────
    # Build raw payload from the request body (includes Pydantic extras)
    raw_payload = body.model_dump(exclude_none=True)
    raw_payload.pop("device_id", None)  # not a telemetry field

    adapter = get_adapter(device.device_type, device.model or device.hardware_model_id)
    normalized = adapter.normalize_heartbeat(raw_payload)

    # Determine telemetry source label from adapter type
    adapter_name = type(adapter).__name__
    if "PR12" in adapter_name:
        source = "pr12_heartbeat"
    elif "Insego" in adapter_name:
        source = "inseego_heartbeat"
    else:
        source = "device_heartbeat"

    # Apply only allowlisted writable fields to the Device row
    for field in DEVICE_WRITABLE_FIELDS:
        value = normalized.get(field)
        if value is not None:
            setattr(device, field, value)

    # ── Bridge: push signal/network data into health-scoring pipeline ──
    # This is the critical link between device heartbeats and health scoring.
    # Without this, signal_dbm from heartbeats never reaches _latest_signals().
    signal_dbm = normalized.get("signal_dbm")
    connection_status = normalized.get("connection_status")
    network_type = normalized.get("network_type")
    sip_status = normalized.get("sip_status")

    # Update device network fields if heartbeat provides them
    if connection_status:
        device.network_status = connection_status
    if signal_dbm is not None or connection_status:
        device.last_network_event = now
        device.telemetry_source = source

    # Store a CommandTelemetry record so _latest_signals() picks it up
    if signal_dbm is not None or connection_status or sip_status:
        db.add(CommandTelemetry(
            tenant_id=device.tenant_id,
            device_id=device.device_id,
            site_id=device.site_id,
            signal_strength=signal_dbm,
            metadata_json=json.dumps({
                k: v for k, v in {
                    "source": source,
                    "connection_status": connection_status,
                    "network_type": network_type,
                    "sip_status": sip_status,
                    "signal_rssi": normalized.get("signal_rssi"),
                    "signal_sinr": normalized.get("signal_sinr"),
                    "signal_rsrq": normalized.get("signal_rsrq"),
                    "ip_address": normalized.get("ip_address"),
                    "board_temp_c": normalized.get("board_temp_c"),
                    "uptime_seconds": normalized.get("uptime_seconds"),
                }.items() if v is not None
            }),
        ))

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
