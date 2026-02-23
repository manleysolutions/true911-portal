from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.e911_change_log import E911ChangeLog
from ..models.user import User
from ..schemas.e911_change_log import E911ChangeLogOut, E911ChangeLogCreate

router = APIRouter(prefix="/e911-changes", tags=["e911"])


@router.get("", response_model=list[E911ChangeLogOut])
async def list_changes(
    site_id: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(E911ChangeLog)
        .where(E911ChangeLog.tenant_id == current_user.tenant_id)
    )
    if site_id:
        q = q.where(E911ChangeLog.site_id == site_id)
    q = q.order_by(desc(E911ChangeLog.requested_at)).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("", response_model=E911ChangeLogOut, dependencies=[Depends(require_permission("UPDATE_E911"))])
async def create_change(
    body: E911ChangeLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    log = E911ChangeLog(
        log_id=body.log_id,
        site_id=body.site_id,
        tenant_id=current_user.tenant_id,
        requested_by=current_user.email,
        requester_name=current_user.name,
        requested_at=body.requested_at,
        old_street=body.old_street,
        old_city=body.old_city,
        old_state=body.old_state,
        old_zip=body.old_zip,
        new_street=body.new_street,
        new_city=body.new_city,
        new_state=body.new_state,
        new_zip=body.new_zip,
        reason=body.reason,
        status=body.status or "applied",
        applied_at=body.applied_at,
        correlation_id=body.correlation_id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log
