from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.call_record import CallRecord
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.call_record import CallRecordOut

router = APIRouter()


@router.get("", response_model=list[CallRecordOut], dependencies=[Depends(require_permission("INTERNAL_OPS"))])
async def list_call_records(
    sort: str | None = Query("-started_at"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    device_id: str | None = None,
    line_id: str | None = None,
    direction: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    provider: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List call detail records (CDRs) for the caller's tenant.

    Tenant-scoped: every row returned belongs to ``current_user.tenant_id``,
    so a customer User sees only their own call history.  This mirrors the
    scoping of ``GET /recordings`` and ``GET /lines`` — no exclusionary
    permission guard, because a customer is entitled to see their own CDRs.

    Filter by ``line_id`` to get the call history for one Red Tag Line.
    """
    q = select(CallRecord).where(CallRecord.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(CallRecord.site_id == site_id)
    if device_id:
        q = q.where(CallRecord.device_id == device_id)
    if line_id:
        q = q.where(CallRecord.line_id == line_id)
    if direction:
        q = q.where(CallRecord.direction == direction)
    if status_filter:
        q = q.where(CallRecord.status == status_filter)
    if provider:
        q = q.where(CallRecord.provider == provider)
    q = apply_sort(q, CallRecord, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [CallRecordOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{call_pk}", response_model=CallRecordOut, dependencies=[Depends(require_permission("INTERNAL_OPS"))])
async def get_call_record(
    call_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch a single call detail record, scoped to the caller's tenant."""
    result = await db.execute(
        select(CallRecord).where(
            CallRecord.id == call_pk,
            CallRecord.tenant_id == current_user.tenant_id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Call record not found")
    return CallRecordOut.model_validate(rec)
