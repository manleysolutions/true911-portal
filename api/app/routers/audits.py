from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.action_audit import ActionAudit
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.action_audit import ActionAuditCreate, ActionAuditOut

router = APIRouter()


@router.get("", response_model=list[ActionAuditOut])
async def list_audits(
    sort: str | None = Query("-timestamp"),
    limit: int = Query(100, le=500),
    site_id: str | None = None,
    action_type: str | None = None,
    user_email: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(ActionAudit).where(ActionAudit.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(ActionAudit.site_id == site_id)
    if action_type:
        q = q.where(ActionAudit.action_type == action_type)
    if user_email:
        q = q.where(ActionAudit.user_email == user_email)
    q = apply_sort(q, ActionAudit, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [ActionAuditOut.model_validate(r) for r in result.scalars().all()]


@router.post("", response_model=ActionAuditOut, status_code=201)
async def create_audit(
    body: ActionAuditCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    audit = ActionAudit(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(audit)
    await db.commit()
    await db.refresh(audit)
    return ActionAuditOut.model_validate(audit)
