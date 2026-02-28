"""Webhook ingress — accept, persist raw payload, enqueue async processing.

All webhook endpoints return 202 immediately. The actual payload processing
happens asynchronously via the job queue.
"""

import uuid

from fastapi import APIRouter, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.dependencies import get_db
from app.models.integration_payload import IntegrationPayload
from app.schemas.webhook import WebhookAck
from app.services import job_service

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
    # TODO: verify Telnyx webhook signature
    return await _ingest_webhook("telnyx", request, db)


@router.post("/vola", response_model=WebhookAck, status_code=202)
async def vola_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    return await _ingest_webhook("vola", request, db)


@router.post("/tmobile", response_model=WebhookAck, status_code=202)
async def tmobile_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    return await _ingest_webhook("tmobile", request, db)
