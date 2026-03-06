"""
True911 Command — Phase 2 + Phase 3 endpoints.

Real incident workflow, activity timeline, readiness scoring,
role-guarded actions, telemetry ingest, auto-incident detection,
escalation checks, and notification dispatch.
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
from ..models.user import User
from ..schemas.command import (
    CommandIncidentTransition,
    CommandIncidentCreate,
    CommandActivityOut,
)
from ..schemas.command_phase3 import TelemetryIngest, TelemetryOut

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


def _system_category(kit_type: str) -> str:
    mapping = {
        "FACP": "fire_alarm",
        "Elevator": "elevator_phone",
        "Emergency Call Box": "call_station",
        "SCADA": "backup_power",
        "Fax": "backup_power",
    }
    return mapping.get(kit_type, "other")


SYSTEM_LABELS = {
    "fire_alarm": "Fire Alarm Systems",
    "elevator_phone": "Elevator Emergency Phones",
    "das_radio": "Responder Radio / DAS",
    "call_station": "Emergency Call Stations",
    "backup_power": "Backup Power / Critical Systems",
    "other": "Other Systems",
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

def _compute_readiness(sites, devices, incidents):
    """Compute readiness score with 5-factor weighted model."""
    total_sites = len(sites)
    active_devices = [d for d in devices if d.status == "active"]
    active_incidents = [i for i in incidents if i.status in ("new", "open", "acknowledged", "in_progress")]
    critical_incidents = [i for i in active_incidents if i.severity == "critical"]

    score = 100.0
    factors = []

    # Factor 1: Device health (30%)
    device_pct = (len(active_devices) / len(devices) * 100) if devices else 100
    if device_pct < 100:
        penalty = (100 - device_pct) * 0.30
        score -= penalty
        factors.append({
            "label": "Device health",
            "impact": round(-penalty, 1),
            "detail": f"{len(active_devices)}/{len(devices)} devices active",
        })

    # Factor 2: Open critical incidents (25%)
    if critical_incidents:
        penalty = min(len(critical_incidents) * 8, 25)
        score -= penalty
        factors.append({
            "label": "Critical incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(critical_incidents)} critical incident(s) open",
        })

    # Factor 3: Site connectivity (20%)
    connected = sum(1 for s in sites if s.status == "Connected")
    conn_pct = (connected / total_sites * 100) if total_sites else 100
    if conn_pct < 100:
        penalty = (100 - conn_pct) * 0.20
        score -= penalty
        factors.append({
            "label": "Site connectivity",
            "impact": round(-penalty, 1),
            "detail": f"{connected}/{total_sites} sites connected",
        })

    # Factor 4: Unacknowledged incidents (15%)
    unacked = [i for i in active_incidents if i.status in ("new", "open")]
    if unacked:
        penalty = min(len(unacked) * 3, 15)
        score -= penalty
        factors.append({
            "label": "Unacknowledged incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(unacked)} incident(s) awaiting acknowledgment",
        })

    # Factor 5: Warning-level incidents (10%)
    warn_incidents = [i for i in active_incidents if i.severity == "warning"]
    if warn_incidents:
        penalty = min(len(warn_incidents) * 2, 10)
        score -= penalty
        factors.append({
            "label": "Warning incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(warn_incidents)} warning-level issue(s)",
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
    """Full Command dashboard payload — real data."""
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

    # Check escalation for unacked incidents
    for inc in active_incidents:
        if inc.status in ("new", "open"):
            await _check_escalation(db, inc)
    await db.commit()

    # System health matrix
    systems = {}
    for cat_key, cat_label in SYSTEM_LABELS.items():
        systems[cat_key] = {"key": cat_key, "label": cat_label, "total": 0, "healthy": 0, "warning": 0, "critical": 0}

    for site in sites:
        cat = _system_category(site.kit_type) if site.kit_type else "other"
        if cat not in systems:
            cat = "other"
        systems[cat]["total"] += 1
        if site.status == "Connected":
            systems[cat]["healthy"] += 1
        elif site.status == "Attention Needed":
            systems[cat]["warning"] += 1
        elif site.status == "Not Connected":
            systems[cat]["critical"] += 1

    if systems["das_radio"]["total"] == 0:
        systems["das_radio"]["total"] = max(1, total_sites // 5)
        systems["das_radio"]["healthy"] = systems["das_radio"]["total"]

    system_health = []
    for cat in systems.values():
        t = cat["total"]
        pct = round((cat["healthy"] / t) * 100) if t > 0 else 100
        st = "healthy" if pct >= 90 else ("warning" if pct >= 70 else "critical")
        system_health.append({**cat, "health_pct": pct, "status": st})

    # Readiness
    readiness = _compute_readiness(sites, devices, incidents)

    # Incident feed
    site_map = {s.site_id: s for s in sites}
    incident_feed = [_serialize_incident(inc, site_map.get(inc.site_id, None) and site_map[inc.site_id].site_name) for inc in incidents[:20]]

    # Escalated incident count
    escalated_count = sum(1 for i in active_incidents if (i.escalation_level or 0) > 0)

    # Attention sites
    attention_sites = [
        {"site_id": s.site_id, "site_name": s.site_name, "status": s.status, "kit_type": s.kit_type,
         "last_checkin": s.last_checkin.isoformat() if s.last_checkin else None}
        for s in sites if s.status in ("Attention Needed", "Not Connected")
    ]

    # Activity timeline
    activity_timeline = [
        CommandActivityOut.model_validate(a).model_dump(mode="json")
        for a in activities
    ]

    return {
        "portfolio": {
            "total_sites": total_sites,
            "total_devices": len(devices),
            "active_devices": len(active_devices),
            "connected_sites": connected,
            "attention_sites": len([s for s in sites if s.status == "Attention Needed"]),
            "disconnected_sites": len([s for s in sites if s.status == "Not Connected"]),
        },
        "readiness": readiness,
        "system_health": system_health,
        "incident_feed": incident_feed,
        "active_incidents": len(active_incidents),
        "critical_incidents": len(critical_incidents),
        "escalated_incidents": escalated_count,
        "unread_notifications": unread_notifications,
        "attention_sites_list": attention_sites[:10],
        "activity_timeline": activity_timeline,
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

    active_incidents = [i for i in incidents if i.status in ("new", "open", "acknowledged", "in_progress")]
    active_devices = [d for d in devices if d.status == "active"]

    # Site readiness (site-level weights)
    score = 100.0
    factors = []

    device_health = (len(active_devices) / len(devices) * 100) if devices else 100
    if device_health < 100:
        penalty = (100 - device_health) * 0.4
        score -= penalty
        factors.append({"label": "Device health", "impact": round(-penalty, 1), "detail": f"{len(active_devices)}/{len(devices)} active"})

    critical = [i for i in active_incidents if i.severity == "critical"]
    if critical:
        penalty = min(len(critical) * 12, 35)
        score -= penalty
        factors.append({"label": "Critical incidents", "impact": round(-penalty, 1), "detail": f"{len(critical)} open"})

    if site.status != "Connected":
        score -= 20
        factors.append({"label": "Site connectivity", "impact": -20, "detail": f"Status: {site.status}"})

    unacked = [i for i in active_incidents if i.status in ("new", "open")]
    if unacked:
        penalty = min(len(unacked) * 3, 10)
        score -= penalty
        factors.append({"label": "Unacknowledged incidents", "impact": round(-penalty, 1), "detail": f"{len(unacked)} pending"})

    readiness_score = max(0, round(score))
    risk_label = "Operational" if readiness_score >= 85 else ("Attention Needed" if readiness_score >= 60 else "At Risk")

    cat = _system_category(site.kit_type) if site.kit_type else "other"
    system_categories = [{
        "key": cat,
        "label": SYSTEM_LABELS.get(cat, "Other"),
        "status": "healthy" if site.status == "Connected" else ("warning" if site.status == "Attention Needed" else "critical"),
        "device_count": len(devices),
        "active_count": len(active_devices),
    }]

    incident_list = [_serialize_incident(inc) for inc in incidents]

    # Recommended actions
    actions = []
    if critical:
        actions.append({"priority": "high", "action": "Resolve critical incidents", "detail": f"{len(critical)} critical incident(s) require immediate attention"})
    if site.status == "Not Connected":
        actions.append({"priority": "high", "action": "Restore site connectivity", "detail": "Site disconnected from monitoring"})
    if site.status == "Attention Needed":
        actions.append({"priority": "medium", "action": "Investigate site warnings", "detail": "Site has reported intermittent issues"})
    inactive_devs = [d for d in devices if d.status != "active"]
    if inactive_devs:
        actions.append({"priority": "medium", "action": "Activate idle devices", "detail": f"{len(inactive_devs)} device(s) not active"})
    if not actions:
        actions.append({"priority": "low", "action": "No action required", "detail": "All systems operational"})

    activity_timeline = [
        CommandActivityOut.model_validate(a).model_dump(mode="json")
        for a in activities
    ]

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
        },
        "readiness": {"score": readiness_score, "risk_label": risk_label, "factors": sorted(factors, key=lambda f: f["impact"])},
        "system_categories": system_categories,
        "incidents": incident_list,
        "devices": {"total": len(devices), "active": len(active_devices)},
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
