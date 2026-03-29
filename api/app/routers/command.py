"""
True911 Command — Phase 2 + Phase 3 + Phase 4 endpoints.

Site-centric command model, incident workflow, activity timeline,
readiness scoring, telemetry, escalation, automation rules,
staleness monitoring, verification-aware readiness, and digest.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..dependencies import get_db, get_current_user, require_permission
from ..models.site import Site
from ..models.device import Device
from ..models.incident import Incident
from ..models.command_activity import CommandActivity
from ..models.notification import CommandNotification
from ..models.escalation_rule import EscalationRule
from ..models.command_telemetry import CommandTelemetry
from ..models.verification_task import VerificationTask
from ..models.site_vendor import SiteVendorAssignment
from ..models.automation_rule import AutomationRule
from ..models.user import User
from ..schemas.command import (
    CommandIncidentTransition,
    CommandIncidentCreate,
    CommandActivityOut,
)
from ..schemas.command_phase3 import TelemetryIngest, TelemetryOut
from ..services.automation_engine import compute_site_staleness, evaluate_rules
from ..services.command_intelligence import compute_intelligence

router = APIRouter()


# ---------------------------------------------------------------------------
# Incident workflow state machine
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    "new":          ["acknowledged", "dismissed"],
    "open":         ["acknowledged", "dismissed"],      # legacy compat
    "acknowledged": ["in_progress", "dismissed"],
    "in_progress":  ["resolved"],
}

TRANSITION_PERMISSIONS = {
    "acknowledged": "COMMAND_ACK",
    "in_progress":  "COMMAND_ASSIGN",
    "resolved":     "COMMAND_RESOLVE",
    "dismissed":    "COMMAND_DISMISS",
}


def _system_category(kit_type: str, device_type: str = None) -> str:
    """Classify a site/device into a system category.

    Checks kit_type first, then device_type for finer classification.
    """
    kt = (kit_type or "").strip().lower()
    dt = (device_type or "").strip().lower()

    # Kit-type mapping (site-level)
    if kt in ("facp", "fire alarm", "fire"):
        return "fire_alarm"
    if "elevator" in kt or "elev" in kt:
        return "elevator_phone"
    if "call" in kt or "emergency call" in kt:
        return "call_station"
    if kt in ("das", "radio", "bda"):
        return "das_radio"
    if kt in ("scada", "backup", "power"):
        return "backup_power"

    # Device-type fallback
    if "fire" in dt or "facp" in dt or "alarm" in dt:
        return "fire_alarm"
    if "elevator" in dt or "elev" in dt or "phone" in dt:
        return "elevator_phone"
    if "call" in dt or "station" in dt:
        return "call_station"
    if "das" in dt or "radio" in dt or "bda" in dt:
        return "das_radio"

    if kt or dt:
        return "emergency_device"
    return "emergency_device"


SYSTEM_LABELS = {
    "fire_alarm": "Fire Alarm Communicators",
    "elevator_phone": "Elevator Emergency Phones",
    "das_radio": "Responder Radio / DAS",
    "call_station": "Emergency Call Stations",
    "backup_power": "Backup Power / Critical Systems",
    "emergency_device": "True911 Emergency Devices",
}


async def _log_activity(
    db: AsyncSession,
    tenant_id: str,
    activity_type: str,
    summary: str,
    *,
    site_id: str = None,
    incident_id: str = None,
    actor: str = None,
    detail: str = None,
    metadata: dict = None,
):
    """Insert a command activity record."""
    act = CommandActivity(
        tenant_id=tenant_id,
        activity_type=activity_type,
        site_id=site_id,
        incident_id=incident_id,
        actor=actor,
        summary=summary,
        detail=detail,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(act)


async def _create_notification(
    db: AsyncSession,
    tenant_id: str,
    title: str,
    *,
    body: str = None,
    severity: str = "info",
    incident_id: str = None,
    site_id: str = None,
    target_role: str = None,
    target_user: str = None,
    channel: str = "in_app",
):
    """Insert an in-app notification."""
    notif = CommandNotification(
        tenant_id=tenant_id,
        channel=channel,
        severity=severity,
        title=title,
        body=body,
        incident_id=incident_id,
        site_id=site_id,
        target_role=target_role,
        target_user=target_user,
    )
    db.add(notif)


async def _check_escalation(db: AsyncSession, inc: Incident):
    """Check if an incident should be escalated based on escalation rules."""
    if inc.status in ("resolved", "dismissed", "closed"):
        return

    now = datetime.now(timezone.utc)
    minutes_open = (now - inc.opened_at).total_seconds() / 60 if inc.opened_at else 0

    rules_q = await db.execute(
        select(EscalationRule)
        .where(
            EscalationRule.tenant_id == inc.tenant_id,
            EscalationRule.severity == inc.severity,
            EscalationRule.enabled == True,  # noqa: E712
        )
        .order_by(EscalationRule.escalate_after_minutes)
    )
    rules = list(rules_q.scalars().all())

    current_level = inc.escalation_level or 0
    for i, rule in enumerate(rules):
        level = i + 1
        if level <= current_level:
            continue
        if minutes_open >= rule.escalate_after_minutes and inc.status in ("new", "open"):
            inc.escalation_level = level
            inc.escalated_at = now
            await _create_notification(
                db, inc.tenant_id,
                f"Escalation L{level}: {inc.summary}",
                body=f"Incident {inc.incident_id} unacknowledged for {int(minutes_open)}min. Rule: {rule.name}",
                severity=inc.severity,
                incident_id=inc.incident_id,
                site_id=inc.site_id,
                target_role=rule.escalation_target if rule.escalation_target in ("Admin", "Manager") else None,
                target_user=rule.escalation_target if rule.escalation_target and "@" in rule.escalation_target else None,
            )
            await _log_activity(
                db, inc.tenant_id, "incident_escalated",
                f"Incident {inc.incident_id} escalated to level {level}",
                site_id=inc.site_id, incident_id=inc.incident_id,
                actor="system",
                detail=f"Rule: {rule.name}, after {rule.escalate_after_minutes}min",
            )
            break  # one escalation per check


def _serialize_incident(inc: Incident, site_name: str = None) -> dict:
    return {
        "id": inc.id,
        "incident_id": inc.incident_id,
        "site_id": inc.site_id,
        "site_name": site_name or inc.site_id,
        "summary": inc.summary,
        "severity": inc.severity,
        "status": inc.status,
        "incident_type": inc.incident_type,
        "source": inc.source,
        "description": inc.description,
        "location_detail": inc.location_detail,
        "opened_at": inc.opened_at.isoformat() if inc.opened_at else None,
        "ack_by": inc.ack_by,
        "ack_at": inc.ack_at.isoformat() if inc.ack_at else None,
        "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
        "closed_at": inc.closed_at.isoformat() if inc.closed_at else None,
        "assigned_to": inc.assigned_to,
        "resolution_notes": inc.resolution_notes,
        "recommended_actions_json": inc.recommended_actions_json,
        "escalation_level": inc.escalation_level or 0,
        "escalated_at": inc.escalated_at.isoformat() if inc.escalated_at else None,
    }


# ---------------------------------------------------------------------------
# Readiness scoring engine
# ---------------------------------------------------------------------------

def _compute_readiness(sites, devices, incidents, *, verification_tasks=None, stale_device_count=0, devices_by_site=None):
    """Compute readiness score with 7-factor weighted model (Phase 4).

    Only evaluates sites that have at least one device assigned.
    Imported-only sites (no devices) are excluded from readiness.
    """
    # Only count sites that have devices for readiness
    if devices_by_site:
        monitored_sites = [s for s in sites if s.site_id in devices_by_site]
    else:
        monitored_sites = sites
    total_sites = len(monitored_sites)
    active_devices = [d for d in devices if d.status == "active"]
    active_incidents = [i for i in incidents if i.status in ("new", "open", "acknowledged", "in_progress")]
    critical_incidents = [i for i in active_incidents if i.severity == "critical"]

    score = 100.0
    factors = []

    # Factor 1: Device health (25%)
    device_pct = (len(active_devices) / len(devices) * 100) if devices else 0
    if device_pct < 100:
        penalty = (100 - device_pct) * 0.25
        score -= penalty
        factors.append({
            "label": "Device health",
            "impact": round(-penalty, 1),
            "detail": f"{len(active_devices)}/{len(devices)} devices active",
        })

    # Factor 2: Open critical incidents (20%)
    if critical_incidents:
        penalty = min(len(critical_incidents) * 8, 20)
        score -= penalty
        factors.append({
            "label": "Critical incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(critical_incidents)} critical incident(s) open",
        })

    # Factor 3: Site connectivity (15%) — only monitored sites
    connected = sum(1 for s in monitored_sites if s.status == "Connected")
    conn_pct = (connected / total_sites * 100) if total_sites else 100
    if conn_pct < 100:
        penalty = (100 - conn_pct) * 0.15
        score -= penalty
        factors.append({
            "label": "Site connectivity",
            "impact": round(-penalty, 1),
            "detail": f"{connected}/{total_sites} sites connected",
        })

    # Factor 4: Unacknowledged incidents (10%)
    unacked = [i for i in active_incidents if i.status in ("new", "open")]
    if unacked:
        penalty = min(len(unacked) * 3, 10)
        score -= penalty
        factors.append({
            "label": "Unacknowledged incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(unacked)} incident(s) awaiting acknowledgment",
        })

    # Factor 5: Warning-level incidents (5%)
    warn_incidents = [i for i in active_incidents if i.severity == "warning"]
    if warn_incidents:
        penalty = min(len(warn_incidents) * 2, 5)
        score -= penalty
        factors.append({
            "label": "Warning incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(warn_incidents)} warning-level issue(s)",
        })

    # Factor 6: Verification tasks (15%) — Phase 4
    if verification_tasks is not None:
        now = datetime.now(timezone.utc)
        pending = [t for t in verification_tasks if t.status in ("pending", "in_progress")]
        overdue = [t for t in pending if t.due_date and t.due_date < now]
        total_tasks = len(verification_tasks)
        if overdue:
            penalty = min(len(overdue) * 3, 15)
            score -= penalty
            factors.append({
                "label": "Overdue verifications",
                "impact": round(-penalty, 1),
                "detail": f"{len(overdue)} overdue verification task(s)",
            })
        elif pending and total_tasks > 0:
            pct_incomplete = len(pending) / total_tasks
            if pct_incomplete > 0.5:
                penalty = round(pct_incomplete * 8, 1)
                score -= penalty
                factors.append({
                    "label": "Incomplete verifications",
                    "impact": round(-penalty, 1),
                    "detail": f"{len(pending)}/{total_tasks} task(s) pending",
                })

    # Factor 7: Stale devices (10%) — Phase 4
    if stale_device_count > 0:
        penalty = min(stale_device_count * 3, 10)
        score -= penalty
        factors.append({
            "label": "Stale devices",
            "impact": round(-penalty, 1),
            "detail": f"{stale_device_count} device(s) with overdue heartbeat",
        })

    readiness_score = max(0, round(score))
    if readiness_score >= 85:
        risk_label = "Operational"
    elif readiness_score >= 60:
        risk_label = "Attention Needed"
    else:
        risk_label = "At Risk"

    return {
        "score": readiness_score,
        "risk_label": risk_label,
        "factors": sorted(factors, key=lambda f: f["impact"]),
    }


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

@router.get("/summary")
async def command_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full Command dashboard payload — site-centric (Phase 4)."""
    tenant = current_user.tenant_id

    sites_q = await db.execute(select(Site).where(Site.tenant_id == tenant))
    sites = list(sites_q.scalars().all())

    devices_q = await db.execute(select(Device).where(Device.tenant_id == tenant))
    devices = list(devices_q.scalars().all())

    incidents_q = await db.execute(
        select(Incident)
        .where(Incident.tenant_id == tenant)
        .order_by(Incident.opened_at.desc())
        .limit(50)
    )
    incidents = list(incidents_q.scalars().all())

    activities_q = await db.execute(
        select(CommandActivity)
        .where(CommandActivity.tenant_id == tenant)
        .order_by(CommandActivity.created_at.desc())
        .limit(20)
    )
    activities = list(activities_q.scalars().all())

    # Verification tasks
    vtasks_q = await db.execute(
        select(VerificationTask).where(VerificationTask.tenant_id == tenant)
    )
    vtasks = list(vtasks_q.scalars().all())

    # Vendor assignment counts per site
    vendor_counts_q = await db.execute(
        select(SiteVendorAssignment.site_id, func.count())
        .where(SiteVendorAssignment.tenant_id == tenant)
        .group_by(SiteVendorAssignment.site_id)
    )
    vendor_counts = dict(vendor_counts_q.all())

    # Notification count
    notif_count_q = await db.execute(
        select(func.count())
        .select_from(CommandNotification)
        .where(
            CommandNotification.tenant_id == tenant,
            CommandNotification.read == False,  # noqa: E712
        )
    )
    unread_notifications = notif_count_q.scalar() or 0

    total_sites = len(sites)
    active_devices = [d for d in devices if d.status == "active"]
    active_incidents = [i for i in incidents if i.status in ("new", "open", "acknowledged", "in_progress")]
    critical_incidents = [i for i in active_incidents if i.severity == "critical"]
    connected = sum(1 for s in sites if s.status == "Connected")

    # Staleness computation
    devs_by_site = {}
    for d in devices:
        devs_by_site.setdefault(d.site_id, []).append(d)
    total_stale = 0
    site_staleness = {}
    for sid, site_devs in devs_by_site.items():
        info = compute_site_staleness(site_devs)
        site_staleness[sid] = info
        total_stale += info["stale_count"]

    # Check escalation for unacked incidents
    for inc in active_incidents:
        if inc.status in ("new", "open"):
            await _check_escalation(db, inc)

    # Run automation rules
    await evaluate_rules(db, tenant)
    await db.commit()

    # Verification summary
    now = datetime.now(timezone.utc)
    vtasks_by_site = {}
    for t in vtasks:
        vtasks_by_site.setdefault(t.site_id, []).append(t)
    overdue_tasks = [t for t in vtasks if t.status in ("pending", "in_progress") and t.due_date and t.due_date < now]

    # Site lookup map (used by system health + incident feed)
    site_map = {s.site_id: s for s in sites}

    # System health matrix — based on devices, only shows categories with data
    systems: dict = {}
    for d in devices:
        # Classify by device_type first, then fall back to site kit_type
        site_obj = site_map.get(d.site_id)
        kit = site_obj.kit_type if site_obj else None
        cat = _system_category(kit, d.device_type)
        if cat not in systems:
            label = SYSTEM_LABELS.get(cat, cat.replace("_", " ").title())
            systems[cat] = {"key": cat, "label": label, "total": 0, "healthy": 0, "warning": 0, "critical": 0}
        systems[cat]["total"] += 1
        if d.status == "active":
            systems[cat]["healthy"] += 1
        elif d.status == "inactive":
            systems[cat]["critical"] += 1
        else:
            systems[cat]["warning"] += 1

    # If no devices exist yet, classify by site kit_type
    if not devices:
        for site in sites:
            cat = _system_category(site.kit_type)
            if cat not in systems:
                label = SYSTEM_LABELS.get(cat, cat.replace("_", " ").title())
                systems[cat] = {"key": cat, "label": label, "total": 0, "healthy": 0, "warning": 0, "critical": 0}
            systems[cat]["total"] += 1
            if site.status == "Connected":
                systems[cat]["healthy"] += 1
            elif site.status == "Not Connected":
                systems[cat]["critical"] += 1
            else:
                systems[cat]["warning"] += 1

    system_health = []
    for cat in systems.values():
        t = cat["total"]
        pct = round((cat["healthy"] / t) * 100) if t > 0 else 100
        st = "healthy" if pct >= 90 else ("warning" if pct >= 70 else "critical")
        system_health.append({**cat, "health_pct": pct, "status": st})

    # Readiness (now with verification + staleness)
    readiness = _compute_readiness(sites, devices, incidents, verification_tasks=vtasks, stale_device_count=total_stale, devices_by_site=devs_by_site)

    # Incident feed
    incident_feed = [_serialize_incident(inc, site_map.get(inc.site_id, None) and site_map[inc.site_id].site_name) for inc in incidents[:20]]

    # Escalated incident count
    escalated_count = sum(1 for i in active_incidents if (i.escalation_level or 0) > 0)

    # Incidents by site
    incs_by_site = {}
    for i in active_incidents:
        incs_by_site.setdefault(i.site_id, []).append(i)

    # Site command summaries — sites needing attention first
    site_summaries = []
    for s in sites:
        s_incs = incs_by_site.get(s.site_id, [])
        s_tasks = vtasks_by_site.get(s.site_id, [])
        s_overdue = [t for t in s_tasks if t.status in ("pending", "in_progress") and t.due_date and t.due_date < now]
        s_stale = site_staleness.get(s.site_id, {}).get("stale_count", 0)
        s_critical = [i for i in s_incs if i.severity == "critical"]
        s_escalated = [i for i in s_incs if (i.escalation_level or 0) > 0]

        needs_attention = (
            s.status in ("Attention Needed", "Not Connected")
            or len(s_critical) > 0
            or len(s_overdue) > 0
            or s_stale > 0
        )

        site_summaries.append({
            "site_id": s.site_id,
            "site_name": s.site_name,
            "customer_name": s.customer_name,
            "status": s.status,
            "kit_type": s.kit_type,
            "needs_attention": needs_attention,
            "active_incidents": len(s_incs),
            "critical_incidents": len(s_critical),
            "escalated_incidents": len(s_escalated),
            "stale_devices": s_stale,
            "total_devices": len(devs_by_site.get(s.site_id, [])),
            "overdue_tasks": len(s_overdue),
            "pending_tasks": len([t for t in s_tasks if t.status in ("pending", "in_progress")]),
            "total_tasks": len(s_tasks),
            "vendor_count": vendor_counts.get(s.site_id, 0),
            "last_checkin": s.last_checkin.isoformat() if s.last_checkin else None,
        })

    # Sort: needs_attention first, then by critical count desc
    site_summaries.sort(key=lambda x: (-x["needs_attention"], -x["critical_incidents"], -x["active_incidents"], x["site_name"]))

    # Activity timeline
    activity_timeline = [
        CommandActivityOut.model_validate(a).model_dump(mode="json")
        for a in activities
    ]

    monitored_sites = [s for s in sites if s.site_id in devs_by_site]
    imported_only = [s for s in sites if s.site_id not in devs_by_site]
    devices_with_heartbeat = [d for d in devices if d.last_heartbeat is not None]
    devices_missing_telemetry = [d for d in devices if d.last_heartbeat is None]

    portfolio_data = {
        "total_sites": total_sites,
        "monitored_sites": len(monitored_sites),
        "imported_only_sites": len(imported_only),
        "total_devices": len(devices),
        "active_devices": len(active_devices),
        "devices_with_telemetry": len(devices_with_heartbeat),
        "devices_missing_telemetry": len(devices_missing_telemetry),
        "connected_sites": connected,
        "attention_sites": len([s for s in sites if s.status == "Attention Needed"]),
        "disconnected_sites": len([s for s in sites if s.status == "Not Connected"]),
        "stale_devices": total_stale,
        "overdue_tasks": len(overdue_tasks),
        "total_verification_tasks": len(vtasks),
    }

    # ── Intelligence layer ────────────────────────────────────────
    intelligence = compute_intelligence(
        portfolio=portfolio_data,
        readiness=readiness,
        system_health=system_health,
        incident_feed=incident_feed,
        active_incidents_count=len(active_incidents),
        critical_incidents_count=len(critical_incidents),
        escalated_count=escalated_count,
        site_summaries=site_summaries,
        activity_timeline=activity_timeline,
    )

    return {
        "portfolio": portfolio_data,
        "readiness": readiness,
        "system_health": system_health,
        "incident_feed": incident_feed,
        "active_incidents": len(active_incidents),
        "critical_incidents": len(critical_incidents),
        "escalated_incidents": escalated_count,
        "unread_notifications": unread_notifications,
        "site_summaries": site_summaries,
        "activity_timeline": activity_timeline,
        # V2 intelligence fields
        "intelligence": intelligence,
    }


# ---------------------------------------------------------------------------
# Site detail
# ---------------------------------------------------------------------------

@router.get("/site/{site_id}")
async def command_site_detail(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant = current_user.tenant_id

    site_q = await db.execute(select(Site).where(Site.tenant_id == tenant, Site.site_id == site_id))
    site = site_q.scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Site not found")

    devices_q = await db.execute(select(Device).where(Device.tenant_id == tenant, Device.site_id == site_id))
    devices = list(devices_q.scalars().all())

    incidents_q = await db.execute(
        select(Incident)
        .where(Incident.tenant_id == tenant, Incident.site_id == site_id)
        .order_by(Incident.opened_at.desc())
        .limit(30)
    )
    incidents = list(incidents_q.scalars().all())

    activities_q = await db.execute(
        select(CommandActivity)
        .where(CommandActivity.tenant_id == tenant, CommandActivity.site_id == site_id)
        .order_by(CommandActivity.created_at.desc())
        .limit(20)
    )
    activities = list(activities_q.scalars().all())

    # Telemetry for site devices
    device_ids = [d.device_id for d in devices]
    telemetry_data = []
    if device_ids:
        telem_q = await db.execute(
            select(CommandTelemetry)
            .where(CommandTelemetry.site_id == site_id, CommandTelemetry.tenant_id == tenant)
            .order_by(CommandTelemetry.recorded_at.desc())
            .limit(len(device_ids) * 5)
        )
        telemetry_data = [TelemetryOut.model_validate(t).model_dump(mode="json") for t in telem_q.scalars().all()]

    # Verification tasks (Phase 4)
    vtasks_q = await db.execute(
        select(VerificationTask)
        .where(VerificationTask.tenant_id == tenant, VerificationTask.site_id == site_id)
        .order_by(VerificationTask.due_date.asc().nullslast(), VerificationTask.priority.desc())
    )
    vtasks = list(vtasks_q.scalars().all())

    # Vendor assignments (Phase 4)
    from ..models.vendor import Vendor
    vassign_q = await db.execute(
        select(SiteVendorAssignment)
        .where(SiteVendorAssignment.tenant_id == tenant, SiteVendorAssignment.site_id == site_id)
        .order_by(SiteVendorAssignment.system_category)
    )
    vassignments = list(vassign_q.scalars().all())
    vendor_ids = list(set(a.vendor_id for a in vassignments))
    vendors_map = {}
    if vendor_ids:
        vendors_q = await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))
        for v in vendors_q.scalars().all():
            vendors_map[v.id] = v

    active_incidents = [i for i in incidents if i.status in ("new", "open", "acknowledged", "in_progress")]
    active_devices = [d for d in devices if d.status == "active"]

    # Staleness (Phase 4)
    staleness = compute_site_staleness(devices)

    # Verification summary
    now = datetime.now(timezone.utc)
    pending_tasks = [t for t in vtasks if t.status in ("pending", "in_progress")]
    overdue_tasks = [t for t in pending_tasks if t.due_date and t.due_date < now]
    completed_tasks = [t for t in vtasks if t.status == "completed"]

    # Site readiness (site-level 7-factor model)
    readiness = _compute_readiness(
        [site], devices, incidents,
        verification_tasks=vtasks,
        stale_device_count=staleness["stale_count"],
    )

    # Build system categories from actual devices at this site
    site_cats: dict = {}
    for d in devices:
        cat = _system_category(site.kit_type, d.device_type)
        if cat not in site_cats:
            label = SYSTEM_LABELS.get(cat, cat.replace("_", " ").title())
            site_cats[cat] = {"key": cat, "label": label, "device_count": 0, "active_count": 0}
        site_cats[cat]["device_count"] += 1
        if d.status == "active":
            site_cats[cat]["active_count"] += 1
    if not site_cats:
        cat = _system_category(site.kit_type)
        label = SYSTEM_LABELS.get(cat, cat.replace("_", " ").title())
        site_cats[cat] = {"key": cat, "label": label, "device_count": 0, "active_count": 0}
    system_categories = []
    for c in site_cats.values():
        st = "healthy" if site.status == "Connected" else ("warning" if site.status == "Attention Needed" else "critical")
        system_categories.append({**c, "status": st})

    incident_list = [_serialize_incident(inc) for inc in incidents]

    # Recommended actions
    actions = []
    critical = [i for i in active_incidents if i.severity == "critical"]
    if critical:
        actions.append({"priority": "high", "action": "Resolve critical incidents", "detail": f"{len(critical)} critical incident(s) require immediate attention"})
    if site.status == "Not Connected":
        actions.append({"priority": "high", "action": "Restore site connectivity", "detail": "Site disconnected from monitoring"})
    if overdue_tasks:
        actions.append({"priority": "high", "action": "Complete overdue verification tasks", "detail": f"{len(overdue_tasks)} task(s) past due date"})
    if staleness["stale_count"] > 0:
        actions.append({"priority": "high", "action": "Investigate stale devices", "detail": f"{staleness['stale_count']} device(s) with overdue heartbeat"})
    if site.status == "Attention Needed":
        actions.append({"priority": "medium", "action": "Investigate site warnings", "detail": "Site has reported intermittent issues"})
    inactive_devs = [d for d in devices if d.status != "active"]
    if inactive_devs:
        actions.append({"priority": "medium", "action": "Activate idle devices", "detail": f"{len(inactive_devs)} device(s) not active"})
    if pending_tasks and not overdue_tasks:
        actions.append({"priority": "medium", "action": "Complete pending verification tasks", "detail": f"{len(pending_tasks)} task(s) remaining"})
    if not actions:
        actions.append({"priority": "low", "action": "No action required", "detail": "All systems operational"})

    activity_timeline = [
        CommandActivityOut.model_validate(a).model_dump(mode="json")
        for a in activities
    ]

    # Serialize verification tasks
    vtasks_out = []
    for t in vtasks:
        is_overdue = t.status in ("pending", "in_progress") and t.due_date is not None and t.due_date < now
        vtasks_out.append({
            "id": t.id, "task_type": t.task_type, "title": t.title,
            "description": t.description, "system_category": t.system_category,
            "status": t.status, "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "completed_by": t.completed_by, "assigned_to": t.assigned_to,
            "result": t.result, "evidence_notes": t.evidence_notes,
            "is_overdue": is_overdue,
        })

    # Serialize vendor assignments
    vassign_out = []
    for a in vassignments:
        v = vendors_map.get(a.vendor_id)
        vassign_out.append({
            "id": a.id, "vendor_id": a.vendor_id, "system_category": a.system_category,
            "is_primary": a.is_primary, "notes": a.notes,
            "vendor_name": v.name if v else None,
            "vendor_contact_name": v.contact_name if v else None,
            "vendor_contact_phone": v.contact_phone if v else None,
            "vendor_contact_email": v.contact_email if v else None,
        })

    return {
        "site": {
            "site_id": site.site_id,
            "site_name": site.site_name,
            "customer_name": site.customer_name,
            "status": site.status,
            "kit_type": site.kit_type,
            "e911_street": site.e911_street,
            "e911_city": site.e911_city,
            "e911_state": site.e911_state,
            "e911_zip": site.e911_zip,
            "last_checkin": site.last_checkin.isoformat() if site.last_checkin else None,
            "poc_name": getattr(site, "poc_name", None),
            "poc_phone": getattr(site, "poc_phone", None),
            "poc_email": getattr(site, "poc_email", None),
        },
        "readiness": readiness,
        "system_categories": system_categories,
        "incidents": incident_list,
        "devices": {"total": len(devices), "active": len(active_devices)},
        "staleness": staleness,
        "verification_tasks": vtasks_out,
        "verification_summary": {
            "total": len(vtasks),
            "pending": len(pending_tasks),
            "completed": len(completed_tasks),
            "overdue": len(overdue_tasks),
            "passed": len([t for t in completed_tasks if t.result == "pass"]),
            "failed": len([t for t in completed_tasks if t.result == "fail"]),
            "completion_pct": round(len(completed_tasks) / len(vtasks) * 100) if vtasks else 0,
        },
        "vendor_assignments": vassign_out,
        "recommended_actions": actions,
        "activity_timeline": activity_timeline,
        "telemetry": telemetry_data,
    }


# ---------------------------------------------------------------------------
# Incident workflow actions
# ---------------------------------------------------------------------------

@router.post("/incidents")
async def command_create_incident(
    body: CommandIncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_CREATE_INCIDENT")),
):
    """Create a new Command incident."""
    incident_id = f"CMD-{uuid.uuid4().hex[:10].upper()}"
    now = datetime.now(timezone.utc)

    inc = Incident(
        incident_id=incident_id,
        tenant_id=current_user.tenant_id,
        site_id=body.site_id,
        opened_at=now,
        severity=body.severity,
        status="new",
        summary=body.summary,
        incident_type=body.incident_type,
        source=body.source or "command",
        description=body.description,
        location_detail=body.location_detail,
        assigned_to=body.assigned_to,
        recommended_actions_json=body.recommended_actions_json,
        metadata_json=body.metadata_json,
        created_by=current_user.email,
    )
    db.add(inc)

    await _log_activity(
        db, current_user.tenant_id, "incident_created",
        f"Incident created: {body.summary}",
        site_id=body.site_id, incident_id=incident_id,
        actor=current_user.email,
    )

    await _create_notification(
        db, current_user.tenant_id,
        f"New {body.severity} incident: {body.summary}",
        severity=body.severity,
        incident_id=incident_id,
        site_id=body.site_id,
    )

    await db.commit()
    await db.refresh(inc)
    return _serialize_incident(inc)


@router.post("/incidents/{incident_pk}/transition/{target_status}")
async def command_transition_incident(
    incident_pk: int,
    target_status: str,
    body: CommandIncidentTransition = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transition an incident through the workflow state machine."""
    # Check permission for target status
    required_perm = TRANSITION_PERMISSIONS.get(target_status)
    if required_perm:
        from ..services.rbac import can as rbac_can
        if not rbac_can(current_user.role, required_perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Permission '{required_perm}' denied for role '{current_user.role}'")

    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_pk,
            Incident.tenant_id == current_user.tenant_id,
        )
    )
    inc = result.scalar_one_or_none()
    if not inc:
        raise HTTPException(404, "Incident not found")

    # Validate transition
    allowed = VALID_TRANSITIONS.get(inc.status, [])
    if target_status not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot transition from '{inc.status}' to '{target_status}'. Allowed: {allowed}",
        )

    now = datetime.now(timezone.utc)
    old_status = inc.status
    inc.status = target_status

    if target_status == "acknowledged":
        inc.ack_by = current_user.email
        inc.ack_at = now
    elif target_status == "in_progress":
        if body and body.assigned_to:
            inc.assigned_to = body.assigned_to
    elif target_status == "resolved":
        inc.resolved_at = now
        inc.closed_at = now
        if body and body.resolution_notes:
            inc.resolution_notes = body.resolution_notes
    elif target_status == "dismissed":
        inc.closed_at = now
        if body and body.resolution_notes:
            inc.resolution_notes = body.resolution_notes

    await _log_activity(
        db, current_user.tenant_id, f"incident_{target_status}",
        f"Incident {inc.incident_id} transitioned: {old_status} -> {target_status}",
        site_id=inc.site_id, incident_id=inc.incident_id,
        actor=current_user.email,
        detail=body.resolution_notes if body and body.resolution_notes else None,
    )

    await _create_notification(
        db, current_user.tenant_id,
        f"Incident {target_status}: {inc.summary}",
        severity="info" if target_status in ("resolved", "dismissed") else inc.severity,
        incident_id=inc.incident_id,
        site_id=inc.site_id,
    )

    await db.commit()
    await db.refresh(inc)
    return _serialize_incident(inc)


@router.post("/incidents/{incident_pk}/assign")
async def command_assign_incident(
    incident_pk: int,
    body: CommandIncidentTransition,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_ASSIGN")),
):
    """Assign an incident to a person without changing status."""
    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_pk,
            Incident.tenant_id == current_user.tenant_id,
        )
    )
    inc = result.scalar_one_or_none()
    if not inc:
        raise HTTPException(404, "Incident not found")

    if body.assigned_to:
        inc.assigned_to = body.assigned_to

    await _log_activity(
        db, current_user.tenant_id, "incident_assigned",
        f"Incident {inc.incident_id} assigned to {body.assigned_to}",
        site_id=inc.site_id, incident_id=inc.incident_id,
        actor=current_user.email,
    )

    await db.commit()
    await db.refresh(inc)
    return _serialize_incident(inc)


# ---------------------------------------------------------------------------
# Telemetry ingest
# ---------------------------------------------------------------------------

@router.post("/telemetry")
async def ingest_telemetry(
    body: TelemetryIngest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_INGEST_TELEMETRY")),
):
    """Ingest device telemetry data and check for anomalies."""
    telem = CommandTelemetry(
        tenant_id=current_user.tenant_id,
        device_id=body.device_id,
        site_id=body.site_id,
        signal_strength=body.signal_strength,
        battery_pct=body.battery_pct,
        uptime_seconds=body.uptime_seconds,
        temperature_c=body.temperature_c,
        error_count=body.error_count,
        firmware_version=body.firmware_version,
        metadata_json=body.metadata_json,
    )
    db.add(telem)

    # Auto-incident detection from telemetry anomalies
    anomalies = []
    if body.battery_pct is not None and body.battery_pct < 10:
        anomalies.append(("critical" if body.battery_pct < 5 else "warning", f"Battery critically low: {body.battery_pct}%", "low_battery"))
    if body.signal_strength is not None and body.signal_strength < -90:
        anomalies.append(("warning", f"Weak signal: {body.signal_strength} dBm", "weak_signal"))
    if body.error_count is not None and body.error_count > 10:
        anomalies.append(("warning", f"High error count: {body.error_count}", "high_errors"))
    if body.temperature_c is not None and body.temperature_c > 70:
        anomalies.append(("critical" if body.temperature_c > 85 else "warning", f"High temperature: {body.temperature_c}C", "overtemp"))

    created_incidents = []
    for severity, summary, inc_type in anomalies:
        incident_id = f"AUTO-{uuid.uuid4().hex[:10].upper()}"
        now = datetime.now(timezone.utc)
        inc = Incident(
            incident_id=incident_id,
            tenant_id=current_user.tenant_id,
            site_id=body.site_id or "UNKNOWN",
            opened_at=now,
            severity=severity,
            status="new",
            summary=f"[Auto] {summary} — Device {body.device_id}",
            incident_type=inc_type,
            source="telemetry_auto",
            description=f"Automatically detected from telemetry ingest for device {body.device_id}",
            location_detail=None,
            created_by="system",
        )
        db.add(inc)
        await _log_activity(
            db, current_user.tenant_id, "incident_created",
            f"Auto-incident: {summary}",
            site_id=body.site_id, incident_id=incident_id,
            actor="system",
            detail=f"Telemetry anomaly detected for device {body.device_id}",
        )
        await _create_notification(
            db, current_user.tenant_id,
            f"Auto-detected: {summary}",
            severity=severity,
            incident_id=incident_id,
            site_id=body.site_id,
        )
        created_incidents.append(incident_id)

    await db.commit()

    return {
        "status": "ok",
        "device_id": body.device_id,
        "anomalies_detected": len(anomalies),
        "incidents_created": created_incidents,
    }


@router.get("/telemetry/{device_id}", response_model=list[TelemetryOut])
async def get_device_telemetry(
    device_id: str,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get recent telemetry for a specific device."""
    result = await db.execute(
        select(CommandTelemetry)
        .where(
            CommandTelemetry.tenant_id == current_user.tenant_id,
            CommandTelemetry.device_id == device_id,
        )
        .order_by(CommandTelemetry.recorded_at.desc())
        .limit(limit)
    )
    return [TelemetryOut.model_validate(t) for t in result.scalars().all()]


@router.get("/telemetry/site/{site_id}", response_model=list[TelemetryOut])
async def get_site_telemetry(
    site_id: str,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get recent telemetry for all devices at a site."""
    result = await db.execute(
        select(CommandTelemetry)
        .where(
            CommandTelemetry.tenant_id == current_user.tenant_id,
            CommandTelemetry.site_id == site_id,
        )
        .order_by(CommandTelemetry.recorded_at.desc())
        .limit(limit)
    )
    return [TelemetryOut.model_validate(t) for t in result.scalars().all()]


# ---------------------------------------------------------------------------
# Activity timeline
# ---------------------------------------------------------------------------

@router.get("/activities", response_model=list[CommandActivityOut])
async def list_activities(
    site_id: str | None = None,
    activity_type: str | None = None,
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(CommandActivity)
        .where(CommandActivity.tenant_id == current_user.tenant_id)
        .order_by(CommandActivity.created_at.desc())
        .limit(limit)
    )
    if site_id:
        q = q.where(CommandActivity.site_id == site_id)
    if activity_type:
        q = q.where(CommandActivity.activity_type == activity_type)
    result = await db.execute(q)
    return [CommandActivityOut.model_validate(a) for a in result.scalars().all()]


# ---------------------------------------------------------------------------
# Incident detail (Phase 4)
# ---------------------------------------------------------------------------

@router.get("/incidents/{incident_pk}")
async def command_incident_detail(
    incident_pk: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full incident detail with timeline, related data."""
    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_pk,
            Incident.tenant_id == current_user.tenant_id,
        )
    )
    inc = result.scalar_one_or_none()
    if not inc:
        raise HTTPException(404, "Incident not found")

    # Site name
    site_q = await db.execute(
        select(Site).where(Site.tenant_id == current_user.tenant_id, Site.site_id == inc.site_id)
    )
    site = site_q.scalar_one_or_none()

    # Incident activity timeline
    acts_q = await db.execute(
        select(CommandActivity)
        .where(
            CommandActivity.tenant_id == current_user.tenant_id,
            CommandActivity.incident_id == inc.incident_id,
        )
        .order_by(CommandActivity.created_at.desc())
        .limit(20)
    )
    timeline = [CommandActivityOut.model_validate(a).model_dump(mode="json") for a in acts_q.scalars().all()]

    data = _serialize_incident(inc, site.site_name if site else None)
    data["timeline"] = timeline
    data["site_status"] = site.status if site else None
    return data


# ---------------------------------------------------------------------------
# Digest / report payload (Phase 4)
# ---------------------------------------------------------------------------

@router.get("/digest")
async def command_digest(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_EXPORT_REPORTS")),
):
    """Digest payload for scheduled reporting — summary of portfolio state."""
    tenant = current_user.tenant_id
    now = datetime.now(timezone.utc)

    sites_q = await db.execute(select(Site).where(Site.tenant_id == tenant))
    sites = list(sites_q.scalars().all())

    devices_q = await db.execute(select(Device).where(Device.tenant_id == tenant))
    devices = list(devices_q.scalars().all())

    incidents_q = await db.execute(
        select(Incident)
        .where(Incident.tenant_id == tenant, Incident.status.in_(["new", "open", "acknowledged", "in_progress"]))
    )
    active_incidents = list(incidents_q.scalars().all())

    vtasks_q = await db.execute(
        select(VerificationTask).where(VerificationTask.tenant_id == tenant)
    )
    vtasks = list(vtasks_q.scalars().all())

    devs_by_site = {}
    for d in devices:
        devs_by_site.setdefault(d.site_id, []).append(d)

    total_stale = 0
    for site_devs in devs_by_site.values():
        info = compute_site_staleness(site_devs)
        total_stale += info["stale_count"]

    overdue = [t for t in vtasks if t.status in ("pending", "in_progress") and t.due_date and t.due_date < now]
    critical = [i for i in active_incidents if i.severity == "critical"]

    readiness = _compute_readiness(sites, devices, active_incidents, verification_tasks=vtasks, stale_device_count=total_stale)

    # Sites needing attention
    incs_by_site = {}
    for i in active_incidents:
        incs_by_site.setdefault(i.site_id, []).append(i)

    attention_sites = []
    for s in sites:
        s_incs = incs_by_site.get(s.site_id, [])
        s_critical = [i for i in s_incs if i.severity == "critical"]
        if s.status in ("Attention Needed", "Not Connected") or s_critical:
            attention_sites.append({
                "site_id": s.site_id, "site_name": s.site_name,
                "status": s.status, "critical_incidents": len(s_critical),
                "active_incidents": len(s_incs),
            })

    return {
        "generated_at": now.isoformat(),
        "readiness": readiness,
        "portfolio": {
            "total_sites": len(sites),
            "connected": sum(1 for s in sites if s.status == "Connected"),
            "attention": sum(1 for s in sites if s.status == "Attention Needed"),
            "disconnected": sum(1 for s in sites if s.status == "Not Connected"),
            "total_devices": len(devices),
            "stale_devices": total_stale,
        },
        "incidents": {
            "active": len(active_incidents),
            "critical": len(critical),
            "escalated": sum(1 for i in active_incidents if (i.escalation_level or 0) > 0),
        },
        "verification": {
            "total": len(vtasks),
            "overdue": len(overdue),
            "completed": len([t for t in vtasks if t.status == "completed"]),
        },
        "attention_sites": attention_sites,
    }


# ---------------------------------------------------------------------------
# Operator view (Phase 4 — simplified role-aware view)
# ---------------------------------------------------------------------------

@router.get("/operator")
async def operator_view(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Simplified operator view — site list with status, active issues, tasks."""
    tenant = current_user.tenant_id
    now = datetime.now(timezone.utc)

    sites_q = await db.execute(select(Site).where(Site.tenant_id == tenant).order_by(Site.site_name))
    sites = list(sites_q.scalars().all())

    incidents_q = await db.execute(
        select(Incident)
        .where(Incident.tenant_id == tenant, Incident.status.in_(["new", "open", "acknowledged", "in_progress"]))
    )
    active_incidents = list(incidents_q.scalars().all())
    incs_by_site = {}
    for i in active_incidents:
        incs_by_site.setdefault(i.site_id, []).append(i)

    vtasks_q = await db.execute(
        select(VerificationTask).where(
            VerificationTask.tenant_id == tenant,
            VerificationTask.status.in_(["pending", "in_progress"]),
        )
    )
    vtasks = list(vtasks_q.scalars().all())
    tasks_by_site = {}
    for t in vtasks:
        tasks_by_site.setdefault(t.site_id, []).append(t)

    site_list = []
    for s in sites:
        s_incs = incs_by_site.get(s.site_id, [])
        s_tasks = tasks_by_site.get(s.site_id, [])
        s_overdue = [t for t in s_tasks if t.due_date and t.due_date < now]
        s_critical = [i for i in s_incs if i.severity == "critical"]

        needs_attention = (
            s.status in ("Attention Needed", "Not Connected")
            or len(s_critical) > 0
            or len(s_overdue) > 0
        )

        site_list.append({
            "site_id": s.site_id,
            "site_name": s.site_name,
            "customer_name": s.customer_name,
            "status": s.status,
            "kit_type": s.kit_type,
            "needs_attention": needs_attention,
            "active_incidents": len(s_incs),
            "critical_incidents": len(s_critical),
            "pending_tasks": len(s_tasks),
            "overdue_tasks": len(s_overdue),
            "last_checkin": s.last_checkin.isoformat() if s.last_checkin else None,
        })

    site_list.sort(key=lambda x: (-x["needs_attention"], -x["critical_incidents"], x["site_name"]))

    return {
        "total_sites": len(sites),
        "sites_needing_attention": sum(1 for s in site_list if s["needs_attention"]),
        "active_incidents": len(active_incidents),
        "sites": site_list,
    }
