"""
True911 Command — Verification and compliance task management.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.verification_task import VerificationTask
from ..models.command_activity import CommandActivity
from ..models.notification import CommandNotification
from ..models.user import User
from ..schemas.command_phase4 import (
    VerificationTaskCreate,
    VerificationTaskUpdate,
    VerificationTaskComplete,
    VerificationTaskOut,
)

router = APIRouter()


def _task_out(task: VerificationTask) -> VerificationTaskOut:
    now = datetime.now(timezone.utc)
    is_overdue = (
        task.status in ("pending", "in_progress")
        and task.due_date is not None
        and task.due_date < now
    )
    return VerificationTaskOut(
        id=task.id,
        tenant_id=task.tenant_id,
        site_id=task.site_id,
        task_type=task.task_type,
        title=task.title,
        description=task.description,
        system_category=task.system_category,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        completed_at=task.completed_at,
        completed_by=task.completed_by,
        assigned_to=task.assigned_to,
        assigned_vendor_id=task.assigned_vendor_id,
        evidence_notes=task.evidence_notes,
        result=task.result,
        created_by=task.created_by,
        created_at=task.created_at,
        is_overdue=is_overdue,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("/verification-tasks", response_model=list[VerificationTaskOut])
async def list_verification_tasks(
    site_id: str | None = None,
    status: str | None = None,
    overdue_only: bool = False,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_VIEW_VERIFICATION")),
):
    q = (
        select(VerificationTask)
        .where(VerificationTask.tenant_id == current_user.tenant_id)
        .order_by(VerificationTask.due_date.asc().nullslast(), VerificationTask.priority.desc())
        .limit(limit)
    )
    if site_id:
        q = q.where(VerificationTask.site_id == site_id)
    if status:
        q = q.where(VerificationTask.status == status)
    if overdue_only:
        now = datetime.now(timezone.utc)
        q = q.where(
            VerificationTask.status.in_(["pending", "in_progress"]),
            VerificationTask.due_date < now,
        )

    result = await db.execute(q)
    return [_task_out(t) for t in result.scalars().all()]


@router.get("/verification-tasks/{task_id}", response_model=VerificationTaskOut)
async def get_verification_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_VIEW_VERIFICATION")),
):
    result = await db.execute(
        select(VerificationTask).where(
            VerificationTask.id == task_id,
            VerificationTask.tenant_id == current_user.tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Verification task not found")
    return _task_out(task)


@router.post("/verification-tasks", response_model=VerificationTaskOut)
async def create_verification_task(
    body: VerificationTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VERIFICATION")),
):
    task = VerificationTask(
        tenant_id=current_user.tenant_id,
        site_id=body.site_id,
        task_type=body.task_type,
        title=body.title,
        description=body.description,
        system_category=body.system_category,
        priority=body.priority,
        due_date=body.due_date,
        assigned_to=body.assigned_to,
        assigned_vendor_id=body.assigned_vendor_id,
        created_by=current_user.email,
    )
    db.add(task)

    db.add(CommandActivity(
        tenant_id=current_user.tenant_id,
        activity_type="verification_created",
        site_id=body.site_id,
        actor=current_user.email,
        summary=f"Verification task created: {body.title}",
    ))

    await db.commit()
    await db.refresh(task)
    return _task_out(task)


@router.put("/verification-tasks/{task_id}", response_model=VerificationTaskOut)
async def update_verification_task(
    task_id: int,
    body: VerificationTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VERIFICATION")),
):
    result = await db.execute(
        select(VerificationTask).where(
            VerificationTask.id == task_id,
            VerificationTask.tenant_id == current_user.tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(task, field, val)
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)
    return _task_out(task)


@router.post("/verification-tasks/{task_id}/complete", response_model=VerificationTaskOut)
async def complete_verification_task(
    task_id: int,
    body: VerificationTaskComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_COMPLETE_VERIFICATION")),
):
    result = await db.execute(
        select(VerificationTask).where(
            VerificationTask.id == task_id,
            VerificationTask.tenant_id == current_user.tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status == "completed":
        raise HTTPException(400, "Task already completed")

    now = datetime.now(timezone.utc)
    task.status = "completed"
    task.result = body.result
    task.evidence_notes = body.evidence_notes
    task.completed_at = now
    task.completed_by = current_user.email
    task.updated_at = now

    db.add(CommandActivity(
        tenant_id=current_user.tenant_id,
        activity_type="verification_completed",
        site_id=task.site_id,
        actor=current_user.email,
        summary=f"Verification completed: {task.title} — {body.result}",
        detail=body.evidence_notes,
    ))

    # Check if all tasks for this site are now complete
    pending_q = await db.execute(
        select(func.count()).select_from(VerificationTask)
        .where(
            VerificationTask.tenant_id == current_user.tenant_id,
            VerificationTask.site_id == task.site_id,
            VerificationTask.status.in_(["pending", "in_progress"]),
            VerificationTask.id != task.id,
        )
    )
    remaining = pending_q.scalar() or 0
    if remaining == 0:
        db.add(CommandNotification(
            tenant_id=current_user.tenant_id,
            channel="in_app",
            severity="info",
            title=f"Site {task.site_id}: All verification tasks complete",
            body="Site is verified and ready.",
            site_id=task.site_id,
        ))

    await db.commit()
    await db.refresh(task)
    return _task_out(task)


@router.delete("/verification-tasks/{task_id}")
async def delete_verification_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_VERIFICATION")),
):
    result = await db.execute(
        select(VerificationTask).where(
            VerificationTask.id == task_id,
            VerificationTask.tenant_id == current_user.tenant_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    await db.delete(task)
    await db.commit()
    return {"deleted": task_id}


# ---------------------------------------------------------------------------
# Summary / stats
# ---------------------------------------------------------------------------

@router.get("/verification-summary")
async def verification_summary(
    site_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get verification task summary counts."""
    tenant = current_user.tenant_id
    now = datetime.now(timezone.utc)

    base = select(VerificationTask).where(VerificationTask.tenant_id == tenant)
    if site_id:
        base = base.where(VerificationTask.site_id == site_id)

    all_q = await db.execute(base)
    tasks = list(all_q.scalars().all())

    pending = [t for t in tasks if t.status in ("pending", "in_progress")]
    completed = [t for t in tasks if t.status == "completed"]
    overdue = [t for t in pending if t.due_date and t.due_date < now]
    passed = [t for t in completed if t.result == "pass"]
    failed = [t for t in completed if t.result == "fail"]

    return {
        "total": len(tasks),
        "pending": len(pending),
        "completed": len(completed),
        "overdue": len(overdue),
        "passed": len(passed),
        "failed": len(failed),
        "completion_pct": round(len(completed) / len(tasks) * 100) if tasks else 0,
    }
