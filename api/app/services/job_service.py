"""Job service — creates DB job rows and (optionally) enqueues to RQ."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job

logger = logging.getLogger("true911.jobs")


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff: min(10 * 2^attempt + jitter, 300s)."""
    delay = min(10 * (2 ** attempt) + random.uniform(0, 5), 300.0)
    return delay


async def create_and_enqueue(
    db: AsyncSession,
    *,
    job_type: str,
    queue: str = "default",
    tenant_id: str | None = None,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
) -> Job:
    """Create a Job row and attempt to enqueue it to RQ.

    If Redis/RQ is unavailable the job row is still created with status='queued'
    so it can be picked up by a future sweep or manual retry.
    """
    job = Job(
        job_type=job_type,
        queue=queue,
        status="queued",
        tenant_id=tenant_id,
        payload=payload,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
    )
    db.add(job)
    await db.flush()  # get job.id

    # Try to enqueue to RQ (graceful degradation if Redis is down)
    try:
        _enqueue_rq(job)
    except Exception:
        logger.info("Redis unavailable — job %s created but not enqueued", job.id)

    return job


def _enqueue_rq(job: Job) -> None:
    """Best-effort RQ enqueue. Fails silently if redis is not available."""
    try:
        from redis import Redis
        from rq import Queue as RqQueue

        from app.config import settings
        redis_url = getattr(settings, "REDIS_URL", None)
        if not redis_url:
            return

        conn = Redis.from_url(redis_url)
        q = RqQueue(job.queue, connection=conn)
        q.enqueue(
            "app.worker.dispatch",
            job.id,
            job_timeout="5m",
        )
    except ImportError:
        pass  # redis/rq not installed yet


async def mark_running(db: AsyncSession, job_id: int) -> Job | None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return None
    job.status = "running"
    job.attempt += 1
    job.started_at = datetime.now(timezone.utc)
    await db.flush()
    return job


async def mark_completed(db: AsyncSession, job_id: int, result_data: dict | None = None) -> None:
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        return
    job.status = "completed"
    job.result = result_data
    job.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def mark_failed(db: AsyncSession, job_id: int, error: str) -> None:
    res = await db.execute(select(Job).where(Job.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        return
    job.error = error
    if job.attempt >= job.max_attempts:
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
    else:
        job.status = "queued"
        # Re-enqueue with backoff
        delay = _backoff_seconds(job.attempt)
        logger.info("Job %s attempt %s failed, retrying in %.1fs", job.id, job.attempt, delay)
        try:
            from redis import Redis
            from rq import Queue as RqQueue

            from app.config import settings
            redis_url = getattr(settings, "REDIS_URL", None)
            if redis_url:
                conn = Redis.from_url(redis_url)
                q = RqQueue(job.queue, connection=conn)
                q.enqueue_in(
                    __import__("datetime").timedelta(seconds=delay),
                    "app.worker.dispatch",
                    job.id,
                    job_timeout="5m",
                )
        except Exception:
            pass
    await db.flush()
