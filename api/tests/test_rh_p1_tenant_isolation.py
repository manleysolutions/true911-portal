"""PR-S1 — RH Go-Live Phase 1 tenant-isolation regression tests.

Pins the five fixes from RH_SECURITY_READINESS.md §5:

  * H1 — GET /subscriber-import/batches/{batch_id}/rows is tenant-scoped via the
         parent ImportBatch (foreign batch_id -> None -> 404).
  * L1 — GET /sites/{pk}/infrastructure child queries (Device/Sim/Line) filter on
         current_user.tenant_id, not just site_id.
  * L2 — GET /devices/{pk}/sims SIM join filters on Sim.tenant_id.
  * L3 — command vendors/contracts vendor-name lookups filter on Vendor.tenant_id.
  * M2 — GET /api/zoho/config is gated behind VIEW_INTEGRATIONS (not customer-reachable).

Approach: the endpoints build their WHERE clauses inline, so a recording fake
session captures every compiled statement and we assert the tenant predicate is
present — proving the filter without a live DB (the suite has no DB fixture).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import (
    sites,
    devices,
    command_vendors,
    command_contracts,
    zoho_crm,
    subscriber_import,
)
from app.services import subscriber_import_engine


# ── Recording fake session ───────────────────────────────────────────
class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class RecordingSession:
    """Captures the compiled SQL of every ``execute`` and returns canned rows.

    Fails loudly on any write — PR-S1 touches only read endpoints.
    """

    def __init__(self, results):
        self._queue = list(results)
        self.statements: list[str] = []

    async def execute(self, stmt, *a, **k):
        self.statements.append(str(stmt))
        rows = self._queue.pop(0) if self._queue else []
        return _Result(rows)

    def add(self, *a, **k):
        raise AssertionError("PR-S1 endpoints must not write (add)")

    async def commit(self):
        raise AssertionError("PR-S1 endpoints must not write (commit)")

    async def flush(self):
        raise AssertionError("PR-S1 endpoints must not write (flush)")


def _client(router, *, role="User", tenant="tenantA", db=None, raise_server=True, prefix=""):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    if db is not None:
        app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        role=role, tenant_id=tenant, email="u@t.example", id=1
    )
    return TestClient(app, raise_server_exceptions=raise_server)


# ── H1 — subscriber-import batch rows ────────────────────────────────
@pytest.mark.asyncio
async def test_h1_engine_returns_none_for_foreign_batch():
    rec = RecordingSession([[]])  # ownership query: no batch owned by this tenant
    result = await subscriber_import_engine.get_batch_rows(rec, "tenantA", "b-foreign")
    assert result is None
    # ownership check is keyed on BOTH batch_id and tenant_id
    assert "tenant_id" in rec.statements[0] and "batch_id" in rec.statements[0]


@pytest.mark.asyncio
async def test_h1_engine_returns_rows_for_owned_batch():
    batch = SimpleNamespace(id=1, batch_id="b1", tenant_id="tenantA")
    row = SimpleNamespace(
        row_number=1, status="created", action_summary="", tenant_action="",
        site_action="", device_action="", line_action="", site_id_resolved=None,
        device_id_resolved=None, line_id_resolved=None, reconciliation_status=None,
        errors_json=None, warnings_json=None,
    )
    rec = RecordingSession([[batch], [row]])
    result = await subscriber_import_engine.get_batch_rows(rec, "tenantA", "b1")
    assert isinstance(result, list) and len(result) == 1
    assert result[0]["row_number"] == 1
    assert "tenant_id" in rec.statements[0]


def test_h1_router_404_when_batch_not_owned(monkeypatch):
    async def _none(db, tenant_id, batch_id):
        return None
    monkeypatch.setattr(subscriber_import, "get_batch_rows", _none)
    c = _client(subscriber_import.router, role="Admin", db=object())
    r = c.get("/subscriber-import/batches/foreign/rows")
    assert r.status_code == 404


def test_h1_router_passes_caller_tenant_and_returns_rows(monkeypatch):
    seen = {}

    async def _capture(db, tenant_id, batch_id):
        seen["tenant"] = tenant_id
        seen["batch"] = batch_id
        return []
    monkeypatch.setattr(subscriber_import, "get_batch_rows", _capture)
    c = _client(subscriber_import.router, role="Admin", tenant="tenantA", db=object())
    r = c.get("/subscriber-import/batches/b1/rows")
    assert r.status_code == 200 and r.json() == []
    assert seen == {"tenant": "tenantA", "batch": "b1"}  # caller tenant, not client-supplied


# ── L1 — site infrastructure child queries ───────────────────────────
def test_l1_site_infrastructure_all_queries_tenant_scoped():
    site = SimpleNamespace(
        id=1, site_id="S1", site_name="RH Yountville",
        e911_street=None, e911_city=None, e911_state=None, e911_zip=None, e911_status=None,
    )
    rec = RecordingSession([[site], [], [], []])  # site + device + sim + line
    c = _client(sites.router, role="User", db=rec, prefix="/sites")
    r = c.get("/sites/1/infrastructure")
    assert r.status_code == 200
    assert len(rec.statements) == 4  # site lookup + 3 child queries
    assert all("tenant_id" in s for s in rec.statements)  # every query tenant-scoped


# ── L2 — device sims join ────────────────────────────────────────────
def test_l2_device_sims_join_tenant_scoped():
    rec = RecordingSession([[SimpleNamespace(id=1)], []])  # device lookup + sim join
    c = _client(devices.router, role="User", db=rec, prefix="/devices")
    r = c.get("/devices/1/sims")
    assert r.status_code == 200
    assert len(rec.statements) == 2
    assert all("tenant_id" in s for s in rec.statements)


# ── L3 — vendor-name lookups ─────────────────────────────────────────
def test_l3_site_vendors_lookup_tenant_scoped():
    assignment = SimpleNamespace(
        vendor_id=7, id=1, site_id="S1", system_category="fire", is_primary=True, notes=None,
    )
    rec = RecordingSession([[assignment], []])  # assignments + vendor lookup
    c = _client(command_vendors.router, role="User", db=rec, raise_server=False)
    c.get("/site/S1/vendors")
    assert len(rec.statements) == 2
    assert all("tenant_id" in s for s in rec.statements)  # incl. the Vendor.id.in_ lookup


def test_l3_contracts_vendor_lookup_tenant_scoped():
    contract = SimpleNamespace(vendor_id=7)
    rec = RecordingSession([[contract], []])  # contracts + vendor lookup
    c = _client(command_contracts.router, role="User", db=rec, raise_server=False)
    c.get("/contracts")
    assert len(rec.statements) == 2
    assert all("tenant_id" in s for s in rec.statements)


# ── M2 — zoho/config gated ───────────────────────────────────────────
def test_m2_zoho_config_forbidden_for_customer(monkeypatch):
    monkeypatch.setattr("app.services.zoho_crm.config_summary", lambda: {"configured": False})
    c = _client(zoho_crm.router, role="User")  # User lacks VIEW_INTEGRATIONS
    r = c.get("/config")
    assert r.status_code == 403


def test_m2_zoho_config_allowed_for_admin(monkeypatch):
    monkeypatch.setattr("app.services.zoho_crm.config_summary", lambda: {"configured": False})
    c = _client(zoho_crm.router, role="Admin")
    r = c.get("/config")
    assert r.status_code == 200


def test_m2_zoho_config_unauthenticated_401():
    app = FastAPI()
    app.include_router(zoho_crm.router)
    app.dependency_overrides[get_db] = lambda: object()  # avoid real session creation
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/config")  # no auth header
    assert r.status_code == 401
