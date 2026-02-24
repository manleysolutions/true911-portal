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
    "VOLA_ADMIN": ["Admin"],
}


def can(role: str, action: str) -> bool:
    return role in PERMISSIONS.get(action, [])
