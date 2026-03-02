from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.device import Device
from app.models.incident import Incident
from app.models.site import Site
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.site import SiteCreate, SiteOut, SiteUpdate
from app.services.continuity import (
    compute_device_computed_status,
    compute_site_computed_status,
)
from app.services.geocoding import geocode_address, has_valid_coords

router = APIRouter()


async def _site_out(site: Site, db: AsyncSession) -> SiteOut:
    """Build SiteOut with computed_status derived from its devices."""
    out = SiteOut.model_validate(site)
    result = await db.execute(
        select(Device).where(
            Device.site_id == site.site_id,
            Device.tenant_id == site.tenant_id,
        )
    )
    devices = result.scalars().all()
    device_statuses = [
        compute_device_computed_status(d.last_heartbeat, d.heartbeat_interval)
        for d in devices
    ]
    out.computed_status = compute_site_computed_status(device_statuses)
    return out


@router.get("", response_model=list[SiteOut])
async def list_sites(
    sort: str | None = Query("-last_checkin"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    carrier: str | None = None,
    kit_type: str | None = None,
    e911_state: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Site).where(Site.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(Site.site_id == site_id)
    if status_filter:
        q = q.where(Site.status == status_filter)
    if carrier:
        q = q.where(Site.carrier == carrier)
    if kit_type:
        q = q.where(Site.kit_type == kit_type)
    if e911_state:
        q = q.where(Site.e911_state == e911_state)
    q = apply_sort(q, Site, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    sites = result.scalars().all()

    # Batch-load all devices for the tenant to avoid N+1 queries
    dev_result = await db.execute(
        select(Device).where(Device.tenant_id == current_user.tenant_id)
    )
    all_devices = dev_result.scalars().all()
    devices_by_site: dict[str, list[Device]] = {}
    for d in all_devices:
        if d.site_id:
            devices_by_site.setdefault(d.site_id, []).append(d)

    out = []
    for site in sites:
        site_out = SiteOut.model_validate(site)
        site_devices = devices_by_site.get(site.site_id, [])
        device_statuses = [
            compute_device_computed_status(d.last_heartbeat, d.heartbeat_interval)
            for d in site_devices
        ]
        site_out.computed_status = compute_site_computed_status(device_statuses)
        out.append(site_out)
    return out


@router.get("/missing-coords", response_model=list[SiteOut])
async def list_missing_coords(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all tenant sites that lack valid lat/lng coordinates."""
    result = await db.execute(
        select(Site).where(Site.tenant_id == current_user.tenant_id)
    )
    all_sites = result.scalars().all()

    # Batch-load devices for computed_status
    dev_result = await db.execute(
        select(Device).where(Device.tenant_id == current_user.tenant_id)
    )
    all_devices = dev_result.scalars().all()
    devices_by_site: dict[str, list[Device]] = {}
    for d in all_devices:
        if d.site_id:
            devices_by_site.setdefault(d.site_id, []).append(d)

    out = []
    for site in all_sites:
        if has_valid_coords(site.lat, site.lng):
            continue
        site_out = SiteOut.model_validate(site)
        site_devices = devices_by_site.get(site.site_id, [])
        device_statuses = [
            compute_device_computed_status(d.last_heartbeat, d.heartbeat_interval)
            for d in site_devices
        ]
        site_out.computed_status = compute_site_computed_status(device_statuses)
        out.append(site_out)
    return out


@router.post(
    "/{site_pk}/geocode",
    response_model=SiteOut,
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
)
async def geocode_site(
    site_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Geocode a site from its E911 address. Admin only."""
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    if not any([site.e911_street, site.e911_city, site.e911_state, site.e911_zip]):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No E911 address on file",
        )

    coords = await geocode_address(
        site.e911_street, site.e911_city, site.e911_state, site.e911_zip
    )
    if not coords:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Geocoding failed — address could not be resolved",
        )

    site.lat, site.lng = coords
    await db.commit()
    await db.refresh(site)
    return await _site_out(site, db)


@router.get("/{site_pk}", response_model=SiteOut)
async def get_site(
    site_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return await _site_out(site, db)


@router.post("", response_model=SiteOut, status_code=201)
async def create_site(
    body: SiteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = Site(**body.model_dump(), tenant_id=current_user.tenant_id)

    # Auto-geocode if E911 address fields were provided
    if any([site.e911_street, site.e911_city, site.e911_state, site.e911_zip]):
        coords = await geocode_address(
            site.e911_street, site.e911_city, site.e911_state, site.e911_zip
        )
        if coords:
            site.lat, site.lng = coords

    db.add(site)
    await db.commit()
    await db.refresh(site)
    return await _site_out(site, db)


@router.patch("/{site_pk}", response_model=SiteOut)
async def update_site(
    site_pk: int,
    body: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    updates = body.model_dump(exclude_unset=True)

    # Validate lat/lng ranges if provided
    if "lat" in updates and updates["lat"] is not None:
        if not (-90 <= updates["lat"] <= 90):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Latitude must be between -90 and 90",
            )
    if "lng" in updates and updates["lng"] is not None:
        if not (-180 <= updates["lng"] <= 180):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Longitude must be between -180 and 180",
            )

    for field, value in updates.items():
        setattr(site, field, value)

    # Auto-geocode when any E911 address field is updated
    e911_fields = {"e911_street", "e911_city", "e911_state", "e911_zip"}
    if e911_fields & body.model_fields_set:
        coords = await geocode_address(
            site.e911_street, site.e911_city, site.e911_state, site.e911_zip
        )
        if coords:
            site.lat, site.lng = coords

    await db.commit()
    await db.refresh(site)
    return await _site_out(site, db)


@router.delete(
    "/{site_pk}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
)
async def delete_site(
    site_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a site. Admin only. Refuses if devices or open incidents reference it."""
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    # Guard: check for devices referencing this site
    dev_count = await db.scalar(
        select(func.count()).select_from(Device).where(
            Device.site_id == site.site_id,
            Device.tenant_id == current_user.tenant_id,
        )
    )
    if dev_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete site: {dev_count} device(s) still assigned. "
            "Decommission or reassign devices first.",
        )

    # Guard: check for open incidents referencing this site
    inc_count = await db.scalar(
        select(func.count()).select_from(Incident).where(
            Incident.site_id == site.site_id,
            Incident.tenant_id == current_user.tenant_id,
            Incident.status != "closed",
        )
    )
    if inc_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete site: {inc_count} open incident(s). "
            "Close all incidents first.",
        )

    await db.delete(site)
    await db.commit()
