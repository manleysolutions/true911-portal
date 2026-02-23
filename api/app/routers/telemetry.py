from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.telemetry_event import TelemetryEvent
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.telemetry_event import TelemetryEventCreate, TelemetryEventOut

router = APIRouter()


@router.get("", response_model=list[TelemetryEventOut])
async def list_telemetry(
    sort: str | None = Query("-timestamp"),
    limit: int = Query(100, le=500),
    severity: str | None = None,
    site_id: str | None = None,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(TelemetryEvent).where(TelemetryEvent.tenant_id == current_user.tenant_id)
    if severity:
        q = q.where(TelemetryEvent.severity == severity)
    if site_id:
        q = q.where(TelemetryEvent.site_id == site_id)
    if category:
        q = q.where(TelemetryEvent.category == category)
    q = apply_sort(q, TelemetryEvent, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [TelemetryEventOut.model_validate(r) for r in result.scalars().all()]


@router.post("", response_model=TelemetryEventOut, status_code=201)
async def create_telemetry(
    body: TelemetryEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = TelemetryEvent(
        **body.model_dump(), tenant_id=current_user.tenant_id
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return TelemetryEventOut.model_validate(event)
