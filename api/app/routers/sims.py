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
from app.schemas.sim import SimActionOut, SimAssign, SimCreate, SimOut, SimUpdate

logger = logging.getLogger("true911.sims")

router = APIRouter()

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

    for cs in carrier_sims:
        existing = existing_by_iccid.get(cs.iccid)
        if existing:
            if existing.tenant_id != tenant_id:
                skipped += 1
                errors.append(f"ICCID {cs.iccid} belongs to another tenant")
                continue
            changed = False
            if cs.msisdn and existing.msisdn != cs.msisdn:
                existing.msisdn = cs.msisdn
                changed = True
            if cs.status and existing.status != cs.status:
                existing.status = cs.status
                changed = True
            if cs.plan and existing.plan != cs.plan:
                existing.plan = cs.plan
                changed = True
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
                carrier=cs.carrier,
                status=cs.status,
                plan=cs.plan,
                apn=cs.apn,
                provider_sim_id=cs.external_id,
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

        for cs in carrier_sims:
            existing = existing_by_iccid.get(cs.iccid)
            if existing:
                if existing.tenant_id != tenant_id:
                    skipped += 1
                    continue
                changed = False
                if cs.msisdn and existing.msisdn != cs.msisdn:
                    existing.msisdn = cs.msisdn
                    changed = True
                if cs.status and existing.status != cs.status:
                    existing.status = cs.status
                    changed = True
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
                    carrier=cs.carrier,
                    status=cs.status,
                    plan=cs.plan,
                    apn=cs.apn,
                    provider_sim_id=cs.external_id,
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
