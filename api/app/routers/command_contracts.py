"""
True911 Command — Service contracts and outbound webhooks.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.service_contract import ServiceContract
from ..models.vendor import Vendor
from ..models.outbound_webhook import OutboundWebhook
from ..models.user import User
from ..schemas.command_phase5 import (
    ServiceContractCreate, ServiceContractUpdate, ServiceContractOut,
    OutboundWebhookCreate, OutboundWebhookUpdate, OutboundWebhookOut,
    TenantOrgUpdate, TenantOrgOut,
)
from ..models.tenant import Tenant

router = APIRouter()


# ---------------------------------------------------------------------------
# Service Contracts
# ---------------------------------------------------------------------------

@router.get("/contracts", response_model=list[ServiceContractOut])
async def list_contracts(
    vendor_id: int | None = None,
    site_id: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_VIEW_VENDORS")),
):
    q = select(ServiceContract).where(ServiceContract.tenant_id == current_user.tenant_id)
    if vendor_id:
        q = q.where(ServiceContract.vendor_id == vendor_id)
    if site_id:
        q = q.where(ServiceContract.site_id == site_id)
    if status:
        q = q.where(ServiceContract.status == status)
    q = q.order_by(ServiceContract.end_date.asc().nullslast())

    result = await db.execute(q)
    contracts = list(result.scalars().all())

    # Get vendor names
    vendor_ids = list(set(c.vendor_id for c in contracts))
    vendors_map = {}
    if vendor_ids:
        v_q = await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))
        for v in v_q.scalars().all():
            vendors_map[v.id] = v.name

    out = []
    for c in contracts:
        data = ServiceContractOut.model_validate(c)
        data.vendor_name = vendors_map.get(c.vendor_id)
        out.append(data)
    return out


@router.post("/contracts", response_model=ServiceContractOut)
async def create_contract(
    body: ServiceContractCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VENDORS")),
):
    # Verify vendor
    v_q = await db.execute(
        select(Vendor).where(Vendor.id == body.vendor_id, Vendor.tenant_id == current_user.tenant_id)
    )
    vendor = v_q.scalar_one_or_none()
    if not vendor:
        raise HTTPException(404, "Vendor not found")

    contract = ServiceContract(
        tenant_id=current_user.tenant_id,
        **body.model_dump(),
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)

    out = ServiceContractOut.model_validate(contract)
    out.vendor_name = vendor.name
    return out


@router.put("/contracts/{contract_id}", response_model=ServiceContractOut)
async def update_contract(
    contract_id: int,
    body: ServiceContractUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VENDORS")),
):
    result = await db.execute(
        select(ServiceContract).where(
            ServiceContract.id == contract_id,
            ServiceContract.tenant_id == current_user.tenant_id,
        )
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(contract, field, val)
    contract.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(contract)
    return ServiceContractOut.model_validate(contract)


@router.delete("/contracts/{contract_id}")
async def delete_contract(
    contract_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VENDORS")),
):
    result = await db.execute(
        select(ServiceContract).where(
            ServiceContract.id == contract_id,
            ServiceContract.tenant_id == current_user.tenant_id,
        )
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(404, "Contract not found")
    await db.delete(contract)
    await db.commit()
    return {"deleted": contract_id}


# ---------------------------------------------------------------------------
# Outbound Webhooks
# ---------------------------------------------------------------------------

@router.get("/outbound-webhooks", response_model=list[OutboundWebhookOut])
async def list_outbound_webhooks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_WEBHOOKS")),
):
    result = await db.execute(
        select(OutboundWebhook)
        .where(OutboundWebhook.tenant_id == current_user.tenant_id)
        .order_by(OutboundWebhook.name)
    )
    return [OutboundWebhookOut.model_validate(h) for h in result.scalars().all()]


@router.post("/outbound-webhooks", response_model=OutboundWebhookOut)
async def create_outbound_webhook(
    body: OutboundWebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_WEBHOOKS")),
):
    hook = OutboundWebhook(
        tenant_id=current_user.tenant_id,
        **body.model_dump(),
    )
    db.add(hook)
    await db.commit()
    await db.refresh(hook)
    return OutboundWebhookOut.model_validate(hook)


@router.put("/outbound-webhooks/{hook_id}", response_model=OutboundWebhookOut)
async def update_outbound_webhook(
    hook_id: int,
    body: OutboundWebhookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_WEBHOOKS")),
):
    result = await db.execute(
        select(OutboundWebhook).where(
            OutboundWebhook.id == hook_id,
            OutboundWebhook.tenant_id == current_user.tenant_id,
        )
    )
    hook = result.scalar_one_or_none()
    if not hook:
        raise HTTPException(404, "Webhook not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(hook, field, val)
    hook.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(hook)
    return OutboundWebhookOut.model_validate(hook)


@router.delete("/outbound-webhooks/{hook_id}")
async def delete_outbound_webhook(
    hook_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_WEBHOOKS")),
):
    result = await db.execute(
        select(OutboundWebhook).where(
            OutboundWebhook.id == hook_id,
            OutboundWebhook.tenant_id == current_user.tenant_id,
        )
    )
    hook = result.scalar_one_or_none()
    if not hook:
        raise HTTPException(404, "Webhook not found")
    await db.delete(hook)
    await db.commit()
    return {"deleted": hook_id}


# ---------------------------------------------------------------------------
# Organization settings
# ---------------------------------------------------------------------------

@router.get("/org", response_model=TenantOrgOut)
async def get_org_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get organization details for the current tenant."""
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Organization not found")
    return TenantOrgOut.model_validate(tenant)


@router.put("/org", response_model=TenantOrgOut)
async def update_org_settings(
    body: TenantOrgUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_ADMIN")),
):
    """Update organization branding and settings."""
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_id == current_user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Organization not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        # Only SuperAdmin can change org_type or parent_tenant_id
        if field in ("org_type", "parent_tenant_id") and current_user.role != "SuperAdmin":
            continue
        setattr(tenant, field, val)

    await db.commit()
    await db.refresh(tenant)
    return TenantOrgOut.model_validate(tenant)


# ---------------------------------------------------------------------------
# MSP — list child organizations
# ---------------------------------------------------------------------------

@router.get("/org/children", response_model=list[TenantOrgOut])
async def list_child_orgs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_ADMIN")),
):
    """List child organizations (for MSP accounts)."""
    result = await db.execute(
        select(Tenant).where(Tenant.parent_tenant_id == current_user.tenant_id)
    )
    return [TenantOrgOut.model_validate(t) for t in result.scalars().all()]
