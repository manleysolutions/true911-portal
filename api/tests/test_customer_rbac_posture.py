"""Customer-plane RBAC posture (RH go-live).

Proves the two invariants the whole design rests on:
  1. Customer roles CAN reach their own surfaces (customer perms + the read
     perms the existing frontend pages gate on: VIEW_SITES/DEVICES/ASSURANCE).
  2. Customer roles are ISOLATED from the internal plane — no INTERNAL_OPS,
     no COMMAND_*, no VIEW_ADMIN / MANAGE_* — so /command/summary and the
     internal operator pages (gated on INTERNAL_OPS) are unreachable.

Also proves the admin invite/create path accepts the customer roles and that
role normalization maps the new role family.
"""

from __future__ import annotations

import pytest

from app.routers.admin import ALLOWED_ROLES
from app.services.rbac import can, normalize_role

CUSTOMER_ROLES = [
    "CUSTOMER_ADMIN", "CUSTOMER_MANAGER", "CUSTOMER_SUPPORT", "CUSTOMER_VIEWER",
    "CUSTOMER_USER", "CUSTOMER_BILLING", "CUSTOMER_READONLY",
]

# Every internal grant a customer must NEVER hold.
FORBIDDEN = [
    "INTERNAL_OPS", "VIEW_ADMIN", "COMMAND_VIEW_OPERATOR", "COMMAND_VIEW_NETWORK",
    "COMMAND_VIEW_AUTO_OPS", "MANAGE_USERS", "MANAGE_SIMS", "UPDATE_E911",
    "MANAGE_DEVICES", "VIEW_REGISTRATIONS", "SUBSCRIBER_IMPORT",
]


@pytest.mark.parametrize("role", CUSTOMER_ROLES)
def test_customer_roles_isolated_from_internal(role):
    for perm in FORBIDDEN:
        assert can(role, perm) is False, f"{role} must NOT hold {perm}"


@pytest.mark.parametrize("role", CUSTOMER_ROLES)
def test_customer_roles_can_see_own_surfaces(role):
    # Every customer role shares: locations/assurance pages + the dashboard.
    assert can(role, "VIEW_SITES") is True
    assert can(role, "VIEW_ASSURANCE") is True
    assert can(role, "CUSTOMER_VIEW_DASHBOARD") is True
    assert can(role, "CUSTOMER_VIEW_LOCATIONS") is True


# Roles that see the operational + E911 detail (BILLING is a finance-only role).
OPERATIONAL_ROLES = [r for r in CUSTOMER_ROLES if r != "CUSTOMER_BILLING"]


@pytest.mark.parametrize("role", OPERATIONAL_ROLES)
def test_operational_customer_roles_see_devices_and_e911(role):
    assert can(role, "VIEW_DEVICES") is True
    assert can(role, "CUSTOMER_VIEW_E911") is True
    assert can(role, "CUSTOMER_VIEW_DEVICES") is True


def test_role_capability_differences():
    # Viewer is read-only: no support management, no billing, no export.
    assert can("CUSTOMER_VIEWER", "CUSTOMER_MANAGE_SUPPORT") is False
    assert can("CUSTOMER_VIEWER", "CUSTOMER_VIEW_BILLING") is False
    assert can("CUSTOMER_VIEWER", "CUSTOMER_EXPORT_REPORTS") is False
    # Manager can manage support + see billing + export.
    assert can("CUSTOMER_MANAGER", "CUSTOMER_MANAGE_SUPPORT") is True
    assert can("CUSTOMER_MANAGER", "CUSTOMER_VIEW_BILLING") is True
    assert can("CUSTOMER_MANAGER", "CUSTOMER_EXPORT_REPORTS") is True
    # Support manages cases but is not a billing/export role.
    assert can("CUSTOMER_SUPPORT", "CUSTOMER_MANAGE_SUPPORT") is True
    assert can("CUSTOMER_SUPPORT", "CUSTOMER_VIEW_BILLING") is False
    # Billing sees billing, not device operational detail.
    assert can("CUSTOMER_BILLING", "CUSTOMER_VIEW_BILLING") is True
    assert can("CUSTOMER_BILLING", "CUSTOMER_VIEW_DEVICES") is False


def test_admin_invite_accepts_customer_roles():
    for role in CUSTOMER_ROLES:
        assert role in ALLOWED_ROLES


def test_role_normalization_new_family():
    assert normalize_role("customer_manager") == "CUSTOMER_MANAGER"
    assert normalize_role("customer viewer") == "CUSTOMER_VIEWER"
    assert normalize_role("customer_support") == "CUSTOMER_SUPPORT"


def test_no_regression_internal_roles_keep_internal_ops():
    # The guard that proves gating internal pages behind INTERNAL_OPS is
    # non-regressive: every existing internal role still holds it.
    for role in ("Admin", "Manager", "User", "DataEntry", "DataSteward", "UX_QA_ANALYST"):
        assert can(role, "INTERNAL_OPS") is True
    # SuperAdmin bypasses via can() returning True for everything.
    assert can("SuperAdmin", "INTERNAL_OPS") is True
