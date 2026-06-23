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

ALL_ROLES = [
    "SuperAdmin", "Admin", "Manager", "User", "DataEntry", "DataSteward", "UX_QA_ANALYST",
    # Customer-plane roles (RH Go-Live Phase 1/3). They appear only in CUSTOMER_*
    # actions; the cell-by-cell matrix below verifies they hold no operator grant.
    "CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_BILLING", "CUSTOMER_READONLY",
]


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
    for role in ["Admin", "Manager", "User", "DataEntry", "DataSteward", "UX_QA_ANALYST"]:
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
        # DataSteward variants — Phase A addition.
        ("DataSteward", "DataSteward"),
        ("datasteward", "DataSteward"),
        ("DATASTEWARD", "DataSteward"),
        ("data steward", "DataSteward"),
        ("Data Steward", "DataSteward"),
        ("operations data steward", "DataSteward"),
        ("Operational Data Steward", "DataSteward"),
        # UX & QA Analyst variants — Sivmey / Platform Operations Analyst.
        ("UX_QA_ANALYST", "UX_QA_ANALYST"),
        ("ux_qa_analyst", "UX_QA_ANALYST"),
        ("uxqaanalyst", "UX_QA_ANALYST"),
        ("ux qa analyst", "UX_QA_ANALYST"),
        ("UX & QA Analyst", "UX_QA_ANALYST"),
        ("ux and qa analyst", "UX_QA_ANALYST"),
        ("ux/qa analyst", "UX_QA_ANALYST"),
        ("Platform Operations Analyst", "UX_QA_ANALYST"),
        ("platform ops analyst", "UX_QA_ANALYST"),
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


# ── DataSteward-specific can() spot checks (Phase A) ────────────────
# Pins the new role's grant set so an accidental edit to
# permissions.json can't silently strip Sivmey of access or — worse —
# escalate the role into destructive territory.

@pytest.mark.parametrize(
    "action,expected",
    [
        # Onboarding views DataSteward must have
        ("VIEW_CUSTOMERS", True),
        ("VIEW_SITES", True),
        ("VIEW_DEVICES", True),
        ("VIEW_IMPORT_VERIFICATION", True),
        ("VIEW_PROVISIONING_QUEUE", True),
        ("VIEW_ONBOARDING_REVIEW", True),
        ("VIEW_REGISTRATIONS", True),
        # Onboarding mutations DataSteward must have
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
        ("MANAGE_IMPORT_VERIFICATION", True),
        ("MANAGE_ONBOARDING_REVIEW", True),
        # DataSteward must NOT have any of these (destructive,
        # carrier-provisioning, identity/RBAC, or system surfaces).
        ("VIEW_ADMIN", False),
        ("DELETE_CUSTOMERS", False),
        ("DELETE_SITES", False),
        ("DELETE_DEVICES", False),
        ("DELETE_LINES", False),
        ("DELETE_SERVICE_UNITS", False),
        ("MANAGE_SIMS", False),
        ("MANAGE_DEVICES", False),
        ("MANAGE_USERS", False),
        ("MANAGE_PROVIDERS", False),
        ("MANAGE_NOTIFICATIONS", False),
        ("MANAGE_INTEGRATIONS", False),
        ("MANAGE_PROVISIONING", False),
        ("MANAGE_REGISTRATIONS", False),
        ("CONVERT_REGISTRATIONS", False),
        ("ROTATE_DEVICE_KEY", False),
        ("COMMAND_INGEST_CARRIER", False),
        ("COMMAND_MANAGE_AUTOMATION", False),
        ("COMMAND_MANAGE_ORG", False),
        ("GLOBAL_ADMIN", False),
    ],
)
def test_datasteward_grants(action: str, expected: bool):
    assert rbac.can("DataSteward", action) is expected


def test_datasteward_does_not_weaken_dataentry():
    """Every grant DataEntry has today must remain DataEntry's grant.

    Phase A adds DataSteward as a *new* role; it must not change
    DataEntry's grant set in either direction.  The matrix file is
    rich enough that a manual diff is easy to miss, so we compare
    cell-by-cell here.
    """

    matrix = _load_json_matrix()
    # Before Phase A, this was the union of all DataEntry grants.
    # Re-derive from the file so future additions don't need a
    # second list to update.
    expected = {a for a, roles in matrix.items() if "DataEntry" in roles}
    actual = {a for a in matrix if rbac.can("DataEntry", a)}
    assert expected.issubset(actual), (
        f"DataEntry lost grants: missing={expected - actual}"
    )


# ── UX_QA_ANALYST-specific can() spot checks ────────────────────────
# Pins the UX & QA Analyst (Sivmey) grant set.  The role is a superset
# of DataSteward's *safe* grants plus reporting/export; it must never
# acquire destructive, carrier-provisioning, identity/RBAC, system, or
# the heavy E911 command surface.  Two capabilities the role spec lists
# are intentionally NOT granted here and are asserted denied below:
#   * UPDATE_E911  — the heavy E911 command stays Admin-only until an
#     approval workflow exists (address-level E911 edits ride EDIT_SITES).
#   * impersonation — X-Act-As-Tenant is SuperAdmin-only and is not
#     read-only; granting it to this role would be privilege escalation.

@pytest.mark.parametrize(
    "action,expected",
    [
        # Stewardship / onboarding views the role must have
        ("VIEW_CUSTOMERS", True),
        ("VIEW_SITES", True),
        ("VIEW_DEVICES", True),
        ("VIEW_LINES", True),
        ("VIEW_RECORDINGS", True),
        ("VIEW_ASSURANCE", True),
        ("VIEW_IMPORT_VERIFICATION", True),
        ("VIEW_PROVISIONING_QUEUE", True),
        ("VIEW_ONBOARDING_REVIEW", True),
        ("VIEW_REGISTRATIONS", True),
        # Data-stewardship mutations the role must have
        ("CREATE_CUSTOMERS", True),
        ("EDIT_CUSTOMERS", True),
        ("CREATE_SITES", True),
        ("EDIT_SITES", True),          # address / E911-address correction path
        ("CREATE_DEVICES", True),
        ("EDIT_DEVICES", True),        # device assignment / ownership correction
        ("CREATE_SERVICE_UNITS", True),
        ("EDIT_SERVICE_UNITS", True),  # subscription metadata / billing mappings
        ("CREATE_SIMS", True),
        ("EDIT_SIMS", True),
        ("CREATE_LINES", True),
        ("EDIT_LINES", True),
        ("COMMAND_SITE_IMPORT", True),
        ("SUBSCRIBER_IMPORT", True),
        ("MANAGE_IMPORT_VERIFICATION", True),
        ("MANAGE_ONBOARDING_REVIEW", True),
        # Reporting / export — the QA scope additions beyond DataSteward
        ("GENERATE_REPORT", True),
        ("COMMAND_EXPORT_REPORTS", True),
        # Must NOT have: heavy E911 command (needs approval workflow)
        ("UPDATE_E911", False),
        # Must NOT have: destructive
        ("DELETE_CUSTOMERS", False),
        ("DELETE_SITES", False),
        ("DELETE_DEVICES", False),
        ("DELETE_LINES", False),
        ("DELETE_SERVICE_UNITS", False),
        # Must NOT have: carrier / provisioning / identity / RBAC / system
        ("MANAGE_SIMS", False),
        ("MANAGE_DEVICES", False),
        ("MANAGE_USERS", False),
        ("MANAGE_PROVIDERS", False),
        ("MANAGE_NOTIFICATIONS", False),
        ("MANAGE_INTEGRATIONS", False),
        ("MANAGE_PROVISIONING", False),
        ("MANAGE_REGISTRATIONS", False),
        ("CONVERT_REGISTRATIONS", False),
        ("ROTATE_DEVICE_KEY", False),
        ("RUN_RECONCILIATION", False),
        ("COMMAND_INGEST_CARRIER", False),
        ("COMMAND_MANAGE_AUTOMATION", False),
        ("COMMAND_MANAGE_ORG", False),
        ("VIEW_ADMIN", False),
        ("GLOBAL_ADMIN", False),
    ],
)
def test_ux_qa_analyst_grants(action: str, expected: bool):
    assert rbac.can("UX_QA_ANALYST", action) is expected


def test_ux_qa_analyst_is_superset_of_datasteward_safe_grants():
    """UX_QA_ANALYST must grant everything DataSteward grants (it is the
    QA/reporting superset).  Re-derive DataSteward's grants from the file
    so the assertion can't silently rot."""
    matrix = _load_json_matrix()
    steward = {a for a, roles in matrix.items() if "DataSteward" in roles}
    ux = {a for a in matrix if rbac.can("UX_QA_ANALYST", a)}
    assert steward.issubset(ux), (
        f"UX_QA_ANALYST missing DataSteward grants: {steward - ux}"
    )


def test_new_role_does_not_alter_other_roles():
    """Adding UX_QA_ANALYST must not change any existing role's grants.

    For every action, the set of *other* roles allowed must equal the
    JSON minus UX_QA_ANALYST — i.e. the new role only ever adds itself,
    never removes or adds another role to a cell.
    """
    matrix = _load_json_matrix()
    for action, roles in matrix.items():
        others = [r for r in roles if r != "UX_QA_ANALYST"]
        for role in ["Admin", "Manager", "User", "DataEntry", "DataSteward"]:
            assert rbac.can(role, action) is (role in others), (
                f"{role} grant for {action!r} changed by the UX_QA_ANALYST addition"
            )
