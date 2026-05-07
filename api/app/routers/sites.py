import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_current_user,
    get_db,
    maybe_log_default_tenant_create,
    require_permission,
)
from app.models.audit_log_entry import AuditLogEntry
from app.models.device import Device
from app.models.incident import Incident
from app.models.line import Line
from app.models.sim import Sim
from app.models.site import Site
from app.models.user import User
from app.routers.helpers import apply_sort
from app.schemas.site import SiteCreate, SiteOut, SiteUpdate
from app.services.continuity import (
    compute_device_computed_status,
    compute_site_computed_status,
)
from app.services.health_scoring import compute_device_health, compute_site_health
from app.services.geocoding import geocode_address, has_valid_coords
from app.services.site_customer_resolution import (
    CustomerNotFoundError,
    CustomerTenantMismatchError,
    resolve_customer_for_site,
    validate_customer_id_for_tenant,
)

# TEMP: persistence-path debug logger.  Remove these log lines once
# building_type / address_notes save behavior is confirmed in prod.
logger = logging.getLogger("true911.sites")

router = APIRouter()

# Site fields DataEntry / Import Operator may correct after import.
# customer_name is intentionally excluded — it is a denormalized string and
# changing it would corrupt the implicit site → customer linkage.
# Monitoring / heartbeat / health / firmware / lat-lng / status fields and
# all NG911 / address-source / reconciliation / template_id fields remain
# Admin-only.
_DATAENTRY_ALLOWED_FIELDS = frozenset({
    "site_name",
    "e911_street",
    "e911_city",
    "e911_state",
    "e911_zip",
    "address_notes",
    "notes",
    "poc_name",
    "poc_phone",
    "poc_email",
    "kit_type",
    "endpoint_type",
    "service_class",
    "building_type",
})


async def _site_out(site: Site, db: AsyncSession) -> SiteOut:
    """Build SiteOut with computed_status derived from its devices."""
    out = SiteOut.model_validate(site)
    result = await db.execute(
        select(Device).where(
            Device.site_id == site.site_id,
            Device.tenant_id == site.tenant_id,
        )
    )
    devices = result.scalars().all()
    device_statuses = [
        compute_device_computed_status(d.last_heartbeat, d.heartbeat_interval)
        for d in devices
    ]
    out.computed_status = compute_site_computed_status(device_statuses)
    return out


@router.get(
    "",
    response_model=list[SiteOut],
    dependencies=[Depends(require_permission("VIEW_SITES"))],
)
async def list_sites(
    sort: str | None = Query("-last_checkin"),
    limit: int = Query(500, le=1000),
    site_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    carrier: str | None = None,
    kit_type: str | None = None,
    e911_state: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Site).where(Site.tenant_id == current_user.tenant_id)
    if site_id:
        q = q.where(Site.site_id == site_id)
    if status_filter:
        q = q.where(Site.status == status_filter)
    if carrier:
        q = q.where(Site.carrier == carrier)
    if kit_type:
        q = q.where(Site.kit_type == kit_type)
    if e911_state:
        q = q.where(Site.e911_state == e911_state)
    q = apply_sort(q, Site, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    sites = result.scalars().all()

    # Batch-load all devices for the tenant to avoid N+1 queries
    dev_result = await db.execute(
        select(Device).where(Device.tenant_id == current_user.tenant_id)
    )
    all_devices = dev_result.scalars().all()
    devices_by_site: dict[str, list[Device]] = {}
    for d in all_devices:
        if d.site_id:
            devices_by_site.setdefault(d.site_id, []).append(d)

    out = []
    for site in sites:
        site_out = SiteOut.model_validate(site)
        site_devices = devices_by_site.get(site.site_id, [])
        device_statuses = [
            compute_device_computed_status(d.last_heartbeat, d.heartbeat_interval)
            for d in site_devices
        ]
        site_out.computed_status = compute_site_computed_status(device_statuses)
        device_healths = [
            compute_device_health(
                last_heartbeat=d.last_heartbeat,
                heartbeat_interval=d.heartbeat_interval,
                network_status=d.network_status,
                last_network_event=d.last_network_event,
                device_status=d.status,
            )
            for d in site_devices
        ]
        site_out.health_status = compute_site_health(device_healths)
        out.append(site_out)
    return out


@router.get(
    "/count",
    dependencies=[Depends(require_permission("VIEW_SITES"))],
)
async def count_sites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return total site count for the current tenant.

    Used by the Sites page header so the count reflects all sites in the
    tenant, not just the rows loaded into the current page.
    """
    total = await db.scalar(
        select(func.count())
        .select_from(Site)
        .where(Site.tenant_id == current_user.tenant_id)
    )
    return {"total": int(total or 0)}


@router.post(
    "/bulk-geocode",
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
)
async def bulk_geocode(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Geocode all tenant sites that have address data but missing coordinates."""
    result = await db.execute(
        select(Site).where(Site.tenant_id == current_user.tenant_id)
    )
    all_sites = result.scalars().all()

    eligible = [
        s for s in all_sites
        if not has_valid_coords(s.lat, s.lng)
        and any([s.e911_street, s.e911_city, s.e911_state, s.e911_zip])
    ]

    geocoded = 0
    failed = 0
    skipped = len(all_sites) - len(eligible) - sum(
        1 for s in all_sites if has_valid_coords(s.lat, s.lng)
    )
    already_have_coords = sum(1 for s in all_sites if has_valid_coords(s.lat, s.lng))

    for site in eligible:
        coords = await geocode_address(
            site.e911_street, site.e911_city, site.e911_state, site.e911_zip
        )
        if coords:
            site.lat, site.lng = coords
            geocoded += 1
        else:
            failed += 1

    if geocoded > 0:
        await db.commit()

    return {
        "total_sites": len(all_sites),
        "already_geocoded": already_have_coords,
        "eligible": len(eligible),
        "geocoded": geocoded,
        "failed": failed,
        "no_address": len(all_sites) - already_have_coords - len(eligible),
    }


@router.post(
    "/fix-numeric-names",
    dependencies=[Depends(require_permission("VIEW_ADMIN"))],
)
async def fix_numeric_names(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fix sites whose site_name is a bare numeric ID.

    Replaces numeric names with customer_name if available and non-numeric,
    or e911 address + city as a readable fallback.
    """
    result = await db.execute(
        select(Site).where(Site.tenant_id == current_user.tenant_id)
    )
    all_sites = result.scalars().all()

    fixed = 0
    for site in all_sites:
        name = (site.site_name or "").strip()
        if not name:
            continue
        # Check if name looks numeric
        cleaned = name.replace("-", "").replace("_", "").replace(" ", "")
        if not cleaned.isdigit():
            continue

        # Try customer_name
        cust = (site.customer_name or "").strip()
        cust_cleaned = cust.replace("-", "").replace("_", "").replace(" ", "")
        if cust and not cust_cleaned.isdigit():
            site.site_name = cust
            fixed += 1
            continue

        # Try building a name from address
        parts = [p for p in [site.e911_street, site.e911_city, site.e911_state] if p and p.strip()]
        if parts:
            site.site_name = ", ".join(parts)
            fixed += 1
            continue

        # Try notes for any useful label
        if site.notes and len(site.notes) < 100:
            site.site_name = site.notes.strip()
            fixed += 1

    if fixed > 0:
        await db.commit()

    return {
        "total_sites": len(all_sites),
        "numeric_names_found": sum(
            1 for s in all_sites
            if (s.site_name or "").replace("-", "").replace("_", "").replace(" ", "").isdigit()
        ),
        "fixed": fixed,
    }


@router.get("/missing-coords", response_model=list[SiteOut])
async def list_missing_coords(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all tenant sites that lack valid lat/lng coordinates."""
    result = await db.execute(
        select(Site).where(Site.tenant_id == current_user.tenant_id)
    )
    all_sites = result.scalars().all()

    # Batch-load devices for computed_status
    dev_result = await db.execute(
        select(Device).where(Device.tenant_id == current_user.tenant_id)
    )
    all_devices = dev_result.scalars().all()
    devices_by_site: dict[str, list[Device]] = {}
    for d in all_devices:
        if d.site_id:
            devices_by_site.setdefault(d.site_id, []).append(d)

    out = []
    for site in all_sites:
        if has_valid_coords(site.lat, site.lng):
            continue
        site_out = SiteOut.model_validate(site)
        site_devices = devices_by_site.get(site.site_id, [])
        device_statuses = [
            compute_device_computed_status(d.last_heartbeat, d.heartbeat_interval)
            for d in site_devices
        ]
        site_out.computed_status = compute_site_computed_status(device_statuses)
        out.append(site_out)
    return out


@router.post(
    "/{site_pk}/geocode",
    response_model=SiteOut,
    dependencies=[Depends(require_permission("EDIT_SITES"))],
)
async def geocode_site(
    site_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Geocode a site from its E911 address.  Available to any role that
    can edit sites (Admin, Manager, DataEntry) so non-admin operators can
    fix locations on their own sites."""
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    if not any([site.e911_street, site.e911_city, site.e911_state, site.e911_zip]):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No E911 address on file",
        )

    coords = await geocode_address(
        site.e911_street, site.e911_city, site.e911_state, site.e911_zip
    )
    if not coords:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Geocoding failed — address could not be resolved",
        )

    site.lat, site.lng = coords
    await db.commit()
    await db.refresh(site)
    return await _site_out(site, db)


@router.get("/{site_pk}", response_model=SiteOut)
async def get_site(
    site_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return await _site_out(site, db)


@router.get("/{site_pk}/infrastructure")
async def get_site_infrastructure(
    site_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all devices, SIMs, and lines attached to a site."""
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    sid = site.site_id

    dev_result = await db.execute(
        select(Device).where(Device.site_id == sid).order_by(Device.created_at.desc())
    )
    devices = dev_result.scalars().all()

    sim_result = await db.execute(
        select(Sim).where(Sim.site_id == sid).order_by(Sim.created_at.desc())
    )
    sims = sim_result.scalars().all()

    line_result = await db.execute(
        select(Line).where(Line.site_id == sid).order_by(Line.created_at.desc())
    )
    lines = line_result.scalars().all()

    has_e911 = bool(site.e911_street and site.e911_city and site.e911_state and site.e911_zip)
    e911_warning = (len(devices) > 0 or len(sims) > 0) and not has_e911

    return {
        "site_id": sid,
        "site_name": site.site_name,
        "devices": [
            {"id": d.id, "device_id": d.device_id, "device_type": d.device_type, "model": d.model,
             "status": d.status, "serial_number": d.serial_number, "imei": d.imei, "carrier": d.carrier,
             "last_heartbeat": d.last_heartbeat.isoformat() if d.last_heartbeat else None}
            for d in devices
        ],
        "sims": [
            {"id": s.id, "iccid": s.iccid, "msisdn": s.msisdn, "carrier": s.carrier,
             "status": s.status, "plan": s.plan, "imsi": s.imsi}
            for s in sims
        ],
        "lines": [
            {"id": l.id, "line_id": l.line_id, "did": l.did, "provider": l.provider,
             "protocol": l.protocol, "status": l.status, "e911_status": l.e911_status}
            for l in lines
        ],
        "counts": {
            "devices": len(devices),
            "sims": len(sims),
            "lines": len(lines),
        },
        "e911": {
            "has_address": has_e911,
            "street": site.e911_street,
            "city": site.e911_city,
            "state": site.e911_state,
            "zip": site.e911_zip,
            "status": site.e911_status,
            "warning": e911_warning,
        },
    }


@router.post(
    "",
    response_model=SiteOut,
    status_code=201,
    dependencies=[Depends(require_permission("CREATE_SITES"))],
)
async def create_site(
    body: SiteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = body.model_dump()

    # Phase 3a dual-write: reconcile customer_id and customer_name before
    # constructing the Site.  Tenant equality is enforced at the API
    # layer in addition to the FK constraint.
    incoming_customer_id = payload.pop("customer_id", None)
    incoming_customer_name = payload.get("customer_name")

    if incoming_customer_id is not None:
        try:
            customer = await validate_customer_id_for_tenant(
                db, current_user.tenant_id, incoming_customer_id
            )
        except (CustomerNotFoundError, CustomerTenantMismatchError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        # If the client supplied both, they must agree.  Compare by id
        # rather than by string so trivial casing differences in the
        # cached name don't trigger a false reject.
        if incoming_customer_name:
            resolution = await resolve_customer_for_site(
                db, current_user.tenant_id, incoming_customer_name
            )
            if resolution.is_resolved and resolution.customer_id != customer.id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"customer_id={customer.id} does not match customer_name="
                    f"'{incoming_customer_name}' (resolves to id={resolution.customer_id})",
                )
        # Refresh the cached name to the canonical value.
        payload["customer_name"] = customer.name
        resolved_customer_id = customer.id
    elif incoming_customer_name:
        # Name-only path: best-effort resolution.  Unresolved names
        # leave customer_id NULL — preserving today's behavior.
        resolution = await resolve_customer_for_site(
            db, current_user.tenant_id, incoming_customer_name
        )
        resolved_customer_id = resolution.customer_id  # None unless RESOLVED
    else:
        # Neither field supplied — SiteCreate already requires
        # customer_name as a string, so this branch is unreachable
        # under normal use; defensive default keeps mypy happy.
        resolved_customer_id = None

    site = Site(
        **payload,
        customer_id=resolved_customer_id,
        tenant_id=current_user.tenant_id,
    )

    # Auto-geocode if E911 address fields were provided
    if any([site.e911_street, site.e911_city, site.e911_state, site.e911_zip]):
        coords = await geocode_address(
            site.e911_street, site.e911_city, site.e911_state, site.e911_zip
        )
        if coords:
            site.lat, site.lng = coords

    maybe_log_default_tenant_create(
        db, current_user,
        target_type="site",
        target_id=site.site_id,
        target_name=site.site_name,
    )

    db.add(site)
    await db.commit()
    await db.refresh(site)
    return await _site_out(site, db)


@router.patch(
    "/{site_pk}",
    response_model=SiteOut,
    dependencies=[Depends(require_permission("EDIT_SITES"))],
)
async def update_site(
    site_pk: int,
    body: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    updates = body.model_dump(exclude_unset=True)
    # TEMP: persistence-path debug — confirm building_type / address_notes
    # arrive at the route and survive role-stripping.  Remove once verified.
    logger.info(
        "PATCH /sites/%s incoming=%s",
        site_pk,
        list(updates.keys()),
    )

    if (current_user.role or "").lower() == "dataentry":
        restricted = {k for k in updates if k not in _DATAENTRY_ALLOWED_FIELDS}
        if restricted:
            db.add(AuditLogEntry(
                entry_id=f"field-block-{uuid.uuid4().hex[:12]}",
                tenant_id=current_user.tenant_id,
                category="security",
                action="restricted_field_edit_blocked",
                actor=current_user.email,
                target_type="site",
                target_id=str(site.id),
                site_id=site.site_id,
                summary=(
                    f"DataEntry {current_user.email} attempted to edit "
                    f"restricted site fields: {', '.join(sorted(restricted))}"
                ),
                detail_json=json.dumps({
                    "site_id": site.site_id,
                    "restricted_fields": sorted(restricted),
                    "allowed_fields": sorted(
                        k for k in updates if k in _DATAENTRY_ALLOWED_FIELDS
                    ),
                }),
            ))
            updates = {k: v for k, v in updates.items() if k in _DATAENTRY_ALLOWED_FIELDS}
        if not updates:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Your role does not allow editing the requested fields.",
            )

    # Validate lat/lng ranges if provided
    if "lat" in updates and updates["lat"] is not None:
        if not (-90 <= updates["lat"] <= 90):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Latitude must be between -90 and 90",
            )
    if "lng" in updates and updates["lng"] is not None:
        if not (-180 <= updates["lng"] <= 180):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Longitude must be between -180 and 180",
            )

    # Phase 3a dual-write: when the request changes customer_id and/or
    # customer_name, validate tenant membership and keep the cached
    # name in lockstep with the FK.  customer_id is intentionally not in
    # _DATAENTRY_ALLOWED_FIELDS, so this branch only runs for Admins.
    if "customer_id" in updates or "customer_name" in updates:
        new_id = updates.get("customer_id", site.customer_id)
        new_name = updates.get("customer_name", site.customer_name)

        if "customer_id" in updates and new_id is not None:
            try:
                customer = await validate_customer_id_for_tenant(
                    db, site.tenant_id, new_id
                )
            except (CustomerNotFoundError, CustomerTenantMismatchError) as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
            # Refresh the cached name.  If the request also supplied a
            # customer_name, it must match by id; the client doesn't get
            # to silently override the canonical name.
            if "customer_name" in updates:
                resolution = await resolve_customer_for_site(
                    db, site.tenant_id, new_name
                )
                if resolution.is_resolved and resolution.customer_id != customer.id:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"customer_id={customer.id} does not match customer_name="
                        f"'{new_name}' (resolves to id={resolution.customer_id})",
                    )
            updates["customer_name"] = customer.name
        elif "customer_name" in updates and new_name:
            # Name-only update.  Try to align the FK with the new name;
            # if the name doesn't resolve, leave customer_id alone (do
            # not silently clear an existing FK).
            resolution = await resolve_customer_for_site(
                db, site.tenant_id, new_name
            )
            if resolution.is_resolved:
                updates["customer_id"] = resolution.customer_id

    # TEMP: persistence-path debug — list of fields actually written to
    # the ORM instance after the role strip.  Remove once verified.
    logger.info(
        "PATCH /sites/%s applying=%s",
        site_pk,
        list(updates.keys()),
    )
    for field, value in updates.items():
        setattr(site, field, value)

    # Auto-geocode when:
    #   (a) the request changed an E911 address field, OR
    #   (b) coords are missing and an address is on file (backfill).
    # Geocoding failures never block the save — geocode_address returns
    # None on any error and the lat/lng simply stays unchanged.
    e911_fields = {"e911_street", "e911_city", "e911_state", "e911_zip"}
    address_changed = bool(e911_fields & body.model_fields_set)
    has_address_now = any([site.e911_street, site.e911_city, site.e911_state, site.e911_zip])
    coords_missing_now = not has_valid_coords(site.lat, site.lng)
    if address_changed or (coords_missing_now and has_address_now):
        coords = await geocode_address(
            site.e911_street, site.e911_city, site.e911_state, site.e911_zip
        )
        if coords:
            site.lat, site.lng = coords

    await db.commit()
    await db.refresh(site)
    return await _site_out(site, db)


@router.delete(
    "/{site_pk}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("DELETE_SITES"))],
)
async def delete_site(
    site_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a site. Admin only. Refuses if devices or open incidents reference it."""
    result = await db.execute(
        select(Site).where(Site.id == site_pk, Site.tenant_id == current_user.tenant_id)
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    # Guard: check for devices referencing this site
    dev_count = await db.scalar(
        select(func.count()).select_from(Device).where(
            Device.site_id == site.site_id,
            Device.tenant_id == current_user.tenant_id,
        )
    )
    if dev_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete site: {dev_count} device(s) still assigned. "
            "Decommission or reassign devices first.",
        )

    # Guard: check for open incidents referencing this site
    inc_count = await db.scalar(
        select(func.count()).select_from(Incident).where(
            Incident.site_id == site.site_id,
            Incident.tenant_id == current_user.tenant_id,
            Incident.status != "closed",
        )
    )
    if inc_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete site: {inc_count} open incident(s). "
            "Close all incidents first.",
        )

    await db.delete(site)
    await db.commit()
