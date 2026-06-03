"""Assurance API tests — flag gating, RBAC, tenant scoping, response shape,
and a read-only (no-mutation) guard.

The endpoint is mounted on a minimal app with get_db / get_current_user
overridden; the loader is patched so no real DB is needed. Read-only behavior is
additionally asserted by scanning the assurance package source for write calls.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import assurance as assurance_router
from app.services.assurance.signals import (
    AssuranceSignals,
    DeviceSignal,
    ServiceUnitSignal,
    TestRecord,
)

NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


def _signals(tenant="integrity", site="IPM-BELLE-TERRE", **kw):
    base = dict(
        tenant_id=tenant, site_id=site, site_name="Belle Terre at Sunrise",
        customer_name="Integrity Property Management",
        site_lifecycle_status="active", onboarding_status="active",
        e911_address_present=True, e911_status="validated", e911_confirmation_required=False,
        devices=(DeviceSignal(device_id="LM150-1", operational_state="connected",
                              device_lifecycle="active", model="FlyingVoice LM150"),),
        service_units=(ServiceUnitSignal(unit_id="U1", unit_name="Elevator 1",
                                         unit_type="elevator_phone", status="active",
                                         device_id="LM150-1", has_active_device=True),),
        last_test=None,  # Belle Terre: no test history → Attention (TEST_MISSING)
    )
    base.update(kw)
    return AssuranceSignals(**base)


class _NoWriteDB:
    """Fake session that fails loudly if anything tries to write."""
    async def execute(self, *a, **k):
        raise AssertionError("loader should be patched in these tests")

    def add(self, *a, **k):
        raise AssertionError("assurance endpoint must not write (add)")

    async def commit(self):
        raise AssertionError("assurance endpoint must not write (commit)")

    async def flush(self):
        raise AssertionError("assurance endpoint must not write (flush)")


def _client(*, role="User", tenant="integrity", flag="true", loader=None, monkeypatch):
    monkeypatch.setattr("app.config.settings.FEATURE_ASSURANCE_ENGINE", flag)
    # Patch the loader symbol used by the router module.
    if loader is not None:
        monkeypatch.setattr(assurance_router, "load_site_assurance_signals", loader)
    app = FastAPI()
    app.include_router(assurance_router.router, prefix="/api/assurance")
    app.dependency_overrides[get_db] = lambda: _NoWriteDB()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        role=role, tenant_id=tenant, email="cindy@integrity.example", id=1
    )
    return TestClient(app)


# ── Feature-flag gating ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_flag_off_returns_404(monkeypatch):
    async def loader(db, t, s):  # would succeed, but flag is off
        return _signals()
    c = _client(flag="false", loader=loader, monkeypatch=monkeypatch)
    r = c.get("/api/assurance/site/IPM-BELLE-TERRE")
    assert r.status_code == 404


# ── RBAC ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_forbidden_without_permission(monkeypatch):
    async def loader(db, t, s):
        return _signals()
    c = _client(role="Guest", loader=loader, monkeypatch=monkeypatch)  # role lacks VIEW_ASSURANCE
    r = c.get("/api/assurance/site/IPM-BELLE-TERRE")
    assert r.status_code == 403


# ── Tenant scoping ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_loader_called_with_caller_tenant(monkeypatch):
    seen = {}

    async def loader(db, tenant_id, site_id):
        seen["tenant"] = tenant_id
        seen["site"] = site_id
        return _signals(tenant=tenant_id)

    c = _client(tenant="integrity", loader=loader, monkeypatch=monkeypatch)
    r = c.get("/api/assurance/site/IPM-BELLE-TERRE")
    assert r.status_code == 200
    assert seen["tenant"] == "integrity"   # caller's tenant, not a client-supplied one
    assert seen["site"] == "IPM-BELLE-TERRE"


@pytest.mark.asyncio
async def test_site_not_found_is_404(monkeypatch):
    async def loader(db, t, s):
        return None  # cross-tenant / missing site
    c = _client(loader=loader, monkeypatch=monkeypatch)
    r = c.get("/api/assurance/site/OTHER-TENANT-SITE")
    assert r.status_code == 404


# ── Response shape (Belle Terre: no test → Attention/TEST_MISSING) ───
@pytest.mark.asyncio
async def test_belle_terre_response_shape(monkeypatch):
    async def loader(db, t, s):
        return _signals()
    c = _client(loader=loader, monkeypatch=monkeypatch)
    r = c.get("/api/assurance/site/IPM-BELLE-TERRE")
    assert r.status_code == 200
    body = r.json()
    assert body["site_id"] == "IPM-BELLE-TERRE"
    assert body["customer_name"] == "Integrity Property Management"
    assert body["assurance_label"] == "Attention Needed"
    assert any(rr["code"] == "ASSURANCE.TEST_MISSING" for rr in body["reasons"])
    assert body["read_only"] is True
    assert "does not replace required manual life-safety testing" in body["disclaimer"]
    # required response fields present
    for field in ("as_of", "summary", "recommended_action", "devices",
                  "service_units", "e911_status", "last_test"):
        assert field in body
    # No raw vendor payloads leaked
    blob = r.text.lower()
    assert "raw_payload" not in blob and "iccid" not in blob and "imei" not in blob


@pytest.mark.asyncio
async def test_protected_statement_includes_timestamp(monkeypatch):
    async def loader(db, t, s):
        # add a fresh passing test → Protected
        return _signals(last_test=TestRecord(at=NOW, result="pass", source="verification_tasks"))
    c = _client(loader=loader, monkeypatch=monkeypatch)
    r = c.get("/api/assurance/site/IPM-BELLE-TERRE")
    body = r.json()
    assert body["assurance_label"] == "Protected"
    assert body["internal_label"] == "Active & Verified"
    assert body["statement"].startswith("Protected as of ")


# ── Read-only guard: assurance package contains no write calls ───────
def test_assurance_package_has_no_db_writes():
    pkg = pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "assurance"
    router = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers" / "assurance.py"
    # Scope to DB-session writes (the session param is named ``db`` in this
    # package) — a plain set.add() is not a write.
    forbidden = ("db.add(", "db.commit(", "db.flush(", "db.delete(", "db.merge(")
    for path in list(pkg.glob("*.py")) + [router]:
        src = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in src, f"{path.name} contains write call {token!r}"
