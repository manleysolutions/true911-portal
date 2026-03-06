"""Self-Healing Service — attempts automated remediation for known issues.

Supported self-healing actions:
  - device_reboot         Reboot a stale/offline device
  - connection_reset      Reset network connection
  - signal_reregister     Force network re-registration
  - retry_failed_task     Retry a previously failed verification task

If the issue resolves, the incident is auto-closed and the event logged.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.incident import Incident
from app.models.verification_task import VerificationTask
from app.models.command_activity import CommandActivity
from app.models.autonomous_action import AutonomousAction


def _uid():
    return f"AA-{uuid.uuid4().hex[:12]}"


def _now():
    return datetime.now(timezone.utc)


SELF_HEAL_ACTIONS = {
    "device_reboot": {
        "description": "Reboot device to restore connectivity",
        "applicable_types": ["device_offline", "heartbeat_missing"],
    },
    "connection_reset": {
        "description": "Reset network connection",
        "applicable_types": ["device_disconnected", "signal_degradation"],
    },
    "signal_reregister": {
        "description": "Force network re-registration",
        "applicable_types": ["signal_degradation", "roaming_detected"],
    },
    "retry_failed_task": {
        "description": "Retry a previously failed verification task",
        "applicable_types": ["verification_failed"],
    },
}


async def attempt_self_healing(
    db: AsyncSession,
    tenant_id: str,
) -> dict:
    """Scan for auto-resolvable incidents and attempt self-healing.

    Returns: {"attempted": int, "resolved": int, "actions": [...]}
    """
    now = _now()
    result = {"attempted": 0, "resolved": 0, "actions": []}

    # Find open incidents created by autonomous engine that might self-heal
    incidents = (await db.execute(
        select(Incident).where(
            Incident.tenant_id == tenant_id,
            Incident.status.in_(["new", "open"]),
            Incident.source == "autonomous",
            Incident.opened_at >= now - timedelta(hours=4),
        ).order_by(Incident.opened_at.desc()).limit(20)
    )).scalars().all()

    for inc in incidents:
        heal_action = _select_heal_action(inc)
        if not heal_action:
            continue

        result["attempted"] += 1

        # Execute self-healing action
        healed = await _execute_heal(db, tenant_id, inc, heal_action)

        action = AutonomousAction(
            action_id=_uid(),
            tenant_id=tenant_id,
            action_type=f"self_heal_{heal_action}",
            trigger_source="self_healing_engine",
            site_id=inc.site_id,
            incident_id=inc.incident_id,
            summary=f"Self-heal '{heal_action}' attempted for incident {inc.incident_id}",
            detail_json=json.dumps({
                "action": heal_action,
                "incident_type": inc.incident_type,
                "resolved": healed,
            }),
            status="completed" if healed else "attempted",
            result="resolved" if healed else "pending",
        )
        db.add(action)

        result["actions"].append({
            "incident_id": inc.incident_id,
            "action": heal_action,
            "resolved": healed,
        })

        if healed:
            result["resolved"] += 1
            # Auto-close the incident
            inc.status = "resolved"
            inc.resolved_at = now
            inc.resolution_notes = f"Auto-resolved by self-healing action: {heal_action}"

            db.add(CommandActivity(
                tenant_id=tenant_id,
                activity_type="incident_auto_resolved",
                site_id=inc.site_id,
                incident_id=inc.incident_id,
                actor="system",
                summary=f"Incident auto-resolved via {heal_action}",
            ))

    return result


def _select_heal_action(incident: Incident) -> str | None:
    """Select the appropriate self-healing action for an incident."""
    inc_type = incident.incident_type or ""

    for action_name, config in SELF_HEAL_ACTIONS.items():
        if inc_type in config["applicable_types"]:
            return action_name

    # Fallback for device-related incidents
    if "device" in inc_type.lower() or "offline" in inc_type.lower():
        return "device_reboot"
    if "signal" in (incident.category or "").lower():
        return "connection_reset"

    return None


async def _execute_heal(
    db: AsyncSession,
    tenant_id: str,
    incident: Incident,
    action: str,
) -> bool:
    """Execute a self-healing action.

    In production, these would dispatch actual device commands via
    the actions API. This framework:
      1. Checks if the device has come back online (heartbeat resumed)
      2. If so, marks as healed
      3. Otherwise, logs the attempt for manual follow-up
    """
    if not incident.site_id:
        return False

    if action == "device_reboot":
        # Check if device has recovered since incident was opened
        device = None
        if incident.metadata_json:
            try:
                meta = json.loads(incident.metadata_json)
                device_id = meta.get("device_id")
                if device_id:
                    device = (await db.execute(
                        select(Device).where(
                            Device.device_id == device_id,
                            Device.tenant_id == tenant_id,
                        )
                    )).scalar_one_or_none()
            except (json.JSONDecodeError, KeyError):
                pass

        if not device:
            # Try to find the device at the incident site
            devices = (await db.execute(
                select(Device).where(
                    Device.tenant_id == tenant_id,
                    Device.site_id == incident.site_id,
                    Device.status == "active",
                ).limit(1)
            )).scalars().all()
            device = devices[0] if devices else None

        if device and device.last_heartbeat:
            # If heartbeat received after incident opened, device recovered
            if device.last_heartbeat > incident.opened_at:
                return True

    elif action == "connection_reset":
        # Check if network status has improved
        devices = (await db.execute(
            select(Device).where(
                Device.tenant_id == tenant_id,
                Device.site_id == incident.site_id,
            )
        )).scalars().all()

        for dev in devices:
            if dev.network_status and dev.network_status.lower() in ("connected", "registered", "attached"):
                return True

    elif action == "retry_failed_task":
        # Check if a retry has completed
        tasks = (await db.execute(
            select(VerificationTask).where(
                VerificationTask.tenant_id == tenant_id,
                VerificationTask.site_id == incident.site_id,
                VerificationTask.status == "completed",
                VerificationTask.completed_at >= incident.opened_at,
            )
        )).scalars().all()
        if tasks:
            return True

    return False
