"""Public (unauthenticated) endpoints for lead capture forms."""

from __future__ import annotations

import logging
from pydantic import BaseModel
from typing import Optional

from fastapi import APIRouter

from ..services.email_service import send_email
from ..config import settings

logger = logging.getLogger("true911.public")
router = APIRouter()


class AccessRequest(BaseModel):
    company: str
    name: str
    email: str
    phone: Optional[str] = None
    role: Optional[str] = None
    message: Optional[str] = None


class QuoteRequest(BaseModel):
    company: str
    name: str
    email: str
    phone: Optional[str] = None
    num_sites: Optional[str] = None
    num_devices: Optional[str] = None
    device_types: list[str] = []
    service_tier: Optional[str] = None
    notes: Optional[str] = None


def _lead_html(title: str, fields: dict) -> str:
    rows = "".join(
        f"<tr><td style='padding:6px 12px;font-weight:600;color:#374151;'>{k}</td>"
        f"<td style='padding:6px 12px;color:#4b5563;'>{v}</td></tr>"
        for k, v in fields.items() if v
    )
    return f"""\
<html><body style="font-family:sans-serif;">
<h2 style="color:#0f172a;">{title}</h2>
<table style="border-collapse:collapse;border:1px solid #e5e7eb;">{rows}</table>
</body></html>"""


@router.post("/request-access")
async def request_access(body: AccessRequest):
    """Capture a request-access / get-started lead."""
    logger.info("Access request from %s <%s> at %s", body.name, body.email, body.company)

    html = _lead_html("New Access Request", {
        "Company": body.company,
        "Name": body.name,
        "Email": body.email,
        "Phone": body.phone,
        "Role": body.role,
        "Message": body.message,
    })
    await send_email(
        settings.TRUE911_BOOTSTRAP_SUPERADMIN_EMAIL,
        f"True911+ Access Request — {body.company}",
        html,
    )
    return {"detail": "Request received. We will be in touch."}


@router.post("/quote-request")
async def quote_request(body: QuoteRequest):
    """Capture a build-a-quote lead."""
    logger.info("Quote request from %s <%s> at %s — %s sites", body.name, body.email, body.company, body.num_sites)

    html = _lead_html("New Quote Request", {
        "Company": body.company,
        "Name": body.name,
        "Email": body.email,
        "Phone": body.phone,
        "Sites": body.num_sites,
        "Devices": body.num_devices,
        "Device Types": ", ".join(body.device_types) if body.device_types else None,
        "Service Tier": body.service_tier,
        "Notes": body.notes,
    })
    await send_email(
        settings.TRUE911_BOOTSTRAP_SUPERADMIN_EMAIL,
        f"True911+ Quote Request — {body.company} ({body.num_sites} sites)",
        html,
    )
    return {"detail": "Quote request received. We will send your quote within one business day."}
