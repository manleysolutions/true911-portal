"""Public (unauthenticated) endpoints for lead capture forms."""

from __future__ import annotations

import logging
from pydantic import BaseModel
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db
from ..schemas.registration import (
    RegistrationCreate,
    RegistrationCreateResponse,
    RegistrationLocationOut,
    RegistrationOut,
    RegistrationServiceUnitOut,
    RegistrationUpdate,
)
from ..services import registration_service as reg_svc
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


# ════════════════════════════════════════════════════════════════════
# Self-service customer registration — Phase R1
# ════════════════════════════════════════════════════════════════════
#
# Anonymous customers walk through a multi-step wizard that stages an
# onboarding submission.  Nothing in this surface creates production
# rows (customers / sites / service_units / users / devices) — those
# are materialised by an internal reviewer in a later phase.
#
# SECURITY TODO before any public launch:
#   1. Apply per-IP rate limiting to POST/PATCH/submit (no shared
#      middleware exists today).  Until rate limiting is in place the
#      registration entry point should not be linked from any public
#      page.
#   2. Add CAPTCHA on the POST endpoint.
#   3. Decide on resume-token-via-email delivery (R1 returns the
#      plaintext only in the POST response).


def _serialize_registration(registration) -> RegistrationOut:
    """Build the read-only public shape from an ORM row + its children.

    Locations/units are loaded lazily by the caller — this helper just
    wires them into the Pydantic model.  Resume-token fields are never
    surfaced beyond the expiry timestamp.
    """

    locations_out: list[RegistrationLocationOut] = []
    for loc in getattr(registration, "_loaded_locations", []) or []:
        units_out = [
            RegistrationServiceUnitOut.model_validate(u)
            for u in getattr(loc, "_loaded_units", []) or []
        ]
        loc_out = RegistrationLocationOut.model_validate(loc)
        loc_out.service_units = units_out
        locations_out.append(loc_out)

    out = RegistrationOut.model_validate(registration)
    out.locations = locations_out
    return out


async def _load_registration_tree(db: AsyncSession, registration) -> None:
    """Attach locations + their service units onto the ORM instance
    via private attributes the serializer reads.  Single query for
    each child table — no N+1.
    """

    locations = list(await reg_svc.list_locations_for(db, registration.id))
    units = list(await reg_svc.list_service_units_for(db, registration.id))

    units_by_loc: dict[int, list] = {}
    for u in units:
        units_by_loc.setdefault(u.registration_location_id, []).append(u)

    for loc in locations:
        setattr(loc, "_loaded_units", units_by_loc.get(loc.id, []))
    setattr(registration, "_loaded_locations", locations)


async def _require_registration(
    db: AsyncSession,
    registration_id: str,
    token: Optional[str],
):
    """Locate a registration by its public id and verify the resume
    token.  Maps service-layer errors to the HTTP contract documented
    in the registration plan: 404 / 403 / 410.
    """

    registration = await reg_svc.get_registration_by_public_id(db, registration_id)
    if not registration:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")

    try:
        reg_svc.verify_resume_token(registration, token)
    except reg_svc.ResumeTokenInvalid:
        # Deliberately identical phrasing for missing token vs wrong
        # token — never leak whether the registration exists.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid resume token")
    except reg_svc.ResumeTokenExpired:
        raise HTTPException(
            status.HTTP_410_GONE,
            "Resume link has expired. Please start a new registration.",
        )

    return registration


@router.post(
    "/registrations",
    response_model=RegistrationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_public_registration(
    body: RegistrationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a draft registration.

    Returns the resume token in plaintext — it is the only time the
    server ever exposes it.  Clients MUST persist it (URL, local
    storage, email) before navigating away.
    """

    result = await reg_svc.create_registration(db, body)
    await _load_registration_tree(db, result.registration)
    return RegistrationCreateResponse(
        registration=_serialize_registration(result.registration),
        resume_token=result.resume_token,
    )


@router.get(
    "/registrations/{registration_id}",
    response_model=RegistrationOut,
)
async def get_public_registration(
    registration_id: str,
    token: Optional[str] = Query(None, description="Resume token issued at creation"),
    db: AsyncSession = Depends(get_db),
):
    """Load a saved-in-progress registration via its resume token."""

    registration = await _require_registration(db, registration_id, token)
    await _load_registration_tree(db, registration)
    return _serialize_registration(registration)


@router.patch(
    "/registrations/{registration_id}",
    response_model=RegistrationOut,
)
async def update_public_registration(
    registration_id: str,
    body: RegistrationUpdate,
    token: Optional[str] = Query(None, description="Resume token issued at creation"),
    db: AsyncSession = Depends(get_db),
):
    """Partial save during the wizard.

    Only fields a customer may legitimately edit are accepted (see
    RegistrationUpdate).  Internal review fields, lifecycle
    timestamps, conversion linkage, and the status column itself are
    not exposed here.
    """

    registration = await _require_registration(db, registration_id, token)

    try:
        await reg_svc.update_registration(db, registration, body)
    except reg_svc.RegistrationNotEditableError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This registration is no longer accepting customer edits.",
        )

    await _load_registration_tree(db, registration)
    return _serialize_registration(registration)


@router.post(
    "/registrations/{registration_id}/submit",
    response_model=RegistrationOut,
)
async def submit_public_registration(
    registration_id: str,
    token: Optional[str] = Query(None, description="Resume token issued at creation"),
    db: AsyncSession = Depends(get_db),
):
    """Finalize a draft.  Moves status draft -> submitted.

    After this call, the public surface is read-only for this
    registration — further customer edits require an operator to
    deliberately re-open the row (later phase).
    """

    registration = await _require_registration(db, registration_id, token)
    try:
        await reg_svc.submit_registration(db, registration)
    except reg_svc.IllegalStatusTransitionError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Registration has already been submitted.",
        )

    await _load_registration_tree(db, registration)
    return _serialize_registration(registration)
