"""RBAC permission matrix — ported from web/src/components/AuthContext.jsx."""

PERMISSIONS: dict[str, list[str]] = {
    "PING": ["Admin", "Manager"],
    "REBOOT": ["Admin"],
    "GENERATE_REPORT": ["Admin", "Manager"],
    "UPDATE_E911": ["Admin"],
    "UPDATE_HEARTBEAT": ["Admin"],
    "VIEW_ADMIN": ["Admin", "SuperAdmin"],
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
    "MANAGE_CUSTOMERS": ["Admin"],
    "VIEW_CUSTOMERS": ["Admin", "Manager", "DataEntry"],
    "CREATE_CUSTOMERS": ["Admin", "DataEntry"],
    "EDIT_CUSTOMERS": ["Admin", "DataEntry"],
    "DELETE_CUSTOMERS": ["Admin"],
    "VIEW_SITES": ["Admin", "Manager", "User", "DataEntry"],
    "CREATE_SITES": ["Admin", "Manager", "DataEntry"],
    "EDIT_SITES": ["Admin", "Manager", "DataEntry"],
    "DELETE_SITES": ["Admin"],
    "VIEW_DEVICES": ["Admin", "Manager", "User", "DataEntry"],
    "CREATE_DEVICES": ["Admin", "Manager", "DataEntry"],
    "EDIT_DEVICES": ["Admin", "Manager", "DataEntry"],
    "DELETE_DEVICES": ["Admin", "Manager"],
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
    # Command Phase 5
    "COMMAND_MANAGE_TEMPLATES": ["Admin"],
    "COMMAND_VIEW_TEMPLATES": ["Admin", "Manager", "User"],
    "COMMAND_BULK_IMPORT": ["Admin"],
    "COMMAND_MANAGE_WEBHOOKS": ["Admin"],
    "COMMAND_VIEW_CONTRACTS": ["Admin", "Manager"],
    "COMMAND_MANAGE_ORG": ["Admin"],
    "COMMAND_VIEW_ORG": ["Admin", "Manager", "User"],
    # Command Phase 7
    "COMMAND_VIEW_NETWORK": ["Admin", "Manager", "User"],
    "COMMAND_MANAGE_NETWORK": ["Admin"],
    "COMMAND_INGEST_CARRIER": ["Admin"],
    "COMMAND_MANAGE_INFRA_TESTS": ["Admin", "Manager"],
    "COMMAND_RUN_INFRA_TESTS": ["Admin", "Manager"],
    "COMMAND_VIEW_INFRA_TESTS": ["Admin", "Manager", "User"],
    "COMMAND_VIEW_AUDIT": ["Admin", "Manager"],
    "COMMAND_EXPORT_AUDIT": ["Admin"],
    # Command Phase 8
    "COMMAND_VIEW_AUTO_OPS": ["Admin", "Manager", "User"],
    "COMMAND_MANAGE_AUTO_OPS": ["Admin"],
    "COMMAND_RUN_ENGINE": ["Admin"],
    "COMMAND_VIEW_DIGESTS": ["Admin", "Manager"],
    "COMMAND_GENERATE_DIGEST": ["Admin"],
    "COMMAND_VIEW_AUTO_LOG": ["Admin", "Manager", "User"],
    # Site Import
    "COMMAND_SITE_IMPORT": ["Admin", "DataEntry"],
    # Subscriber Import
    "SUBSCRIBER_IMPORT": ["Admin", "DataEntry"],
    # Line / service-unit destructive actions
    "DELETE_LINES": ["Admin", "Manager"],
    "DELETE_SERVICE_UNITS": ["Admin"],
    # Device management
    "MANAGE_DEVICES": ["Admin"],
    # Import verification (DataEntry can view and manage but not delete)
    "VIEW_IMPORT_VERIFICATION": ["Admin", "Manager", "DataEntry"],
    "MANAGE_IMPORT_VERIFICATION": ["Admin", "DataEntry"],
    # Provisioning queue (unassigned devices)
    "VIEW_PROVISIONING_QUEUE": ["Admin", "DataEntry"],
    "MANAGE_PROVISIONING": ["Admin"],
}


ROLE_NORMALIZE = {
    "superadmin": "SuperAdmin",
    "admin": "Admin",
    "manager": "Manager",
    "user": "User",
    "dataentry": "DataEntry",
    "data entry": "DataEntry",
    "data entry / import operator": "DataEntry",
}


def normalize_role(role: str) -> str:
    """Normalize role string to canonical PascalCase."""
    if not role:
        return "User"
    return ROLE_NORMALIZE.get(role.lower(), role)


def can(role: str, action: str) -> bool:
    role = normalize_role(role)
    if role == "SuperAdmin":
        return True
    return role in PERMISSIONS.get(action, [])
