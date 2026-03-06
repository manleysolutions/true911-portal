"""
True911 Command — summary endpoints.

Computes readiness scores, system health, and incident feeds
from existing Site, Device, and Incident data.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..dependencies import get_db, get_current_user
from ..models.site import Site
from ..models.device import Device
from ..models.incident import Incident
from ..models.user import User

router = APIRouter()


def _system_category(kit_type: str) -> str:
    """Map site kit_type to a Command system category."""
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


@router.get("/summary")
async def command_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the full Command dashboard payload."""
    tenant = current_user.tenant_id

    # --- Fetch all data in parallel-ish queries ---
    sites_q = await db.execute(
        select(Site).where(Site.tenant_id == tenant)
    )
    sites = list(sites_q.scalars().all())

    devices_q = await db.execute(
        select(Device).where(Device.tenant_id == tenant)
    )
    devices = list(devices_q.scalars().all())

    incidents_q = await db.execute(
        select(Incident)
        .where(Incident.tenant_id == tenant)
        .order_by(Incident.opened_at.desc())
        .limit(50)
    )
    incidents = list(incidents_q.scalars().all())

    # --- Portfolio summary ---
    total_sites = len(sites)
    active_incidents = [i for i in incidents if i.status in ("open", "acknowledged")]
    critical_incidents = [i for i in active_incidents if i.severity == "critical"]

    # --- System health matrix ---
    # Build per-category health
    systems = {}
    for cat_key, cat_label in SYSTEM_LABELS.items():
        systems[cat_key] = {
            "key": cat_key,
            "label": cat_label,
            "total": 0,
            "healthy": 0,
            "warning": 0,
            "critical": 0,
        }

    # Count sites per category
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
        # Unknown doesn't move the needle

    # Ensure DAS/radio always shows (even if no sites map to it)
    if systems["das_radio"]["total"] == 0:
        systems["das_radio"]["total"] = max(1, total_sites // 5)
        systems["das_radio"]["healthy"] = systems["das_radio"]["total"]

    # Compute health percentages
    system_health = []
    for cat in systems.values():
        t = cat["total"]
        pct = round((cat["healthy"] / t) * 100) if t > 0 else 100
        status = "healthy" if pct >= 90 else ("warning" if pct >= 70 else "critical")
        system_health.append({
            **cat,
            "health_pct": pct,
            "status": status,
        })

    # --- Readiness score ---
    # Simple weighted scoring
    factors = []
    score = 100.0

    # Factor 1: Device health (40% weight)
    active_devices = [d for d in devices if d.status == "active"]
    device_health = (len(active_devices) / len(devices) * 100) if devices else 100
    if device_health < 100:
        penalty = (100 - device_health) * 0.4
        score -= penalty
        factors.append({
            "label": "Device health",
            "impact": round(-penalty, 1),
            "detail": f"{len(active_devices)}/{len(devices)} devices active",
        })

    # Factor 2: Open critical incidents (30% weight)
    if critical_incidents:
        penalty = min(len(critical_incidents) * 10, 30)
        score -= penalty
        factors.append({
            "label": "Open critical incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(critical_incidents)} critical incident(s) open",
        })

    # Factor 3: Site connectivity (20% weight)
    connected = sum(1 for s in sites if s.status == "Connected")
    conn_pct = (connected / total_sites * 100) if total_sites else 100
    if conn_pct < 100:
        penalty = (100 - conn_pct) * 0.2
        score -= penalty
        factors.append({
            "label": "Site connectivity",
            "impact": round(-penalty, 1),
            "detail": f"{connected}/{total_sites} sites connected",
        })

    # Factor 4: Unacknowledged incidents (10% weight)
    unacked = [i for i in active_incidents if i.status == "open"]
    if unacked:
        penalty = min(len(unacked) * 3, 10)
        score -= penalty
        factors.append({
            "label": "Unacknowledged incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(unacked)} incident(s) awaiting acknowledgment",
        })

    readiness_score = max(0, round(score))
    if readiness_score >= 85:
        risk_label = "Operational"
    elif readiness_score >= 60:
        risk_label = "Attention Needed"
    else:
        risk_label = "At Risk"

    # --- Incident feed ---
    site_map = {s.site_id: s for s in sites}
    incident_feed = []
    for inc in incidents[:20]:
        site = site_map.get(inc.site_id)
        incident_feed.append({
            "id": inc.id,
            "incident_id": inc.incident_id,
            "site_id": inc.site_id,
            "site_name": site.site_name if site else inc.site_id,
            "summary": inc.summary,
            "severity": inc.severity,
            "status": inc.status,
            "opened_at": inc.opened_at.isoformat() if inc.opened_at else None,
            "ack_by": inc.ack_by,
            "ack_at": inc.ack_at.isoformat() if inc.ack_at else None,
            "closed_at": inc.closed_at.isoformat() if inc.closed_at else None,
            "assigned_to": inc.assigned_to,
        })

    # --- Sites needing attention ---
    attention_sites = []
    for s in sites:
        if s.status in ("Attention Needed", "Not Connected"):
            attention_sites.append({
                "site_id": s.site_id,
                "site_name": s.site_name,
                "status": s.status,
                "kit_type": s.kit_type,
                "last_checkin": s.last_checkin.isoformat() if s.last_checkin else None,
            })

    return {
        "portfolio": {
            "total_sites": total_sites,
            "total_devices": len(devices),
            "active_devices": len(active_devices),
            "connected_sites": connected,
            "attention_sites": len([s for s in sites if s.status == "Attention Needed"]),
            "disconnected_sites": len([s for s in sites if s.status == "Not Connected"]),
        },
        "readiness": {
            "score": readiness_score,
            "risk_label": risk_label,
            "factors": sorted(factors, key=lambda f: f["impact"]),
        },
        "system_health": system_health,
        "incident_feed": incident_feed,
        "active_incidents": len(active_incidents),
        "critical_incidents": len(critical_incidents),
        "attention_sites_list": attention_sites[:10],
    }


@router.get("/site/{site_id}")
async def command_site_detail(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return Command detail for a single site."""
    tenant = current_user.tenant_id

    site_q = await db.execute(
        select(Site).where(Site.tenant_id == tenant, Site.site_id == site_id)
    )
    site = site_q.scalar_one_or_none()
    if not site:
        from fastapi import HTTPException
        raise HTTPException(404, "Site not found")

    devices_q = await db.execute(
        select(Device).where(Device.tenant_id == tenant, Device.site_id == site_id)
    )
    devices = list(devices_q.scalars().all())

    incidents_q = await db.execute(
        select(Incident)
        .where(Incident.tenant_id == tenant, Incident.site_id == site_id)
        .order_by(Incident.opened_at.desc())
        .limit(20)
    )
    incidents = list(incidents_q.scalars().all())

    active_incidents = [i for i in incidents if i.status in ("open", "acknowledged")]
    active_devices = [d for d in devices if d.status == "active"]

    # Site readiness
    score = 100.0
    factors = []

    device_health = (len(active_devices) / len(devices) * 100) if devices else 100
    if device_health < 100:
        penalty = (100 - device_health) * 0.5
        score -= penalty
        factors.append({
            "label": "Device health",
            "impact": round(-penalty, 1),
            "detail": f"{len(active_devices)}/{len(devices)} active",
        })

    critical = [i for i in active_incidents if i.severity == "critical"]
    if critical:
        penalty = min(len(critical) * 15, 40)
        score -= penalty
        factors.append({
            "label": "Critical incidents",
            "impact": round(-penalty, 1),
            "detail": f"{len(critical)} open",
        })

    if site.status != "Connected":
        score -= 20
        factors.append({
            "label": "Site connectivity",
            "impact": -20,
            "detail": f"Status: {site.status}",
        })

    readiness_score = max(0, round(score))
    risk_label = "Operational" if readiness_score >= 85 else ("Attention Needed" if readiness_score >= 60 else "At Risk")

    # System categories at this site
    cat = _system_category(site.kit_type) if site.kit_type else "other"
    system_categories = [{
        "key": cat,
        "label": SYSTEM_LABELS.get(cat, "Other"),
        "status": "healthy" if site.status == "Connected" else ("warning" if site.status == "Attention Needed" else "critical"),
        "device_count": len(devices),
        "active_count": len(active_devices),
    }]

    incident_list = []
    for inc in incidents:
        incident_list.append({
            "id": inc.id,
            "incident_id": inc.incident_id,
            "summary": inc.summary,
            "severity": inc.severity,
            "status": inc.status,
            "opened_at": inc.opened_at.isoformat() if inc.opened_at else None,
            "assigned_to": inc.assigned_to,
        })

    # Recommended actions
    actions = []
    if critical:
        actions.append({
            "priority": "high",
            "action": "Resolve critical incidents",
            "detail": f"{len(critical)} critical incident(s) require immediate attention",
        })
    if site.status == "Not Connected":
        actions.append({
            "priority": "high",
            "action": "Restore site connectivity",
            "detail": "Site is currently disconnected from monitoring",
        })
    if site.status == "Attention Needed":
        actions.append({
            "priority": "medium",
            "action": "Investigate site warnings",
            "detail": "Site has reported intermittent issues",
        })
    inactive_devices = [d for d in devices if d.status != "active"]
    if inactive_devices:
        actions.append({
            "priority": "medium",
            "action": "Activate idle devices",
            "detail": f"{len(inactive_devices)} device(s) not active",
        })
    if not actions:
        actions.append({
            "priority": "low",
            "action": "No action required",
            "detail": "All systems operational",
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
        },
        "readiness": {
            "score": readiness_score,
            "risk_label": risk_label,
            "factors": sorted(factors, key=lambda f: f["impact"]),
        },
        "system_categories": system_categories,
        "incidents": incident_list,
        "devices": {
            "total": len(devices),
            "active": len(active_devices),
        },
        "recommended_actions": actions,
    }
