from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.recording import Recording
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.recording import RecordingCreate, RecordingOut

router = APIRouter()


@router.get("", response_model=list[RecordingOut])
async def list_recordings(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    device_id: str | None = None,
    line_id: str | None = None,
    provider: str | None = None,
    direction: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Recording).where(Recording.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(Recording.site_id == site_id)
    if device_id:
        q = q.where(Recording.device_id == device_id)
    if line_id:
        q = q.where(Recording.line_id == line_id)
    if provider:
        q = q.where(Recording.provider == provider)
    if direction:
        q = q.where(Recording.direction == direction)
    q = apply_sort(q, Recording, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [RecordingOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{recording_pk}", response_model=RecordingOut)
async def get_recording(
    recording_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Recording).where(Recording.id == recording_pk, Recording.tenant_id == current_user.tenant_id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recording not found")
    return RecordingOut.model_validate(rec)


@router.post("", response_model=RecordingOut, status_code=201)
async def create_recording(
    body: RecordingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rec = Recording(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return RecordingOut.model_validate(rec)
