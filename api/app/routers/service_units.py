"""Service Units — CRUD and compliance evaluation for site assets.

Service units represent distinct emergency communications endpoints:
elevator phones, fire alarm communicators, emergency call stations, etc.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.service_unit import ServiceUnitCreate, ServiceUnitOut, ServiceUnitUpdate
from app.services.compliance_engine import evaluate_service_unit, evaluate_site_compliance

router = APIRouter()


# ── CRUD ──────────────────────────────────────────────────────────

@router.get("", response_model=list[ServiceUnitOut])
async def list_service_units(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    unit_type: str | None = None,
    compliance_status: str | None = None,
    has_video: bool | None = Query(None),
    has_camera: bool | None = Query(None),
    install_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(ServiceUnit).where(ServiceUnit.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(ServiceUnit.site_id == site_id)
    if unit_type:
        q = q.where(ServiceUnit.unit_type == unit_type)
    if compliance_status:
        q = q.where(ServiceUnit.compliance_status == compliance_status)
    if has_video is True:
        q = q.where(ServiceUnit.video_supported == True)
    elif has_video is False:
        q = q.where(ServiceUnit.video_supported == False)
    if has_camera is True:
        q = q.where(ServiceUnit.camera_present == True)
    elif has_camera is False:
        q = q.where(ServiceUnit.camera_present == False)
    if install_type:
        q = q.where(ServiceUnit.install_type == install_type)
    q = apply_sort(q, ServiceUnit, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [ServiceUnitOut.model_validate(u) for u in result.scalars().all()]


@router.get("/{pk}", response_model=ServiceUnitOut)
async def get_service_unit(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ServiceUnit).where(ServiceUnit.id == pk, ServiceUnit.tenant_id == current_user.tenant_id)
    )
    unit = result.scalar_one_or_none()
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service unit not found")
    return ServiceUnitOut.model_validate(unit)


@router.post("", response_model=ServiceUnitOut, status_code=201)
async def create_service_unit(
    body: ServiceUnitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify site exists
    site_result = await db.execute(
        select(Site).where(Site.site_id == body.site_id, Site.tenant_id == current_user.tenant_id)
    )
    if not site_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    unit = ServiceUnit(**body.model_dump(), tenant_id=current_user.tenant_id)

    # Auto-evaluate compliance on creation
    result = evaluate_service_unit(unit)
    unit.compliance_status = result.status

    db.add(unit)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A service unit with this ID already exists")
    await db.commit()
    await db.refresh(unit)
    return ServiceUnitOut.model_validate(unit)


@router.patch("/{pk}", response_model=ServiceUnitOut)
async def update_service_unit(
    pk: int,
    body: ServiceUnitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ServiceUnit).where(ServiceUnit.id == pk, ServiceUnit.tenant_id == current_user.tenant_id)
    )
    unit = result.scalar_one_or_none()
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service unit not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)

    # Re-evaluate compliance after update
    comp = evaluate_service_unit(unit)
    unit.compliance_status = comp.status
    unit.compliance_last_reviewed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(unit)
    return ServiceUnitOut.model_validate(unit)


@router.delete("/{pk}", status_code=204)
async def delete_service_unit(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ServiceUnit).where(ServiceUnit.id == pk, ServiceUnit.tenant_id == current_user.tenant_id)
    )
    unit = result.scalar_one_or_none()
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service unit not found")
    await db.delete(unit)
    await db.commit()


# ── Compliance ────────────────────────────────────────────────────

@router.get("/{pk}/compliance")
async def get_unit_compliance(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Evaluate compliance for a single service unit."""
    result = await db.execute(
        select(ServiceUnit).where(ServiceUnit.id == pk, ServiceUnit.tenant_id == current_user.tenant_id)
    )
    unit = result.scalar_one_or_none()
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service unit not found")

    comp = evaluate_service_unit(unit)
    return {
        "unit_id": unit.unit_id,
        "unit_name": unit.unit_name,
        "status": comp.status,
        "checks": [{"rule": c.rule, "passed": c.passed, "severity": c.severity, "message": c.message} for c in comp.checks],
        "warnings": comp.warnings,
        "passed": comp.passed_count,
        "failed": comp.failed_count,
        "disclaimer": "This is operational guidance, not a legal compliance determination.",
    }


@router.get("/site/{site_id}/compliance")
async def get_site_compliance(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Evaluate compliance across all service units at a site."""
    # Verify site access
    site_result = await db.execute(
        select(Site).where(Site.site_id == site_id, Site.tenant_id == current_user.tenant_id)
    )
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    unit_result = await db.execute(
        select(ServiceUnit).where(
            ServiceUnit.site_id == site_id,
            ServiceUnit.tenant_id == current_user.tenant_id,
            ServiceUnit.status != "decommissioned",
        )
    )
    units = unit_result.scalars().all()

    result = evaluate_site_compliance(units)

    # Add E911 status from the site
    has_e911 = bool(site.e911_street and site.e911_city and site.e911_state and site.e911_zip)
    result["e911"] = {
        "has_address": has_e911,
        "status": site.e911_status,
        "street": site.e911_street,
        "city": site.e911_city,
        "state": site.e911_state,
        "zip": site.e911_zip,
        "warning": not has_e911 and len(units) > 0,
    }
    if not has_e911 and len(units) > 0:
        result["warnings"].insert(0, "E911 address missing — emergency routing cannot be confirmed")

    result["disclaimer"] = "This is operational guidance, not a legal compliance determination."
    return result
