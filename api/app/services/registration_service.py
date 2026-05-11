"""Self-service customer registration — Phase R1.

This module owns the staging side of the registration workflow:

  * registration_id and resume-token generation (sha256-hashed at rest)
  * draft creation, partial update, and submit transition
  * status state machine (validated transitions only)
  * audit trail (registration_status_events)

Phase R1 explicitly does NOT cover:

  * conversion into production customers / sites / service_units / users
  * approval / rejection by an internal reviewer
  * billing automation
  * external integrations (Field Nation, T-Mobile, Zoho)

All conversion logic lives in a later phase.  Keep this module
side-effect-free with respect to production tables.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.registration import Registration
from app.models.registration_location import RegistrationLocation
from app.models.registration_service_unit import RegistrationServiceUnit
from app.models.registration_status_event import RegistrationStatusEvent
from app.schemas.registration import (
    MAX_LOCATIONS_PER_REGISTRATION,
    MAX_SERVICE_UNITS_PER_REGISTRATION,
    RegistrationCreate,
    RegistrationLocationIn,
    RegistrationServiceUnitIn,
    RegistrationUpdate,
)

logger = logging.getLogger("true911.registration")


# Resume tokens are valid for 30 days from creation.  Documented in
# CLAUDE.md / the Phase R1 plan; if this needs to change, update both.
RESUME_TOKEN_TTL = timedelta(days=30)

# Tenant slug that owns anonymously-submitted registrations until they
# are converted into a real customer-tenant.  Conversion (later phase)
# is the only path that re-parents a registration to a real tenant.
OPS_TENANT_ID = "ops"


# ─────────────────────────────────────────────────────────────────────
# Status state machine
# ─────────────────────────────────────────────────────────────────────

class Status:
    """String constants for every legal status.  The DB column is a
    plain VARCHAR, not a Postgres enum, so we keep these as constants
    instead of using `enum.Enum` — that matches the existing pattern
    used for sites.status / devices.status / customers.status.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    INTERNAL_REVIEW = "internal_review"
    PENDING_CUSTOMER_INFO = "pending_customer_info"
    PENDING_EQUIPMENT_ASSIGNMENT = "pending_equipment_assignment"
    PENDING_SIM_ASSIGNMENT = "pending_sim_assignment"
    PENDING_INSTALLER_SCHEDULE = "pending_installer_schedule"
    SCHEDULED = "scheduled"
    INSTALLED = "installed"
    QA_REVIEW = "qa_review"
    READY_FOR_ACTIVATION = "ready_for_activation"
    ACTIVE = "active"
    CANCELLED = "cancelled"


ALL_STATUSES: frozenset[str] = frozenset({
    Status.DRAFT,
    Status.SUBMITTED,
    Status.INTERNAL_REVIEW,
    Status.PENDING_CUSTOMER_INFO,
    Status.PENDING_EQUIPMENT_ASSIGNMENT,
    Status.PENDING_SIM_ASSIGNMENT,
    Status.PENDING_INSTALLER_SCHEDULE,
    Status.SCHEDULED,
    Status.INSTALLED,
    Status.QA_REVIEW,
    Status.READY_FOR_ACTIVATION,
    Status.ACTIVE,
    Status.CANCELLED,
})

TERMINAL_STATUSES: frozenset[str] = frozenset({Status.ACTIVE, Status.CANCELLED})


# Allowed forward transitions.  Cancelled is reachable from any
# non-terminal state and is added programmatically below.
_TRANSITIONS: dict[str, frozenset[str]] = {
    Status.DRAFT: frozenset({Status.SUBMITTED}),
    Status.SUBMITTED: frozenset({Status.INTERNAL_REVIEW}),
    Status.INTERNAL_REVIEW: frozenset({
        Status.PENDING_CUSTOMER_INFO,
        Status.PENDING_EQUIPMENT_ASSIGNMENT,
    }),
    Status.PENDING_CUSTOMER_INFO: frozenset({Status.INTERNAL_REVIEW}),
    Status.PENDING_EQUIPMENT_ASSIGNMENT: frozenset({Status.PENDING_SIM_ASSIGNMENT}),
    Status.PENDING_SIM_ASSIGNMENT: frozenset({Status.PENDING_INSTALLER_SCHEDULE}),
    Status.PENDING_INSTALLER_SCHEDULE: frozenset({Status.SCHEDULED}),
    Status.SCHEDULED: frozenset({Status.INSTALLED}),
    Status.INSTALLED: frozenset({Status.QA_REVIEW}),
    Status.QA_REVIEW: frozenset({Status.READY_FOR_ACTIVATION, Status.PENDING_EQUIPMENT_ASSIGNMENT}),
    Status.READY_FOR_ACTIVATION: frozenset({Status.ACTIVE}),
    Status.ACTIVE: frozenset(),
    Status.CANCELLED: frozenset(),
}


def allowed_next_statuses(current: str) -> frozenset[str]:
    """Return the set of statuses reachable from ``current``.

    Cancellation is reachable from any non-terminal status.
    """

    base = _TRANSITIONS.get(current, frozenset())
    if current not in TERMINAL_STATUSES:
        return base | {Status.CANCELLED}
    return base


def is_legal_transition(from_status: str, to_status: str) -> bool:
    return to_status in allowed_next_statuses(from_status)


class IllegalStatusTransitionError(ValueError):
    """Raised when a status transition is rejected by the state machine."""

    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"illegal transition: {from_status!r} -> {to_status!r}"
        )


# ─────────────────────────────────────────────────────────────────────
# Resume-token helpers
# ─────────────────────────────────────────────────────────────────────

def generate_resume_token() -> str:
    """Generate a fresh URL-safe resume token (plaintext).

    Mirrors the auth.py password-reset pattern — 48 bytes of entropy,
    URL-safe base64-encoded.  Callers are responsible for hashing via
    :func:`hash_resume_token` before persistence.
    """

    return secrets.token_urlsafe(48)


def hash_resume_token(token: str) -> str:
    """One-way hash of a resume token for storage."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(plaintext: Optional[str], stored_hash: Optional[str]) -> bool:
    """Constant-time compare of a candidate token against the stored hash."""

    if not plaintext or not stored_hash:
        return False
    candidate = hash_resume_token(plaintext)
    return secrets.compare_digest(candidate, stored_hash)


def is_token_expired(expiry: Optional[datetime], *, now: Optional[datetime] = None) -> bool:
    if expiry is None:
        return True
    if now is None:
        now = datetime.now(timezone.utc)
    if expiry.tzinfo is None:
        # Treat naive timestamps as UTC.  Matches how the rest of the
        # codebase handles this (e.g. auth.py reset-token expiry).
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry < now


# ─────────────────────────────────────────────────────────────────────
# Public-facing identifier
# ─────────────────────────────────────────────────────────────────────

def generate_registration_id() -> str:
    """Return a URL-friendly public id, e.g. ``REG-AB12CD34EF56``.

    Distinct from the DB primary key so we can hand this value out to
    customers without exposing internal row numbering.
    """

    suffix = secrets.token_hex(6).upper()
    return f"REG-{suffix}"


# ─────────────────────────────────────────────────────────────────────
# Token verification result shape
# ─────────────────────────────────────────────────────────────────────

class ResumeTokenInvalid(ValueError):
    """Resume token did not match the stored hash for this registration."""


class ResumeTokenExpired(ValueError):
    """Resume token matched but has passed its expiry."""


def verify_resume_token(registration: Registration, token: Optional[str]) -> None:
    """Raise the appropriate error if ``token`` cannot reopen this
    registration.

    Order matters: we check expiry only after a successful hash match
    so a 410 is never returned for an obviously bogus token.
    """

    if not token_matches(token, registration.resume_token_hash):
        raise ResumeTokenInvalid()
    if is_token_expired(registration.resume_token_expires_at):
        raise ResumeTokenExpired()


# ─────────────────────────────────────────────────────────────────────
# Editability gate
# ─────────────────────────────────────────────────────────────────────

# Customers may PATCH a registration only while it is editable.  After
# submit, the public surface is read-only — operators may move the
# state forward via the internal surface (later phase).
PUBLIC_EDITABLE_STATUSES: frozenset[str] = frozenset({Status.DRAFT})


def is_publicly_editable(registration: Registration) -> bool:
    return registration.status in PUBLIC_EDITABLE_STATUSES


class RegistrationNotEditableError(ValueError):
    """The registration is no longer accepting public edits."""


# ─────────────────────────────────────────────────────────────────────
# CRUD on the staging row
# ─────────────────────────────────────────────────────────────────────

@dataclass
class _CreateResult:
    registration: Registration
    resume_token: str  # plaintext — caller must hand it back to the client


async def create_registration(
    db: AsyncSession,
    body: RegistrationCreate,
    *,
    tenant_id: str = OPS_TENANT_ID,
) -> _CreateResult:
    """Insert a draft registration plus any inline locations/units.

    Returns the persisted ORM row and the plaintext resume token —
    the only time the plaintext is ever exposed.

    No production-table side effects: this writes only to
    registrations / registration_locations / registration_service_units
    / registration_status_events.
    """

    token = generate_resume_token()
    expiry = datetime.now(timezone.utc) + RESUME_TOKEN_TTL

    reg = Registration(
        registration_id=generate_registration_id(),
        tenant_id=tenant_id,
        status=Status.DRAFT,
        resume_token_hash=hash_resume_token(token),
        resume_token_expires_at=expiry,

        submitter_email=body.submitter_email.lower(),
        submitter_name=body.submitter_name,
        submitter_phone=body.submitter_phone,
        customer_name=body.customer_name,
        customer_legal_name=body.customer_legal_name,
        customer_account_number=body.customer_account_number,

        poc_name=body.poc_name,
        poc_phone=body.poc_phone,
        poc_email=body.poc_email.lower() if body.poc_email else None,
        poc_role=body.poc_role,

        use_case_summary=body.use_case_summary,
        selected_plan_code=body.selected_plan_code,
        plan_quantity_estimate=body.plan_quantity_estimate,

        billing_email=body.billing_email.lower() if body.billing_email else None,
        billing_address_street=body.billing_address_street,
        billing_address_city=body.billing_address_city,
        billing_address_state=body.billing_address_state,
        billing_address_zip=body.billing_address_zip,
        billing_address_country=body.billing_address_country,
        billing_method=body.billing_method,

        support_preference_json=body.support_preference_json,

        preferred_install_window_start=body.preferred_install_window_start,
        preferred_install_window_end=body.preferred_install_window_end,
        installer_notes=body.installer_notes,
    )

    db.add(reg)
    await db.flush()  # populate reg.id for nested rows below

    for location_in in body.locations:
        await _add_location(db, reg, location_in)

    # Initial status event so the audit trail shows the row's birth.
    db.add(
        RegistrationStatusEvent(
            registration_id=reg.id,
            from_status=None,
            to_status=Status.DRAFT,
            actor_email=reg.submitter_email,
            note="registration created",
        )
    )

    await db.commit()
    await db.refresh(reg)
    logger.info(
        "Registration created: registration_id=%s tenant_id=%s submitter=%s",
        reg.registration_id, reg.tenant_id, reg.submitter_email,
    )
    return _CreateResult(registration=reg, resume_token=token)


async def update_registration(
    db: AsyncSession,
    registration: Registration,
    body: RegistrationUpdate,
) -> Registration:
    """Apply a partial customer-facing update.

    Caller must have already verified the resume token and confirmed
    the row is in :data:`PUBLIC_EDITABLE_STATUSES`.
    """

    if not is_publicly_editable(registration):
        raise RegistrationNotEditableError(registration.status)

    updates = body.model_dump(exclude_unset=True)
    # Normalize email-bearing fields the same way create does.
    for email_field in ("poc_email", "billing_email"):
        if email_field in updates and updates[email_field]:
            updates[email_field] = updates[email_field].lower()

    for field, value in updates.items():
        setattr(registration, field, value)

    await db.commit()
    await db.refresh(registration)
    return registration


# ─────────────────────────────────────────────────────────────────────
# Location + service-unit helpers
# ─────────────────────────────────────────────────────────────────────

async def _add_location(
    db: AsyncSession,
    registration: Registration,
    body: RegistrationLocationIn,
) -> RegistrationLocation:
    """Internal helper — used by create_registration to attach nested
    locations during the initial POST.  Service units inside the
    location are inserted in the same call.
    """

    await _enforce_location_cap(db, registration.id, adding=1)
    await _enforce_total_unit_cap(
        db, registration.id, adding=len(body.service_units)
    )

    loc = RegistrationLocation(
        registration_id=registration.id,
        location_label=body.location_label,
        street=body.street,
        city=body.city,
        state=body.state,
        zip=body.zip,
        country=body.country,
        poc_name=body.poc_name,
        poc_phone=body.poc_phone,
        poc_email=body.poc_email.lower() if body.poc_email else None,
        dispatchable_description=body.dispatchable_description,
        access_notes=body.access_notes,
    )
    db.add(loc)
    await db.flush()

    for unit_in in body.service_units:
        db.add(
            RegistrationServiceUnit(
                registration_id=registration.id,
                registration_location_id=loc.id,
                unit_label=unit_in.unit_label,
                unit_type=unit_in.unit_type,
                phone_number_existing=unit_in.phone_number_existing,
                hardware_model_request=unit_in.hardware_model_request,
                carrier_request=unit_in.carrier_request,
                quantity=unit_in.quantity,
                install_type=unit_in.install_type,
                notes=unit_in.notes,
            )
        )

    return loc


async def _enforce_location_cap(
    db: AsyncSession, registration_id: int, *, adding: int
) -> None:
    """Refuse to push the registration past the per-row location cap."""

    current = await _count_locations(db, registration_id)
    if current + adding > MAX_LOCATIONS_PER_REGISTRATION:
        raise ValueError(
            f"location cap exceeded: have {current}, adding {adding}, "
            f"limit {MAX_LOCATIONS_PER_REGISTRATION}"
        )


async def _enforce_total_unit_cap(
    db: AsyncSession, registration_id: int, *, adding: int
) -> None:
    """Refuse to push the registration past the total service-unit cap."""

    current = await _count_service_units(db, registration_id)
    if current + adding > MAX_SERVICE_UNITS_PER_REGISTRATION:
        raise ValueError(
            f"service unit cap exceeded: have {current}, adding {adding}, "
            f"limit {MAX_SERVICE_UNITS_PER_REGISTRATION}"
        )


async def _count_locations(db: AsyncSession, registration_id: int) -> int:
    from sqlalchemy import func
    result = await db.scalar(
        select(func.count())
        .select_from(RegistrationLocation)
        .where(RegistrationLocation.registration_id == registration_id)
    )
    return int(result or 0)


async def _count_service_units(db: AsyncSession, registration_id: int) -> int:
    from sqlalchemy import func
    result = await db.scalar(
        select(func.count())
        .select_from(RegistrationServiceUnit)
        .where(RegistrationServiceUnit.registration_id == registration_id)
    )
    return int(result or 0)


# ─────────────────────────────────────────────────────────────────────
# Submit transition
# ─────────────────────────────────────────────────────────────────────

async def submit_registration(
    db: AsyncSession,
    registration: Registration,
) -> Registration:
    """Move a draft registration to ``submitted``.

    Only the draft -> submitted edge is exposed on the public surface.
    Subsequent transitions (internal_review, pending_*, etc.) live on
    the internal review surface in a later phase.
    """

    if registration.status != Status.DRAFT:
        # Reuse the state-machine error so callers can treat all
        # illegal transitions uniformly.
        raise IllegalStatusTransitionError(registration.status, Status.SUBMITTED)

    await transition_status(
        db,
        registration,
        to_status=Status.SUBMITTED,
        actor_email=registration.submitter_email,
        note="submitted via public registration API",
    )
    return registration


# ─────────────────────────────────────────────────────────────────────
# Generic transition (used by submit and, later, the internal surface)
# ─────────────────────────────────────────────────────────────────────

async def transition_status(
    db: AsyncSession,
    registration: Registration,
    *,
    to_status: str,
    actor_user_id: Optional[uuid.UUID] = None,
    actor_email: Optional[str] = None,
    note: Optional[str] = None,
) -> Registration:
    """Apply a status transition with validation + audit trail.

    Writes a registration_status_events row and stamps any lifecycle
    timestamps that change with the new status.  This is the single
    chokepoint for *all* status changes — direct ORM assignment to
    ``registration.status`` is prohibited by convention.
    """

    if to_status not in ALL_STATUSES:
        raise IllegalStatusTransitionError(registration.status, to_status)
    if not is_legal_transition(registration.status, to_status):
        raise IllegalStatusTransitionError(registration.status, to_status)

    from_status = registration.status
    now = datetime.now(timezone.utc)

    registration.status = to_status

    # Stamp lifecycle timestamps that map 1:1 to a status.  Approved /
    # activated stamps are intentionally NOT auto-set here — they are
    # written by the internal-review service when conversion runs.
    if to_status == Status.SUBMITTED and registration.submitted_at is None:
        registration.submitted_at = now
    if to_status == Status.CANCELLED and registration.cancelled_at is None:
        registration.cancelled_at = now

    db.add(
        RegistrationStatusEvent(
            registration_id=registration.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            note=note,
        )
    )

    # Phase R5 — activation hooks.  When the new status fires a side
    # effect (issue_invite on ready_for_activation, mark_customer_complete
    # on active), run it BEFORE commit so the side-effect writes share
    # the transition's single commit.  Any failure rolls back the whole
    # transition, leaving the registration in its prior status.
    activation_result = None
    if to_status in (Status.READY_FOR_ACTIVATION, Status.ACTIVE):
        # Lazy import: registration_activation imports Status from
        # this module, so importing at top-level would be circular.
        from app.services.registration_activation import run_activation_hook
        try:
            activation_result = await run_activation_hook(
                db, registration, to_status,
                actor_user_id=actor_user_id, actor_email=actor_email,
            )
        except Exception:
            # Roll back so registration.status reverts in real
            # SQLAlchemy.  Then re-raise the ActivationError (or
            # whatever other exception) so the API layer can map it
            # to a structured 4xx response.
            await db.rollback()
            raise

    await db.commit()
    await db.refresh(registration)
    # Stash the activation outcome on the instance so the router can
    # surface the freshly-issued invite (plaintext token, etc.) on
    # the transition response.  Transient — never persisted, never
    # re-derivable on a subsequent GET.
    registration._activation_result = activation_result
    logger.info(
        "Registration %s status %s -> %s actor=%s",
        registration.registration_id, from_status, to_status,
        actor_email or actor_user_id,
    )
    return registration


# ─────────────────────────────────────────────────────────────────────
# Lookup helpers
# ─────────────────────────────────────────────────────────────────────

async def get_registration_by_public_id(
    db: AsyncSession, registration_id: str
) -> Optional[Registration]:
    result = await db.execute(
        select(Registration).where(Registration.registration_id == registration_id)
    )
    return result.scalar_one_or_none()


async def list_locations_for(
    db: AsyncSession, registration_id: int
) -> Iterable[RegistrationLocation]:
    result = await db.execute(
        select(RegistrationLocation)
        .where(RegistrationLocation.registration_id == registration_id)
        .order_by(RegistrationLocation.id.asc())
    )
    return result.scalars().all()


async def list_service_units_for(
    db: AsyncSession, registration_id: int
) -> Iterable[RegistrationServiceUnit]:
    result = await db.execute(
        select(RegistrationServiceUnit)
        .where(RegistrationServiceUnit.registration_id == registration_id)
        .order_by(RegistrationServiceUnit.id.asc())
    )
    return result.scalars().all()


# ─────────────────────────────────────────────────────────────────────
# Internal review surface (Phase R3)
# ─────────────────────────────────────────────────────────────────────
#
# Helpers below back /api/registrations.  None of them create or
# modify production rows (customers, sites, service_units, devices,
# users) — that lives in a later conversion phase.

from sqlalchemy import func  # noqa: E402  (local to admin helpers)

# Fields the admin-update path is permitted to write on a Registration
# ORM row.  Everything else stays read-only on this surface — including
# status (use transition_status), submitter_email (immutable identity),
# resume_token_hash / expires_at (only the resume flow rotates them),
# and customer_id (only the future convert_registration endpoint sets
# it).  Keeping this allow-list local to the service module means the
# router can't accidentally widen it.
_ADMIN_WRITABLE_FIELDS = frozenset({
    "reviewer_notes",
    "target_tenant_id",
    "selected_plan_code",
    "plan_quantity_estimate",
    "billing_method",
    "installer_notes",
})


async def list_registrations_admin(
    db: AsyncSession,
    *,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    sort: str = "-created_at",
) -> list[Registration]:
    """Return a filtered, sorted list of registrations.

    `search` is matched against registration_id, customer_name, and
    submitter_email — the three values a reviewer is most likely to
    type when hunting for a specific record.

    The function deliberately does NOT scope by current_user.tenant_id:
    registrations all live in the "ops" tenant during staging and the
    internal queue is a global ops queue gated by RBAC, not tenancy.
    """

    q = select(Registration)
    if status_filter:
        q = q.where(Registration.status == status_filter)
    if search:
        pattern = f"%{search.lower()}%"
        q = q.where(
            func.lower(Registration.registration_id).like(pattern)
            | func.lower(Registration.customer_name).like(pattern)
            | func.lower(Registration.submitter_email).like(pattern)
        )

    # Sort: leading "-" means descending.  Falls back to created_at on
    # an unknown column rather than raising — keeps the router simple.
    desc = sort.startswith("-")
    col_name = sort.lstrip("-") or "created_at"
    column = getattr(Registration, col_name, Registration.created_at)
    q = q.order_by(column.desc() if desc else column.asc())

    q = q.limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_child_counts(
    db: AsyncSession, registration_ids: list[int]
) -> dict[int, tuple[int, int]]:
    """Return (locations_count, service_units_count) per registration id.

    Two single grouped queries — avoids the N+1 the frontend would
    otherwise need to issue when rendering the queue.
    """

    if not registration_ids:
        return {}

    loc_rows = await db.execute(
        select(
            RegistrationLocation.registration_id,
            func.count(RegistrationLocation.id),
        )
        .where(RegistrationLocation.registration_id.in_(registration_ids))
        .group_by(RegistrationLocation.registration_id)
    )
    unit_rows = await db.execute(
        select(
            RegistrationServiceUnit.registration_id,
            func.count(RegistrationServiceUnit.id),
        )
        .where(RegistrationServiceUnit.registration_id.in_(registration_ids))
        .group_by(RegistrationServiceUnit.registration_id)
    )

    out: dict[int, tuple[int, int]] = {rid: (0, 0) for rid in registration_ids}
    for rid, count in loc_rows.all():
        existing = out.get(rid, (0, 0))
        out[rid] = (int(count or 0), existing[1])
    for rid, count in unit_rows.all():
        existing = out.get(rid, (0, 0))
        out[rid] = (existing[0], int(count or 0))
    return out


async def get_unit_summary(
    db: AsyncSession, registration_ids: list[int]
) -> dict[int, tuple[Optional[str], Optional[str]]]:
    """Return (hardware_summary, carrier_summary) per registration id.

    Summaries are comma-joined distinct values from the registration's
    service units, capped to a short string suitable for the list
    column.
    """

    if not registration_ids:
        return {}

    result = await db.execute(
        select(
            RegistrationServiceUnit.registration_id,
            RegistrationServiceUnit.hardware_model_request,
            RegistrationServiceUnit.carrier_request,
        ).where(RegistrationServiceUnit.registration_id.in_(registration_ids))
    )
    hardware: dict[int, set[str]] = {}
    carrier: dict[int, set[str]] = {}
    for rid, hw, ca in result.all():
        if hw:
            hardware.setdefault(rid, set()).add(hw)
        if ca:
            carrier.setdefault(rid, set()).add(ca)

    def _summarize(values: set[str]) -> Optional[str]:
        if not values:
            return None
        joined = ", ".join(sorted(values))
        return joined if len(joined) <= 80 else joined[:77] + "…"

    out: dict[int, tuple[Optional[str], Optional[str]]] = {}
    for rid in registration_ids:
        out[rid] = (_summarize(hardware.get(rid, set())), _summarize(carrier.get(rid, set())))
    return out


async def count_registrations_by_status(db: AsyncSession) -> dict[str, int]:
    """Return a {status: count} map across all registrations.

    Backs the count badges on the internal list page.
    """

    result = await db.execute(
        select(Registration.status, func.count(Registration.id)).group_by(Registration.status)
    )
    return {status: int(n or 0) for status, n in result.all()}


async def list_status_events(
    db: AsyncSession, registration_id: int
) -> list[RegistrationStatusEvent]:
    """Return the full status timeline for a registration, oldest first."""

    result = await db.execute(
        select(RegistrationStatusEvent)
        .where(RegistrationStatusEvent.registration_id == registration_id)
        .order_by(RegistrationStatusEvent.created_at.asc(), RegistrationStatusEvent.id.asc())
    )
    return list(result.scalars().all())


async def admin_update_registration(
    db: AsyncSession,
    registration: Registration,
    updates: dict,
) -> Registration:
    """Apply admin-editable fields to a registration.

    Any keys not in :data:`_ADMIN_WRITABLE_FIELDS` are silently dropped.
    This is the single chokepoint for non-status mutations from the
    internal surface — direct ORM assignment in the router is
    prohibited by convention so future field additions land here and
    nowhere else.
    """

    filtered = {k: v for k, v in updates.items() if k in _ADMIN_WRITABLE_FIELDS}
    for field, value in filtered.items():
        setattr(registration, field, value)
    if filtered:
        await db.commit()
        await db.refresh(registration)
    return registration


async def request_more_info(
    db: AsyncSession,
    registration: Registration,
    *,
    message: str,
    actor_user_id: Optional[uuid.UUID],
    actor_email: Optional[str],
) -> Registration:
    """Move a registration to ``pending_customer_info`` with a note
    that records the reviewer's question.

    Phase R3 does not email the customer — that hook lives in a later
    phase.  The recorded note is the source of truth for "what we
    asked them".
    """

    return await transition_status(
        db,
        registration,
        to_status=Status.PENDING_CUSTOMER_INFO,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        note=f"request_info: {message}",
    )


async def cancel_registration(
    db: AsyncSession,
    registration: Registration,
    *,
    reason: str,
    actor_user_id: Optional[uuid.UUID],
    actor_email: Optional[str],
) -> Registration:
    """Move a registration to ``cancelled`` and stamp the reason.

    The reason is mirrored onto registrations.cancel_reason so the
    list view can show it without joining the status events table.
    """

    registration.cancel_reason = reason
    return await transition_status(
        db,
        registration,
        to_status=Status.CANCELLED,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        note=reason,
    )
