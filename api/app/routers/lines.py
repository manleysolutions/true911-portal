from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.line import Line
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.line import LineCreate, LineOut, LineUpdate

router = APIRouter()

_LINE_CONFLICT_MSG = "A line with this DID already exists in your tenant"


def _parse_line_conflict(e: IntegrityError) -> str:
    msg = str(e.orig) if e.orig else str(e)
    if "uq_lines_did_tenant" in msg:
        return _LINE_CONFLICT_MSG
    return "Duplicate value: a line with one of these identifiers already exists"


@router.get("", response_model=list[LineOut])
async def list_lines(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    device_id: str | None = None,
    provider: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    e911_status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Line).where(Line.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(Line.site_id == site_id)
    if device_id:
        q = q.where(Line.device_id == device_id)
    if provider:
        q = q.where(Line.provider == provider)
    if status_filter:
        q = q.where(Line.status == status_filter)
    if e911_status:
        q = q.where(Line.e911_status == e911_status)
    q = apply_sort(q, Line, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [LineOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{line_pk}", response_model=LineOut)
async def get_line(
    line_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Line).where(Line.id == line_pk, Line.tenant_id == current_user.tenant_id)
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    return LineOut.model_validate(line)


@router.post("", response_model=LineOut, status_code=201)
async def create_line(
    body: LineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    line = Line(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(line)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_parse_line_conflict(e))
    await db.commit()
    await db.refresh(line)
    return LineOut.model_validate(line)


@router.patch("/{line_pk}", response_model=LineOut)
async def update_line(
    line_pk: int,
    body: LineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Line).where(Line.id == line_pk, Line.tenant_id == current_user.tenant_id)
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(line, field, value)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_parse_line_conflict(e))
    await db.commit()
    await db.refresh(line)
    return LineOut.model_validate(line)


@router.delete("/{line_pk}", status_code=204)
async def delete_line(
    line_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Line).where(Line.id == line_pk, Line.tenant_id == current_user.tenant_id)
    )
    line = result.scalar_one_or_none()
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Line not found")
    await db.delete(line)
    await db.commit()
