from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.provider import Provider
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.provider import ProviderCreate, ProviderOut, ProviderUpdate

router = APIRouter()


@router.get("", response_model=list[ProviderOut])
async def list_providers(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    provider_type: str | None = None,
    enabled: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Provider).where(Provider.tenant_id == current_user.tenant_id)
    if provider_type:
        q = q.where(Provider.provider_type == provider_type)
    if enabled is not None:
        q = q.where(Provider.enabled == enabled)
    q = apply_sort(q, Provider, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [ProviderOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{provider_pk}", response_model=ProviderOut)
async def get_provider(
    provider_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Provider).where(Provider.id == provider_pk, Provider.tenant_id == current_user.tenant_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    return ProviderOut.model_validate(provider)


@router.post(
    "",
    response_model=ProviderOut,
    status_code=201,
    dependencies=[Depends(require_permission("MANAGE_PROVIDERS"))],
)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider = Provider(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return ProviderOut.model_validate(provider)


@router.patch(
    "/{provider_pk}",
    response_model=ProviderOut,
    dependencies=[Depends(require_permission("MANAGE_PROVIDERS"))],
)
async def update_provider(
    provider_pk: int,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Provider).where(Provider.id == provider_pk, Provider.tenant_id == current_user.tenant_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(provider, field, value)
    await db.commit()
    await db.refresh(provider)
    return ProviderOut.model_validate(provider)


@router.delete(
    "/{provider_pk}",
    status_code=204,
    dependencies=[Depends(require_permission("MANAGE_PROVIDERS"))],
)
async def delete_provider(
    provider_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Provider).where(Provider.id == provider_pk, Provider.tenant_id == current_user.tenant_id)
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
    await db.delete(provider)
    await db.commit()
