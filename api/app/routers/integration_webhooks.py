"""Integration webhook ingestion + admin API for Zoho CRM and QuickBooks.

Webhook endpoints (no JWT auth — HMAC signed):
    POST /api/integrations/zoho/webhook
    POST /api/integrations/qb/webhook

Admin endpoints (JWT + RBAC):
    GET  /api/integrations/events
    GET  /api/integrations/reconciliation/latest
    POST /api/integrations/reconciliation/run
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission
from app.models.integration_event import IntegrationEvent
from app.models.reconciliation_snapshot import ReconciliationSnapshot
from app.models.user import User
from app.services import job_service
from app.services.webhook_auth import verify_webhook_signature

logger = logging.getLogger("true911.integrations")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════
# Webhook ingestion (HMAC auth, no JWT)
# ═══════════════════════════════════════════════════════════════════

async def _ingest_webhook(source: str, request: Request, db: AsyncSession) -> dict:
    """Shared ingestion for all provider webhooks.

    1. Verify HMAC signature
    2. Parse payload + derive idempotency key
    3. INSERT … ON CONFLICT DO NOTHING (idempotent)
    4. Enqueue background processing job
    5. Return 202
    """
    raw_body = await request.body()

    # Verify HMAC
    sig_header = request.headers.get("X-True911-Signature")
    ts_header = request.headers.get("X-True911-Timestamp")
    verify_webhook_signature(raw_body, sig_header, ts_header)

    # Parse JSON
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON body")

    # Extract fields from canonical payload
    org_id = payload.get("org_id") or payload.get("tenant_id") or "unknown"
    event_type = payload.get("event_type", "unknown")
    external_id = payload.get("external_id") or payload.get("external_account_id") or payload.get("external_subscription_id")

    # Derive idempotency key
    idempotency_key = payload.get("idempotency_key")
    if not idempotency_key:
        idempotency_key = hashlib.sha256(raw_body).hexdigest()

    # Idempotent insert using ON CONFLICT DO NOTHING
    stmt = pg_insert(IntegrationEvent).values(
        org_id=org_id,
        source=source,
        event_type=event_type,
        external_id=external_id,
        idempotency_key=idempotency_key,
        status="received",
        payload_json=payload,
    ).on_conflict_do_nothing(
        constraint="uq_integration_events_idempotency",
    ).returning(IntegrationEvent.id)

    result = await db.execute(stmt)
    row = result.fetchone()

    if row is None:
        # Duplicate — already ingested
        await db.commit()
        return {"accepted": True, "duplicate": True, "message": "Event already received"}

    event_id = row[0]

    # Enqueue processing job
    job = await job_service.create_and_enqueue(
        db,
        job_type=f"integration.process.{source}",
        queue="default",
        tenant_id=org_id,
        payload={"integration_event_id": event_id, "source": source},
        idempotency_key=f"intg.{source}.{idempotency_key}",
    )
    await db.commit()

    return {"accepted": True, "event_id": event_id, "job_id": job.id}


@router.post("/zoho/webhook", status_code=202)
async def zoho_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    return await _ingest_webhook("zoho", request, db)


@router.post("/qb/webhook", status_code=202)
async def qb_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    return await _ingest_webhook("qb", request, db)


# ═══════════════════════════════════════════════════════════════════
# Admin read endpoints (JWT + RBAC)
# ═══════════════════════════════════════════════════════════════════

@router.get("/events")
async def list_integration_events(
    source: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_INTEGRATIONS")),
):
    q = select(IntegrationEvent).where(IntegrationEvent.org_id == current_user.tenant_id)
    if source:
        q = q.where(IntegrationEvent.source == source)
    if status_filter:
        q = q.where(IntegrationEvent.status == status_filter)
    q = q.order_by(desc(IntegrationEvent.received_at)).offset(offset).limit(limit)

    result = await db.execute(q)
    events = result.scalars().all()

    # Also get total count for pagination
    count_q = select(func.count(IntegrationEvent.id)).where(IntegrationEvent.org_id == current_user.tenant_id)
    if source:
        count_q = count_q.where(IntegrationEvent.source == source)
    if status_filter:
        count_q = count_q.where(IntegrationEvent.status == status_filter)
    total = (await db.execute(count_q)).scalar() or 0

    return {
        "items": [
            {
                "id": e.id,
                "source": e.source,
                "event_type": e.event_type,
                "external_id": e.external_id,
                "status": e.status,
                "error": e.error,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "processed_at": e.processed_at.isoformat() if e.processed_at else None,
            }
            for e in events
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/reconciliation/latest")
async def get_latest_reconciliation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_INTEGRATIONS")),
):
    result = await db.execute(
        select(ReconciliationSnapshot)
        .where(ReconciliationSnapshot.org_id == current_user.tenant_id)
        .order_by(desc(ReconciliationSnapshot.created_at))
        .limit(1)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        return {"snapshot": None, "message": "No reconciliation has been run yet"}

    return {
        "snapshot": {
            "id": snap.id,
            "total_customers": snap.total_customers,
            "total_subscriptions": snap.total_subscriptions,
            "total_billed_lines": snap.total_billed_lines,
            "total_deployed_lines": snap.total_deployed_lines,
            "mismatches_count": snap.mismatches_count,
            "results_json": snap.results_json,
            "created_at": snap.created_at.isoformat() if snap.created_at else None,
        }
    }


@router.post("/reconciliation/run", status_code=202)
async def run_reconciliation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("RUN_RECONCILIATION")),
):
    """Trigger a reconciliation job."""
    job = await job_service.create_and_enqueue(
        db,
        job_type="integration.reconcile",
        queue="default",
        tenant_id=current_user.tenant_id,
        payload={"org_id": current_user.tenant_id, "triggered_by": current_user.email},
        idempotency_key=f"reconcile.{current_user.tenant_id}.{int(datetime.now(timezone.utc).timestamp())}",
    )
    await db.commit()
    return {"job_id": job.id, "message": "Reconciliation job queued"}
