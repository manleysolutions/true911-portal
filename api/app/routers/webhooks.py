"""Webhook ingress — accept, persist raw payload, enqueue async processing.

All webhook endpoints return 202 immediately. The actual payload processing
happens asynchronously via the job queue.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.integration_payload import IntegrationPayload
from app.schemas.webhook import WebhookAck
from app.services import job_service
from app.services.telnyx_service import (
    TelnyxSignatureError,
    ingest_call_event,
    verify_webhook_signature,
)

logger = logging.getLogger("true911.webhooks")

router = APIRouter()


async def _ingest_webhook(
    source: str,
    request: Request,
    db: AsyncSession,
) -> WebhookAck:
    """Shared ingestion logic for all provider webhooks."""
    payload_id = f"wh-{uuid.uuid4().hex[:12]}"

    # Read raw body
    raw = await request.body()
    body_text = raw.decode("utf-8", errors="replace")

    # Try to parse as JSON
    try:
        import json
        body_json = json.loads(body_text)
    except (json.JSONDecodeError, ValueError):
        body_json = None

    # Persist raw payload
    ip = IntegrationPayload(
        payload_id=payload_id,
        source=source,
        direction="inbound",
        headers=dict(request.headers),
        body=body_json,
        raw_body=body_text if body_json is None else None,
        processed=False,
    )
    db.add(ip)
    await db.flush()

    # Enqueue async processing job
    job = await job_service.create_and_enqueue(
        db,
        job_type=f"webhook.{source}",
        queue="default",
        payload={"payload_id": payload_id, "source": source},
    )
    await db.commit()

    return WebhookAck(payload_id=payload_id, job_id=job.id)


@router.post("/telnyx", response_model=WebhookAck, status_code=202)
async def telnyx_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Telnyx webhook ingress.

    Verifies the Telnyx Ed25519 signature when ``TELNYX_PUBLIC_KEY`` is
    configured (config-gated — with no key set this behaves exactly as
    before Phase 3), archives the raw payload, and best-effort ingests
    ``call.hangup`` events into the ``call_records`` (CDR) table.
    """
    raw = await request.body()

    try:
        verify_webhook_signature(
            request.headers.get("telnyx-signature-ed25519"),
            request.headers.get("telnyx-timestamp"),
            raw,
        )
    except TelnyxSignatureError as exc:
        logger.warning("Rejected Telnyx webhook: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telnyx signature")

    ack = await _ingest_webhook("telnyx", request, db)

    # Best-effort CDR ingestion — never fail the webhook (Telnyx retries).
    try:
        await ingest_call_event(db, raw)
    except Exception:
        logger.exception("Telnyx call-event ingestion failed (raw payload archived)")

    return ack


@router.post("/vola", response_model=WebhookAck, status_code=202)
async def vola_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    return await _ingest_webhook("vola", request, db)


@router.post("/tmobile", response_model=WebhookAck, status_code=202)
async def tmobile_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    return await _ingest_webhook("tmobile", request, db)
