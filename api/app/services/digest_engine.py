"""Operational Digest Engine — generates daily and weekly operational summaries.

Daily digest includes:
  - Sites needing attention
  - Devices offline
  - Verification tasks due
  - Incidents opened/resolved
  - Autonomous actions taken

Weekly digest includes:
  - Portfolio readiness trends
  - Device health trends
  - Vendor response metrics
  - Week-over-week comparisons
"""

import json
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.site import Site
from app.models.device import Device
from app.models.incident import Incident
from app.models.verification_task import VerificationTask
from app.models.autonomous_action import AutonomousAction
from app.models.operational_digest import OperationalDigest


def _uid():
    return f"DG-{uuid.uuid4().hex[:12]}"


def _now():
    return datetime.now(timezone.utc)


async def generate_daily_digest(
    db: AsyncSession,
    tenant_id: str,
) -> OperationalDigest:
    """Generate a daily operational summary."""
    now = _now()
    period_start = now - timedelta(days=1)
    period_end = now

    # Sites needing attention
    sites = (await db.execute(
        select(Site).where(Site.tenant_id == tenant_id)
    )).scalars().all()

    sites_attention = [
        {"site_id": s.site_id, "name": s.site_name, "status": s.status}
        for s in sites if s.status != "Connected"
    ]

    # Devices offline
    devices = (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id)
    )).scalars().all()

    total_devices = len(devices)
    devices_offline = [
        {"device_id": d.device_id, "site_id": d.site_id, "status": d.status,
         "last_heartbeat": d.last_heartbeat.isoformat() if d.last_heartbeat else None}
        for d in devices if d.status in ("inactive", "decommissioned")
        or (d.last_heartbeat and (now - d.last_heartbeat).total_seconds() > (d.heartbeat_interval or 300) * 3)
    ]

    # Verification tasks due
    tasks_due = (await db.execute(
        select(func.count()).select_from(VerificationTask).where(
            VerificationTask.tenant_id == tenant_id,
            VerificationTask.status.in_(["pending", "in_progress"]),
            VerificationTask.due_date <= now + timedelta(days=7),
        )
    )).scalar() or 0

    tasks_overdue = (await db.execute(
        select(func.count()).select_from(VerificationTask).where(
            VerificationTask.tenant_id == tenant_id,
            VerificationTask.status.in_(["pending", "in_progress"]),
            VerificationTask.due_date < now,
        )
    )).scalar() or 0

    # Incidents opened/resolved in period
    incidents_opened = (await db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.opened_at >= period_start,
        )
    )).scalar() or 0

    incidents_resolved = (await db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.resolved_at >= period_start,
        )
    )).scalar() or 0

    incidents_open = (await db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.status.in_(["new", "open", "acked"]),
        )
    )).scalar() or 0

    # Autonomous actions in period
    auto_actions = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tenant_id,
            AutonomousAction.created_at >= period_start,
        )
    )).scalar() or 0

    summary = {
        "period": "daily",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "sites_total": len(sites),
        "sites_needing_attention": len(sites_attention),
        "sites_attention_list": sites_attention[:10],
        "devices_total": total_devices,
        "devices_offline": len(devices_offline),
        "devices_offline_list": devices_offline[:10],
        "verification_tasks_due": tasks_due,
        "verification_tasks_overdue": tasks_overdue,
        "incidents_opened": incidents_opened,
        "incidents_resolved": incidents_resolved,
        "incidents_currently_open": incidents_open,
        "autonomous_actions": auto_actions,
    }

    digest = OperationalDigest(
        digest_id=_uid(),
        tenant_id=tenant_id,
        digest_type="daily",
        period_start=period_start,
        period_end=period_end,
        summary_json=json.dumps(summary),
    )
    db.add(digest)
    await db.commit()
    await db.refresh(digest)
    return digest


async def generate_weekly_digest(
    db: AsyncSession,
    tenant_id: str,
) -> OperationalDigest:
    """Generate a weekly operational summary with trends."""
    now = _now()
    period_start = now - timedelta(days=7)
    period_end = now
    prev_start = period_start - timedelta(days=7)

    # Current week counts
    incidents_this_week = (await db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.opened_at >= period_start,
        )
    )).scalar() or 0

    resolved_this_week = (await db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.resolved_at >= period_start,
        )
    )).scalar() or 0

    # Previous week counts (for trends)
    incidents_prev_week = (await db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.opened_at >= prev_start,
            Incident.opened_at < period_start,
        )
    )).scalar() or 0

    resolved_prev_week = (await db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.resolved_at >= prev_start,
            Incident.resolved_at < period_start,
        )
    )).scalar() or 0

    # Device health
    devices = (await db.execute(
        select(Device).where(Device.tenant_id == tenant_id)
    )).scalars().all()
    active_devices = sum(1 for d in devices if d.status == "active")
    total_devices = len(devices)

    # Verification completion
    completed_this_week = (await db.execute(
        select(func.count()).select_from(VerificationTask).where(
            VerificationTask.tenant_id == tenant_id,
            VerificationTask.completed_at >= period_start,
        )
    )).scalar() or 0

    pending_tasks = (await db.execute(
        select(func.count()).select_from(VerificationTask).where(
            VerificationTask.tenant_id == tenant_id,
            VerificationTask.status.in_(["pending", "in_progress"]),
        )
    )).scalar() or 0

    # Autonomous operations
    auto_actions_week = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tenant_id,
            AutonomousAction.created_at >= period_start,
        )
    )).scalar() or 0

    auto_heals = (await db.execute(
        select(func.count()).select_from(AutonomousAction).where(
            AutonomousAction.tenant_id == tenant_id,
            AutonomousAction.action_type.like("self_heal_%"),
            AutonomousAction.result == "resolved",
            AutonomousAction.created_at >= period_start,
        )
    )).scalar() or 0

    # Trend calculations
    def trend(current, previous):
        if previous == 0:
            return "new" if current > 0 else "stable"
        change = ((current - previous) / previous) * 100
        if change > 10:
            return "increasing"
        if change < -10:
            return "decreasing"
        return "stable"

    summary = {
        "period": "weekly",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "incidents": {
            "opened": incidents_this_week,
            "resolved": resolved_this_week,
            "trend": trend(incidents_this_week, incidents_prev_week),
            "prev_opened": incidents_prev_week,
            "prev_resolved": resolved_prev_week,
        },
        "devices": {
            "total": total_devices,
            "active": active_devices,
            "health_pct": round((active_devices / total_devices * 100) if total_devices else 100, 1),
        },
        "verifications": {
            "completed": completed_this_week,
            "pending": pending_tasks,
        },
        "autonomous_ops": {
            "total_actions": auto_actions_week,
            "self_heals_resolved": auto_heals,
        },
    }

    digest = OperationalDigest(
        digest_id=_uid(),
        tenant_id=tenant_id,
        digest_type="weekly",
        period_start=period_start,
        period_end=period_end,
        summary_json=json.dumps(summary),
    )
    db.add(digest)
    await db.commit()
    await db.refresh(digest)
    return digest
