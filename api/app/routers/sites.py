from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.site import Site
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.site import SiteCreate, SiteOut, SiteUpdate

router = APIRouter()


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
    return [SiteOut.model_validate(r) for r in result.scalars().all()]


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
    return SiteOut.model_validate(site)


@router.post("", response_model=SiteOut, status_code=201)
async def create_site(
    body: SiteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = Site(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return SiteOut.model_validate(site)


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

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(site, field, value)
    await db.commit()
    await db.refresh(site)
    return SiteOut.model_validate(site)
