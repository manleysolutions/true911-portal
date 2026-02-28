"""Line service — async provisioning actions for E911 and DIDs."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job

logger = logging.getLogger("true911.lines")


async def handle_provision_e911(db: AsyncSession, job: Job) -> dict[str, Any]:
    """Call Telnyx API to provision E911 for a phone number."""
    payload = job.payload or {}
    logger.info(
        "Would provision E911 for line %s: %s, %s, %s %s",
        payload.get("line_id"),
        payload.get("street"),
        payload.get("city"),
        payload.get("state"),
        payload.get("zip"),
    )
    return {"status": "skipped", "reason": "provider credentials not configured"}


async def handle_sync_did(db: AsyncSession, job: Job) -> dict[str, Any]:
    """Sync DID assignment from Telnyx."""
    payload = job.payload or {}
    logger.info("Would sync DID for line %s", payload.get("line_id"))
    return {"status": "skipped", "reason": "provider credentials not configured"}
