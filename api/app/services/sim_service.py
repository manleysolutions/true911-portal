"""SIM lifecycle service — enqueues async actions and handles worker dispatch."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.sim import Sim
from app.models.sim_event import SimEvent
from app.models.user import User
from app.schemas.sim import SimActionOut
from app.services import job_service

logger = logging.getLogger("true911.sims")

# Valid state transitions
_TRANSITIONS: dict[str, list[str]] = {
    "activate": ["inventory", "suspended"],
    "suspend": ["active"],
    "resume": ["suspended"],
}


async def enqueue_sim_action(
    db: AsyncSession,
    sim_id: int,
    action: str,
    current_user: User,
) -> SimActionOut:
    """Validate, create a SimEvent, and enqueue a job for the action."""
    result = await db.execute(
        select(Sim).where(Sim.id == sim_id, Sim.tenant_id == current_user.tenant_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SIM not found")

    valid_from = _TRANSITIONS.get(action, [])
    if sim.status not in valid_from:
        from fastapi import HTTPException, status
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot {action} SIM in status '{sim.status}' (valid from: {valid_from})",
        )

    # Create immutable event log
    event = SimEvent(
        sim_id=sim_id,
        event_type=action,
        status_before=sim.status,
        initiated_by=current_user.email,
    )
    db.add(event)

    # Enqueue job
    job = await job_service.create_and_enqueue(
        db,
        job_type=f"sim.{action}",
        queue="provisioning",
        tenant_id=current_user.tenant_id,
        payload={"sim_id": sim_id, "iccid": sim.iccid, "carrier": sim.carrier},
        idempotency_key=f"sim.{action}.{sim_id}",
    )

    # Link event to job
    event.job_id = job.id
    await db.commit()

    return SimActionOut(
        sim_id=sim_id,
        action=action,
        job_id=job.id,
        message=f"SIM {action} queued as job {job.id}",
    )


# ── Worker Handlers (called by worker.py dispatch) ──────────────

async def handle_sim_activate(db: AsyncSession, job: Job) -> dict[str, Any]:
    """Call the carrier API to activate the SIM."""
    payload = job.payload or {}
    sim_id = payload["sim_id"]
    carrier = payload["carrier"]

    result = await db.execute(select(Sim).where(Sim.id == sim_id))
    sim = result.scalar_one_or_none()
    if not sim:
        return {"error": "SIM not found"}

    # Call provider
    try:
        from app.integrations.registry import get_client
        from app.models.integration import IntegrationAccount  # noqa: F811

        # In production, look up the API key from integration_accounts
        # For now, log the action
        logger.info("Would call %s API to activate SIM %s", carrier, sim.iccid)
    except Exception as exc:
        logger.warning("Provider call skipped: %s", exc)

    sim.status = "active"
    await db.flush()
    return {"sim_id": sim_id, "new_status": "active"}


async def handle_sim_suspend(db: AsyncSession, job: Job) -> dict[str, Any]:
    payload = job.payload or {}
    sim_id = payload["sim_id"]

    result = await db.execute(select(Sim).where(Sim.id == sim_id))
    sim = result.scalar_one_or_none()
    if not sim:
        return {"error": "SIM not found"}

    logger.info("Would call %s API to suspend SIM %s", payload.get("carrier"), sim.iccid)
    sim.status = "suspended"
    await db.flush()
    return {"sim_id": sim_id, "new_status": "suspended"}


async def handle_sim_resume(db: AsyncSession, job: Job) -> dict[str, Any]:
    payload = job.payload or {}
    sim_id = payload["sim_id"]

    result = await db.execute(select(Sim).where(Sim.id == sim_id))
    sim = result.scalar_one_or_none()
    if not sim:
        return {"error": "SIM not found"}

    logger.info("Would call %s API to resume SIM %s", payload.get("carrier"), sim.iccid)
    sim.status = "active"
    await db.flush()
    return {"sim_id": sim_id, "new_status": "active"}


async def handle_poll_usage(db: AsyncSession, job: Job) -> dict[str, Any]:
    """Poll carrier API for usage data and store in sim_usage_daily."""
    payload = job.payload or {}
    logger.info("Would poll usage for SIM %s", payload.get("sim_id"))
    return {"status": "skipped", "reason": "provider credentials not configured"}


async def _mark_payload_processed(db: AsyncSession, payload_id: str) -> None:
    """Legacy-stub side effect: mark the archived payload processed.

    Extracted so the T-Mobile flag-off branch and the non-T-Mobile
    branch can share the same write without duplicating the SELECT.
    """
    from app.models.integration_payload import IntegrationPayload
    result = await db.execute(
        select(IntegrationPayload).where(IntegrationPayload.payload_id == payload_id)
    )
    ip = result.scalar_one_or_none()
    if ip:
        ip.processed = True
        await db.flush()


async def handle_webhook(db: AsyncSession, job: Job) -> dict[str, Any]:
    """Process a persisted webhook payload.

    Result shape (always populated, useful for ``jobs.result``-based
    debugging from Postgres without re-running the worker):

      Every return value includes ``payload_id``, ``processed`` (True),
      and ``source`` (the job's payload source, may be ``None``).

      For T-Mobile jobs (``source == "tmobile"``):
        * Flag on → adds the full ``tmobile_*`` set from
          :func:`process_payload` (``tmobile_status``, ``tmobile_reason``,
          ``tmobile_matched_sim_iccid``, ``tmobile_matched_device_id``).
        * Flag off → adds ``tmobile_status="skipped:flag_off"`` so
          operators inspecting ``jobs.result`` can immediately see that
          the worker process did not have ``FEATURE_TMOBILE_CALLBACK_INGEST=true``
          (a common failure mode when the env var was set on the API
          service via the Render dashboard but not propagated to the
          worker service — Blueprint sync only applies vars listed in
          ``render.yaml`` per service).

    For all sources the legacy "mark IntegrationPayload processed"
    side effect still runs — no change to the audit trail.
    """
    payload = job.payload or {}
    payload_id = payload.get("payload_id")
    source = payload.get("source")
    logger.info("Processing webhook %s from %s", payload_id, source)

    # T-Mobile callback ingest — flag-gated delegation.  Imported
    # lazily so a `FEATURE_TMOBILE_CALLBACK_INGEST` env-var typo or
    # an off-flag deploy never touches the new module at import time.
    if source == "tmobile":
        from app.config import settings
        if settings.FEATURE_TMOBILE_CALLBACK_INGEST.strip().lower() == "true":
            from app.services.tmobile_callback_processor import process_payload
            result = await process_payload(db, payload_id)
            logger.info(
                "T-Mobile callback %s processor result: %s%s",
                payload_id,
                result.status,
                f" ({result.reason})" if result.reason else "",
            )
            return {
                "payload_id": payload_id,
                "processed": True,
                "source": "tmobile",
                "tmobile_status": result.status,
                "tmobile_reason": result.reason,
                "tmobile_matched_sim_iccid": result.matched_sim_iccid,
                "tmobile_matched_device_id": result.matched_device_id,
                "tmobile_account_capture": result.account_capture,
            }
        # Flag off on this worker — the most common cause is that
        # FEATURE_TMOBILE_CALLBACK_INGEST was set via Render dashboard
        # on the API service only, leaving the worker service env
        # unchanged (Blueprint sync only propagates vars listed in
        # render.yaml per service).  Log loudly so the symptom is
        # visible in worker logs, AND tag the result so it appears
        # in jobs.result without needing log access.
        logger.warning(
            "T-Mobile webhook %s arrived but the worker's "
            "FEATURE_TMOBILE_CALLBACK_INGEST is not 'true' — using "
            "legacy stub (no promotion).  Set the env var on the "
            "WORKER service (not just the API) to enable promotion. "
            "See docs/TMOBILE_CALLBACK_INGEST_MVP.md operator note.",
            payload_id,
        )
        await _mark_payload_processed(db, payload_id)
        return {
            "payload_id": payload_id,
            "processed": True,
            "source": "tmobile",
            "tmobile_status": "skipped:flag_off",
        }

    # Non-T-Mobile sources — unchanged behavior, source surfaced
    # in the result so operators can tell at a glance whether the
    # job carried the expected source.
    await _mark_payload_processed(db, payload_id)
    return {"payload_id": payload_id, "processed": True, "source": source}
