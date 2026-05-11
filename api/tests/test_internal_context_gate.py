"""Regression tests for ``require_platform_role`` — the gate that
prevents customer-tenant Admins and SuperAdmins-in-impersonation from
reaching internal-only endpoints (the Registration review queue,
the conversion workflow, etc.).

Background:
  Before this gate landed, /api/registrations relied on
  ``require_permission`` which only consulted the user's ROLE.
  A SuperAdmin impersonating a customer tenant kept their underlying
  SuperAdmin role server-side (impersonation only overrode tenant_id),
  so every internal endpoint was reachable from the customer view.
  ``require_platform_role`` adds a context check on top of the
  permission check.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.dependencies import (
    is_platform_user,
    require_platform_role,
    require_permission,
)


def _user(*, role, tenant_id="default", impersonating=False, original_tenant_id=None):
    """Build the User-shaped SimpleNamespace ``get_current_user`` would
    have produced, including the transient attributes the gate reads.
    """
    u = SimpleNamespace(
        id=uuid.uuid4(),
        email=f"{role.lower()}@example.com",
        role=role,
        tenant_id=tenant_id,
    )
    u._is_impersonating = impersonating
    u._original_tenant_id = original_tenant_id if original_tenant_id else tenant_id
    return u


# ─────────────────────────────────────────────────────────────────────
# is_platform_user
# ─────────────────────────────────────────────────────────────────────

class TestIsPlatformUser:
    def test_superadmin_is_platform_user_regardless_of_tenant(self):
        # SuperAdmin always counts as platform staff — that's the whole
        # role.  The tenant_id check is a backstop for Admin/DataEntry/
        # Manager.
        assert is_platform_user(_user(role="SuperAdmin", tenant_id="default"))
        assert is_platform_user(_user(role="SuperAdmin", tenant_id="some-customer"))

    def test_admin_in_internal_tenant_is_platform_user(self):
        # An Admin whose home tenant is in INTERNAL_TENANT_IDS counts
        # as internal — e.g. our own ops team running the system.
        assert is_platform_user(_user(role="Admin", tenant_id="default"))

    def test_admin_in_customer_tenant_is_not_platform_user(self):
        # The production scenario we explicitly want to block: an
        # Admin who happens to live in a customer tenant must NOT
        # gain access to the Registration review queue just because
        # permissions.json grants Admin VIEW_REGISTRATIONS.
        assert not is_platform_user(_user(role="Admin", tenant_id="integrity-property-management"))

    def test_dataentry_in_internal_tenant_is_platform_user(self):
        # DataEntry in the internal tenant is our import-operator
        # persona; they should still see Registrations in normal use.
        assert is_platform_user(_user(role="DataEntry", tenant_id="default"))

    def test_dataentry_in_customer_tenant_is_not_platform_user(self):
        assert not is_platform_user(_user(role="DataEntry", tenant_id="integrity-property-management"))

    def test_manager_user_in_customer_tenant_is_not_platform_user(self):
        assert not is_platform_user(_user(role="Manager", tenant_id="acme"))
        assert not is_platform_user(_user(role="User", tenant_id="acme"))

    def test_uses_original_tenant_id_when_impersonating(self):
        # During impersonation, get_current_user sets user.tenant_id to
        # the impersonated tenant and stashes the real one on
        # _original_tenant_id.  is_platform_user must read the
        # original — otherwise a SuperAdmin who happens to be
        # impersonating an internal tenant_id would silently flip
        # back to internal.  (SuperAdmin is always internal anyway,
        # but the same logic protects the future Admin-in-impersonation
        # case if we ever allow it.)
        user = _user(
            role="Admin",
            tenant_id="some-customer",      # the impersonated tenant
            original_tenant_id="default",   # the real one
            impersonating=True,
        )
        assert is_platform_user(user)


# ─────────────────────────────────────────────────────────────────────
# require_platform_role behavior
# ─────────────────────────────────────────────────────────────────────

def _run_check(dep, user):
    """Invoke the dep's _check coroutine synchronously for assertion."""
    return asyncio.run(dep(current_user=user))


class TestRequirePlatformRole:
    def test_real_superadmin_in_normal_mode_is_allowed(self):
        dep = require_platform_role("VIEW_REGISTRATIONS")
        user = _user(role="SuperAdmin", tenant_id="default", impersonating=False)
        # No exception means allowed.  We re-assert the returned user
        # matches the input so a regression that quietly swaps users
        # would surface here.
        result = _run_check(dep, user)
        assert result is user

    def test_real_admin_in_internal_tenant_is_allowed(self):
        # The "DataEntry/Admin/internal users should still see them in
        # normal internal context" requirement from the user spec.
        dep = require_platform_role("VIEW_REGISTRATIONS")
        user = _user(role="Admin", tenant_id="default", impersonating=False)
        result = _run_check(dep, user)
        assert result is user

    def test_dataentry_in_internal_tenant_is_allowed(self):
        dep = require_platform_role("VIEW_REGISTRATIONS")
        user = _user(role="DataEntry", tenant_id="default", impersonating=False)
        result = _run_check(dep, user)
        assert result is user

    def test_superadmin_during_impersonation_is_rejected(self):
        # The headline bug: SuperAdmin acting as a customer tenant
        # must lose access to internal-only endpoints even though
        # their underlying role is SuperAdmin and rbac_can() would
        # normally grant them everything.
        dep = require_platform_role("VIEW_REGISTRATIONS")
        user = _user(
            role="SuperAdmin",
            tenant_id="integrity-property-management",  # impersonated
            original_tenant_id="default",               # real
            impersonating=True,
        )
        with pytest.raises(HTTPException) as exc:
            _run_check(dep, user)
        assert exc.value.status_code == 403
        # The error message must name impersonation specifically so an
        # operator who sees the toast can act on it.
        assert "acting as another tenant" in exc.value.detail

    def test_admin_in_customer_tenant_is_rejected(self):
        # The longer-standing gap: a real Admin whose home tenant is a
        # customer tenant must NOT inherit internal access purely
        # from the Admin role grant in permissions.json.
        dep = require_platform_role("VIEW_REGISTRATIONS")
        user = _user(role="Admin", tenant_id="integrity-property-management", impersonating=False)
        with pytest.raises(HTTPException) as exc:
            _run_check(dep, user)
        assert exc.value.status_code == 403
        assert "internal/platform context" in exc.value.detail

    def test_user_role_is_rejected_even_in_internal_tenant(self):
        # User role isn't in VIEW_REGISTRATIONS in permissions.json.
        # Even though the tenant check passes (default is internal),
        # the role check should still block.
        dep = require_platform_role("VIEW_REGISTRATIONS")
        user = _user(role="User", tenant_id="default", impersonating=False)
        with pytest.raises(HTTPException) as exc:
            _run_check(dep, user)
        assert exc.value.status_code == 403
        assert "denied for role 'User'" in exc.value.detail

    def test_manage_registrations_rejects_dataentry_even_internal(self):
        # MANAGE_REGISTRATIONS is granted only to Admin+SuperAdmin in
        # permissions.json.  Internal-tenant DataEntry must still be
        # rejected for the manage surface.  Confirms the gate composes
        # with the existing role check, not in lieu of it.
        dep = require_platform_role("MANAGE_REGISTRATIONS")
        user = _user(role="DataEntry", tenant_id="default", impersonating=False)
        with pytest.raises(HTTPException) as exc:
            _run_check(dep, user)
        assert exc.value.status_code == 403
        assert "denied for role 'DataEntry'" in exc.value.detail

    def test_convert_registrations_rejects_impersonation(self):
        # Lock in the same rule for the conversion-specific permission.
        dep = require_platform_role("CONVERT_REGISTRATIONS")
        user = _user(
            role="SuperAdmin",
            tenant_id="customer-x",
            original_tenant_id="default",
            impersonating=True,
        )
        with pytest.raises(HTTPException) as exc:
            _run_check(dep, user)
        assert exc.value.status_code == 403

    def test_require_permission_alone_still_passes_impersonation(self):
        # Sanity check: the existing ``require_permission`` is
        # intentionally NOT affected by this change — sites /
        # customers / devices etc. still work during impersonation.
        # If a regression accidentally added the impersonation check
        # to require_permission, this test catches it.
        dep = require_permission("VIEW_REGISTRATIONS")
        user = _user(
            role="SuperAdmin",
            tenant_id="customer-x",
            original_tenant_id="default",
            impersonating=True,
        )
        result = _run_check(dep, user)
        assert result is user

    def test_internal_tenant_id_set_is_honored_from_settings(self):
        # The internal-tenant whitelist comes from settings — verify
        # the gate respects a runtime override (Render env change)
        # without code changes.
        from app.config import settings
        with patch.object(
            type(settings), "internal_tenant_id_set",
            new=property(lambda self: {"ops"}),
        ):
            dep = require_platform_role("VIEW_REGISTRATIONS")
            # "default" is no longer internal under this override.
            user_default = _user(role="Admin", tenant_id="default", impersonating=False)
            with pytest.raises(HTTPException):
                _run_check(dep, user_default)
            # "ops" is now the only internal tenant.
            user_ops = _user(role="Admin", tenant_id="ops", impersonating=False)
            _run_check(dep, user_ops)  # no raise
