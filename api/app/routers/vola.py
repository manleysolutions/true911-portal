"""Proxy routes for the Vola Connector microservice.

All endpoints require the VOLA_ADMIN RBAC permission (Admin role).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.dependencies import require_permission
from app.models.user import User
from app.services import vola_connector

router = APIRouter()

_admin = require_permission("VOLA_ADMIN")


# ── Request / response schemas ──────────────────────────────────────────────

class GetParamsSyncRequest(BaseModel):
    parameter_names: list[str]
    timeout_seconds: int = 20
    poll_interval_seconds: float = 1.0


class SetParamsSyncRequest(BaseModel):
    parameter_values: list[list[str]]  # [[node, value], ...]
    timeout_seconds: int = 20
    poll_interval_seconds: float = 1.0


# ── Health ───────────────────────────────────────────────────────────────────

@router.get("/health")
async def vola_health(user: User = Depends(_admin)):
    return await vola_connector.get("/health")


# ── Devices ──────────────────────────────────────────────────────────────────

@router.get("/devices")
async def vola_devices(
    usage_status: str = Query("inUse"),
    user: User = Depends(_admin),
):
    return await vola_connector.get("/vola/devices", {"usage_status": usage_status})


# ── Reboot ───────────────────────────────────────────────────────────────────

@router.post("/devices/{device_sn}/reboot")
async def vola_reboot(device_sn: str, user: User = Depends(_admin)):
    return await vola_connector.post("/vola/device/reboot", {"deviceSN": device_sn})


# ── Get params (sync) ───────────────────────────────────────────────────────

@router.post("/devices/{device_sn}/params/get_sync")
async def vola_get_params_sync(
    device_sn: str,
    body: GetParamsSyncRequest,
    user: User = Depends(_admin),
):
    return await vola_connector.post("/vola/device/params/get_sync", {
        "device_sn": device_sn,
        "parameter_names": body.parameter_names,
        "timeout_seconds": body.timeout_seconds,
        "poll_interval_seconds": body.poll_interval_seconds,
    })


# ── Set params (sync) ───────────────────────────────────────────────────────

@router.post("/devices/{device_sn}/params/set_sync")
async def vola_set_params_sync(
    device_sn: str,
    body: SetParamsSyncRequest,
    user: User = Depends(_admin),
):
    return await vola_connector.post("/vola/device/params/set_sync", {
        "device_sn": device_sn,
        "parameter_values": body.parameter_values,
        "timeout_seconds": body.timeout_seconds,
        "poll_interval_seconds": body.poll_interval_seconds,
    })
