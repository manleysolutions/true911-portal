"""PR-C1 — customer API two-key gate + dedicated-permission RBAC separation.

Proves:
  * require_customer_api 404s unless FEATURE_CUSTOMER_API is on AND the caller's
    tenant is allowlisted (both at the dependency and on the /_health route),
  * the four customer roles resolve exactly their CUSTOMER_* grants,
  * NO internal role gains any CUSTOMER_* perm, and NO customer role gains any
    operator/INTERNAL_OPS perm (dedicated perms — no overlap).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.services import rbac
from app.services.customer.gate import require_customer_api
from app.routers import customer

RH = "restoration-hardware"
INTERNAL_ROLES = ["Admin", "Manager", "User", "DataEntry", "DataSteward", "UX_QA_ANALYST"]
CUSTOMER_ROLES = ["CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_BILLING", "CUSTOMER_READONLY"]
CUSTOMER_PERMS = [
    "CUSTOMER_VIEW_DASHBOARD", "CUSTOMER_VIEW_LOCATIONS", "CUSTOMER_VIEW_SERVICES",
    "CUSTOMER_VIEW_DEVICES", "CUSTOMER_VIEW_E911", "CUSTOMER_VIEW_SUPPORT",
    "CUSTOMER_MANAGE_SUPPORT", "CUSTOMER_VIEW_BILLING", "CUSTOMER_VIEW_REPORTS",
    "CUSTOMER_EXPORT_REPORTS",
]
# Operator/internal-only perms a customer must NEVER hold.  (VIEW_SITES/
# VIEW_DEVICES/VIEW_ASSURANCE are NOT here — at go-live they became legitimate
# customer read grants for the customer pages; see CUSTOMER_EXPERIENCE_BOUNDARY
# §1.5 and test_customer_rbac_posture.py.)
OPERATOR_PERMS = ["INTERNAL_OPS", "VIEW_ADMIN", "COMMAND_VIEW_OPERATOR", "MANAGE_USERS"]

EXPECTED = {
    "CUSTOMER_VIEW_DASHBOARD": {"CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_BILLING", "CUSTOMER_READONLY"},
    "CUSTOMER_VIEW_LOCATIONS": {"CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_BILLING", "CUSTOMER_READONLY"},
    "CUSTOMER_VIEW_SERVICES": {"CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_READONLY"},
    "CUSTOMER_VIEW_DEVICES": {"CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_READONLY"},
    "CUSTOMER_VIEW_E911": {"CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_READONLY"},
    "CUSTOMER_VIEW_SUPPORT": {"CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_READONLY"},
    "CUSTOMER_MANAGE_SUPPORT": {"CUSTOMER_ADMIN", "CUSTOMER_USER"},
    "CUSTOMER_VIEW_BILLING": {"CUSTOMER_ADMIN", "CUSTOMER_BILLING"},
    "CUSTOMER_VIEW_REPORTS": {"CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_BILLING", "CUSTOMER_READONLY"},
    "CUSTOMER_EXPORT_REPORTS": {"CUSTOMER_ADMIN", "CUSTOMER_BILLING"},
}


def _user(tenant=RH, role="CUSTOMER_ADMIN"):
    return SimpleNamespace(role=role, tenant_id=tenant, email="judy@rh.example", id=1)


def _enable(monkeypatch, flag="true", allow=RH):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_API", flag)
    monkeypatch.setattr("app.config.settings.CUSTOMER_API_TENANT_ALLOWLIST", allow)


# ── Two-key gate (dependency level) ──────────────────────────────────
def test_gate_404_when_flag_off(monkeypatch):
    _enable(monkeypatch, flag="false", allow=RH)
    with pytest.raises(HTTPException) as ei:
        require_customer_api(current_user=_user())
    assert ei.value.status_code == 404


def test_gate_404_when_tenant_not_allowlisted(monkeypatch):
    _enable(monkeypatch, flag="true", allow="some-other-tenant")
    with pytest.raises(HTTPException) as ei:
        require_customer_api(current_user=_user(tenant=RH))
    assert ei.value.status_code == 404


def test_gate_passes_when_enabled_and_allowlisted(monkeypatch):
    _enable(monkeypatch, flag="true", allow="another," + RH)
    assert require_customer_api(current_user=_user()) is not None


# ── Two-key gate (route level via /_health) ──────────────────────────
def _client(role="CUSTOMER_ADMIN", tenant=RH):
    app = FastAPI()
    app.include_router(customer.router, prefix="/api/customer")
    app.dependency_overrides[get_current_user] = lambda: _user(tenant=tenant, role=role)
    return TestClient(app, raise_server_exceptions=False)


def test_health_404_when_disabled(monkeypatch):
    _enable(monkeypatch, flag="false")
    assert _client().get("/api/customer/_health").status_code == 404


def test_health_200_when_enabled_for_tenant(monkeypatch):
    _enable(monkeypatch, flag="true", allow=RH)
    r = _client().get("/api/customer/_health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_health_404_for_non_allowlisted_tenant(monkeypatch):
    _enable(monkeypatch, flag="true", allow=RH)
    assert _client(tenant="integrity").get("/api/customer/_health").status_code == 404


# ── Dedicated-permission RBAC matrix ─────────────────────────────────
@pytest.mark.parametrize("perm", CUSTOMER_PERMS)
def test_customer_perm_grants_match_matrix(perm):
    for role in CUSTOMER_ROLES:
        assert rbac.can(role, perm) is (role in EXPECTED[perm]), f"{role}/{perm}"


@pytest.mark.parametrize("role", INTERNAL_ROLES)
@pytest.mark.parametrize("perm", CUSTOMER_PERMS)
def test_internal_roles_get_no_customer_perms(role, perm):
    assert rbac.can(role, perm) is False


@pytest.mark.parametrize("role", CUSTOMER_ROLES)
@pytest.mark.parametrize("perm", OPERATOR_PERMS)
def test_customer_roles_get_no_operator_perms(role, perm):
    assert rbac.can(role, perm) is False
