"""Server-side device actions — replaces client-side simulation in actions.jsx.

Each action:
1. Checks RBAC permission
2. Creates an ActionAudit record
3. Optionally creates a TelemetryEvent
4. Updates the Site record (e.g. last_checkin for ping)
5. Returns a result payload
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.action_audit import ActionAudit
from ..models.telemetry_event import TelemetryEvent
from ..models.site import Site
from ..models.e911_change_log import E911ChangeLog
from ..models.user import User

router = APIRouter(prefix="/actions", tags=["actions"])


# ── Request schemas ──────────────────────────────────────────────

class SiteAction(BaseModel):
    site_id: str


class E911Action(BaseModel):
    site_id: str
    street: str
    city: str
    state: str
    zip: str


class HeartbeatAction(BaseModel):
    site_id: str
    interval_minutes: int


class ContainerAction(BaseModel):
    site_id: str
    container_name: str | None = None


class ChannelAction(BaseModel):
    site_id: str
    channel: str


# ── Helpers ──────────────────────────────────────────────────────

def _uid(prefix: str = "REQ") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_site(db: AsyncSession, site_id: str, tenant_id: str) -> Site:
    q = select(Site).where(Site.site_id == site_id, Site.tenant_id == tenant_id)
    site = (await db.execute(q)).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Site not found")
    return site


async def _audit(db: AsyncSession, user: User, action_type: str, site_id: str, result: str, details: str = "") -> ActionAudit:
    audit = ActionAudit(
        audit_id=_uid("AUD"),
        request_id=_uid("REQ"),
        tenant_id=user.tenant_id,
        user_email=user.email,
        requester_name=user.name,
        role=user.role,
        action_type=action_type,
        site_id=site_id,
        timestamp=_now(),
        result=result,
        details=details,
    )
    db.add(audit)
    return audit


async def _telemetry(db: AsyncSession, tenant_id: str, site_id: str, category: str, severity: str, message: str):
    event = TelemetryEvent(
        event_id=_uid("EVT"),
        site_id=site_id,
        tenant_id=tenant_id,
        timestamp=_now(),
        category=category,
        severity=severity,
        message=message,
    )
    db.add(event)


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/ping", dependencies=[Depends(require_permission("PING"))])
async def ping_device(
    body: SiteAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = await _get_site(db, body.site_id, current_user.tenant_id)
    now = _now()

    # Simulate ping result based on current status
    success = site.status != "Not Connected"
    latency = 42 if success else None

    site.last_checkin = now
    await _audit(db, current_user, "PING", body.site_id, "success" if success else "failure",
                 f"Ping {'OK' if success else 'FAILED'} — latency {latency}ms" if success else "Ping timed out")
    await _telemetry(db, current_user.tenant_id, body.site_id, "network", "info",
                     f"Ping from {current_user.name}: {'OK' if success else 'FAILED'}")

    await db.commit()
    return {
        "success": success,
        "message": f"Ping {'successful' if success else 'failed'} — {latency}ms latency" if success else "Ping timed out — device unreachable",
        "latency_ms": latency,
    }


@router.post("/reboot", dependencies=[Depends(require_permission("REBOOT"))])
async def reboot_device(
    body: SiteAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = await _get_site(db, body.site_id, current_user.tenant_id)

    site.status = "Attention Needed"
    await _audit(db, current_user, "REBOOT", body.site_id, "success", "Remote reboot initiated")
    await _telemetry(db, current_user.tenant_id, body.site_id, "system", "warning",
                     f"Reboot initiated by {current_user.name}")
    await db.commit()
    return {"success": True, "message": "Reboot initiated. Device will return online within ~45 seconds."}


@router.post("/update-e911", dependencies=[Depends(require_permission("UPDATE_E911"))])
async def update_e911(
    body: E911Action,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = await _get_site(db, body.site_id, current_user.tenant_id)

    old = {"street": site.e911_street, "city": site.e911_city, "state": site.e911_state, "zip": site.e911_zip}

    site.e911_street = body.street
    site.e911_city = body.city
    site.e911_state = body.state
    site.e911_zip = body.zip

    await _audit(db, current_user, "UPDATE_E911", body.site_id, "success",
                 f"E911 updated: {old['street']} → {body.street}")
    await _telemetry(db, current_user.tenant_id, body.site_id, "e911", "info",
                     f"E911 address updated by {current_user.name}")
    await db.commit()
    return {"success": True, "message": "E911 address updated successfully."}


@router.post("/update-heartbeat", dependencies=[Depends(require_permission("UPDATE_HEARTBEAT"))])
async def update_heartbeat(
    body: HeartbeatAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = await _get_site(db, body.site_id, current_user.tenant_id)

    site.heartbeat_interval = body.interval_minutes
    await _audit(db, current_user, "UPDATE_HEARTBEAT", body.site_id, "success",
                 f"Heartbeat interval set to {body.interval_minutes}m")
    await db.commit()
    return {"success": True, "message": f"Heartbeat interval updated to {body.interval_minutes} minutes."}


@router.post("/restart-container", dependencies=[Depends(require_permission("RESTART_CONTAINER"))])
async def restart_container(
    body: ContainerAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_site(db, body.site_id, current_user.tenant_id)
    name = body.container_name or "primary"

    await _audit(db, current_user, "RESTART_CONTAINER", body.site_id, "success",
                 f"Container '{name}' restarted")
    await _telemetry(db, current_user.tenant_id, body.site_id, "system", "warning",
                     f"Container '{name}' restarted by {current_user.name}")
    await db.commit()
    return {"success": True, "message": f"Container '{name}' restart initiated."}


@router.post("/pull-logs", dependencies=[Depends(require_permission("PULL_LOGS"))])
async def pull_logs(
    body: ContainerAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_site(db, body.site_id, current_user.tenant_id)
    name = body.container_name or "primary"

    await _audit(db, current_user, "PULL_LOGS", body.site_id, "success",
                 f"Logs pulled for container '{name}'")
    await db.commit()
    return {
        "success": True,
        "message": f"Logs retrieved for container '{name}'.",
        "logs": [
            f"[INFO] Container '{name}' healthy — uptime 47h",
            f"[INFO] Last restart: none since deploy",
            f"[DEBUG] Memory usage: 128MB / 512MB",
        ],
    }


@router.post("/switch-channel", dependencies=[Depends(require_permission("SWITCH_CHANNEL"))])
async def switch_channel(
    body: ChannelAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = await _get_site(db, body.site_id, current_user.tenant_id)

    old_channel = site.update_channel or "stable"
    site.update_channel = body.channel

    await _audit(db, current_user, "SWITCH_CHANNEL", body.site_id, "success",
                 f"Channel switched: {old_channel} → {body.channel}")
    await _telemetry(db, current_user.tenant_id, body.site_id, "system", "info",
                     f"Update channel switched to '{body.channel}' by {current_user.name}")
    await db.commit()
    return {"success": True, "message": f"Update channel switched to '{body.channel}'."}
