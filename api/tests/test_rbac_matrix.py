"""Guard the RBAC matrix against drift.

These tests load ``permissions.json`` directly and assert that
``app.services.rbac`` agrees with it for every cell.  They also pin
the role-normalization rules so a future case-shifted DB value (e.g.
``"data entry / import operator"``) keeps resolving to ``"DataEntry"``.

If a permission is added to or removed from ``permissions.json``, these
tests automatically pick it up — there is no second list to update.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pytest

from app.services import rbac

# Resolve the repo-root permissions file independently of rbac's own
# loader so a regression in rbac doesn't hide itself.
_PERMISSIONS_PATH = Path(__file__).resolve().parents[2] / "permissions.json"

ALL_ROLES = ["SuperAdmin", "Admin", "Manager", "User", "DataEntry"]


def _load_json_matrix() -> Dict[str, List[str]]:
    with _PERMISSIONS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


# ── Structural integrity ─────────────────────────────────────────────

def test_permissions_json_exists_and_parses():
    assert _PERMISSIONS_PATH.exists(), (
        f"Expected permissions.json at {_PERMISSIONS_PATH}; the backend "
        "loader and these tests both depend on it."
    )
    data = _load_json_matrix()
    assert isinstance(data, dict) and data, "permissions.json must be a non-empty object"
    for action, roles in data.items():
        assert isinstance(action, str) and action.strip(), \
            f"action key {action!r} must be a non-empty string"
        assert isinstance(roles, list), \
            f"value for {action!r} must be a list, got {type(roles).__name__}"
        for r in roles:
            assert isinstance(r, str), f"role under {action!r} must be a string, got {r!r}"
            assert r in ALL_ROLES, (
                f"role {r!r} under {action!r} is not a known role "
                f"(expected one of {ALL_ROLES})"
            )


def test_rbac_module_matches_json_exactly():
    """rbac.PERMISSIONS must equal the JSON for every action and every role list.

    This is the single guard against backend ↔ JSON drift.  It cannot
    detect frontend drift directly, but the frontend imports the same
    file via the @permissions Vite alias, so if the JSON is correct and
    the backend matches the JSON, the frontend matches transitively.
    """
    expected = _load_json_matrix()
    assert set(rbac.PERMISSIONS.keys()) == set(expected.keys()), (
        "rbac.PERMISSIONS keys differ from permissions.json keys.  "
        f"only-in-backend={set(rbac.PERMISSIONS) - set(expected)}  "
        f"only-in-json={set(expected) - set(rbac.PERMISSIONS)}"
    )
    for action, roles in expected.items():
        assert rbac.PERMISSIONS[action] == roles, (
            f"role list for {action!r} differs: "
            f"backend={rbac.PERMISSIONS[action]} json={roles}"
        )


# ── Cell-by-cell can() coverage ──────────────────────────────────────
# Build (action, role, expected_bool) tuples for every action × role.

def _matrix_cases():
    matrix = _load_json_matrix()
    cases = []
    for action, allowed in matrix.items():
        for role in ALL_ROLES:
            # SuperAdmin always passes (short-circuit in rbac.can), so
            # the expectation collapses regardless of the JSON entry.
            if role == "SuperAdmin":
                expected = True
            else:
                expected = role in allowed
            cases.append(pytest.param(action, role, expected, id=f"{action}-{role}"))
    return cases


@pytest.mark.parametrize("action,role,expected", _matrix_cases())
def test_can_matches_matrix(action: str, role: str, expected: bool):
    assert rbac.can(role, action) is expected, (
        f"can({role!r}, {action!r}) returned {rbac.can(role, action)!r}, "
        f"expected {expected!r}"
    )


# ── SuperAdmin shortcut ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "action",
    [
        "VIEW_ADMIN",
        "DELETE_CUSTOMERS",
        "MANAGE_SIMS",
        "GLOBAL_ADMIN",
        # Unknown action — SuperAdmin still passes, by design.
        "ACTION_THAT_DOES_NOT_EXIST",
    ],
)
def test_superadmin_passes_every_action(action: str):
    assert rbac.can("SuperAdmin", action) is True


def test_unknown_action_denies_non_superadmin():
    for role in ["Admin", "Manager", "User", "DataEntry"]:
        assert rbac.can(role, "ACTION_THAT_DOES_NOT_EXIST") is False, (
            f"Unknown actions must deny {role}"
        )


# ── Role normalization ──────────────────────────────────────────────
# These pin the variants that can show up on a User.role string from
# the database (admin UI options, hand edits, legacy seeds).

@pytest.mark.parametrize(
    "raw,canonical",
    [
        # DataEntry variants — the historical bug class.
        ("DataEntry", "DataEntry"),
        ("dataentry", "DataEntry"),
        ("DATAENTRY", "DataEntry"),
        ("data entry", "DataEntry"),
        ("Data Entry", "DataEntry"),
        ("data entry / import operator", "DataEntry"),
        ("Data Entry / Import Operator", "DataEntry"),
        # Other roles, mixed case.
        ("superadmin", "SuperAdmin"),
        ("SuperAdmin", "SuperAdmin"),
        ("admin", "Admin"),
        ("Admin", "Admin"),
        ("manager", "Manager"),
        ("user", "User"),
        # Empty defaults to lowest-privilege canonical role.
        ("", "User"),
        (None, "User"),
    ],
)
def test_normalize_role(raw, canonical):
    assert rbac.normalize_role(raw) == canonical


def test_unknown_role_falls_through_unchanged():
    """normalize_role does not invent canonical mappings — anything not
    in ROLE_NORMALIZE returns the raw string unchanged.  The
    get_current_user dependency (in app.dependencies) is what downgrades
    such values to ``"User"`` and writes an audit row; this test pins
    the rbac-layer behavior so that downgrade contract stays consistent.
    """
    assert rbac.normalize_role("not_a_real_role") == "not_a_real_role"
    assert rbac.normalize_role("Curator") == "Curator"


# ── DataEntry-specific can() spot checks ────────────────────────────
# These pin the most-discussed grants from the recent session so a
# subtle JSON edit can't silently revoke them.

@pytest.mark.parametrize(
    "action,expected",
    [
        # Onboarding views DataEntry must keep
        ("VIEW_CUSTOMERS", True),
        ("VIEW_SITES", True),
        ("VIEW_DEVICES", True),
        ("VIEW_IMPORT_VERIFICATION", True),
        ("VIEW_PROVISIONING_QUEUE", True),
        # Onboarding mutations
        ("CREATE_CUSTOMERS", True),
        ("EDIT_CUSTOMERS", True),
        ("CREATE_SITES", True),
        ("EDIT_SITES", True),
        ("CREATE_DEVICES", True),
        ("EDIT_DEVICES", True),
        ("CREATE_SERVICE_UNITS", True),
        ("EDIT_SERVICE_UNITS", True),
        ("CREATE_SIMS", True),
        ("EDIT_SIMS", True),
        ("CREATE_LINES", True),
        ("EDIT_LINES", True),
        ("COMMAND_SITE_IMPORT", True),
        ("SUBSCRIBER_IMPORT", True),
        # DataEntry must NOT have these
        ("VIEW_ADMIN", False),
        ("DELETE_CUSTOMERS", False),
        ("DELETE_SITES", False),
        ("DELETE_DEVICES", False),
        ("DELETE_LINES", False),
        ("DELETE_SERVICE_UNITS", False),
        ("MANAGE_SIMS", False),       # carrier/billing layer — Admin only
        ("MANAGE_DEVICES", False),
        ("MANAGE_USERS", False),
        ("MANAGE_PROVIDERS", False),
        ("MANAGE_NOTIFICATIONS", False),
        ("ROTATE_DEVICE_KEY", False),
        ("GLOBAL_ADMIN", False),
    ],
)
def test_dataentry_grants(action: str, expected: bool):
    assert rbac.can("DataEntry", action) is expected
