"""VOLA / FlyingVoice PR12 integration routes.

Phase 1 routes for device sync, reboot, parameter read/write, and provisioning.
All routes require JWT auth and are tenant-scoped.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.integrations.vola import extract_parameter_values, normalize_vola_device
from app.models.device import Device
from app.models.user import User
from app.services.vola_service import (
    bind_device_to_site,
    build_provision_payload,
    get_tenant_vola_client,
    sync_vola_devices,
)

logger = logging.getLogger("true911.routers.vola")

router = APIRouter()


# ── Pydantic models ─────────────────────────────────────────────────────────

class VolaOrgOut(BaseModel):
    org_id: str = ""
    org_name: str = ""


class VolaOrgsResponse(BaseModel):
    orgs: list[VolaOrgOut]


class VolaDeviceOut(BaseModel):
    device_sn: str = ""
    mac: str = ""
    model: str = ""
    firmware_version: str = ""
    ip: str = ""
    status: str = ""
    usage_status: str = ""
    org_id: str = ""
    org_name: str = ""


class VolaDevicesResponse(BaseModel):
    total: int
    devices: list[VolaDeviceOut]


class SyncResponse(BaseModel):
    imported: int
    updated: int
    skipped: int
    devices: list[dict[str, Any]]


class RebootRequest(BaseModel):
    device_sn: str


class TaskCreatedResponse(BaseModel):
    task_id: str
    device_sn: str


class TaskResultRequest(BaseModel):
    task_ids: list[str]


class GetParamsRequest(BaseModel):
    device_sn: str
    parameter_names: list[str]


class GetParamsSyncRequest(BaseModel):
    device_sn: str
    parameter_names: list[str]
    timeout_seconds: int = 20
    poll_interval_seconds: float = 1.0


class GetParamsSyncResponse(BaseModel):
    task_id: str
    device_sn: str
    status: str
    raw_task_result: dict | list | None = None
    extracted_values: dict[str, str] = Field(default_factory=dict)


class SetParamsRequest(BaseModel):
    device_sn: str
    parameter_values: list[list[str]]


class SetParamsSyncRequest(BaseModel):
    device_sn: str
    parameter_values: list[list[str]]
    timeout_seconds: int = 20
    poll_interval_seconds: float = 1.0


class SetParamsSyncResponse(BaseModel):
    task_id: str
    device_sn: str
    status: str
    raw_task_result: dict | list | None = None
    applied: dict[str, str] = Field(default_factory=dict)


class BindRequest(BaseModel):
    site_id: str


class ProvisionBasicRequest(BaseModel):
    device_sn: str
    site_code: str
    inform_interval: int = 300
    extra_params: list[list[str]] | None = None
    sync: bool = True
    timeout_seconds: int = 20


class ProvisionBasicResponse(BaseModel):
    task_id: str
    device_sn: str
    status: str
    applied: dict[str, str] = Field(default_factory=dict)
    raw_task_result: dict | list | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str
    vola_base_url: str = ""


# ── Routes ──────────────────────────────────────────────────────────────────

@router.get("/test", response_model=TestConnectionResponse)
async def test_vola_connection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test VOLA API connectivity and authentication."""
    try:
        client = await get_tenant_vola_client(db, current_user.tenant_id)
        await client.get_access_token()
        return TestConnectionResponse(
            ok=True,
            message="Successfully authenticated with VOLA API",
            vola_base_url=client.base_url,
        )
    except Exception as exc:
        logger.exception("VOLA connection test failed")
        return TestConnectionResponse(
            ok=False,
            message=f"Connection failed: {exc}",
        )


@router.get("/orgs", response_model=VolaOrgsResponse)
async def list_orgs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List VOLA organizations for the authenticated tenant."""
    try:
        client = await get_tenant_vola_client(db, current_user.tenant_id)
        raw = await client.get_org_list()
    except Exception as exc:
        logger.exception("Failed to fetch VOLA org list")
        raise HTTPException(status_code=502, detail=f"VOLA API error: {exc}")

    orgs = []
    for item in raw:
        try:
            orgs.append(VolaOrgOut(
                org_id=item.get("orgId", ""),
                org_name=item.get("orgName", ""),
            ))
        except Exception:
            logger.warning("Skipping unparseable org entry: %s", item)
    return VolaOrgsResponse(orgs=orgs)


@router.get("/devices", response_model=VolaDevicesResponse)
async def list_vola_devices(
    usage_status: str = Query("inUse"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List devices from VOLA Cloud (not yet imported into True911)."""
    try:
        client = await get_tenant_vola_client(db, current_user.tenant_id)
        data = await client.get_device_list(usage_status)
    except Exception as exc:
        logger.exception("Failed to fetch VOLA device list")
        raise HTTPException(status_code=502, detail=f"VOLA API error: {exc}")

    raw_list = data.get("list", data.get("deviceList", [])) if isinstance(data, dict) else data
    devices = [VolaDeviceOut(**normalize_vola_device(d)) for d in raw_list]
    total = data.get("total", len(devices)) if isinstance(data, dict) else len(devices)
    return VolaDevicesResponse(total=total, devices=devices)


@router.post("/devices/sync", response_model=SyncResponse)
async def sync_devices(
    usage_status: str = Query("inUse"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Pull devices from VOLA and import/sync into True911.

    Deduplicates by serial number and MAC address. Safe to call multiple times.
    """
    try:
        client = await get_tenant_vola_client(db, current_user.tenant_id)
        data = await client.get_device_list(usage_status)
    except Exception as exc:
        logger.exception("Failed to fetch VOLA device list for sync")
        raise HTTPException(status_code=502, detail=f"VOLA API error: {exc}")

    raw_list = data.get("list", data.get("deviceList", [])) if isinstance(data, dict) else data
    result = await sync_vola_devices(
        db, current_user.tenant_id, raw_list,
        user_email=current_user.email,
    )
    return SyncResponse(**result)


@router.post("/device/{device_sn}/reboot", response_model=TaskCreatedResponse)
async def reboot_device(
    device_sn: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Create a reboot task for a VOLA device."""
    try:
        client = await get_tenant_vola_client(db, current_user.tenant_id)
        data = await client.create_reboot_task(device_sn)
    except Exception as exc:
        logger.exception("Failed to create VOLA reboot task")
        raise HTTPException(status_code=502, detail=f"VOLA API error: {exc}")

    task_id = data.get("taskId", data.get("id", ""))
    if not task_id:
        raise HTTPException(status_code=502, detail="VOLA did not return a taskId")
    return TaskCreatedResponse(task_id=task_id, device_sn=device_sn)


@router.post("/task/results")
async def get_task_results(
    body: TaskResultRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Poll task results from VOLA."""
    if not body.task_ids:
        raise HTTPException(status_code=400, detail="task_ids must not be empty")
    try:
        client = await get_tenant_vola_client(db, current_user.tenant_id)
        results = await client.get_task_results(body.task_ids)
    except Exception as exc:
        logger.exception("Failed to fetch VOLA task results")
        raise HTTPException(status_code=502, detail=f"VOLA API error: {exc}")

    return {"results": results}


@router.post("/device/{device_sn}/params/read", response_model=GetParamsSyncResponse)
async def read_params(
    device_sn: str,
    body: GetParamsSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read TR-069 parameters from a VOLA device (synchronous with polling)."""
    client = await get_tenant_vola_client(db, current_user.tenant_id)

    # Validate
    err = client.validate_param_names(body.parameter_names)
    if err:
        raise HTTPException(status_code=400, detail=err)

    # Create task
    try:
        data = await client.create_get_parameter_values_task(device_sn, body.parameter_names)
    except Exception as exc:
        logger.exception("Failed to create getParameterValues task")
        raise HTTPException(status_code=502, detail=f"VOLA API error: {exc}")

    task_id = data.get("taskId", data.get("id", ""))
    if not task_id:
        raise HTTPException(status_code=502, detail="VOLA did not return a taskId")

    # Poll
    result = await client.poll_task_sync(task_id, body.timeout_seconds, body.poll_interval_seconds)

    if result["status"] == "timeout":
        raise HTTPException(
            status_code=504,
            detail={"message": f"Task {task_id} did not complete within {body.timeout_seconds}s", "task_id": task_id, "device_sn": device_sn},
        )

    return GetParamsSyncResponse(
        task_id=task_id,
        device_sn=device_sn,
        status=result["status"],
        raw_task_result=result["result"],
        extracted_values=extract_parameter_values(result["result"]),
    )


@router.post("/device/{device_sn}/params/write", response_model=SetParamsSyncResponse)
async def write_params(
    device_sn: str,
    body: SetParamsSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Write TR-069 parameters to a VOLA device (synchronous with polling)."""
    client = await get_tenant_vola_client(db, current_user.tenant_id)

    # Validate safety
    err = client.validate_set_param_values(body.parameter_values)
    if err:
        raise HTTPException(status_code=400, detail=err)

    applied = {pair[0]: pair[1] for pair in body.parameter_values}

    # Create task
    try:
        data = await client.create_set_parameter_values_task(device_sn, body.parameter_values)
    except Exception as exc:
        logger.exception("Failed to create setParameterValues task")
        raise HTTPException(status_code=502, detail=f"VOLA API error: {exc}")

    task_id = data.get("taskId", data.get("id", ""))
    if not task_id:
        raise HTTPException(status_code=502, detail="VOLA did not return a taskId")

    # Poll
    result = await client.poll_task_sync(task_id, body.timeout_seconds, body.poll_interval_seconds)

    if result["status"] == "timeout":
        raise HTTPException(
            status_code=504,
            detail={"message": f"Task {task_id} did not complete within {body.timeout_seconds}s", "task_id": task_id, "device_sn": device_sn},
        )

    return SetParamsSyncResponse(
        task_id=task_id,
        device_sn=device_sn,
        status=result["status"],
        raw_task_result=result["result"],
        applied=applied,
    )


@router.post("/device/{device_id_pk}/bind")
async def bind_to_site(
    device_id_pk: int,
    body: BindRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Bind a True911 device (by PK) to a site."""
    try:
        device = await bind_device_to_site(
            db, current_user.tenant_id, device_id_pk, body.site_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "ok": True,
        "device_id": device.device_id,
        "site_id": device.site_id,
        "status": device.status,
    }


@router.post("/device/{device_sn}/provision/basic", response_model=ProvisionBasicResponse)
async def provision_basic(
    device_sn: str,
    body: ProvisionBasicRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Apply basic PR12 provisioning parameters (site code, inform interval).

    Uses the safe allowlist/denylist controls. Returns the result synchronously.
    """
    client = await get_tenant_vola_client(db, current_user.tenant_id)

    params = build_provision_payload(
        site_code=body.site_code,
        inform_interval=body.inform_interval,
        extra_params=body.extra_params,
    )

    # Validate safety
    err = client.validate_set_param_values(params)
    if err:
        raise HTTPException(status_code=400, detail=err)

    applied = {pair[0]: pair[1] for pair in params}

    try:
        data = await client.create_set_parameter_values_task(device_sn, params)
    except Exception as exc:
        logger.exception("Failed to create provisioning task")
        raise HTTPException(status_code=502, detail=f"VOLA API error: {exc}")

    task_id = data.get("taskId", data.get("id", ""))
    if not task_id:
        raise HTTPException(status_code=502, detail="VOLA did not return a taskId")

    if not body.sync:
        return ProvisionBasicResponse(
            task_id=task_id, device_sn=device_sn, status="pending", applied=applied,
        )

    result = await client.poll_task_sync(task_id, body.timeout_seconds)

    if result["status"] == "timeout":
        raise HTTPException(
            status_code=504,
            detail={"message": f"Provisioning task {task_id} timed out", "task_id": task_id, "device_sn": device_sn},
        )

    return ProvisionBasicResponse(
        task_id=task_id,
        device_sn=device_sn,
        status=result["status"],
        raw_task_result=result["result"],
        applied=applied,
    )


@router.get("/device/{device_sn}/status")
async def device_status(
    device_sn: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get combined status: True911 DB record + optional VOLA live read."""
    # Find local device
    result = await db.execute(
        select(Device).where(
            Device.tenant_id == current_user.tenant_id,
            Device.serial_number == device_sn,
        )
    )
    device = result.scalar_one_or_none()

    local = None
    if device:
        local = {
            "device_id": device.device_id,
            "site_id": device.site_id,
            "status": device.status,
            "serial_number": device.serial_number,
            "mac_address": device.mac_address,
            "firmware_version": device.firmware_version,
            "last_heartbeat": device.last_heartbeat.isoformat() if device.last_heartbeat else None,
        }

    return {
        "device_sn": device_sn,
        "local": local,
    }
