"""Zero-Touch Provisioning deployment routes.

Provides a single endpoint that creates customer + site + devices + user
in one orchestrated flow.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.services.provision_deploy import run_provision_deployment

logger = logging.getLogger("true911.routers.deployments")

router = APIRouter()


# ── Request / Response models ───────────────────────────────────────────────

class ProvisionDeployRequest(BaseModel):
    customer_name: str
    site_name: str
    device_sns: list[str] = Field(default_factory=list)
    address: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    site_code: Optional[str] = None
    site_id: Optional[str] = None
    carrier: Optional[str] = None
    inform_interval: int = 300


class ProvisionDeployDeviceResult(BaseModel):
    device_sn: str
    device_id: str | None = None
    device_pk: int | None = None
    status: str
    error: str | None = None
    steps: dict[str, str] = Field(default_factory=dict)
    provision_task_id: str | None = None
    reboot_task_id: str | None = None
    applied: dict[str, str] = Field(default_factory=dict)


class UserInviteResult(BaseModel):
    user_id: str | None = None
    email: str
    status: str  # created | already_exists
    invite_token: str | None = None
    temp_password: str | None = None


class ProvisionDeployResponse(BaseModel):
    status: str  # success | partial | failed
    steps: dict[str, str] = Field(default_factory=dict)
    customer: dict[str, Any] | None = None
    site: dict[str, Any] | None = None
    devices: list[ProvisionDeployDeviceResult] = Field(default_factory=list)
    user_invite: UserInviteResult | None = None
    error: str | None = None


# ── Route ───────────────────────────────────────────────────────────────────

@router.post("/provision", response_model=ProvisionDeployResponse)
async def provision_deployment(
    body: ProvisionDeployRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_DEVICES")),
):
    """Zero-Touch Provisioning: create customer + site + devices + user in one call.

    Steps:
    1. Ensure tenant exists
    2. Create or find customer
    3. Create or find site
    4. For each device_sn: ensure in True911, bind to site, provision via VOLA, reboot
    5. Create user account with invite link (if contact_email provided)
    """
    if not body.customer_name.strip():
        raise HTTPException(status_code=400, detail="customer_name is required")
    if not body.site_name.strip():
        raise HTTPException(status_code=400, detail="site_name is required")
    if len(body.device_sns) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 devices per deployment")

    result = await run_provision_deployment(
        db,
        operator_tenant_id=current_user.tenant_id,
        customer_name=body.customer_name.strip(),
        site_name=body.site_name.strip(),
        device_sns=body.device_sns,
        address=body.address,
        contact_email=body.contact_email,
        contact_name=body.contact_name,
        site_code=body.site_code,
        site_id=body.site_id,
        carrier=body.carrier,
        inform_interval=body.inform_interval,
    )

    # Map device dicts to pydantic models
    device_results = []
    for d in result.get("devices", []):
        device_results.append(ProvisionDeployDeviceResult(**d))

    user_invite = None
    if result.get("user_invite"):
        user_invite = UserInviteResult(**result["user_invite"])

    return ProvisionDeployResponse(
        status=result["status"],
        steps=result["steps"],
        customer=result.get("customer"),
        site=result.get("site"),
        devices=device_results,
        user_invite=user_invite,
        error=result.get("error"),
    )
