"""
True911 Command — Automation engine and staleness checker.

Evaluates automation rules against current system state and
computes device/site staleness from heartbeat data.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.device import Device
from ..models.site import Site
from ..models.incident import Incident
from ..models.verification_task import VerificationTask
from ..models.automation_rule import AutomationRule
from ..models.command_activity import CommandActivity
from ..models.notification import CommandNotification


# ---------------------------------------------------------------------------
# Staleness computation
# ---------------------------------------------------------------------------

def compute_device_staleness(device, now=None):
    """Determine if a device is stale based on its heartbeat interval and last heartbeat."""
    now = now or datetime.now(timezone.utc)
    last_hb = device.last_heartbeat
    interval = device.heartbeat_interval  # minutes

    if not last_hb:
        return {"stale": True, "minutes_overdue": None, "reason": "never_seen"}

    if not interval or interval <= 0:
        interval = 5  # default 5 min

    threshold = timedelta(minutes=interval * 3)  # 3x interval = stale
    elapsed = now - last_hb

    if elapsed > threshold:
        minutes_overdue = int(elapsed.total_seconds() / 60) - (interval * 3)
        return {
            "stale": True,
            "minutes_overdue": max(0, minutes_overdue),
            "minutes_since": int(elapsed.total_seconds() / 60),
            "reason": "heartbeat_overdue",
        }

    return {"stale": False, "minutes_since": int(elapsed.total_seconds() / 60)}


def compute_site_staleness(devices):
    """Compute site-level staleness from its devices."""
    now = datetime.now(timezone.utc)
    total = len(devices)
    stale_devices = []

    for d in devices:
        info = compute_device_staleness(d, now)
        if info["stale"]:
            stale_devices.append({
                "device_id": d.device_id,
                "status": d.status,
                **info,
            })

    return {
        "total_devices": total,
        "stale_count": len(stale_devices),
        "stale_devices": stale_devices,
        "has_stale_critical": any(
            d["status"] == "active" for d in stale_devices
        ),
    }


# ---------------------------------------------------------------------------
# Automation rule evaluator
# ---------------------------------------------------------------------------

TRIGGER_TYPES = [
    "heartbeat_missing",
    "readiness_below",
    "verification_overdue",
    "incident_unresolved",
    "all_verifications_complete",
]

ACTION_TYPES = [
    "create_incident",
    "notify",
    "update_site_status",
    "recalculate_readiness",
]


async def evaluate_rules(db: AsyncSession, tenant_id: str):
    """Evaluate all enabled automation rules for a tenant. Returns list of actions taken."""
    rules_q = await db.execute(
        select(AutomationRule)
        .where(AutomationRule.tenant_id == tenant_id, AutomationRule.enabled == True)  # noqa: E712
    )
    rules = list(rules_q.scalars().all())
    actions_taken = []
    now = datetime.now(timezone.utc)

    for rule in rules:
        try:
            condition = json.loads(rule.condition_json)
            config = json.loads(rule.action_config_json) if rule.action_config_json else {}
        except (json.JSONDecodeError, TypeError):
            continue

        fired = False

        if rule.trigger_type == "heartbeat_missing":
            fired = await _eval_heartbeat_missing(db, tenant_id, condition, config, rule, now)

        elif rule.trigger_type == "readiness_below":
            # Evaluated during readiness computation — flag only
            pass

        elif rule.trigger_type == "verification_overdue":
            fired = await _eval_verification_overdue(db, tenant_id, condition, config, rule, now)

        elif rule.trigger_type == "incident_unresolved":
            fired = await _eval_incident_unresolved(db, tenant_id, condition, config, rule, now)

        elif rule.trigger_type == "all_verifications_complete":
            fired = await _eval_all_verifications_complete(db, tenant_id, condition, config, rule, now)

        rule.last_evaluated_at = now
        if fired:
            rule.last_fired_at = now
            rule.fire_count = (rule.fire_count or 0) + 1
            actions_taken.append({"rule_id": rule.id, "rule_name": rule.name, "trigger": rule.trigger_type, "action": rule.action_type})

    return actions_taken


async def _eval_heartbeat_missing(db, tenant_id, condition, config, rule, now):
    """If any device heartbeat missing > threshold_minutes, create incident."""
    threshold = condition.get("threshold_minutes", 30)
    site_id = condition.get("site_id")  # optional filter

    q = select(Device).where(Device.tenant_id == tenant_id, Device.status == "active")
    if site_id:
        q = q.where(Device.site_id == site_id)
    result = await db.execute(q)
    devices = list(result.scalars().all())

    cutoff = now - timedelta(minutes=threshold)
    stale = [d for d in devices if not d.last_heartbeat or d.last_heartbeat < cutoff]

    if not stale:
        return False

    # Don't duplicate — check for recent auto incidents from this rule
    cooldown = now - timedelta(minutes=max(threshold, 60))
    existing_q = await db.execute(
        select(func.count()).select_from(Incident)
        .where(
            Incident.tenant_id == tenant_id,
            Incident.source == f"automation_rule_{rule.id}",
            Incident.opened_at > cooldown,
        )
    )
    if (existing_q.scalar() or 0) > 0:
        return False

    for d in stale[:5]:  # cap at 5 per evaluation
        incident_id = f"AUTO-{uuid.uuid4().hex[:10].upper()}"
        inc = Incident(
            incident_id=incident_id,
            tenant_id=tenant_id,
            site_id=d.site_id or "UNKNOWN",
            opened_at=now,
            severity=config.get("severity", "warning"),
            status="new",
            summary=f"[Auto] Heartbeat missing: {d.device_id} — last seen {_time_ago(d.last_heartbeat, now)}",
            incident_type="heartbeat_missing",
            source=f"automation_rule_{rule.id}",
            description=f"Rule '{rule.name}': Device {d.device_id} heartbeat overdue by >{threshold}min",
            created_by="system",
        )
        db.add(inc)

        db.add(CommandActivity(
            tenant_id=tenant_id,
            activity_type="incident_created",
            site_id=d.site_id,
            incident_id=incident_id,
            actor="system",
            summary=f"Auto-rule: Heartbeat missing for {d.device_id}",
            detail=f"Rule: {rule.name}",
        ))

    return True


async def _eval_verification_overdue(db, tenant_id, condition, config, rule, now):
    """If any verification task is overdue, create a notification."""
    overdue_q = await db.execute(
        select(VerificationTask)
        .where(
            VerificationTask.tenant_id == tenant_id,
            VerificationTask.status.in_(["pending", "in_progress"]),
            VerificationTask.due_date < now,
        )
        .limit(10)
    )
    overdue = list(overdue_q.scalars().all())
    if not overdue:
        return False

    # Cooldown: 1 notification per day per rule
    cooldown = now - timedelta(hours=24)
    existing_q = await db.execute(
        select(func.count()).select_from(CommandNotification)
        .where(
            CommandNotification.tenant_id == tenant_id,
            CommandNotification.title.contains(f"Rule: {rule.name}"),
            CommandNotification.created_at > cooldown,
        )
    )
    if (existing_q.scalar() or 0) > 0:
        return False

    db.add(CommandNotification(
        tenant_id=tenant_id,
        channel="in_app",
        severity="warning",
        title=f"{len(overdue)} overdue verification task(s)",
        body=f"Rule: {rule.name}. Sites affected: {', '.join(set(t.site_id for t in overdue[:5]))}",
        target_role=config.get("notify_role", "Admin"),
    ))

    return True


async def _eval_incident_unresolved(db, tenant_id, condition, config, rule, now):
    """If critical incident unresolved > threshold, notify."""
    threshold = condition.get("threshold_minutes", 120)
    severity = condition.get("severity", "critical")
    cutoff = now - timedelta(minutes=threshold)

    unresolved_q = await db.execute(
        select(func.count()).select_from(Incident)
        .where(
            Incident.tenant_id == tenant_id,
            Incident.severity == severity,
            Incident.status.in_(["new", "open", "acknowledged", "in_progress"]),
            Incident.opened_at < cutoff,
        )
    )
    count = unresolved_q.scalar() or 0
    if count == 0:
        return False

    cooldown = now - timedelta(hours=4)
    existing_q = await db.execute(
        select(func.count()).select_from(CommandNotification)
        .where(
            CommandNotification.tenant_id == tenant_id,
            CommandNotification.title.contains(f"Rule: {rule.name}"),
            CommandNotification.created_at > cooldown,
        )
    )
    if (existing_q.scalar() or 0) > 0:
        return False

    target = config.get("notify_target")
    db.add(CommandNotification(
        tenant_id=tenant_id,
        channel="in_app",
        severity=severity,
        title=f"{count} {severity} incident(s) unresolved >{threshold}min",
        body=f"Rule: {rule.name}. Escalation target: {target or 'default'}",
        target_role=config.get("notify_role"),
        target_user=target if target and "@" in target else None,
    ))

    return True


async def _eval_all_verifications_complete(db, tenant_id, condition, config, rule, now):
    """If all verification tasks for a site are complete, notify / update status."""
    site_id = condition.get("site_id")
    if not site_id:
        return False

    pending_q = await db.execute(
        select(func.count()).select_from(VerificationTask)
        .where(
            VerificationTask.tenant_id == tenant_id,
            VerificationTask.site_id == site_id,
            VerificationTask.status.in_(["pending", "in_progress"]),
        )
    )
    if (pending_q.scalar() or 0) > 0:
        return False

    total_q = await db.execute(
        select(func.count()).select_from(VerificationTask)
        .where(VerificationTask.tenant_id == tenant_id, VerificationTask.site_id == site_id)
    )
    if (total_q.scalar() or 0) == 0:
        return False

    db.add(CommandNotification(
        tenant_id=tenant_id,
        channel="in_app",
        severity="info",
        title=f"Site {site_id}: All verification tasks complete",
        body=f"Rule: {rule.name}. Site is verified and ready.",
        site_id=site_id,
    ))

    db.add(CommandActivity(
        tenant_id=tenant_id,
        activity_type="site_verified",
        site_id=site_id,
        actor="system",
        summary=f"All verification tasks completed for site {site_id}",
        detail=f"Automation rule: {rule.name}",
    ))

    return True


def _time_ago(dt, now):
    if not dt:
        return "never"
    diff = now - dt
    minutes = int(diff.total_seconds() / 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"
