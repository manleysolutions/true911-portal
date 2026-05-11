"""Phase R4 — registration → production-row conversion.

This module is the single bridge between the staging schema
(registrations / registration_locations / registration_service_units)
and the production schema (tenants / customers / sites /
service_units / subscriptions).  It is intentionally kept isolated
from registration_service.py so the admin/transition logic stays
small and the conversion module can be reviewed on its own.

What this module does
=====================

Given an explicit reviewer decision (tenant_choice, customer_choice,
create_subscription, dry_run, confirm), it:

    1. Validates that the registration is in a convertable state
    2. Resolves or creates the target Tenant (only on reviewer demand)
    3. Resolves or creates the target Customer (scoped to that tenant)
    4. Materialises each registration_location into a Site row
    5. Materialises each registration_service_unit into a ServiceUnit
    6. Optionally creates a pending Subscription
    7. Stamps the staging rows with materialized_*_id values
    8. Writes registration_status_events + audit_log_entries
    9. Commits once at the end (or rolls back on dry_run / failure)

What this module does NOT do
============================

  * Create devices, SIMs, lines, or users
  * Call T-Mobile, Field Nation, billing, or E911 carrier APIs
  * Run geocoding (lat/lng stays NULL; the existing bulk_geocode
    cron will catch the new sites on its next pass)
  * Transition the registration's workflow status (the reviewer's
    next explicit /transition call advances the workflow)

These restrictions are enforced by what this module imports and
calls — there is no provisioning, carrier, or billing import in
this file.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_entry import AuditLogEntry
from app.models.customer import Customer
from app.models.registration import Registration
from app.models.registration_location import RegistrationLocation
from app.models.registration_service_unit import RegistrationServiceUnit
from app.models.registration_status_event import RegistrationStatusEvent
from app.models.service_unit import ServiceUnit
from app.models.site import Site
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.services.registration_service import Status
from app.services.site_customer_resolution import (
    CustomerNotFoundError,
    CustomerTenantMismatchError,
    validate_customer_id_for_tenant,
)

logger = logging.getLogger("true911.registration.convert")


# ─────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────

class ConversionError(Exception):
    """Structured error returned by the convert service.

    Each instance names the stage that failed so the API layer can
    surface a consistent ``{stage, message, next_steps}`` body to the
    reviewer.  Plain ``ValueError`` is intentionally NOT used because
    the conversion path needs structured failure data the frontend can
    parse without string-matching.
    """

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        next_steps: str = "",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.stage = stage
        self.message = message
        self.next_steps = next_steps
        self.details: dict[str, Any] = details or {}
        super().__init__(f"{stage}: {message}")


# ─────────────────────────────────────────────────────────────────────
# Convertable-state gate
# ─────────────────────────────────────────────────────────────────────

# Conversion is rejected from terminal or pre-review states.  Drafts
# haven't been submitted yet; cancelled and active records are
# terminal and converting them would either be premature or
# nonsensical.  Every other non-terminal state — including
# pending_customer_info — is fair game: the reviewer may legitimately
# want to set up production rows in parallel with chasing the
# customer for clarification.
NON_CONVERTABLE_STATES: frozenset[str] = frozenset({
    Status.DRAFT,
    Status.CANCELLED,
    Status.ACTIVE,
})


def is_convertable(reg: Registration) -> bool:
    return reg.status not in NON_CONVERTABLE_STATES


# ─────────────────────────────────────────────────────────────────────
# id slug helpers
# ─────────────────────────────────────────────────────────────────────

_SLUG_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def _slugify(label: str) -> str:
    """Convert a free-form label into an upper-snake site-id slug.

    Empty / nonsense input falls back to "LOC" so the caller always
    gets a usable prefix.  The result never contains leading/trailing
    dashes — those would visually merge with the conflict suffix.
    """
    s = _SLUG_NON_ALNUM.sub("-", (label or "").upper()).strip("-")
    return s or "LOC"


async def _next_available_site_id(db: AsyncSession, base: str) -> str:
    """Find the first non-colliding site_id of the form ``base[-N]``.

    The unique index on sites.site_id is the source of truth — this
    helper just probes it.  The race window between probe and INSERT
    is covered by the IntegrityError path in the conversion loop.
    """
    candidate = base
    n = 2
    while True:
        existing = await db.execute(select(Site.id).where(Site.site_id == candidate))
        if existing.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1
        if n > 9999:  # pathological guard
            raise ConversionError(
                stage="create_site",
                message=f"could not find a free site_id starting with '{base}'",
                next_steps="Edit the location label and retry.",
            )


def _unit_id(site_id: str, sequence: int) -> str:
    """Format a service-unit id consistent with how the existing
    operator wizard (SiteOnboarding.jsx) names them: SITE-XXX-U01.
    """
    return f"{site_id}-U{sequence:02d}"


# ─────────────────────────────────────────────────────────────────────
# Result container
# ─────────────────────────────────────────────────────────────────────

@dataclass
class _ConvertedTenant:
    tenant_id: str
    name: str
    was_created: bool


@dataclass
class _ConvertedCustomer:
    id: Optional[int]
    name: str
    tenant_id: str
    was_created: bool


@dataclass
class _ConvertedSite:
    id: Optional[int]
    site_id: str
    location_label: str
    registration_location_id: int
    was_created: bool


@dataclass
class _ConvertedServiceUnit:
    id: Optional[int]
    unit_id: str
    unit_label: str
    site_id: str
    registration_service_unit_id: int
    was_created: bool


@dataclass
class _ConvertedSubscription:
    id: Optional[int]
    plan_name: str
    status: str
    was_created: bool


@dataclass
class ConversionResult:
    """Everything the API layer needs to render the response."""

    registration: Registration
    dry_run: bool
    tenant: _ConvertedTenant
    customer: _ConvertedCustomer
    sites: list[_ConvertedSite] = field(default_factory=list)
    service_units: list[_ConvertedServiceUnit] = field(default_factory=list)
    subscription: Optional[_ConvertedSubscription] = None


# ─────────────────────────────────────────────────────────────────────
# Tenant resolution
# ─────────────────────────────────────────────────────────────────────

async def _resolve_tenant(
    db: AsyncSession,
    registration: Registration,
    *,
    tenant_choice: str,
    existing_tenant_id: Optional[str],
    new_tenant_id: Optional[str],
    new_tenant_name: Optional[str],
) -> tuple[Tenant, bool]:
    """Return (tenant, was_created).

    Honors any pre-existing ``registration.target_tenant_id`` from a
    previous successful convert — in that case the request body's
    choice fields are ignored and we re-load the stamped tenant.
    """
    # Retry-on-already-converted path.  If a previous convert
    # committed, registration.target_tenant_id is the source of truth.
    if registration.target_tenant_id:
        existing = await db.execute(
            select(Tenant).where(Tenant.tenant_id == registration.target_tenant_id)
        )
        t = existing.scalar_one_or_none()
        if not t:
            # The tenant was deleted out from under us.  Refuse to
            # silently re-create — that would re-attach orphaned
            # production rows to a fresh tenant of the same slug.
            raise ConversionError(
                stage="resolve_tenant",
                message=(
                    f"registration is already linked to tenant "
                    f"'{registration.target_tenant_id}' which no longer exists"
                ),
                next_steps="Investigate why the tenant was deleted before retrying.",
            )
        return t, False

    if tenant_choice == "attach_existing":
        existing = await db.execute(
            select(Tenant).where(Tenant.tenant_id == existing_tenant_id)
        )
        t = existing.scalar_one_or_none()
        if not t:
            raise ConversionError(
                stage="resolve_tenant",
                message=f"tenant '{existing_tenant_id}' does not exist",
                next_steps="Pick a different tenant or create a new one.",
            )
        return t, False

    # tenant_choice == "create_new"
    existing = await db.execute(
        select(Tenant).where(Tenant.tenant_id == new_tenant_id)
    )
    if existing.scalar_one_or_none():
        raise ConversionError(
            stage="resolve_tenant",
            message=f"tenant slug '{new_tenant_id}' is already taken",
            next_steps="Pick a different slug or attach to the existing tenant.",
        )
    t = Tenant(
        tenant_id=new_tenant_id,
        name=(new_tenant_name or new_tenant_id).strip(),
    )
    db.add(t)
    await db.flush()
    return t, True


# ─────────────────────────────────────────────────────────────────────
# Customer resolution
# ─────────────────────────────────────────────────────────────────────

async def _resolve_customer(
    db: AsyncSession,
    registration: Registration,
    tenant: Tenant,
    *,
    customer_choice: str,
    existing_customer_id: Optional[int],
) -> tuple[Customer, bool]:
    """Return (customer, was_created).

    Honors any pre-existing ``registration.customer_id`` from a
    previous successful convert.
    """
    # Retry path — registration already carries a customer linkage.
    if registration.customer_id:
        c = await db.get(Customer, registration.customer_id)
        if not c:
            raise ConversionError(
                stage="resolve_customer",
                message=(
                    f"registration is already linked to customer id="
                    f"{registration.customer_id} which no longer exists"
                ),
                next_steps="Investigate why the customer was deleted before retrying.",
            )
        if c.tenant_id != tenant.tenant_id:
            raise ConversionError(
                stage="resolve_customer",
                message=(
                    f"linked customer belongs to tenant '{c.tenant_id}', "
                    f"not '{tenant.tenant_id}'"
                ),
                next_steps="Check the registration's target_tenant_id stamp.",
            )
        return c, False

    if customer_choice == "attach_existing":
        try:
            c = await validate_customer_id_for_tenant(
                db, tenant.tenant_id, existing_customer_id
            )
        except CustomerNotFoundError as exc:
            raise ConversionError(
                stage="resolve_customer",
                message=str(exc),
                next_steps="Pick a different customer or create a new one.",
            )
        except CustomerTenantMismatchError as exc:
            raise ConversionError(
                stage="resolve_customer",
                message=str(exc),
                next_steps=(
                    "Conversion cannot attach a customer that belongs to "
                    "a different tenant. Re-check tenant_choice."
                ),
            )
        return c, False

    # customer_choice == "create_new"
    name = (registration.customer_name or "").strip()
    if not name:
        raise ConversionError(
            stage="resolve_customer",
            message="registration has no customer_name to create a Customer with",
            next_steps="Edit the registration to add a customer name first.",
        )
    c = Customer(
        tenant_id=tenant.tenant_id,
        name=name,
        billing_email=registration.billing_email or registration.submitter_email,
        billing_phone=registration.poc_phone or registration.submitter_phone,
        status="active",
        onboarding_status="in_progress",
    )
    db.add(c)
    await db.flush()
    return c, True


# ─────────────────────────────────────────────────────────────────────
# Site materialisation
# ─────────────────────────────────────────────────────────────────────

async def _materialize_sites(
    db: AsyncSession,
    registration: Registration,
    tenant: Tenant,
    customer: Customer,
) -> list[_ConvertedSite]:
    """Create one Site per registration_location row that hasn't been
    materialised yet.

    Idempotency: locations with materialized_site_id already set are
    skipped — we load the existing Site so the per-location response
    still carries useful data, but we mark was_created=False.
    """
    loc_result = await db.execute(
        select(RegistrationLocation)
        .where(RegistrationLocation.registration_id == registration.id)
        .order_by(RegistrationLocation.id.asc())
    )
    locations = list(loc_result.scalars().all())
    if not locations:
        raise ConversionError(
            stage="validate_prerequisites",
            message="registration has no locations to materialize",
            next_steps="Edit the registration to add at least one location.",
        )

    out: list[_ConvertedSite] = []
    for loc in locations:
        if loc.materialized_site_id:
            site = await db.get(Site, loc.materialized_site_id)
            if not site:
                raise ConversionError(
                    stage="create_site",
                    message=(
                        f"location {loc.id} is marked materialized to "
                        f"site id={loc.materialized_site_id} which no longer exists"
                    ),
                    details={"registration_location_id": loc.id},
                    next_steps=(
                        "Investigate the missing site before retrying — manual "
                        "cleanup may be required."
                    ),
                )
            out.append(_ConvertedSite(
                id=site.id,
                site_id=site.site_id,
                location_label=loc.location_label,
                registration_location_id=loc.id,
                was_created=False,
            ))
            continue

        base = _slugify(loc.location_label)
        site_id = await _next_available_site_id(db, base)
        site = Site(
            site_id=site_id,
            tenant_id=tenant.tenant_id,
            site_name=loc.location_label or site_id,
            customer_name=customer.name,
            customer_id=customer.id,
            status="Connected",
            e911_street=loc.street,
            e911_city=loc.city,
            e911_state=loc.state,
            e911_zip=loc.zip,
            notes=loc.access_notes,
            onboarding_status="active",
        )
        db.add(site)
        try:
            await db.flush()
        except IntegrityError as exc:
            # Race lost to a parallel writer.  Re-probe and retry once.
            await db.rollback()
            raise ConversionError(
                stage="create_site",
                message=(
                    f"site_id '{site_id}' collided during INSERT; another writer "
                    f"may have taken it concurrently"
                ),
                details={"registration_location_id": loc.id, "site_id": site_id},
                next_steps="Retry the conversion — the slug picker will skip the now-taken id.",
            ) from exc

        loc.materialized_site_id = site.id
        out.append(_ConvertedSite(
            id=site.id,
            site_id=site.site_id,
            location_label=loc.location_label,
            registration_location_id=loc.id,
            was_created=True,
        ))

    return out


# ─────────────────────────────────────────────────────────────────────
# Service unit materialisation
# ─────────────────────────────────────────────────────────────────────

async def _materialize_service_units(
    db: AsyncSession,
    registration: Registration,
    tenant: Tenant,
    converted_sites: list[_ConvertedSite],
) -> list[_ConvertedServiceUnit]:
    """Create one ServiceUnit per registration_service_unit row,
    naming each one ``{site_id}-U{NN}`` per site.
    """
    unit_result = await db.execute(
        select(RegistrationServiceUnit)
        .where(RegistrationServiceUnit.registration_id == registration.id)
        .order_by(RegistrationServiceUnit.id.asc())
    )
    reg_units = list(unit_result.scalars().all())
    if not reg_units:
        raise ConversionError(
            stage="validate_prerequisites",
            message="registration has no service units to materialize",
            next_steps="Edit the registration to add at least one service unit.",
        )

    sites_by_loc_id: dict[int, _ConvertedSite] = {
        s.registration_location_id: s for s in converted_sites
    }
    sequence_by_site: dict[str, int] = {}

    # Seed the per-site sequence from existing materialized units so a
    # retry-after-partial doesn't reuse the same NN suffix.
    for ru in reg_units:
        if ru.materialized_service_unit_id is None:
            continue
        site = sites_by_loc_id.get(ru.registration_location_id)
        if site is None:
            continue
        existing_unit = await db.get(ServiceUnit, ru.materialized_service_unit_id)
        if existing_unit:
            # Pull "NN" out of the unit_id suffix to anchor the next seq.
            match = re.match(r".*-U(\d{2,})$", existing_unit.unit_id or "")
            if match:
                used = int(match.group(1))
                sequence_by_site[site.site_id] = max(
                    sequence_by_site.get(site.site_id, 0), used
                )

    out: list[_ConvertedServiceUnit] = []
    for ru in reg_units:
        site = sites_by_loc_id.get(ru.registration_location_id)
        if site is None:
            # Defensive: should never happen because every unit must
            # point at a location and every location got materialized
            # in the previous step.
            raise ConversionError(
                stage="create_service_unit",
                message=(
                    f"service unit {ru.id} references location "
                    f"{ru.registration_location_id} which was not materialized"
                ),
                details={"registration_service_unit_id": ru.id},
                next_steps="Investigate the orphan unit before retrying.",
            )

        if ru.materialized_service_unit_id:
            existing_unit = await db.get(ServiceUnit, ru.materialized_service_unit_id)
            if not existing_unit:
                raise ConversionError(
                    stage="create_service_unit",
                    message=(
                        f"service unit {ru.id} is marked materialized to "
                        f"id={ru.materialized_service_unit_id} which no longer exists"
                    ),
                    details={"registration_service_unit_id": ru.id},
                    next_steps="Manual cleanup may be required before retrying.",
                )
            out.append(_ConvertedServiceUnit(
                id=existing_unit.id,
                unit_id=existing_unit.unit_id,
                unit_label=ru.unit_label,
                site_id=site.site_id,
                registration_service_unit_id=ru.id,
                was_created=False,
            ))
            continue

        next_seq = sequence_by_site.get(site.site_id, 0) + 1
        sequence_by_site[site.site_id] = next_seq
        unit_id = _unit_id(site.site_id, next_seq)

        unit = ServiceUnit(
            tenant_id=tenant.tenant_id,
            site_id=site.site_id,
            unit_id=unit_id,
            unit_name=ru.unit_label,
            unit_type=ru.unit_type or "other",
            install_type=ru.install_type,
            notes=ru.notes,
            status="pending_install",
        )
        db.add(unit)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise ConversionError(
                stage="create_service_unit",
                message=f"unit_id '{unit_id}' collided during INSERT",
                details={"registration_service_unit_id": ru.id, "unit_id": unit_id},
                next_steps="Retry the conversion — the sequence picker will skip the taken id.",
            ) from exc

        ru.materialized_service_unit_id = unit.id
        out.append(_ConvertedServiceUnit(
            id=unit.id,
            unit_id=unit.unit_id,
            unit_label=ru.unit_label,
            site_id=site.site_id,
            registration_service_unit_id=ru.id,
            was_created=True,
        ))

    return out


# ─────────────────────────────────────────────────────────────────────
# Subscription (optional)
# ─────────────────────────────────────────────────────────────────────

# Marker we use both as external_subscription_id and as the lookup key
# for idempotency.  Distinct enough from any real Zoho/QB id that it
# won't collide.
def _subscription_external_id(registration: Registration) -> str:
    return f"reg:{registration.registration_id}"


async def _maybe_create_subscription(
    db: AsyncSession,
    registration: Registration,
    tenant: Tenant,
    customer: Customer,
    *,
    create_subscription: bool,
) -> Optional[_ConvertedSubscription]:
    """Create a Subscription in 'pending' status — only when both the
    reviewer asked for it AND the registration has a plan code.

    No billing-side calls.  No charges.  No external integration.
    """
    if not create_subscription:
        return None
    plan = (registration.selected_plan_code or "").strip()
    if not plan:
        # Silently skip rather than error — the convert request can
        # legitimately set create_subscription=true even if no plan
        # was selected, and the reviewer hasn't been told to clear
        # the flag.
        return None

    ext_id = _subscription_external_id(registration)
    existing = await db.execute(
        select(Subscription).where(Subscription.external_subscription_id == ext_id)
    )
    sub = existing.scalar_one_or_none()
    if sub:
        return _ConvertedSubscription(
            id=sub.id,
            plan_name=sub.plan_name,
            status=sub.status,
            was_created=False,
        )

    qty = registration.plan_quantity_estimate or 0
    sub = Subscription(
        tenant_id=tenant.tenant_id,
        customer_id=customer.id,
        plan_name=plan,
        status="pending",
        qty_lines=qty,
        external_subscription_id=ext_id,
        external_source="registration",
    )
    db.add(sub)
    await db.flush()
    return _ConvertedSubscription(
        id=sub.id,
        plan_name=sub.plan_name,
        status=sub.status,
        was_created=True,
    )


# ─────────────────────────────────────────────────────────────────────
# Audit + status events
# ─────────────────────────────────────────────────────────────────────

def _audit(
    db: AsyncSession,
    *,
    tenant_id: str,
    actor_email: Optional[str],
    action: str,
    target_type: str,
    target_id: Optional[str],
    summary: str,
    site_id: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Append one AuditLogEntry row.  Synchronous on the session;
    the conversion's single commit publishes everything atomically.
    """
    db.add(AuditLogEntry(
        entry_id=f"convert-{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        category="conversion",
        action=action,
        actor=actor_email,
        target_type=target_type,
        target_id=target_id,
        site_id=site_id,
        summary=summary,
        detail_json=json.dumps(detail) if detail else None,
    ))


def _status_event(
    db: AsyncSession,
    registration: Registration,
    *,
    note: str,
    actor_user_id: Optional[uuid.UUID],
    actor_email: Optional[str],
) -> None:
    """Append a registration_status_events row that does NOT change
    the registration's status — used purely to record the conversion
    phase progression in the audit timeline.
    """
    db.add(RegistrationStatusEvent(
        registration_id=registration.id,
        from_status=registration.status,
        to_status=registration.status,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        note=note,
    ))


# ─────────────────────────────────────────────────────────────────────
# Top-level orchestration
# ─────────────────────────────────────────────────────────────────────

async def convert_registration(
    db: AsyncSession,
    registration: Registration,
    *,
    tenant_choice: str,
    existing_tenant_id: Optional[str],
    new_tenant_id: Optional[str],
    new_tenant_name: Optional[str],
    customer_choice: str,
    existing_customer_id: Optional[int],
    create_subscription: bool,
    dry_run: bool,
    actor_user_id: Optional[uuid.UUID],
    actor_email: Optional[str],
) -> ConversionResult:
    """Execute the full conversion pipeline within a single transaction.

    On success (real run): commits all writes.
    On dry_run: rolls back so nothing persists; the returned payload
    still describes what would have happened.
    On any failure: rolls back; raises ConversionError so the API
    layer can return a structured 4xx response.
    """
    if not is_convertable(registration):
        raise ConversionError(
            stage="validate_prerequisites",
            message=f"registration in status '{registration.status}' cannot be converted",
            next_steps=(
                "Conversion is allowed from internal_review through "
                "ready_for_activation. Drafts, cancelled, and active "
                "registrations are out of scope."
            ),
        )

    try:
        tenant, tenant_created = await _resolve_tenant(
            db, registration,
            tenant_choice=tenant_choice,
            existing_tenant_id=existing_tenant_id,
            new_tenant_id=new_tenant_id,
            new_tenant_name=new_tenant_name,
        )
        customer, customer_created = await _resolve_customer(
            db, registration, tenant,
            customer_choice=customer_choice,
            existing_customer_id=existing_customer_id,
        )
        converted_sites = await _materialize_sites(db, registration, tenant, customer)
        converted_units = await _materialize_service_units(
            db, registration, tenant, converted_sites,
        )
        converted_sub = await _maybe_create_subscription(
            db, registration, tenant, customer,
            create_subscription=create_subscription,
        )

        # Stamp the registration linkage.
        registration.target_tenant_id = tenant.tenant_id
        registration.customer_id = customer.id
        if registration.approved_at is None:
            registration.approved_at = datetime.now(timezone.utc)

        # Status events — one per phase.  Status itself does NOT change.
        _status_event(
            db, registration,
            note=(
                f"convert: tenant resolved -> {tenant.tenant_id} "
                f"({'created' if tenant_created else 'attached'})"
            ),
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
        _status_event(
            db, registration,
            note=(
                f"convert: customer resolved -> id={customer.id} "
                f"({'created' if customer_created else 'attached'})"
            ),
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
        sites_summary = ", ".join(s.site_id for s in converted_sites if s.was_created) or "none new"
        _status_event(
            db, registration,
            note=f"convert: {len(converted_sites)} site(s); new: [{sites_summary}]",
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
        units_new = sum(1 for u in converted_units if u.was_created)
        _status_event(
            db, registration,
            note=f"convert: {len(converted_units)} service unit(s); new: {units_new}",
            actor_user_id=actor_user_id, actor_email=actor_email,
        )
        if converted_sub:
            _status_event(
                db, registration,
                note=(
                    f"convert: subscription id={converted_sub.id} "
                    f"({'created' if converted_sub.was_created else 'attached'})"
                ),
                actor_user_id=actor_user_id, actor_email=actor_email,
            )
        _status_event(
            db, registration,
            note=f"convert: complete (dry_run={dry_run})",
            actor_user_id=actor_user_id, actor_email=actor_email,
        )

        # Global audit-log summary row.
        _audit(
            db,
            tenant_id=tenant.tenant_id,
            actor_email=actor_email,
            action="convert_registration",
            target_type="registration",
            target_id=registration.registration_id,
            summary=(
                f"Converted {registration.registration_id} -> "
                f"tenant={tenant.tenant_id}, customer={customer.id}, "
                f"sites={len(converted_sites)}, units={len(converted_units)}, "
                f"subscription={converted_sub.id if converted_sub else 'none'}"
            ),
            detail=dict(
                registration_id=registration.registration_id,
                tenant_id=tenant.tenant_id,
                tenant_was_created=tenant_created,
                customer_id=customer.id,
                customer_was_created=customer_created,
                site_ids=[s.site_id for s in converted_sites],
                unit_ids=[u.unit_id for u in converted_units],
                subscription_id=converted_sub.id if converted_sub else None,
                dry_run=dry_run,
            ),
        )

        # Per-creation audit rows.  Skipped in dry_run since nothing
        # will persist anyway.
        if not dry_run:
            if tenant_created:
                _audit(
                    db, tenant_id=tenant.tenant_id, actor_email=actor_email,
                    action="create_tenant", target_type="tenant",
                    target_id=tenant.tenant_id,
                    summary=f"Tenant {tenant.tenant_id} created via registration convert",
                )
            if customer_created:
                _audit(
                    db, tenant_id=tenant.tenant_id, actor_email=actor_email,
                    action="create_customer", target_type="customer",
                    target_id=str(customer.id),
                    summary=f"Customer {customer.name} created via registration convert",
                )
            for s in converted_sites:
                if s.was_created:
                    _audit(
                        db, tenant_id=tenant.tenant_id, actor_email=actor_email,
                        action="create_site", target_type="site",
                        target_id=str(s.id), site_id=s.site_id,
                        summary=f"Site {s.site_id} created via registration convert",
                    )
            for u in converted_units:
                if u.was_created:
                    _audit(
                        db, tenant_id=tenant.tenant_id, actor_email=actor_email,
                        action="create_service_unit", target_type="service_unit",
                        target_id=str(u.id), site_id=u.site_id,
                        summary=f"Service unit {u.unit_id} created via registration convert",
                    )
            if converted_sub and converted_sub.was_created:
                _audit(
                    db, tenant_id=tenant.tenant_id, actor_email=actor_email,
                    action="create_subscription", target_type="subscription",
                    target_id=str(converted_sub.id),
                    summary=(
                        f"Pending subscription {converted_sub.id} "
                        f"({converted_sub.plan_name}) created via registration convert"
                    ),
                )

        # Commit or roll back as a single unit.
        if dry_run:
            await db.rollback()
            # Refresh the registration from the DB so any in-memory
            # mutations (target_tenant_id / customer_id / approved_at)
            # don't leak into the caller's view.
            await db.refresh(registration)
            # Null the ids on the dataclasses so the response can't
            # be confused with a real run.
            tenant_out = _ConvertedTenant(
                tenant_id=tenant.tenant_id, name=tenant.name, was_created=tenant_created,
            )
            customer_out = _ConvertedCustomer(
                id=None, name=customer.name, tenant_id=tenant.tenant_id, was_created=customer_created,
            )
            sites_out = [
                _ConvertedSite(
                    id=None, site_id=s.site_id, location_label=s.location_label,
                    registration_location_id=s.registration_location_id,
                    was_created=s.was_created,
                )
                for s in converted_sites
            ]
            units_out = [
                _ConvertedServiceUnit(
                    id=None, unit_id=u.unit_id, unit_label=u.unit_label,
                    site_id=u.site_id,
                    registration_service_unit_id=u.registration_service_unit_id,
                    was_created=u.was_created,
                )
                for u in converted_units
            ]
            sub_out = None
            if converted_sub:
                sub_out = _ConvertedSubscription(
                    id=None, plan_name=converted_sub.plan_name,
                    status=converted_sub.status, was_created=converted_sub.was_created,
                )
            return ConversionResult(
                registration=registration, dry_run=True,
                tenant=tenant_out, customer=customer_out,
                sites=sites_out, service_units=units_out, subscription=sub_out,
            )

        await db.commit()
        await db.refresh(registration)
        logger.info(
            "Registration %s converted: tenant=%s customer_id=%s sites=%d units=%d sub=%s",
            registration.registration_id, tenant.tenant_id, customer.id,
            len(converted_sites), len(converted_units),
            converted_sub.id if converted_sub else None,
        )

        return ConversionResult(
            registration=registration, dry_run=False,
            tenant=_ConvertedTenant(
                tenant_id=tenant.tenant_id, name=tenant.name, was_created=tenant_created,
            ),
            customer=_ConvertedCustomer(
                id=customer.id, name=customer.name, tenant_id=tenant.tenant_id,
                was_created=customer_created,
            ),
            sites=converted_sites,
            service_units=converted_units,
            subscription=converted_sub,
        )

    except ConversionError as ce:
        # Roll back any partial writes so the staging row stays clean.
        await db.rollback()
        # Best-effort failure breadcrumb on the timeline + audit log.
        # Wrapped in its own try/except — if even THAT fails, we don't
        # want to mask the original conversion error.
        try:
            await db.refresh(registration)
            tenant_id_for_audit = registration.target_tenant_id or registration.tenant_id
            _status_event(
                db, registration,
                note=f"convert FAILED at stage={ce.stage}: {ce.message}",
                actor_user_id=actor_user_id, actor_email=actor_email,
            )
            _audit(
                db, tenant_id=tenant_id_for_audit, actor_email=actor_email,
                action="convert_registration_failed",
                target_type="registration",
                target_id=registration.registration_id,
                summary=f"Convert failed at {ce.stage}: {ce.message}",
                detail=dict(stage=ce.stage, message=ce.message, next_steps=ce.next_steps),
            )
            await db.commit()
        except Exception:
            logger.exception(
                "Failed to record convert-failure breadcrumb for %s",
                registration.registration_id,
            )
            await db.rollback()
        raise

    except Exception:
        # Any other exception is unexpected — log it, roll back, and
        # let FastAPI turn it into a 500.
        await db.rollback()
        logger.exception(
            "Unexpected error converting registration %s",
            registration.registration_id,
        )
        raise
