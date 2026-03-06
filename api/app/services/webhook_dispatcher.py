"""
True911 — Outbound webhook dispatcher.

Fires HTTP POST requests to registered webhook URLs when events occur.
Uses HMAC-SHA256 signing when a secret is configured.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.outbound_webhook import OutboundWebhook

logger = logging.getLogger("true911.webhooks")

# Supported event types
EVENT_TYPES = [
    "incident.created",
    "incident.resolved",
    "incident.escalated",
    "readiness.changed",
    "verification.overdue",
    "verification.completed",
    "device.stale",
    "site.created",
    "site.onboarding_complete",
]


async def dispatch_event(
    db: AsyncSession,
    tenant_id: str,
    event_type: str,
    payload: dict,
):
    """Find all webhooks subscribed to this event type and fire them.

    This is a best-effort fire-and-forget dispatcher.
    Failed deliveries increment failure_count for monitoring.
    """
    if event_type not in EVENT_TYPES:
        logger.warning("Unknown webhook event type: %s", event_type)
        return

    hooks_q = await db.execute(
        select(OutboundWebhook).where(
            OutboundWebhook.tenant_id == tenant_id,
            OutboundWebhook.enabled == True,  # noqa: E712
        )
    )
    hooks = list(hooks_q.scalars().all())
    if not hooks:
        return

    now = datetime.now(timezone.utc)
    body = json.dumps({
        "event": event_type,
        "timestamp": now.isoformat(),
        "tenant_id": tenant_id,
        "data": payload,
    })

    for hook in hooks:
        try:
            subscribed = json.loads(hook.events)
        except (json.JSONDecodeError, TypeError):
            continue

        if event_type not in subscribed and "*" not in subscribed:
            continue

        # Build headers
        headers = {"Content-Type": "application/json"}
        if hook.secret:
            sig = hmac.new(
                hook.secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-True911-Signature"] = sig
            headers["X-True911-Timestamp"] = now.isoformat()

        # Fire webhook (best-effort, non-blocking)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(hook.url, content=body, headers=headers)
                hook.last_triggered_at = now
                hook.last_status_code = resp.status_code
                if resp.status_code >= 400:
                    hook.failure_count = (hook.failure_count or 0) + 1
                    logger.warning(
                        "Webhook %s returned %d for %s",
                        hook.name, resp.status_code, event_type,
                    )
                else:
                    # Reset failure count on success
                    hook.failure_count = 0
        except ImportError:
            # httpx not installed — log the intent but don't fail
            logger.info(
                "Webhook dispatch skipped (httpx not installed): %s -> %s",
                event_type, hook.url,
            )
            hook.last_triggered_at = now
            hook.last_status_code = None
        except Exception as exc:
            hook.failure_count = (hook.failure_count or 0) + 1
            hook.last_triggered_at = now
            hook.last_status_code = None
            logger.error("Webhook %s failed for %s: %s", hook.name, event_type, exc)

    # Persist webhook state updates
    # (caller should commit the session)
