"""RBAC permission matrix — ported from web/src/components/AuthContext.jsx."""

PERMISSIONS: dict[str, list[str]] = {
    "PING": ["Admin", "Manager"],
    "REBOOT": ["Admin"],
    "GENERATE_REPORT": ["Admin", "Manager"],
    "UPDATE_E911": ["Admin"],
    "UPDATE_HEARTBEAT": ["Admin"],
    "VIEW_ADMIN": ["Admin"],
    "RESTART_CONTAINER": ["Admin"],
    "PULL_LOGS": ["Admin"],
    "SWITCH_CHANNEL": ["Admin"],
    "ACK_INCIDENT": ["Admin", "Manager"],
    "CLOSE_INCIDENT": ["Admin", "Manager"],
    "MANAGE_NOTIFICATIONS": ["Admin"],
    "MANAGE_PROVIDERS": ["Admin"],
    "ROTATE_DEVICE_KEY": ["Admin"],
    "MANAGE_USERS": ["Admin"],
    "MANAGE_SIMS": ["Admin"],
    "VIEW_JOBS": ["Admin", "Manager"],
    "MANAGE_INTEGRATIONS": ["Admin"],
    "VIEW_INTEGRATIONS": ["Admin", "Manager"],
    "RUN_RECONCILIATION": ["Admin"],
    "GLOBAL_ADMIN": ["SuperAdmin"],
    # Command Phase 2
    "COMMAND_ACK": ["Admin", "Manager"],
    "COMMAND_ASSIGN": ["Admin", "Manager"],
    "COMMAND_RESOLVE": ["Admin", "Manager"],
    "COMMAND_DISMISS": ["Admin"],
    "COMMAND_CREATE_INCIDENT": ["Admin", "Manager"],
    # Command Phase 3
    "COMMAND_VIEW_NOTIFICATIONS": ["Admin", "Manager", "User"],
    "COMMAND_MANAGE_ESCALATION": ["Admin"],
    "COMMAND_INGEST_TELEMETRY": ["Admin", "Manager"],
    "COMMAND_EXPORT_REPORTS": ["Admin", "Manager"],
    # Command Phase 4
    "COMMAND_MANAGE_VENDORS": ["Admin"],
    "COMMAND_VIEW_VENDORS": ["Admin", "Manager", "User"],
    "COMMAND_MANAGE_VERIFICATION": ["Admin", "Manager"],
    "COMMAND_COMPLETE_VERIFICATION": ["Admin", "Manager"],
    "COMMAND_VIEW_VERIFICATION": ["Admin", "Manager", "User"],
    "COMMAND_MANAGE_AUTOMATION": ["Admin"],
    "COMMAND_VIEW_OPERATOR": ["Admin", "Manager", "User"],
}


def can(role: str, action: str) -> bool:
    if role == "SuperAdmin":
        return True
    return role in PERMISSIONS.get(action, [])
