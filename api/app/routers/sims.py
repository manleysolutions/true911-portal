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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Sim).where(Sim.tenant_id == current_user.tenant_id)
    if carrier:
        q = q.where(Sim.carrier == carrier)
    if status_filter:
        q = q.where(Sim.status == status_filter)
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
# These are added in Phase 5 via sim_service — placeholder endpoints below

@router.post(
    "/{pk}/activate",
    response_model=SimActionOut,
    status_code=202,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def activate_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.sim_service import enqueue_sim_action
    return await enqueue_sim_action(db, pk, "activate", current_user)


@router.post(
    "/{pk}/suspend",
    response_model=SimActionOut,
    status_code=202,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def suspend_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.sim_service import enqueue_sim_action
    return await enqueue_sim_action(db, pk, "suspend", current_user)


@router.post(
    "/{pk}/resume",
    response_model=SimActionOut,
    status_code=202,
    dependencies=[Depends(require_permission("MANAGE_SIMS"))],
)
async def resume_sim(
    pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.sim_service import enqueue_sim_action
    return await enqueue_sim_action(db, pk, "resume", current_user)
