"""RBAC permission matrix — single source of truth shared with the
frontend.

The map lives in ``permissions.json`` at the repo root.  The frontend
(``web/src/contexts/AuthContext.jsx``) imports the same file via the
``@permissions`` Vite alias, so the two sides cannot drift.

To change a role's grant: edit ``permissions.json`` only.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List

_PERMISSIONS_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "permissions.json"
)


def _load_permissions() -> Dict[str, List[str]]:
    """Load the permission matrix from the shared JSON file.

    Loaded once at module import.  If the file is missing or invalid,
    raise loudly — running the API with no RBAC matrix is far worse
    than refusing to start.
    """
    try:
        raw = _PERMISSIONS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise RuntimeError(
            f"RBAC permissions file not found at {_PERMISSIONS_PATH!s}. "
            "This file is the single source of truth for the permission "
            "matrix and must exist at the repo root."
        ) from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"RBAC permissions file at {_PERMISSIONS_PATH!s} is not valid JSON: {e}"
        ) from e
    if not isinstance(data, dict):
        raise RuntimeError(
            f"RBAC permissions file at {_PERMISSIONS_PATH!s} must be a JSON object."
        )
    # Light schema check — every value must be a list of role strings.
    for action, roles in data.items():
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            raise RuntimeError(
                f"RBAC permissions[{action!r}] must be a list of role strings."
            )
    logging.getLogger("true911").info(
        "RBAC: loaded %d permissions from %s", len(data), _PERMISSIONS_PATH,
    )
    return data


PERMISSIONS: Dict[str, List[str]] = _load_permissions()


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
