from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission
from app.models.job import Job
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.job import JobDetailOut, JobOut

router = APIRouter()


@router.get(
    "",
    response_model=list[JobOut],
    dependencies=[Depends(require_permission("VIEW_JOBS"))],
)
async def list_jobs(
    sort: str | None = Query("-created_at"),
    limit: int = Query(50, le=200),
    status_filter: str | None = Query(None, alias="status"),
    job_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_JOBS")),
):
    q = select(Job).where(Job.tenant_id == current_user.tenant_id)
    if status_filter:
        q = q.where(Job.status == status_filter)
    if job_type:
        q = q.where(Job.job_type == job_type)
    q = apply_sort(q, Job, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [JobOut.model_validate(j) for j in result.scalars().all()]


@router.get(
    "/{pk}",
    response_model=JobDetailOut,
    dependencies=[Depends(require_permission("VIEW_JOBS"))],
)
async def get_job(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_JOBS")),
):
    result = await db.execute(
        select(Job).where(Job.id == pk, Job.tenant_id == current_user.tenant_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return JobDetailOut.model_validate(job)
