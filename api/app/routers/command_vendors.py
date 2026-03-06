"""
True911 Command — Vendor management and site assignments.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.vendor import Vendor
from ..models.site_vendor import SiteVendorAssignment
from ..models.user import User
from ..schemas.command_phase4 import (
    VendorCreate, VendorUpdate, VendorOut,
    SiteVendorAssignmentCreate, SiteVendorAssignmentOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Vendor CRUD
# ---------------------------------------------------------------------------

@router.get("/vendors", response_model=list[VendorOut])
async def list_vendors(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_VIEW_VENDORS")),
):
    q = select(Vendor).where(Vendor.tenant_id == current_user.tenant_id)
    if active_only:
        q = q.where(Vendor.is_active == True)  # noqa: E712
    q = q.order_by(Vendor.name)
    result = await db.execute(q)
    return [VendorOut.model_validate(v) for v in result.scalars().all()]


@router.post("/vendors", response_model=VendorOut)
async def create_vendor(
    body: VendorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VENDORS")),
):
    vendor = Vendor(tenant_id=current_user.tenant_id, **body.model_dump())
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return VendorOut.model_validate(vendor)


@router.put("/vendors/{vendor_id}", response_model=VendorOut)
async def update_vendor(
    vendor_id: int,
    body: VendorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VENDORS")),
):
    result = await db.execute(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.tenant_id == current_user.tenant_id)
    )
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(404, "Vendor not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(vendor, field, val)
    vendor.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(vendor)
    return VendorOut.model_validate(vendor)


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(
    vendor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VENDORS")),
):
    result = await db.execute(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.tenant_id == current_user.tenant_id)
    )
    vendor = result.scalar_one_or_none()
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    await db.delete(vendor)
    await db.commit()
    return {"deleted": vendor_id}


# ---------------------------------------------------------------------------
# Site Vendor Assignments
# ---------------------------------------------------------------------------

@router.get("/site/{site_id}/vendors")
async def get_site_vendors(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all vendor assignments for a site with vendor details."""
    q = (
        select(SiteVendorAssignment)
        .where(
            SiteVendorAssignment.tenant_id == current_user.tenant_id,
            SiteVendorAssignment.site_id == site_id,
        )
        .order_by(SiteVendorAssignment.system_category)
    )
    result = await db.execute(q)
    assignments = list(result.scalars().all())

    # Fetch vendor details
    vendor_ids = list(set(a.vendor_id for a in assignments))
    vendors_map = {}
    if vendor_ids:
        vendors_q = await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))
        for v in vendors_q.scalars().all():
            vendors_map[v.id] = v

    out = []
    for a in assignments:
        v = vendors_map.get(a.vendor_id)
        out.append(SiteVendorAssignmentOut(
            id=a.id,
            site_id=a.site_id,
            vendor_id=a.vendor_id,
            system_category=a.system_category,
            is_primary=a.is_primary,
            notes=a.notes,
            vendor_name=v.name if v else None,
            vendor_contact_name=v.contact_name if v else None,
            vendor_contact_phone=v.contact_phone if v else None,
            vendor_contact_email=v.contact_email if v else None,
            created_at=a.created_at,
        ))
    return out


@router.post("/site/{site_id}/vendors", response_model=SiteVendorAssignmentOut)
async def assign_vendor_to_site(
    site_id: str,
    body: SiteVendorAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VENDORS")),
):
    # Verify vendor exists
    vendor_q = await db.execute(
        select(Vendor).where(Vendor.id == body.vendor_id, Vendor.tenant_id == current_user.tenant_id)
    )
    vendor = vendor_q.scalar_one_or_none()
    if not vendor:
        raise HTTPException(404, "Vendor not found")

    assignment = SiteVendorAssignment(
        tenant_id=current_user.tenant_id,
        site_id=site_id,
        vendor_id=body.vendor_id,
        system_category=body.system_category,
        is_primary=body.is_primary,
        notes=body.notes,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)

    return SiteVendorAssignmentOut(
        id=assignment.id,
        site_id=assignment.site_id,
        vendor_id=assignment.vendor_id,
        system_category=assignment.system_category,
        is_primary=assignment.is_primary,
        notes=assignment.notes,
        vendor_name=vendor.name,
        vendor_contact_name=vendor.contact_name,
        vendor_contact_phone=vendor.contact_phone,
        vendor_contact_email=vendor.contact_email,
        created_at=assignment.created_at,
    )


@router.delete("/site/{site_id}/vendors/{assignment_id}")
async def remove_vendor_assignment(
    site_id: str,
    assignment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VENDORS")),
):
    result = await db.execute(
        select(SiteVendorAssignment).where(
            SiteVendorAssignment.id == assignment_id,
            SiteVendorAssignment.tenant_id == current_user.tenant_id,
            SiteVendorAssignment.site_id == site_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(404, "Assignment not found")
    await db.delete(assignment)
    await db.commit()
    return {"deleted": assignment_id}
