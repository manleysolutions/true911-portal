from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.incident import Incident
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.incident import (
    IncidentCloseRequest,
    IncidentCreate,
    IncidentOut,
    IncidentUpdate,
)

router = APIRouter()


@router.get("", response_model=list[IncidentOut])
async def list_incidents(
    sort: str | None = Query("-opened_at"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Incident).where(Incident.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(Incident.site_id == site_id)
    if status_filter:
        q = q.where(Incident.status == status_filter)
    if severity:
        q = q.where(Incident.severity == severity)
    q = apply_sort(q, Incident, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [IncidentOut.model_validate(r) for r in result.scalars().all()]


@router.post("", response_model=IncidentOut, status_code=201)
async def create_incident(
    body: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    incident = Incident(
        **body.model_dump(),
        tenant_id=current_user.tenant_id,
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    return IncidentOut.model_validate(incident)


@router.patch("/{incident_pk}", response_model=IncidentOut)
async def update_incident(
    incident_pk: int,
    body: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_pk,
            Incident.tenant_id == current_user.tenant_id,
        )
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(incident, field, value)
    await db.commit()
    await db.refresh(incident)
    return IncidentOut.model_validate(incident)


@router.post("/{incident_pk}/ack", response_model=IncidentOut)
async def ack_incident(
    incident_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("ACK_INCIDENT")),
):
    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_pk,
            Incident.tenant_id == current_user.tenant_id,
        )
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    incident.status = "acknowledged"
    incident.ack_by = current_user.email
    incident.ack_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(incident)
    return IncidentOut.model_validate(incident)


@router.post("/{incident_pk}/close", response_model=IncidentOut)
async def close_incident(
    incident_pk: int,
    body: IncidentCloseRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("CLOSE_INCIDENT")),
):
    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_pk,
            Incident.tenant_id == current_user.tenant_id,
        )
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")

    incident.status = "closed"
    incident.closed_at = datetime.now(timezone.utc)
    if body and body.resolution_notes:
        incident.resolution_notes = body.resolution_notes
    await db.commit()
    await db.refresh(incident)
    return IncidentOut.model_validate(incident)
