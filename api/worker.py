"""RQ worker entry point — dispatches jobs by type to handler functions.

Usage:
    rq worker default provisioning polling --url $REDIS_URL --path api

Or via the Render worker service start command.
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("true911.worker")

# Handler registry: job_type -> async handler function path
_HANDLERS: dict[str, str] = {
    "sim.activate": "app.services.sim_service:handle_sim_activate",
    "sim.suspend": "app.services.sim_service:handle_sim_suspend",
    "sim.resume": "app.services.sim_service:handle_sim_resume",
    "sim.poll_usage": "app.services.sim_service:handle_poll_usage",
    "webhook.telnyx": "app.services.sim_service:handle_webhook",
    "webhook.vola": "app.services.sim_service:handle_webhook",
    "webhook.tmobile": "app.services.sim_service:handle_webhook",
    "line.provision_e911": "app.services.line_service:handle_provision_e911",
    "line.sync_did": "app.services.line_service:handle_sync_did",
}


def _import_handler(dotted_path: str):
    """Import 'module:func' and return the callable."""
    module_path, func_name = dotted_path.rsplit(":", 1)
    module = __import__(module_path, fromlist=[func_name])
    return getattr(module, func_name)


def dispatch(job_id: int) -> None:
    """Main dispatch function called by RQ for every job.

    Loads the Job row, resolves the handler, and runs it.
    """
    asyncio.run(_dispatch_async(job_id))


async def _dispatch_async(job_id: int) -> None:
    from app.database import AsyncSessionLocal
    from app.services import job_service

    async with AsyncSessionLocal() as db:
        job = await job_service.mark_running(db, job_id)
        if not job:
            logger.error("Job %s not found", job_id)
            return

        handler_path = _HANDLERS.get(job.job_type)
        if not handler_path:
            await job_service.mark_failed(db, job_id, f"Unknown job type: {job.job_type}")
            await db.commit()
            return

        try:
            handler = _import_handler(handler_path)
            result = await handler(db, job)
            await job_service.mark_completed(db, job_id, result)
        except Exception as exc:
            logger.exception("Job %s (%s) failed", job_id, job.job_type)
            await job_service.mark_failed(db, job_id, str(exc))

        await db.commit()


if __name__ == "__main__":
    # Start the RQ worker directly
    try:
        from redis import Redis
        from rq import Worker, Queue

        from app.config import settings

        conn = Redis.from_url(settings.REDIS_URL)
        queues = [Queue(name, connection=conn) for name in ("default", "provisioning", "polling")]
        worker = Worker(queues, connection=conn)
        logger.info("Starting RQ worker on queues: default, provisioning, polling")
        worker.work()
    except ImportError:
        logger.error("redis and rq packages required. Install: pip install redis rq")
        sys.exit(1)
