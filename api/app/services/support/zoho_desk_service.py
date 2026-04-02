"""Zoho Desk API service wrapper.

Handles OAuth2 token refresh, ticket creation, and ticket search.
When ZOHO_DESK_DOMAIN is empty, operates in stub mode (logs only).

Pattern follows the existing zoho_crm.py service.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.config import settings

logger = logging.getLogger("true911.support.zoho_desk")

# Module-level token cache
_token_cache: dict = {"access_token": "", "expires_at": 0.0}


def is_configured() -> bool:
    """Check whether Zoho Desk credentials are set."""
    return bool(settings.ZOHO_DESK_DOMAIN and settings.ZOHO_DESK_REFRESH_TOKEN)


async def create_ticket(
    subject: str,
    description: str,
    priority: str = "High",
    category: str = "Support Escalation",
    contact_email: str | None = None,
    custom_fields: dict | None = None,
) -> dict:
    """Create a Zoho Desk ticket.

    Returns dict with keys: ticket_id, ticket_number, ticket_url, status.
    On failure returns: ticket_id=None, status="failed", error=<message>.
    In stub mode returns: ticket_id=None, status="stub".
    """
    if not is_configured():
        logger.info("Zoho Desk stub mode — ticket not created. Subject: %s", subject)
        return {"ticket_id": None, "ticket_number": None, "ticket_url": None, "status": "stub"}

    try:
        import httpx

        token = await _get_access_token()
        domain = settings.ZOHO_DESK_DOMAIN.rstrip("/")

        payload: dict = {
            "subject": subject[:255],
            "description": description,
            "priority": priority,
            "category": category,
            "status": "Open",
        }
        if settings.ZOHO_DESK_DEPARTMENT_ID:
            payload["departmentId"] = settings.ZOHO_DESK_DEPARTMENT_ID
        if contact_email:
            payload["email"] = contact_email
        if custom_fields:
            payload["cf"] = custom_fields

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{domain}/api/v1/tickets",
                headers={
                    "Authorization": f"Zoho-oauthtoken {token}",
                    "orgId": settings.ZOHO_DESK_ORG_ID,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        ticket_id = str(data.get("id", ""))
        ticket_number = str(data.get("ticketNumber", ""))
        ticket_url = f"{domain}/agent/tickets/{ticket_id}" if ticket_id else None

        logger.info("Zoho Desk ticket created: %s (#%s)", ticket_id, ticket_number)
        return {
            "ticket_id": ticket_id,
            "ticket_number": ticket_number,
            "ticket_url": ticket_url,
            "zoho_status": data.get("status", "Open"),
            "status": "created",
        }

    except Exception as exc:
        logger.exception("Zoho Desk ticket creation failed")
        return {
            "ticket_id": None,
            "ticket_number": None,
            "ticket_url": None,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }


async def search_open_tickets(
    tenant_id: str,
    site_id: int | None = None,
    device_id: int | None = None,
    category: str | None = None,
) -> list[dict]:
    """Search for existing open tickets matching the given context.

    Returns a list of dicts with ticket_id, ticket_number, subject, status.
    Used for deduplication checks.

    TODO: Wire to Zoho Desk search API when available.
    For now, deduplication is handled via local escalation records.
    """
    if not is_configured():
        return []

    # TODO: Implement Zoho Desk search
    # GET /api/v1/tickets/search?status=Open&cf_tenant_id={tenant_id}
    logger.debug("Zoho Desk ticket search stub — returning empty (dedupe uses local DB)")
    return []


async def _get_access_token() -> str:
    """Get or refresh the Zoho OAuth2 access token."""
    global _token_cache

    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    import httpx

    accounts_domain = settings.ZOHO_DESK_ACCOUNTS_DOMAIN.rstrip("/")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{accounts_domain}/oauth/v2/token",
            params={
                "grant_type": "refresh_token",
                "client_id": settings.ZOHO_DESK_CLIENT_ID,
                "client_secret": settings.ZOHO_DESK_CLIENT_SECRET,
                "refresh_token": settings.ZOHO_DESK_REFRESH_TOKEN,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    access_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)

    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = time.time() + expires_in

    logger.info("Zoho Desk access token refreshed (expires in %ds)", expires_in)
    return access_token
