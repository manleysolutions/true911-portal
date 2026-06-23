"""PR-B1 — Customer RBAC Foundation regression tests (RH Go-Live Phase 1).

Proves:
  * INTERNAL_OPS is granted to every internal role (+ SuperAdmin), and to NONE
    of the four customer roles.
  * Customer roles hold no internal permissions at all (no grants in this PR).
  * The 38 newly-guarded internal GET endpoints reject customer roles (403) and
    still admit internal roles (guard passes — no regression).
  * The four customer roles normalize to canonical names.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db, require_permission
from app.services import rbac
from app.routers import telemetry, audits, sims, vola, command, lines

INTERNAL_ROLES = ["Admin", "Manager", "User", "DataEntry", "DataSteward", "UX_QA_ANALYST"]
CUSTOMER_ROLES = ["CUSTOMER_ADMIN", "CUSTOMER_USER", "CUSTOMER_BILLING", "CUSTOMER_READONLY"]


def _user(role):
    return SimpleNamespace(role=role, tenant_id="tenantA", email="u@t.example", id=1)


# ── INTERNAL_OPS grant matrix ────────────────────────────────────────
@pytest.mark.parametrize("role", INTERNAL_ROLES + ["SuperAdmin"])
def test_internal_roles_have_internal_ops(role):
    assert rbac.can(role, "INTERNAL_OPS") is True


@pytest.mark.parametrize("role", CUSTOMER_ROLES)
def test_customer_roles_lack_internal_ops(role):
    assert rbac.can(role, "INTERNAL_OPS") is False


@pytest.mark.parametrize("role", CUSTOMER_ROLES)
@pytest.mark.parametrize(
    "perm",
    ["INTERNAL_OPS", "VIEW_ADMIN", "COMMAND_VIEW_OPERATOR", "MANAGE_USERS",
     "VIEW_SITES", "VIEW_DEVICES", "VIEW_ASSURANCE"],
)
def test_customer_roles_have_no_permissions_yet(role, perm):
    # PR-B1 registers the roles but grants them nothing (no customer API yet).
    assert rbac.can(role, perm) is False


# ── Guard dependency behaviour (no DB needed) ────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("role", INTERNAL_ROLES + ["SuperAdmin"])
async def test_guard_admits_internal_role(role):
    dep = require_permission("INTERNAL_OPS")
    user = _user(role)
    assert await dep(current_user=user) is user


@pytest.mark.asyncio
@pytest.mark.parametrize("role", CUSTOMER_ROLES)
async def test_guard_blocks_customer_role(role):
    dep = require_permission("INTERNAL_OPS")
    with pytest.raises(HTTPException) as ei:
        await dep(current_user=_user(role))
    assert ei.value.status_code == 403


# ── Endpoint-level wiring (a representative sample of the 38) ─────────
SAMPLE = [
    (telemetry.router, "/telemetry", ""),
    (audits.router, "/audits", ""),
    (sims.router, "/sims", ""),
    (vola.router, "/vola", "/test"),
    (command.router, "/command", "/summary"),
    (lines.router, "/lines", ""),
]


def _client(router, prefix, role):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: _user(role)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("router,prefix,path", SAMPLE)
def test_guarded_endpoint_blocks_customer(router, prefix, path):
    c = _client(router, prefix, "CUSTOMER_ADMIN")
    assert c.get(prefix + path).status_code == 403


@pytest.mark.parametrize("router,prefix,path", SAMPLE)
def test_guarded_endpoint_admits_internal(router, prefix, path):
    # Internal role passes the guard; handler then runs (may 200/500 with a
    # stub DB) — the point is it is NOT blocked at the guard (403).
    c = _client(router, prefix, "Admin")
    assert c.get(prefix + path).status_code != 403


# ── Role normalization ───────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expect",
    [
        ("customer admin", "CUSTOMER_ADMIN"),
        ("CUSTOMER_ADMIN", "CUSTOMER_ADMIN"),
        ("customer user", "CUSTOMER_USER"),
        ("customer billing", "CUSTOMER_BILLING"),
        ("customer read only", "CUSTOMER_READONLY"),
        ("customer_readonly", "CUSTOMER_READONLY"),
    ],
)
def test_customer_role_normalization(raw, expect):
    assert rbac.normalize_role(raw) == expect
