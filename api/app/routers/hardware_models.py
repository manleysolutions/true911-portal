from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission
from app.models.hardware_model import HardwareModel
from app.schemas.hardware_model import HardwareModelCreate, HardwareModelOut, HardwareModelUpdate

router = APIRouter()


@router.get("", response_model=list[HardwareModelOut])
async def list_hardware_models(
    manufacturer: str | None = None,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """List hardware models. Public endpoint (no auth needed for onboarding)."""
    q = select(HardwareModel)
    if active_only:
        q = q.where(HardwareModel.is_active == True)
    if manufacturer:
        q = q.where(HardwareModel.manufacturer == manufacturer)
    q = q.order_by(HardwareModel.manufacturer, HardwareModel.model_name)
    result = await db.execute(q)
    return [HardwareModelOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{model_id}", response_model=HardwareModelOut)
async def get_hardware_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HardwareModel).where(HardwareModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hardware model not found")
    return HardwareModelOut.model_validate(model)


@router.post(
    "",
    response_model=HardwareModelOut,
    status_code=201,
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
)
async def create_hardware_model(
    body: HardwareModelCreate,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(HardwareModel).where(HardwareModel.id == body.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Hardware model '{body.id}' already exists")
    model = HardwareModel(**body.model_dump())
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return HardwareModelOut.model_validate(model)


@router.put(
    "/{model_id}",
    response_model=HardwareModelOut,
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
)
async def update_hardware_model(
    model_id: str,
    body: HardwareModelUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HardwareModel).where(HardwareModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hardware model not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    await db.commit()
    await db.refresh(model)
    return HardwareModelOut.model_validate(model)


@router.delete(
    "/{model_id}",
    response_model=HardwareModelOut,
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
)
async def delete_hardware_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: sets is_active=false."""
    result = await db.execute(select(HardwareModel).where(HardwareModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hardware model not found")
    model.is_active = False
    await db.commit()
    await db.refresh(model)
    return HardwareModelOut.model_validate(model)
