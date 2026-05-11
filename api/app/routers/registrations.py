"""Internal authenticated registration review surface (Phase R3).

This router backs the operations queue at /api/registrations.  All
endpoints are authenticated and gated by either VIEW_REGISTRATIONS or
MANAGE_REGISTRATIONS.

Conversion of a registration into production rows (customers, sites,
service_units, users) is deliberately NOT part of this surface — the
CONVERT_REGISTRATIONS permission key exists in permissions.json but
no endpoint currently consumes it.  Conversion lands in Phase R4.

The internal queue is intentionally global: registrations live in the
"ops" tenant until conversion, so tenant-scoping the list would hide
every record from non-SuperAdmin reviewers.  Access is gated by RBAC
permissions, not tenancy.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.registration import Registration
from app.models.user import User
from app.schemas.registration import (
    ConvertedCustomerOut,
    ConvertedServiceUnitOut,
    ConvertedSiteOut,
    ConvertedSubscriptionOut,
    ConvertedTenantOut,
    RegistrationAdminUpdate,
    RegistrationCancelRequest,
    RegistrationConvertRequest,
    RegistrationConvertResponse,
    RegistrationCountByStatus,
    RegistrationDetailOut,
    RegistrationListItemOut,
    RegistrationLocationOut,
    RegistrationRequestInfoRequest,
    RegistrationServiceUnitOut,
    RegistrationStatusEventOut,
    RegistrationTransitionRequest,
)
from app.services import registration_conversion as reg_convert
from app.services import registration_service as reg_svc

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────

def _list_item(
    registration: Registration,
    *,
    locations_count: int,
    service_units_count: int,
    hardware_summary: Optional[str],
    carrier_summary: Optional[str],
) -> RegistrationListItemOut:
    base = RegistrationListItemOut.model_validate(registration)
    base.locations_count = locations_count
    base.service_units_count = service_units_count
    base.hardware_summary = hardware_summary
    base.carrier_summary = carrier_summary
    return base


async def _build_detail(
    db: AsyncSession, registration: Registration
) -> RegistrationDetailOut:
    """Assemble the full detail payload including locations, units,
    and the status timeline.
    """

    locations = list(await reg_svc.list_locations_for(db, registration.id))
    units = list(await reg_svc.list_service_units_for(db, registration.id))
    status_events = await reg_svc.list_status_events(db, registration.id)

    units_by_loc: dict[int, list] = {}
    for u in units:
        units_by_loc.setdefault(u.registration_location_id, []).append(u)

    locations_out: list[RegistrationLocationOut] = []
    for loc in locations:
        loc_out = RegistrationLocationOut.model_validate(loc)
        loc_out.service_units = [
            RegistrationServiceUnitOut.model_validate(u)
            for u in units_by_loc.get(loc.id, [])
        ]
        locations_out.append(loc_out)

    detail = RegistrationDetailOut.model_validate(registration)
    detail.locations = locations_out
    detail.reviewer_user_id = (
        str(registration.reviewer_user_id) if registration.reviewer_user_id else None
    )
    detail.status_events = [RegistrationStatusEventOut.model_validate(e) for e in status_events]
    return detail


# ─────────────────────────────────────────────────────────────────────
# List + count
# ─────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[RegistrationListItemOut],
    dependencies=[Depends(require_permission("VIEW_REGISTRATIONS"))],
)
async def list_registrations(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None, description="Match by reg id, customer name, or submitter email"),
    sort: str = Query("-created_at"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    rows = await reg_svc.list_registrations_admin(
        db, status_filter=status_filter, search=search, sort=sort, limit=limit,
    )
    if not rows:
        return []

    ids = [r.id for r in rows]
    counts = await reg_svc.get_child_counts(db, ids)
    summaries = await reg_svc.get_unit_summary(db, ids)

    out: list[RegistrationListItemOut] = []
    for r in rows:
        loc_count, unit_count = counts.get(r.id, (0, 0))
        hw, ca = summaries.get(r.id, (None, None))
        out.append(_list_item(
            r,
            locations_count=loc_count,
            service_units_count=unit_count,
            hardware_summary=hw,
            carrier_summary=ca,
        ))
    return out


@router.get(
    "/count",
    response_model=RegistrationCountByStatus,
    dependencies=[Depends(require_permission("VIEW_REGISTRATIONS"))],
)
async def count_registrations(db: AsyncSession = Depends(get_db)):
    by_status = await reg_svc.count_registrations_by_status(db)
    total = sum(by_status.values())
    return RegistrationCountByStatus(total=total, by_status=by_status)


# ─────────────────────────────────────────────────────────────────────
# Detail
# ─────────────────────────────────────────────────────────────────────

async def _require_registration(
    db: AsyncSession, registration_id: str
) -> Registration:
    """Resolve a registration by its public id or raise 404."""

    reg = await reg_svc.get_registration_by_public_id(db, registration_id)
    if not reg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registration not found")
    return reg


@router.get(
    "/{registration_id}",
    response_model=RegistrationDetailOut,
    dependencies=[Depends(require_permission("VIEW_REGISTRATIONS"))],
)
async def get_registration(
    registration_id: str,
    db: AsyncSession = Depends(get_db),
):
    reg = await _require_registration(db, registration_id)
    return await _build_detail(db, reg)


# ─────────────────────────────────────────────────────────────────────
# Mutations (MANAGE_REGISTRATIONS)
# ─────────────────────────────────────────────────────────────────────

@router.patch(
    "/{registration_id}",
    response_model=RegistrationDetailOut,
    dependencies=[Depends(require_permission("MANAGE_REGISTRATIONS"))],
)
async def update_registration(
    registration_id: str,
    body: RegistrationAdminUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Admin-side partial update.

    Only fields in the service module's _ADMIN_WRITABLE_FIELDS
    allow-list will be persisted.  Status changes go through
    /transition, not this endpoint.
    """

    reg = await _require_registration(db, registration_id)
    updates = body.model_dump(exclude_unset=True)
    await reg_svc.admin_update_registration(db, reg, updates)
    return await _build_detail(db, reg)


@router.post(
    "/{registration_id}/transition",
    response_model=RegistrationDetailOut,
    dependencies=[Depends(require_permission("MANAGE_REGISTRATIONS"))],
)
async def transition_registration(
    registration_id: str,
    body: RegistrationTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move a registration to a new status.

    The state machine in registration_service rejects illegal
    transitions with IllegalStatusTransitionError → 409.
    """

    reg = await _require_registration(db, registration_id)
    try:
        await reg_svc.transition_status(
            db,
            reg,
            to_status=body.to_status,
            actor_user_id=current_user.id,
            actor_email=current_user.email,
            note=body.note,
        )
    except reg_svc.IllegalStatusTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return await _build_detail(db, reg)


@router.post(
    "/{registration_id}/request-info",
    response_model=RegistrationDetailOut,
    dependencies=[Depends(require_permission("MANAGE_REGISTRATIONS"))],
)
async def request_more_info(
    registration_id: str,
    body: RegistrationRequestInfoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reg = await _require_registration(db, registration_id)
    try:
        await reg_svc.request_more_info(
            db,
            reg,
            message=body.message,
            actor_user_id=current_user.id,
            actor_email=current_user.email,
        )
    except reg_svc.IllegalStatusTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return await _build_detail(db, reg)


@router.post(
    "/{registration_id}/cancel",
    response_model=RegistrationDetailOut,
    dependencies=[Depends(require_permission("MANAGE_REGISTRATIONS"))],
)
async def cancel_registration(
    registration_id: str,
    body: RegistrationCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reg = await _require_registration(db, registration_id)
    try:
        await reg_svc.cancel_registration(
            db,
            reg,
            reason=body.reason,
            actor_user_id=current_user.id,
            actor_email=current_user.email,
        )
    except reg_svc.IllegalStatusTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return await _build_detail(db, reg)


# ─────────────────────────────────────────────────────────────────────
# Conversion (Phase R4)
# ─────────────────────────────────────────────────────────────────────

@router.post(
    "/{registration_id}/convert",
    response_model=RegistrationConvertResponse,
    dependencies=[Depends(require_permission("CONVERT_REGISTRATIONS"))],
)
async def convert_registration(
    registration_id: str,
    body: RegistrationConvertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Materialise a registration into production rows.

    Creates (per reviewer choice + idempotency stamps):
      - Tenant      (only when tenant_choice == "create_new")
      - Customer    (only when customer_choice == "create_new")
      - Sites       (one per registration_location)
      - ServiceUnits (one per registration_service_unit)
      - Subscription (only when create_subscription=true AND plan present)

    Does NOT create devices, SIMs, lines, or users.  Does NOT call any
    external integration (T-Mobile, Field Nation, billing, E911).

    The state machine is unchanged by convert — the reviewer's next
    explicit /transition call advances the workflow.
    """
    reg = await _require_registration(db, registration_id)

    try:
        result = await reg_convert.convert_registration(
            db,
            reg,
            tenant_choice=body.tenant_choice,
            existing_tenant_id=body.existing_tenant_id,
            new_tenant_id=body.new_tenant_id,
            new_tenant_name=body.new_tenant_name,
            customer_choice=body.customer_choice,
            existing_customer_id=body.existing_customer_id,
            create_subscription=body.create_subscription,
            dry_run=body.dry_run,
            actor_user_id=current_user.id,
            actor_email=current_user.email,
        )
    except reg_convert.ConversionError as exc:
        # Map each stage to the most appropriate HTTP status.  422 is
        # the default — these are validation / business-rule failures
        # the reviewer can correct and retry.
        if exc.stage == "validate_prerequisites":
            http_status = status.HTTP_409_CONFLICT
        elif exc.stage == "resolve_tenant" and "already taken" in exc.message:
            http_status = status.HTTP_409_CONFLICT
        else:
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(
            http_status,
            {
                "stage": exc.stage,
                "message": exc.message,
                "next_steps": exc.next_steps,
                "details": exc.details,
            },
        )

    # Reload the registration with children + timeline for the response.
    detail = await _build_detail(db, result.registration)

    return RegistrationConvertResponse(
        registration=detail,
        dry_run=result.dry_run,
        tenant=ConvertedTenantOut(
            tenant_id=result.tenant.tenant_id,
            name=result.tenant.name,
            was_created=result.tenant.was_created,
        ),
        customer=ConvertedCustomerOut(
            id=result.customer.id,
            name=result.customer.name,
            tenant_id=result.customer.tenant_id,
            was_created=result.customer.was_created,
        ),
        sites=[
            ConvertedSiteOut(
                id=s.id,
                site_id=s.site_id,
                location_label=s.location_label,
                registration_location_id=s.registration_location_id,
                was_created=s.was_created,
            )
            for s in result.sites
        ],
        service_units=[
            ConvertedServiceUnitOut(
                id=u.id,
                unit_id=u.unit_id,
                unit_label=u.unit_label,
                site_id=u.site_id,
                registration_service_unit_id=u.registration_service_unit_id,
                was_created=u.was_created,
            )
            for u in result.service_units
        ],
        subscription=(
            ConvertedSubscriptionOut(
                id=result.subscription.id,
                plan_name=result.subscription.plan_name,
                status=result.subscription.status,
                was_created=result.subscription.was_created,
            )
            if result.subscription else None
        ),
    )
