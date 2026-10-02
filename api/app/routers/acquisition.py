"""Internal acquisition queue (read-only): durable public leads and the outcome of
each record's notification side effect, so a failed or unconfigured notification
is observable instead of silently losing a lead (D-031).

Internal / platform context only — same gate as the registration review queue.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_platform_role
from app.models.acquisition import KINDS, NOTIFICATION_STATES, STATUSES, AcquisitionRecord
from app.services import acquisition_service as acq

router = APIRouter()


@router.get("/records", dependencies=[Depends(require_platform_role("VIEW_REGISTRATIONS"))])
async def list_records(
    status: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    notification: Optional[str] = Query(None, description="pending | sent | failed | not_configured"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(AcquisitionRecord)
    if status in STATUSES:
        q = q.where(AcquisitionRecord.status == status)
    if kind in KINDS:
        q = q.where(AcquisitionRecord.kind == kind)
    if notification in NOTIFICATION_STATES:
        q = q.where(AcquisitionRecord.notification_status == notification)
    rows = (await db.execute(q.order_by(AcquisitionRecord.id.desc()).limit(limit))).scalars().all()
    return {"records": [acq.serialize_internal(r) for r in rows], "count": len(rows)}
