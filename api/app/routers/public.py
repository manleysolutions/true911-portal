"""Public (unauthenticated) endpoints: durable lead capture + the registration wizard.

Durability invariant (D-031): a public submission is acknowledged ONLY after it
is committed to True911's database.  Notification is a post-persistence side
effect whose outcome is recorded on the acquisition record.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
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
from ..services import acquisition_service as acq
from ..services import registration_service as reg_svc

logger = logging.getLogger("true911.public")
router = APIRouter()

_IDEMPOTENCY = re.compile(r"^[A-Za-z0-9-]{16,64}$")
MAX_LEAD_BYTES = 16 * 1024
MAX_REGISTRATION_BYTES = 256 * 1024
# Accurate 503s for writes that were rolled back (nothing durable happened).
_NOT_SAVED = "We couldn't save your registration, and nothing was stored. Please try again."
_NOT_SUBMITTED = ("We couldn't submit your registration. It is still saved as a draft — "
                  "please try submitting again.")


def _guard(request: Request, max_bytes: int) -> None:
    """Payload-size + rate-limit screening shared by public submissions."""
    try:
        length = int(request.headers.get("content-length") or 0)
    except ValueError:
        length = 0
    if length > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Submission is too large.")
    if not acq.allow_submission(request):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many submissions from this connection. Please try again later.")


def _honeypot(value: Optional[str]) -> None:
    # Never acknowledge a honeypot hit as received (no false success, D-031).
    if value and value.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Submission could not be accepted.")


class _LeadBase(BaseModel):
    company: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=40)
    idempotency_key: str = Field(..., min_length=16, max_length=64)
    attribution: Optional[dict[str, Optional[str]]] = None
    website: Optional[str] = Field(None, max_length=200)      # honeypot — must stay empty

    @field_validator("company", "name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("required")
        return v

    @field_validator("idempotency_key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not _IDEMPOTENCY.match(v):
            raise ValueError("invalid idempotency key")
        return v


class AssessmentRequest(_LeadBase):
    role: Optional[str] = Field(None, max_length=100)
    message: Optional[str] = Field(None, max_length=4000)


class QuoteRequest(_LeadBase):
    num_locations: Optional[int] = Field(None, ge=1, le=100000)
    service_interests: list[str] = Field(default_factory=list, max_length=10)
    needs: list[str] = Field(default_factory=list, max_length=10)
    notes: Optional[str] = Field(None, max_length=4000)


async def _accept(db, request, body, *, kind, entry_point, **fields):
    _honeypot(body.website)
    rec, created = await acq.create_record(
        db, kind=kind, status="inquiry", entry_point=entry_point, email=str(body.email),
        idempotency_key=body.idempotency_key, attribution=body.attribution,
        company=body.company, contact_name=body.name, phone=(body.phone or "").strip() or None,
        **fields)
    receipt = acq.serialize_receipt(rec)     # from committed state, before any side effect
    if created:
        await acq.notify(db, rec)               # side effect: never decides receipt
    return receipt


@router.post("/request-access", status_code=status.HTTP_201_CREATED)
async def request_assessment(body: AssessmentRequest, request: Request,
                             db: AsyncSession = Depends(get_db)):
    """Request a Life-Safety Assessment conversation (the /get-started form).
    Path kept for client compatibility."""
    _guard(request, MAX_LEAD_BYTES)
    return await _accept(db, request, body, kind="assessment_request",
                         entry_point="assessment_request_form",
                         role=(body.role or "").strip() or None,
                         message=(body.message or "").strip() or None)


@router.post("/quote-request", status_code=status.HTTP_201_CREATED)
async def quote_request(body: QuoteRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Request a quote.  Quote-assisted: nothing is priced or purchased here."""
    _guard(request, MAX_LEAD_BYTES)
    return await _accept(db, request, body, kind="quote_request", entry_point="quote_form",
                         num_locations=body.num_locations,
                         service_interests=acq.allowlisted(body.service_interests, acq.SERVICE_INTERESTS),
                         needs=acq.allowlisted(body.needs, acq.NEEDS),
                         message=(body.notes or "").strip() or None)


# ════════════════════════════════════════════════════════════════════
# Self-service customer registration — Phase R1
# ════════════════════════════════════════════════════════════════════
#
# Anonymous customers walk through a multi-step wizard that stages an
# onboarding submission.  Nothing in this surface creates production
# rows (customers / sites / service_units / users / devices) — those
# are materialised by an internal reviewer in a later phase.
#
# Abuse controls (D-031): payload-size cap, per-client rate limiting on create /
# submit / resume lookups, and a honeypot on create.  CAPTCHA deliberately not
# added yet (see docs/ACQUISITION.md).  Resume-token-via-email delivery is still
# undecided (R1 returns the plaintext only in the POST response).
# Each wizard registration also gets an acquisition record (kind=assessment) so
# the database is the single acquisition system of record.


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
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a draft registration.

    Returns the resume token in plaintext — it is the only time the
    server ever exposes it.  Clients MUST persist it (URL, local
    storage, email) before navigating away.
    """

    _guard(request, MAX_REGISTRATION_BYTES)
    _honeypot(body.website)

    async def _stage_assessment(reg):
        # Same transaction as the registration: both rows commit, or neither.
        acq.stage_record(
            db, kind="assessment", status="assessment_draft", entry_point="registration_wizard",
            email=str(body.submitter_email), idempotency_key=f"reg-{reg.registration_id}",
            attribution=body.attribution, company=body.customer_name, contact_name=body.submitter_name,
            phone=body.submitter_phone, registration_ref=reg.registration_id)

    try:
        result = await reg_svc.create_registration(db, body, before_commit=_stage_assessment)
    except reg_svc.RegistrationNotPersisted:
        logger.exception("public registration create rolled back; nothing was saved")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_SAVED)
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
    request: Request,
    token: Optional[str] = Query(None, description="Resume token issued at creation"),
    db: AsyncSession = Depends(get_db),
):
    """Load a saved-in-progress registration via its resume token."""

    if not acq.LOOKUP_LIMITER.allow(acq.client_key(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please try again later.")
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
    request: Request,
    token: Optional[str] = Query(None, description="Resume token issued at creation"),
    db: AsyncSession = Depends(get_db),
):
    """Finalize a draft.  Moves status draft -> submitted.

    After this call, the public surface is read-only for this
    registration — further customer edits require an operator to
    deliberately re-open the row (later phase).
    """

    if not acq.allow_submission(request):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many submissions from this connection. Please try again later.")
    registration = await _require_registration(db, registration_id, token)
    ref = registration.registration_id

    async def _stage_submitted(reg):
        # Same transaction as the draft -> submitted transition.
        await acq.stage_registration_status(db, reg.registration_id, "assessment_submitted")

    try:
        await reg_svc.submit_registration(db, registration, before_commit=_stage_submitted)
    except reg_svc.IllegalStatusTransitionError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Registration has already been submitted.",
        )
    except reg_svc.RegistrationNotPersisted:
        logger.exception("public registration submit for %s rolled back; still a draft", ref)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_SUBMITTED)

    # Internal notification: a post-commit side effect that never decides the response.
    try:
        rec = await acq.get_by_idempotency_key(db, f"reg-{ref}")
        if rec is not None:
            await acq.notify(db, rec)
    except Exception:   # noqa: BLE001 — the submit is already committed
        logger.exception("acquisition notification for %s failed", ref)
        await db.rollback()
    # A failed side effect may have rolled the session back (expiring loaded
    # rows); reload explicitly so the response reflects committed state.
    await db.refresh(registration)
    await _load_registration_tree(db, registration)
    return _serialize_registration(registration)
