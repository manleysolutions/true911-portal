"""Diagnostics adapters — pull live status from existing True911 services.

Each adapter returns a normalized DiagnosticResult dict:
    status: ok | warning | critical | unknown
    severity: info | warning | critical
    confidence: 0.0–1.0
    customer_safe_summary: plain-language for customer
    internal_summary: technical detail for admins
    raw_payload: full data dict (admin-only)

Adapters that depend on services not yet fully wired return stub results
with TODO markers for future integration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("true911.support.diagnostics")


async def check_heartbeat(db: AsyncSession, tenant_id: str, device_id: int | None = None, site_id: int | None = None) -> dict:
    """Check device heartbeat freshness."""
    from app.models.device import Device

    q = select(Device).where(Device.tenant_id == tenant_id)
    if device_id:
        q = q.where(Device.id == device_id)
    elif site_id:
        q = q.where(Device.site_id == site_id)
    else:
        q = q.limit(50)

    result = await db.execute(q)
    devices = result.scalars().all()

    if not devices:
        return _result("unknown", "info", 0.5,
                       "No devices found to check.",
                       "No devices matched the query for heartbeat check.",
                       {"device_count": 0})

    stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
    total = len(devices)
    stale = [d for d in devices if d.last_heartbeat and d.last_heartbeat < stale_threshold]
    offline = [d for d in devices if not d.last_heartbeat]

    if not stale and not offline:
        return _result("ok", "info", 0.95,
                       f"All {total} device(s) are reporting in normally.",
                       f"All {total} devices have heartbeat within last 10 minutes.",
                       {"total": total, "stale": 0, "offline": 0})

    severity = "critical" if len(stale) + len(offline) > total * 0.5 else "warning"
    return _result(severity, severity, 0.9,
                   f"{len(stale) + len(offline)} of {total} device(s) may have a connectivity issue. Our team is aware.",
                   f"{len(stale)} stale heartbeats, {len(offline)} never reported. IDs: {[d.id for d in (stale + offline)[:10]]}",
                   {"total": total, "stale": len(stale), "offline": len(offline),
                    "stale_ids": [d.id for d in stale[:10]], "offline_ids": [d.id for d in offline[:10]]})


async def check_device_status(db: AsyncSession, tenant_id: str, device_id: int | None = None, site_id: int | None = None) -> dict:
    """Check device provisioning/active status."""
    from app.models.device import Device

    q = select(Device).where(Device.tenant_id == tenant_id)
    if device_id:
        q = q.where(Device.id == device_id)
    elif site_id:
        q = q.where(Device.site_id == site_id)
    else:
        q = q.limit(50)

    result = await db.execute(q)
    devices = result.scalars().all()

    if not devices:
        return _result("unknown", "info", 0.5,
                       "No devices found.",
                       "No devices matched query.",
                       {"device_count": 0})

    by_status = {}
    for d in devices:
        by_status.setdefault(d.status, []).append(d.id)

    active = len(by_status.get("active", []))
    total = len(devices)

    if active == total:
        return _result("ok", "info", 0.95,
                       f"All {total} device(s) are active and operational.",
                       f"All {total} devices in 'active' status.",
                       {"total": total, "by_status": {k: len(v) for k, v in by_status.items()}})

    return _result("warning", "warning", 0.85,
                   f"{active} of {total} device(s) are active. Some may be in setup or maintenance.",
                   f"Device status breakdown: {', '.join(f'{k}={len(v)}' for k, v in by_status.items())}",
                   {"total": total, "by_status": {k: len(v) for k, v in by_status.items()}})


async def check_sip_registration(db: AsyncSession, tenant_id: str, device_id: int | None = None, site_id: int | None = None) -> dict:
    """Check SIP registration state. TODO: Wire to actual SIP monitoring when available."""
    # Stub — SIP registration monitoring is not yet integrated
    return _result("unknown", "info", 0.3,
                   "Voice registration status is being checked. If you're experiencing call issues, we can escalate to our team.",
                   "SIP registration adapter not yet connected to live SIP monitoring. Returning stub.",
                   {"stub": True, "todo": "Connect to SIP registrar monitoring service"})


async def check_telemetry(db: AsyncSession, tenant_id: str, device_id: int | None = None, site_id: int | None = None) -> dict:
    """Check recent telemetry/signal data."""
    from app.models.telemetry_event import TelemetryEvent

    q = select(func.count()).select_from(TelemetryEvent).where(TelemetryEvent.tenant_id == tenant_id)
    if site_id:
        q = q.where(TelemetryEvent.site_id == site_id)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    q = q.where(TelemetryEvent.created_at >= cutoff)

    result = await db.execute(q)
    count = result.scalar() or 0

    if count > 0:
        return _result("ok", "info", 0.8,
                       "Your system is reporting data normally.",
                       f"{count} telemetry events in the last hour.",
                       {"recent_event_count": count})

    return _result("warning", "warning", 0.6,
                   "We haven't received recent data from your system. This may be temporary.",
                   f"Zero telemetry events in the last hour for tenant={tenant_id} site={site_id}.",
                   {"recent_event_count": 0})


async def check_ata_reachability(db: AsyncSession, tenant_id: str, device_id: int | None = None, site_id: int | None = None) -> dict:
    """Check ATA device reachability. TODO: Wire to actual ping/SNMP checks when available."""
    # Stub — ATA reachability monitoring requires network probe integration
    return _result("unknown", "info", 0.3,
                   "Checking device reachability. If your phone isn't connecting, we can run a deeper test.",
                   "ATA reachability adapter not yet connected. Returning stub.",
                   {"stub": True, "todo": "Connect to network probe or VOLA status API"})


async def check_recent_incidents(db: AsyncSession, tenant_id: str, device_id: int | None = None, site_id: int | None = None) -> dict:
    """Summarize recent open incidents without exposing raw data to customers."""
    from app.models.incident import Incident

    q = select(Incident).where(
        Incident.tenant_id == tenant_id,
        Incident.status.in_(["open", "acknowledged"]),
    )
    if site_id:
        q = q.where(Incident.site_id == site_id)
    q = q.limit(20)

    result = await db.execute(q)
    incidents = result.scalars().all()

    if not incidents:
        return _result("ok", "info", 0.9,
                       "No active issues found for your account.",
                       "Zero open/acknowledged incidents.",
                       {"open_count": 0})

    critical = sum(1 for i in incidents if i.severity == "critical")
    total = len(incidents)
    severity = "critical" if critical > 0 else "warning"

    return _result(severity, severity, 0.9,
                   f"We're aware of {total} active issue(s) affecting your service. Our team is monitoring the situation.",
                   f"{total} open incidents ({critical} critical). IDs: {[i.incident_id for i in incidents[:5]]}",
                   {"open_count": total, "critical_count": critical,
                    "incident_ids": [i.incident_id for i in incidents[:10]]})


async def check_e911_completeness(db: AsyncSession, tenant_id: str, site_id: int | None = None) -> dict:
    """Check E911 address completeness for sites."""
    from app.models.site import Site

    q = select(Site).where(Site.tenant_id == tenant_id)
    if site_id:
        q = q.where(Site.id == site_id)
    else:
        q = q.limit(100)

    result = await db.execute(q)
    sites = result.scalars().all()

    if not sites:
        return _result("unknown", "info", 0.5,
                       "No sites found to check.",
                       "No sites matched the query.",
                       {"site_count": 0})

    missing = [s for s in sites if not s.address or not s.city or not s.state]
    total = len(sites)

    if not missing:
        return _result("ok", "info", 0.9,
                       f"E911 address information is complete for all {total} site(s).",
                       f"All {total} sites have address, city, and state.",
                       {"total": total, "incomplete": 0})

    return _result("warning", "warning", 0.85,
                   f"{len(missing)} of {total} site(s) may need address information updated for E911 compliance.",
                   f"{len(missing)} sites missing address/city/state. IDs: {[s.id for s in missing[:10]]}",
                   {"total": total, "incomplete": len(missing),
                    "incomplete_ids": [s.id for s in missing[:10]]})


async def check_zoho_tickets(db: AsyncSession, tenant_id: str, **kwargs) -> dict:
    """Look up existing Zoho Desk tickets for this tenant. TODO: Wire to Zoho Desk API."""
    # Stub — Zoho Desk integration not yet wired
    return _result("unknown", "info", 0.2,
                   "Checking for any existing support tickets on your account.",
                   "Zoho Desk ticket lookup not yet integrated. Returning stub.",
                   {"stub": True, "todo": "Connect to Zoho Desk API"})


# ── Registry ────────────────────────────────────────────────────

DIAGNOSTIC_CHECKS = {
    "heartbeat": check_heartbeat,
    "device_status": check_device_status,
    "sip_registration": check_sip_registration,
    "telemetry": check_telemetry,
    "ata_reachability": check_ata_reachability,
    "incidents": check_recent_incidents,
    "e911": check_e911_completeness,
    "zoho_ticket": check_zoho_tickets,
}

ALL_CHECK_TYPES = list(DIAGNOSTIC_CHECKS.keys())


async def run_diagnostics(
    db: AsyncSession,
    tenant_id: str,
    checks: list[str] | None = None,
    device_id: int | None = None,
    site_id: int | None = None,
) -> list[dict]:
    """Run specified (or all) diagnostic checks and return normalized results."""
    check_names = checks or ALL_CHECK_TYPES
    results = []
    for name in check_names:
        fn = DIAGNOSTIC_CHECKS.get(name)
        if not fn:
            continue
        try:
            r = await fn(db, tenant_id, device_id=device_id, site_id=site_id)
            r["check_type"] = name
            results.append(r)
        except Exception as exc:
            logger.exception("Diagnostic check %s failed", name)
            results.append({
                "check_type": name,
                **_result("unknown", "info", 0.1,
                          "This check is temporarily unavailable.",
                          f"Check {name} raised {type(exc).__name__}: {exc}",
                          {"error": str(exc)})
            })
    return results


def _result(status: str, severity: str, confidence: float,
            customer_safe_summary: str, internal_summary: str,
            raw_payload: dict | None = None) -> dict:
    return {
        "status": status,
        "severity": severity,
        "confidence": confidence,
        "customer_safe_summary": customer_safe_summary,
        "internal_summary": internal_summary,
        "raw_payload": raw_payload,
    }
