"""Triage / diagnostic hooks for a support session.

Prepares the diagnostic surface the spec calls for — device health, last
seen, carrier/SIM status, SIP/ATA registration, signal strength, recent
events, open tickets, billing/service status — WITHOUT requiring every
integration to be live.  Each hook degrades gracefully: when the data
source is not wired yet (or the device is unknown) the check returns
``unavailable`` rather than failing the whole triage.

All reads are scoped to ``session.matched_tenant_id`` — triage only runs
after caller verification (enforced by the router), so cross-tenant
exposure is impossible here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device

# Order matters — first the device-state checks, then service/billing.
_CHECK_ORDER = [
    "device_health",
    "last_seen",
    "carrier_sim_status",
    "sip_ata_registration",
    "signal_strength",
    "recent_events",
    "open_tickets",
    "billing_service_status",
]

_UNAVAILABLE = "Diagnostic source not yet integrated for this session."


def _check(check: str, status: str, summary: str, detail: Optional[dict] = None) -> dict:
    return {"check": check, "status": status, "customer_safe_summary": summary, "detail": detail}


async def _load_device(db: AsyncSession, tenant_id: str, device_id: str) -> Optional[Device]:
    q = select(Device).where(Device.device_id == device_id, Device.tenant_id == tenant_id)
    return (await db.execute(q)).scalar_one_or_none()


def _hours_since(ts: Optional[datetime]) -> Optional[float]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0


async def run_triage(db: AsyncSession, session) -> dict:
    """Run the diagnostic hooks for *session*.  Returns a dict shaped for
    :class:`app.schemas.ops_center.TriageResponse`."""
    checks: list[dict] = []
    device: Optional[Device] = None

    if session.matched_device_id and session.matched_tenant_id:
        device = await _load_device(db, session.matched_tenant_id, session.matched_device_id)

    # ── device_health ────────────────────────────────────────────────
    if device is not None:
        status_map = {"active": "ok", "provisioning": "warning", "inactive": "critical", "decommissioned": "critical"}
        dev_status = (device.status or "").lower()
        checks.append(
            _check(
                "device_health",
                status_map.get(dev_status, "unknown"),
                f"Device status is '{device.status or 'unknown'}'.",
                {"device_status": device.status},
            )
        )
    else:
        checks.append(_check("device_health", "unavailable", "No device is linked to this session yet.", None))

    # ── last_seen ────────────────────────────────────────────────────
    if device is not None:
        hrs = _hours_since(getattr(device, "last_heartbeat", None))
        if hrs is None:
            checks.append(_check("last_seen", "unknown", "No recent check-in recorded for this device.", None))
        elif hrs <= 1:
            checks.append(_check("last_seen", "ok", "Device checked in within the last hour.", {"hours_since": round(hrs, 2)}))
        elif hrs <= 24:
            checks.append(_check("last_seen", "warning", f"Last check-in was about {round(hrs)} hours ago.", {"hours_since": round(hrs, 2)}))
        else:
            checks.append(_check("last_seen", "critical", f"No check-in for about {round(hrs / 24)} day(s).", {"hours_since": round(hrs, 2)}))
    else:
        checks.append(_check("last_seen", "unavailable", _UNAVAILABLE, None))

    # ── carrier_sim_status (stub — SIM/carrier integration not wired) ─
    if device is not None and getattr(device, "iccid", None):
        checks.append(
            _check(
                "carrier_sim_status",
                "unknown",
                "A SIM is on record; live carrier status check is not yet enabled.",
                {"iccid_on_file": True},
            )
        )
    else:
        checks.append(_check("carrier_sim_status", "unavailable", _UNAVAILABLE, None))

    # ── sip_ata_registration (stub) ──────────────────────────────────
    checks.append(_check("sip_ata_registration", "unavailable", _UNAVAILABLE, None))

    # ── signal_strength (stub) ───────────────────────────────────────
    checks.append(_check("signal_strength", "unavailable", _UNAVAILABLE, None))

    # ── recent_events (stub) ─────────────────────────────────────────
    checks.append(_check("recent_events", "unavailable", _UNAVAILABLE, None))

    # ── open_tickets (stub — Zoho Desk lookup not wired here) ────────
    checks.append(_check("open_tickets", "unavailable", _UNAVAILABLE, None))

    # ── billing_service_status (stub — never exposed pre-verification) ─
    checks.append(_check("billing_service_status", "unavailable", _UNAVAILABLE, None))

    # ── Roll up an overall severity ──────────────────────────────────
    severities = {c["status"] for c in checks}
    if "critical" in severities:
        overall = "critical"
    elif "warning" in severities:
        overall = "attention"
    elif {"ok"} & severities:
        overall = "ok"
    else:
        overall = "unknown"

    recommended = _recommend(session.issue_category, overall, checks)

    return {
        "session_id": session.id,
        "issue_category": session.issue_category,
        "overall": overall,
        "checks": checks,
        "recommended_action": recommended,
    }


def _recommend(issue_category: Optional[str], overall: str, checks: list[dict]) -> str:
    by_name = {c["check"]: c for c in checks}
    last_seen = by_name.get("last_seen", {})
    if last_seen.get("status") == "critical":
        return "Device has not checked in recently — dispatch a field check / verify power and connectivity, then escalate."
    if overall == "critical":
        return "Critical device condition detected — escalate to Tier-2 with the handoff summary."
    if issue_category == "no_dial_tone":
        return "Confirm line power and ATA registration on site; if unresolved, escalate to Tier-2 voice."
    if overall == "ok":
        return "No fault detected from available diagnostics — confirm the reported symptom with the caller before escalating."
    return "Diagnostics inconclusive (integrations pending) — gather caller detail and escalate to a human agent."
