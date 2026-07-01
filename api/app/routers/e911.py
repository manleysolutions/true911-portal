from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission, require_any_permission
from ..models.e911_change_log import E911ChangeLog
from ..models.user import User
from ..schemas.e911_change_log import E911ChangeLogOut, E911ChangeLogCreate
from ..services import e911_review
from ..services.e911_gaps import list_e911_gaps

router = APIRouter(prefix="/e911-changes", tags=["e911"])

# Internal E911 review queue is open to UPDATE_E911 or MANAGE_SERVICE_CLASSIFICATION
# holders (never a customer role).
_REVIEW_GUARD = [Depends(require_any_permission("UPDATE_E911", "MANAGE_SERVICE_CLASSIFICATION"))]


class _DecisionBody(BaseModel):
    note: str | None = None
    apply: bool = False


@router.get("/reviews", dependencies=_REVIEW_GUARD)
async def list_e911_reviews(
    status: str = "pending",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Pending (or all/approved/rejected) customer E911 confirmations + correction
    requests for the operator's tenant."""
    return await e911_review.list_reviews(db, current_user.tenant_id, status=status)


@router.post("/reviews/{review_id}/approve", dependencies=_REVIEW_GUARD)
async def approve_e911_review(
    review_id: str,
    body: _DecisionBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Approve a review (append-only audit).  Optionally mark applied — applying
    to the OFFICIAL record stays the controlled UPDATE_E911 step, never automatic."""
    out = await e911_review.decide(db, current_user, review_id, decision="approve",
                                   note=body.note or "", apply=body.apply)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    return out


@router.post("/reviews/{review_id}/reject", dependencies=_REVIEW_GUARD)
async def reject_e911_review(
    review_id: str,
    body: _DecisionBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Reject a review (append-only audit)."""
    out = await e911_review.decide(db, current_user, review_id, decision="reject", note=body.note or "")
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    return out


@router.get("/gaps", dependencies=[Depends(require_permission("UPDATE_E911"))])
async def e911_gaps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Internal E911 correction worklist — every location in the caller's tenant
    whose emergency record is incomplete or not yet verified.  Read-only; drives
    the fix-before-verify loop so the customer E911 axis stays honest even while
    the operational axis is shown green in preview."""
    gaps = await list_e911_gaps(db, current_user.tenant_id)
    return {"tenant_id": current_user.tenant_id, "gap_count": len(gaps), "gaps": gaps}


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
