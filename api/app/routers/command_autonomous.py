"""Command Autonomous Router — autonomous operations, engine trigger, digests.

Endpoints:
  POST /autonomous/run              Trigger autonomous engine cycle
  GET  /autonomous/summary          Autonomous operations dashboard
  GET  /autonomous/actions          List autonomous action log
  POST /autonomous/self-heal        Trigger self-healing scan
  GET  /digests                     List operational digests
  POST /digests/generate            Generate a new digest
  GET  /digests/{digest_id}         Get digest detail
"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from app.models.autonomous_action import AutonomousAction
from app.models.operational_digest import OperationalDigest
from app.services.autonomous_engine import run_autonomous_engine
from app.services.self_healing import attempt_self_healing
from app.services.digest_engine import generate_daily_digest, generate_weekly_digest
from app.schemas.command_phase8 import (
    AutonomousActionOut,
    OperationalDigestOut,
    GenerateDigestRequest,
    EngineRunResult,
    AutoOpsSummary,
)

router = APIRouter()


# ── Engine Trigger ──────────────────────────────────────────────────

@router.post("/autonomous/run", response_model=EngineRunResult)
async def trigger_engine(
    user=Depends(require_permission("COMMAND_RUN_ENGINE")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger one full cycle of the autonomous engine."""
    stats = await run_autonomous_engine(db, user.tenant_id)
    return EngineRunResult(**stats)


# ── Self-Healing ────────────────────────────────────────────────────

@router.post("/autonomous/self-heal")
async def trigger_self_heal(
    user=Depends(require_permission("COMMAND_MANAGE_AUTO_OPS")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger self-healing scan for auto-resolvable incidents."""
    result = await attempt_self_healing(db, user.tenant_id)
    await db.commit()
    return result


# ── Autonomous Actions Log ─────────────────────────────────────────

@router.get("/autonomous/actions", response_model=list[AutonomousActionOut])
async def list_autonomous_actions(
    user=Depends(require_permission("COMMAND_VIEW_AUTO_LOG")),
    db: AsyncSession = Depends(get_db),
    action_type: str | None = None,
    site_id: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
):

    q = select(AutonomousAction).where(
        AutonomousAction.tenant_id == user.tenant_id,
    ).order_by(AutonomousAction.created_at.desc())

    if action_type:
        q = q.where(AutonomousAction.action_type == action_type)
    if site_id:
        q = q.where(AutonomousAction.site_id == site_id)

    q = q.offset(offset).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows


# ── Autonomous Dashboard Summary ───────────────────────────────────

@router.get("/autonomous/summary", response_model=AutoOpsSummary)
async def autonomous_summary(
    user=Depends(require_permission("COMMAND_VIEW_AUTO_OPS")),
    db: AsyncSession = Depends(get_db),
):
    tid = user.tenant_id
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    total_24h = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tid,
            AutonomousAction.created_at >= since_24h,
        )
    )).scalar() or 0

    incidents_auto = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tid,
            AutonomousAction.action_type == "incident_created",
            AutonomousAction.created_at >= since_24h,
        )
    )).scalar() or 0

    diagnostics = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tid,
            AutonomousAction.action_type == "diagnostic_executed",
            AutonomousAction.created_at >= since_24h,
        )
    )).scalar() or 0

    heals_attempted = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tid,
            AutonomousAction.action_type.like("self_heal_%"),
            AutonomousAction.created_at >= since_24h,
        )
    )).scalar() or 0

    heals_resolved = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tid,
            AutonomousAction.action_type.like("self_heal_%"),
            AutonomousAction.result == "resolved",
            AutonomousAction.created_at >= since_24h,
        )
    )).scalar() or 0

    escalations = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tid,
            AutonomousAction.action_type == "escalations_processed",
            AutonomousAction.created_at >= since_24h,
        )
    )).scalar() or 0

    verifications = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tid,
            AutonomousAction.action_type == "verifications_scheduled",
            AutonomousAction.created_at >= since_24h,
        )
    )).scalar() or 0

    recent = (await db.execute(
        select(AutonomousAction).where(
            AutonomousAction.tenant_id == tid,
        ).order_by(AutonomousAction.created_at.desc()).limit(20)
    )).scalars().all()

    return AutoOpsSummary(
        total_actions_24h=total_24h,
        incidents_auto_created=incidents_auto,
        diagnostics_run=diagnostics,
        self_heals_attempted=heals_attempted,
        self_heals_resolved=heals_resolved,
        escalations_triggered=escalations,
        verifications_scheduled=verifications,
        recent_actions=recent,
    )


# ── Operational Digests ─────────────────────────────────────────────

@router.get("/digests", response_model=list[OperationalDigestOut])
async def list_digests(
    user=Depends(require_permission("COMMAND_VIEW_DIGESTS")),
    db: AsyncSession = Depends(get_db),
    digest_type: str | None = None,
    limit: int = Query(20, le=100),
):

    q = select(OperationalDigest).where(
        OperationalDigest.tenant_id == user.tenant_id,
    ).order_by(OperationalDigest.created_at.desc())

    if digest_type:
        q = q.where(OperationalDigest.digest_type == digest_type)

    q = q.limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("/digests/generate", response_model=OperationalDigestOut)
async def generate_digest(
    body: GenerateDigestRequest,
    user=Depends(require_permission("COMMAND_GENERATE_DIGEST")),
    db: AsyncSession = Depends(get_db),
):

    if body.digest_type == "weekly":
        digest = await generate_weekly_digest(db, user.tenant_id)
    else:
        digest = await generate_daily_digest(db, user.tenant_id)

    return digest


@router.get("/digests/{digest_pk}", response_model=OperationalDigestOut)
async def get_digest(
    digest_pk: int,
    user=Depends(require_permission("COMMAND_VIEW_DIGESTS")),
    db: AsyncSession = Depends(get_db),
):

    digest = (await db.execute(
        select(OperationalDigest).where(
            OperationalDigest.id == digest_pk,
            OperationalDigest.tenant_id == user.tenant_id,
        )
    )).scalar_one_or_none()
    if not digest:
        raise HTTPException(404, "Digest not found")
    return digest
