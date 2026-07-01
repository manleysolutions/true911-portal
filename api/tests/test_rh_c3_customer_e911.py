"""PR-C3 — customer E911 summary (read-only, address axis only).

Covers GET /api/customer/locations/{location_ref}/e911 (flag gate, RBAC,
opaque-ref 404, active+unverified = Critical, history sanitization, axis
separation) and the e911_history_item allow-list mapper.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import customer
from app.services.customer import portfolio as cportfolio
from app.services.customer import serialize as cs

RH = "restoration-hardware"
NOW = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


def _user(role="CUSTOMER_ADMIN", tenant=RH):
    return SimpleNamespace(role=role, tenant_id=tenant, email="judy@rh.example", id=1)


def _enable(monkeypatch, flag="true", allow=RH):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_API", flag)
    monkeypatch.setattr("app.config.settings.CUSTOMER_API_TENANT_ALLOWLIST", allow)


def _client(role="CUSTOMER_ADMIN", tenant=RH):
    app = FastAPI()
    app.include_router(customer.router, prefix="/api/customer")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: _user(role=role, tenant=tenant)
    return TestClient(app, raise_server_exceptions=False)


def _site(sid=2, name="RH Boston", **kw):
    base = dict(id=sid, site_id="RH-BOS-1", site_name=name, e911_street="234 Berkeley St", e911_city="Boston",
                e911_state="MA", e911_zip="02116", e911_status="pending", status="active",
                e911_confirmation_required=False, psap_id="LEAKPSAP", ng911_uri="LEAKNG",
                emergency_class="LEAKEC", address_source="LEAKSRC")
    base.update(kw)
    return SimpleNamespace(**base)


def _log(status="validated", **kw):
    base = dict(applied_at=NOW, requested_at=NOW, status=status, requester_name="Manley Tech",
                requested_by="internal@manley.example", correlation_id="LEAKCORR",
                old_street="LEAKOLD", new_street="234 Berkeley St")
    base.update(kw)
    return SimpleNamespace(**base)


def _patch(monkeypatch, site, logs, endpoints=None):
    async def _rsite(db, t, ref):
        return site

    async def _rhist(db, t, sid):
        return list(logs)

    async def _reps(db, t, sid):
        return list(endpoints or [])
    monkeypatch.setattr(cportfolio, "resolve_site", _rsite)
    monkeypatch.setattr(cportfolio, "load_e911_history", _rhist)
    monkeypatch.setattr(cportfolio, "load_e911_endpoints", _reps)


# ── Endpoint ─────────────────────────────────────────────────────────
def test_e911_active_unverified_is_critical(monkeypatch):
    _enable(monkeypatch)
    _patch(monkeypatch, _site(e911_status="pending", status="active"), [_log(status="pending")])
    r = _client().get(f"/api/customer/locations/{cs.encode_ref('loc', 2)}/e911")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["emergency_dispatch_address"] == "234 Berkeley St, Boston, MA 02116"
    assert d["verification"]["state"] == "Not yet verified"
    assert d["verification"]["is_critical"] is True
    assert d["customer_actions"] == ["Request an address correction"]
    # axis separation — no operational/device health on the E911 surface
    for k in ("protection", "health", "equipment"):
        assert k not in d
    # history sanitized (no requester email / correlation id)
    blob = json.dumps(d)
    assert "LEAKCORR" not in blob and "internal@manley.example" not in blob and "LEAKPSAP" not in blob
    assert d["address_history"][0]["by"] == "Manley Tech"


def test_e911_verified_active_not_critical(monkeypatch):
    _enable(monkeypatch)
    _patch(monkeypatch, _site(e911_status="validated", status="active"), [])
    d = _client().get(f"/api/customer/locations/{cs.encode_ref('loc', 2)}/e911").json()["data"]
    assert d["verification"]["state"] == "Verified"
    assert d["verification"]["is_critical"] is False


def test_e911_404_forged(monkeypatch):
    _enable(monkeypatch)

    async def _rsite(db, t, ref):
        return None
    monkeypatch.setattr(cportfolio, "resolve_site", _rsite)
    assert _client().get("/api/customer/locations/loc_forged.bad/e911").status_code == 404


def test_e911_404_flag_off(monkeypatch):
    _enable(monkeypatch, flag="false")
    assert _client().get(f"/api/customer/locations/{cs.encode_ref('loc', 2)}/e911").status_code == 404


def test_e911_403_billing_role(monkeypatch):
    _enable(monkeypatch)  # CUSTOMER_BILLING lacks CUSTOMER_VIEW_E911
    assert _client(role="CUSTOMER_BILLING").get(
        f"/api/customer/locations/{cs.encode_ref('loc', 2)}/e911").status_code == 403


# ── History mapper (allow-list) ──────────────────────────────────────
def test_e911_history_item_sanitized():
    item = cs.e911_history_item(_log(status="validated"))
    assert set(item) == {"when", "change", "by", "state"}
    assert item["change"] == "Address verified" and item["by"] == "Manley Tech"
