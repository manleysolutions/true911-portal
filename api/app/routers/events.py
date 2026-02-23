from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.event import Event
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.event import EventCreate, EventOut

router = APIRouter()


@router.get("", response_model=list[EventOut])
async def list_events(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    device_id: str | None = None,
    line_id: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Event).where(Event.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(Event.site_id == site_id)
    if device_id:
        q = q.where(Event.device_id == device_id)
    if line_id:
        q = q.where(Event.line_id == line_id)
    if event_type:
        q = q.where(Event.event_type == event_type)
    if severity:
        q = q.where(Event.severity == severity)
    q = apply_sort(q, Event, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [EventOut.model_validate(r) for r in result.scalars().all()]


@router.post("", response_model=EventOut, status_code=201)
async def create_event(
    body: EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = Event(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return EventOut.model_validate(event)
