import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.device import Device
from app.models.device_sim import DeviceSim
from app.models.sim import Sim
from app.models.user import User
from app.routers.helpers import apply_sort
from app.models.site import Site
from app.schemas.sim import SimActionOut, SimAssign, SimBulkSiteAssign, SimCreate, SimManualAssign, SimOut, SimUpdate

logger = logging.getLogger("true911.sims")

router = APIRouter()

def _upsert_sim_from_carrier(sim: Sim, cs, now) -> bool:
    """Update a SIM record from carrier data. Returns True if any field changed."""
    changed = False
    for attr, val in [
        ("msisdn", cs.msisdn),
        ("imsi", cs.imsi),
        ("imei", cs.imei),
        ("status", cs.status),
        ("activation_status", cs.activation_status),
        ("network_status", cs.network_status),
        ("plan", cs.plan),
        ("apn", cs.apn),
        ("provider_sim_id", cs.external_id),
        ("carrier_label", cs.carrier_label),
        ("inferred_lat", cs.inferred_lat),
        ("inferred_lng", cs.inferred_lng),
        ("inferred_location_source", cs.inferred_location_source),
    ]:
        if val is not None and getattr(sim, attr) != val:
            setattr(sim, attr, val)
            changed = True
    sim.last_synced_at = now
    sim.data_source = "carrier_sync"
    return changed


_CONSTRAINT_MESSAGES = {
    "uq_sims_iccid": "A SIM with this ICCID already exists",
    "uq_sims_msisdn": "A SIM with this MSISDN already exists",
    "uq_sims_imsi": "A SIM with this IMSI already exists",
}


def _parse_sim_conflict(e: IntegrityError) -> str:
    msg = str(e.orig) if e.orig else str(e)
    for constraint, detail in _CONSTRAINT_MESSAGES.items():
        if constraint in msg:
            return detail
    return "Duplicate value: a SIM with one of these identifiers already exists"


# ── CRUD ──────────────────────────────────────────────────────────

@router.get("", response_model=list[SimOut])
async def list_sims(
    sort: str | None = Query("-created_at"),
    limit: int = Query(100, le=500),
    carrier: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    unassigned: bool | None = Query(None),
    assigned_to_site: str | None = Query(None, description="Filter by site_id"),
    has_site: bool | None = Query(None, description="true=assigned to any site, false=no site"),
    has_device: bool | None = Query(None, description="true=assigned to any device, false=no device"),
    data_source: str | None = Query(None, description="manual, carrier_sync, device_discovered, etc."),
    reconciliation: str | None = Query(None, description="unverified, partial, verified"),
    needs_review: bool | None = Query(None, description="true = orphaned/partial/unverified status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Sim).where(Sim.tenant_id == current_user.tenant_id)
    if carrier:
        q = q.where(Sim.carrier == carrier)
    if status_filter:
        q = q.where(Sim.status == status_filter)
    if unassigned:
        active_link = select(DeviceSim.sim_id).where(DeviceSim.active == True).subquery()
        q = q.where(~Sim.id.in_(select(active_link)))
    if assigned_to_site:
        q = q.where(Sim.site_id == assigned_to_site)
    if has_site is True:
        q = q.where(Sim.site_id.isnot(None))
    elif has_site is False:
        q = q.where(Sim.site_id.is_(None))
    if has_device is True:
        q = q.where(Sim.device_id.isnot(None))
    elif has_device is False:
        q = q.where(Sim.device_id.is_(None))
    if data_source:
        q = q.where(Sim.data_source == data_source)
    if reconciliation:
        q = q.where(Sim.reconciliation_status == reconciliation)
    if needs_review:
        from sqlalchemy import or_
        q = q.where(or_(
            Sim.status.in_(["orphaned", "error"]),
            Sim.reconciliation_status.in_(["unverified", "partial"]),
        ))
    q = apply_sort(q, Sim, sort)
    q = q.limit(limit)
    result = await db.execute(q)
    return [SimOut.model_validate(s) for s in result.scalars().all()]


@router.get("/{pk}", response_model=SimOut)
async def get_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Sim).where(Sim.id == pk, Sim.tenant_id == current_user.tenant_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SIM not found")
    return SimOut.model_validate(sim)


@router.post(
    "",
    response_model=SimOut,
    status_code=201,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def create_sim(
    body: SimCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sim = Sim(**body.model_dump(), tenant_id=current_user.tenant_id)
    db.add(sim)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_parse_sim_conflict(e))
    await db.commit()
    await db.refresh(sim)
    return SimOut.model_validate(sim)


@router.patch(
    "/{pk}",
    response_model=SimOut,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def update_sim(
    pk: int,
    body: SimUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Sim).where(Sim.id == pk, Sim.tenant_id == current_user.tenant_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SIM not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sim, field, value)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_parse_sim_conflict(e))
    await db.commit()
    await db.refresh(sim)
    return SimOut.model_validate(sim)


@router.delete(
    "/{pk}",
    response_model=SimOut,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def delete_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: sets status to 'terminated'."""
    result = await db.execute(
        select(Sim).where(Sim.id == pk, Sim.tenant_id == current_user.tenant_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SIM not found")
    sim.status = "terminated"
    await db.commit()
    await db.refresh(sim)
    return SimOut.model_validate(sim)


# ── Assign / Unassign ────────────────────────────────────────────

@router.post(
    "/{pk}/assign",
    response_model=SimActionOut,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def assign_sim(
    pk: int,
    body: SimAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Sim).where(Sim.id == pk, Sim.tenant_id == current_user.tenant_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SIM not found")

    # Verify device exists and belongs to same tenant
    dev_result = await db.execute(
        select(Device).where(Device.id == body.device_id, Device.tenant_id == current_user.tenant_id)
    )
    if not dev_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    assignment = DeviceSim(
        device_id=body.device_id,
        sim_id=pk,
        slot=body.slot,
        active=True,
        assigned_by=current_user.email,
    )
    db.add(assignment)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "SIM is already assigned or device slot is occupied",
        )
    await db.commit()
    return SimActionOut(sim_id=pk, action="assign", message=f"SIM assigned to device {body.device_id} slot {body.slot}")


@router.post(
    "/{pk}/unassign",
    response_model=SimActionOut,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def unassign_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Sim).where(Sim.id == pk, Sim.tenant_id == current_user.tenant_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SIM not found")

    assign_result = await db.execute(
        select(DeviceSim).where(DeviceSim.sim_id == pk, DeviceSim.active == True)
    )
    assignment = assign_result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active assignment for this SIM")

    assignment.active = False
    assignment.unassigned_at = datetime.now(timezone.utc)
    await db.commit()
    return SimActionOut(sim_id=pk, action="unassign", message="SIM unassigned from device")


# ── Manual SIM Entry + Assign ──────────────────────────────────────

@router.post(
    "/assign-manual",
    response_model=SimOut,
    status_code=201,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def assign_manual_sim(
    body: SimManualAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create (or find) a SIM by MSISDN and assign it to a device in one call.

    For SIMs not in inventory (e.g. existing T-Mobile SIMs on PR12 devices).
    If a SIM with the same MSISDN already exists, reuses it. If ICCID is
    provided and matches, reuses that. Otherwise creates a new SIM record.
    """
    msisdn = body.msisdn.strip()
    if not msisdn:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MSISDN is required")

    tenant_id = current_user.tenant_id

    # Verify device exists
    dev_result = await db.execute(
        select(Device).where(Device.id == body.device_id, Device.tenant_id == tenant_id)
    )
    device = dev_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    # Try to find existing SIM by MSISDN
    sim = None
    existing_q = select(Sim).where(Sim.tenant_id == tenant_id, Sim.msisdn == msisdn).limit(1)
    existing_result = await db.execute(existing_q)
    sim = existing_result.scalar_one_or_none()

    # Also try by ICCID if provided
    if not sim and body.iccid:
        iccid_q = select(Sim).where(Sim.tenant_id == tenant_id, Sim.iccid == body.iccid.strip()).limit(1)
        iccid_result = await db.execute(iccid_q)
        sim = iccid_result.scalar_one_or_none()

    if sim:
        # Update fields if new info provided
        if body.iccid and not sim.iccid.startswith("MANUAL-"):
            pass  # keep real ICCID
        elif body.iccid:
            sim.iccid = body.iccid.strip()
        if not sim.msisdn:
            sim.msisdn = msisdn
        if body.carrier and body.carrier != "Unknown":
            sim.carrier = body.carrier
        logger.info("Reusing existing SIM %d (iccid=%s) for manual assign", sim.id, sim.iccid)
    else:
        # Create new SIM — generate placeholder ICCID if not provided
        iccid = body.iccid.strip() if body.iccid else f"MANUAL-{msisdn}"
        # Determine reconciliation status based on completeness
        has_iccid = bool(body.iccid and body.iccid.strip())
        has_carrier = bool(body.carrier and body.carrier != "Unknown")
        recon = "verified" if (has_iccid and has_carrier) else "partial" if has_carrier else "unverified"
        sim = Sim(
            tenant_id=tenant_id,
            iccid=iccid,
            msisdn=msisdn,
            carrier=body.carrier or "Unknown",
            status="active",
            data_source="manual",
            reconciliation_status=recon,
            last_seen_at=datetime.now(timezone.utc),
            notes=body.notes or f"Manual entry for device {device.device_id}",
        )
        db.add(sim)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # ICCID collision — try fetching by the generated ICCID
            retry = await db.execute(
                select(Sim).where(Sim.iccid == iccid, Sim.tenant_id == tenant_id).limit(1)
            )
            sim = retry.scalar_one_or_none()
            if not sim:
                raise HTTPException(status.HTTP_409_CONFLICT, "SIM with this ICCID or MSISDN already exists")

    # Assign to device
    assignment = DeviceSim(
        device_id=body.device_id,
        sim_id=sim.id,
        slot=body.slot,
        active=True,
        assigned_by=current_user.email,
    )
    db.add(assignment)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "SIM is already assigned or device slot is occupied",
        )

    # Also update device-level MSISDN for convenience
    if not device.msisdn or device.msisdn != msisdn:
        device.msisdn = msisdn

    await db.commit()
    await db.refresh(sim)

    logger.info(
        "Manual SIM assign: sim=%d iccid=%s msisdn=%s -> device=%d (%s) by %s",
        sim.id, sim.iccid, msisdn, device.id, device.device_id, current_user.email,
    )
    return SimOut.model_validate(sim)


# ── Async Actions (activate / suspend / resume) ──────────────────
#
# When carrier write operations are not enabled (the default in production),
# these endpoints update the SIM status directly in the database without
# creating jobs or touching the carrier API.  When carrier ops are enabled
# and a Redis worker is running, they enqueue an async job instead.

# Status that each action transitions TO
_ACTION_TARGET_STATUS = {"activate": "active", "suspend": "suspended", "resume": "active"}
# Statuses from which each action is allowed
_ACTION_VALID_FROM = {
    "activate": ("inventory", "suspended"),
    "suspend":  ("active",),
    "resume":   ("suspended",),
}


async def _direct_sim_action(
    db: AsyncSession,
    pk: int,
    action: str,
    current_user: "User",
) -> SimActionOut:
    """Update SIM status directly — no job queue, no carrier API call."""
    result = await db.execute(
        select(Sim).where(Sim.id == pk, Sim.tenant_id == current_user.tenant_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SIM not found")

    valid_from = _ACTION_VALID_FROM.get(action, ())
    if sim.status not in valid_from:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot {action} SIM in status '{sim.status}' "
            f"(allowed from: {', '.join(valid_from)})",
        )

    new_status = _ACTION_TARGET_STATUS[action]
    sim.status = new_status
    await db.commit()
    await db.refresh(sim)

    logger.info("SIM %s %s: %s -> %s (direct, no carrier API)", pk, action, valid_from, new_status)
    return SimActionOut(
        sim_id=pk,
        action=action,
        message=f"SIM status updated to '{new_status}' (local database only)",
    )


def _carrier_write_enabled() -> bool:
    """Check if carrier write operations are enabled via env var."""
    import os
    return os.environ.get("FEATURE_CARRIER_WRITE_OPS", "").lower() == "true"


@router.post(
    "/{pk}/activate",
    response_model=SimActionOut,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def activate_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if _carrier_write_enabled():
        from app.services.sim_service import enqueue_sim_action
        return await enqueue_sim_action(db, pk, "activate", current_user)
    return await _direct_sim_action(db, pk, "activate", current_user)


@router.post(
    "/{pk}/suspend",
    response_model=SimActionOut,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def suspend_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if _carrier_write_enabled():
        from app.services.sim_service import enqueue_sim_action
        return await enqueue_sim_action(db, pk, "suspend", current_user)
    return await _direct_sim_action(db, pk, "suspend", current_user)


@router.post(
    "/{pk}/resume",
    response_model=SimActionOut,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def resume_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if _carrier_write_enabled():
        from app.services.sim_service import enqueue_sim_action
        return await enqueue_sim_action(db, pk, "resume", current_user)
    return await _direct_sim_action(db, pk, "resume", current_user)


# ── Bulk Site Assignment ──────────────────────────────────────────

@router.post(
    "/bulk-assign-site",
    response_model=dict,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def bulk_assign_sims_to_site(
    body: SimBulkSiteAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Assign multiple SIMs to a site in one operation."""
    # Verify site exists and is accessible
    site_q = select(Site).where(Site.site_id == body.site_id)
    if current_user.role != "SuperAdmin":
        site_q = site_q.where(Site.tenant_id == current_user.tenant_id)
    site_result = await db.execute(site_q)
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    # Fetch SIMs
    sim_result = await db.execute(
        select(Sim).where(Sim.id.in_(body.sim_ids))
    )
    sims = sim_result.scalars().all()

    # Tenant check for non-SuperAdmin
    assigned = 0
    skipped = 0
    for sim in sims:
        if current_user.role != "SuperAdmin" and sim.tenant_id != current_user.tenant_id:
            skipped += 1
            continue
        sim.site_id = body.site_id
        # Align tenant_id with the site if currently different
        if sim.tenant_id != site.tenant_id:
            sim.tenant_id = site.tenant_id
        assigned += 1

    await db.commit()
    logger.info(
        "Bulk SIM site assign: %d assigned, %d skipped, site=%s, user=%s",
        assigned, skipped, body.site_id, current_user.email,
    )
    return {"assigned": assigned, "skipped": skipped, "site_id": body.site_id}


# ── Carrier Sync ─────────────────────────────────────────────────

from pydantic import BaseModel


class SyncResultOut(BaseModel):
    carrier: str
    created: int
    updated: int
    unchanged: int
    skipped: int
    failed: int
    errors: list[str]
    total: int


@router.post(
    "/sync/{carrier}",
    response_model=SyncResultOut,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def sync_carrier(
    carrier: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync SIM inventory from a specific carrier provider."""
    from app.services.carrier_provider import get_provider
    from app.services.carrier_provider.base import CarrierProviderError

    try:
        provider = get_provider(carrier)
    except KeyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown carrier: {carrier}")

    if not provider.is_configured:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{carrier} carrier API is not configured. Use manual SIM entry.",
        )

    try:
        carrier_sims = await provider.fetch_sims()
    except CarrierProviderError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))

    tenant_id = current_user.tenant_id

    # Upsert logic
    incoming_iccids = {s.iccid for s in carrier_sims}
    existing_result = await db.execute(
        select(Sim).where(Sim.iccid.in_(incoming_iccids))
    )
    existing_by_iccid = {s.iccid: s for s in existing_result.scalars().all()}

    created = updated = unchanged = skipped = 0
    errors: list[str] = []

    now = datetime.now(timezone.utc)
    for cs in carrier_sims:
        existing = existing_by_iccid.get(cs.iccid)
        if existing:
            if existing.tenant_id != tenant_id:
                skipped += 1
                errors.append(f"ICCID {cs.iccid} belongs to another tenant")
                continue
            changed = _upsert_sim_from_carrier(existing, cs, now)
            if changed:
                updated += 1
            else:
                unchanged += 1
        else:
            new_sim = Sim(
                tenant_id=tenant_id,
                iccid=cs.iccid,
                msisdn=cs.msisdn,
                imsi=cs.imsi,
                imei=cs.imei,
                carrier=cs.carrier,
                status=cs.status,
                activation_status=cs.activation_status,
                network_status=cs.network_status,
                plan=cs.plan,
                apn=cs.apn,
                provider_sim_id=cs.external_id,
                carrier_label=cs.carrier_label,
                data_source="carrier_sync",
                last_synced_at=now,
                inferred_lat=cs.inferred_lat,
                inferred_lng=cs.inferred_lng,
                inferred_location_source=cs.inferred_location_source,
                meta={"raw_payload": cs.raw} if cs.raw else None,
            )
            db.add(new_sim)
            created += 1

    await db.commit()
    logger.info(
        "SIM sync %s: tenant=%s created=%d updated=%d unchanged=%d skipped=%d",
        carrier, tenant_id, created, updated, unchanged, skipped,
    )
    return SyncResultOut(
        carrier=carrier,
        created=created,
        updated=updated,
        unchanged=unchanged,
        skipped=skipped,
        failed=0,
        errors=errors,
        total=created + updated + unchanged + skipped,
    )


@router.post(
    "/sync-all",
    response_model=list[SyncResultOut],
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def sync_all_carriers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync SIM inventory from all configured carrier providers."""
    from app.services.carrier_provider import PROVIDERS, get_provider
    from app.services.carrier_provider.base import CarrierProviderError

    results = []
    for carrier_name, cls in PROVIDERS.items():
        provider = cls()
        if not provider.is_configured:
            results.append(SyncResultOut(
                carrier=carrier_name,
                created=0, updated=0, unchanged=0, skipped=0, failed=0,
                errors=[f"{carrier_name} is not configured — skipped"],
                total=0,
            ))
            continue

        try:
            carrier_sims = await provider.fetch_sims()
        except CarrierProviderError as e:
            results.append(SyncResultOut(
                carrier=carrier_name,
                created=0, updated=0, unchanged=0, skipped=0, failed=1,
                errors=[str(e)],
                total=0,
            ))
            continue

        tenant_id = current_user.tenant_id
        incoming_iccids = {s.iccid for s in carrier_sims}
        existing_result = await db.execute(
            select(Sim).where(Sim.iccid.in_(incoming_iccids))
        )
        existing_by_iccid = {s.iccid: s for s in existing_result.scalars().all()}

        created = updated = unchanged = skipped = 0
        errors: list[str] = []

        now = datetime.now(timezone.utc)
        for cs in carrier_sims:
            existing = existing_by_iccid.get(cs.iccid)
            if existing:
                if existing.tenant_id != tenant_id:
                    skipped += 1
                    continue
                changed = _upsert_sim_from_carrier(existing, cs, now)
                if changed:
                    updated += 1
                else:
                    unchanged += 1
            else:
                db.add(Sim(
                    tenant_id=tenant_id,
                    iccid=cs.iccid,
                    msisdn=cs.msisdn,
                    imsi=cs.imsi,
                    imei=cs.imei,
                    carrier=cs.carrier,
                    status=cs.status,
                    activation_status=cs.activation_status,
                    network_status=cs.network_status,
                    plan=cs.plan,
                    apn=cs.apn,
                    provider_sim_id=cs.external_id,
                    data_source="carrier_sync",
                    last_synced_at=now,
                    inferred_lat=cs.inferred_lat,
                    inferred_lng=cs.inferred_lng,
                    inferred_location_source=cs.inferred_location_source,
                    meta={"raw_payload": cs.raw} if cs.raw else None,
                ))
                created += 1

        await db.commit()
        results.append(SyncResultOut(
            carrier=carrier_name,
            created=created, updated=updated, unchanged=unchanged,
            skipped=skipped, failed=0, errors=errors,
            total=created + updated + unchanged + skipped,
        ))

    return results
