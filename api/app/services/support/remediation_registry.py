"""Remediation action registry — explicit mapping of issue types to safe actions.

Every action that the self-healing engine can run MUST be registered here.
This is the allow-list. Actions not in this registry cannot be executed.

SAFETY: Only Tier 1 (safe) and gated Tier 2 actions are registered.
Dangerous actions (reboot, reprovision, E911 changes) are deliberately absent.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionDefinition:
    """Definition of a remediation action."""
    action_type: str
    level: str          # safe | low_risk | gated
    description: str
    cooldown_minutes: int
    max_attempts_24h: int
    verification_required: bool
    enabled: bool       # gated actions default to False


# ═══════════════════════════════════════════════════════════════════
# ACTION DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

ACTIONS: dict[str, ActionDefinition] = {
    # ── Tier 1: Safe (always enabled) ──
    "refresh_diagnostics": ActionDefinition(
        action_type="refresh_diagnostics",
        level="safe",
        description="Re-run full diagnostic suite",
        cooldown_minutes=5,
        max_attempts_24h=10,
        verification_required=True,
        enabled=True,
    ),
    "refresh_device_status": ActionDefinition(
        action_type="refresh_device_status",
        level="safe",
        description="Re-check device provisioning and heartbeat status",
        cooldown_minutes=5,
        max_attempts_24h=10,
        verification_required=True,
        enabled=True,
    ),
    "refresh_telemetry": ActionDefinition(
        action_type="refresh_telemetry",
        level="safe",
        description="Re-query telemetry data for freshness",
        cooldown_minutes=5,
        max_attempts_24h=10,
        verification_required=True,
        enabled=True,
    ),
    "retry_voice_check": ActionDefinition(
        action_type="retry_voice_check",
        level="safe",
        description="Re-check SIP/voice registration status",
        cooldown_minutes=10,
        max_attempts_24h=6,
        verification_required=True,
        enabled=True,
    ),
    "retry_connectivity_check": ActionDefinition(
        action_type="retry_connectivity_check",
        level="safe",
        description="Re-check device connectivity and reachability",
        cooldown_minutes=10,
        max_attempts_24h=6,
        verification_required=True,
        enabled=True,
    ),
    "retry_zoho_sync": ActionDefinition(
        action_type="retry_zoho_sync",
        level="safe",
        description="Retry failed Zoho Desk ticket sync",
        cooldown_minutes=15,
        max_attempts_24h=5,
        verification_required=True,
        enabled=True,
    ),

    # ── Tier 2: Gated (disabled by default) ──
    "recheck_after_delay": ActionDefinition(
        action_type="recheck_after_delay",
        level="low_risk",
        description="Wait and re-check diagnostics after a short delay",
        cooldown_minutes=15,
        max_attempts_24h=4,
        verification_required=True,
        enabled=True,  # Safe enough to enable — just a delayed re-check
    ),
    "check_backup_path": ActionDefinition(
        action_type="check_backup_path",
        level="low_risk",
        description="Verify backup connectivity path availability",
        cooldown_minutes=15,
        max_attempts_24h=4,
        verification_required=True,
        enabled=True,  # Read-only check
    ),
    "restart_local_monitoring_service": ActionDefinition(
        action_type="restart_local_monitoring_service",
        level="gated",
        description="Restart internal monitoring process (not customer-visible)",
        cooldown_minutes=240,  # 4 hours
        max_attempts_24h=1,
        verification_required=True,
        enabled=False,  # Disabled by default — must be explicitly enabled
    ),
}

# ═══════════════════════════════════════════════════════════════════
# ISSUE-TO-ACTION MAPPING
# ═══════════════════════════════════════════════════════════════════

ISSUE_ACTION_MAP: dict[str, list[str]] = {
    "telemetry_stale": ["refresh_telemetry", "recheck_after_delay"],
    "heartbeat_missed": ["refresh_device_status", "refresh_diagnostics", "recheck_after_delay"],
    "device_offline": ["refresh_device_status", "retry_connectivity_check", "recheck_after_delay"],
    "voice_quality": ["retry_voice_check", "refresh_diagnostics"],
    "sip_warning": ["retry_voice_check", "recheck_after_delay"],
    "connectivity_warning": ["retry_connectivity_check", "check_backup_path", "recheck_after_delay"],
    "zoho_sync_failed": ["retry_zoho_sync"],
    "e911_incomplete": [],  # No safe auto-remediation — requires human action
    "general": ["refresh_diagnostics"],
}

# ═══════════════════════════════════════════════════════════════════
# BLOCKED ACTIONS (explicit deny-list for safety documentation)
# ═══════════════════════════════════════════════════════════════════

BLOCKED_ACTIONS: set[str] = {
    "reboot_device",
    "reboot_modem",
    "reboot_ata",
    "reprovision_device",
    "modify_e911",
    "force_transport_switch",
    "restart_customer_service",
}


def get_action(action_type: str) -> ActionDefinition | None:
    """Get an action definition by type. Returns None if not registered."""
    return ACTIONS.get(action_type)


def get_actions_for_issue(issue_category: str) -> list[ActionDefinition]:
    """Get enabled actions for an issue category."""
    action_types = ISSUE_ACTION_MAP.get(issue_category, ISSUE_ACTION_MAP["general"])
    return [ACTIONS[t] for t in action_types if t in ACTIONS and ACTIONS[t].enabled]


def is_blocked(action_type: str) -> bool:
    """Check if an action is on the explicit deny-list."""
    return action_type in BLOCKED_ACTIONS
