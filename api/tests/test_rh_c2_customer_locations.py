"""PR-C2 — customer locations list + detail endpoints.

Covers GET /api/customer/locations (flag gate, RBAC, pagination, status/q
filters, serialization) and GET /api/customer/locations/{location_ref}
(detail shape, scope limits, opaque-ref 404).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import customer
from app.services.customer import portfolio as cportfolio
from app.services.customer import serialize as cs

RH = "restoration-hardware"


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


def _site(sid, name, **kw):
    base = dict(id=sid, site_name=name, building_type="Gallery",
                e911_street="1 Main St", e911_city="Boston", e911_state="MA",
                e911_zip="02116", e911_status="validated", status="active",
                e911_confirmation_required=False,
                poc_name="Ops", poc_phone="555-0100", poc_email="ops@rh.example")
    base.update(kw)
    return SimpleNamespace(**base)


def _prot(label="Protected"):
    if label == "Protected":
        return cs.status_object("Protected", as_of="t", evidence=cs.evidence_object("t", ["online"]))
    return cs.status_object(label, as_of="t", reason="reason")


def _patch_portfolio(monkeypatch, pairs):
    async def _lp(db, tenant, now):
        return list(pairs)
    monkeypatch.setattr(cportfolio, "load_portfolio", _lp)


# ── Locations list ───────────────────────────────────────────────────
def test_locations_list_200(monkeypatch):
    _enable(monkeypatch)
    _patch_portfolio(monkeypatch, [
        (_site(1, "RH Boston"), _prot("Critical")),
        (_site(2, "RH Yountville"), _prot("Protected")),
    ])
    r = _client().get("/api/customer/locations")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["total"] == 2 and len(d["items"]) == 2
    assert d["items"][0]["location"] == "RH Boston"
    assert d["items"][0]["location_ref"].startswith("loc_")
    assert "emergency_address_state" in d["items"][0]
    assert "LEAK" not in r.text


def test_locations_filter_by_status(monkeypatch):
    _enable(monkeypatch)
    _patch_portfolio(monkeypatch, [
        (_site(1, "A"), _prot("Critical")),
        (_site(2, "B"), _prot("Protected")),
    ])
    items = _client().get("/api/customer/locations?status=Critical").json()["data"]["items"]
    assert len(items) == 1 and items[0]["protection"]["status"] == "Critical"


def test_locations_search_by_name(monkeypatch):
    _enable(monkeypatch)
    _patch_portfolio(monkeypatch, [
        (_site(1, "RH Boston"), _prot()),
        (_site(2, "RH Yountville"), _prot()),
    ])
    items = _client().get("/api/customer/locations?q=yount").json()["data"]["items"]
    assert len(items) == 1 and items[0]["location"] == "RH Yountville"


def test_locations_pagination(monkeypatch):
    _enable(monkeypatch)
    _patch_portfolio(monkeypatch, [(_site(i, f"S{i}"), _prot()) for i in range(1, 31)])
    d = _client().get("/api/customer/locations?page=2&page_size=10").json()["data"]
    assert d["total"] == 30 and d["page"] == 2 and len(d["items"]) == 10


def test_locations_page_size_capped_at_100(monkeypatch):
    # Contract: page_size max is 100.  Requesting more is a 422 (the blank-
    # dashboard bug: the frontend must page at <=100 and accumulate).  `total`
    # is always returned so the client can page through the whole portfolio.
    _enable(monkeypatch)
    _patch_portfolio(monkeypatch, [(_site(i, f"S{i}"), _prot()) for i in range(1, 43)])  # RH: 42
    ok = _client().get("/api/customer/locations?page=1&page_size=100")
    assert ok.status_code == 200 and ok.json()["data"]["total"] == 42
    assert len(ok.json()["data"]["items"]) == 42                # all 42 fit in one page of 100
    assert _client().get("/api/customer/locations?page_size=101").status_code == 422


def test_locations_404_when_flag_off(monkeypatch):
    _enable(monkeypatch, flag="false")
    _patch_portfolio(monkeypatch, [])
    assert _client().get("/api/customer/locations").status_code == 404


def test_locations_403_when_role_lacks_perm(monkeypatch):
    _enable(monkeypatch)
    _patch_portfolio(monkeypatch, [])
    assert _client(role="User").get("/api/customer/locations").status_code == 403


# ── Location detail ──────────────────────────────────────────────────
def test_location_detail_200(monkeypatch):
    _enable(monkeypatch)
    site = _site(5, "RH Yountville", e911_street="6725 Washington St",
                 e911_city="Yountville", e911_state="CA", e911_zip="94599")
    prot = _prot("Protected")

    async def _rl(db, tenant, ref, now):
        return (site, prot, [], [])  # (site, protection, services[], devices[])
    monkeypatch.setattr(cportfolio, "resolve_location", _rl)

    ref = cs.encode_ref("loc", 5)
    r = _client().get(f"/api/customer/locations/{ref}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["location"] == "RH Yountville"
    assert d["service_address"] == "6725 Washington St, Yountville, CA 94599"
    assert d["site_contact"]["editable"] is False
    assert d["emergency_address_state"] == "Verified"
    # PR-C3: services[] preview present; full E911 object still on its own endpoint
    assert "services" in d and "emergency_dispatch_address" not in d
    assert "LEAK" not in r.text


def test_location_detail_404_for_unknown_or_forged_ref(monkeypatch):
    _enable(monkeypatch)

    async def _rl(db, tenant, ref, now):
        return None
    monkeypatch.setattr(cportfolio, "resolve_location", _rl)
    assert _client().get("/api/customer/locations/loc_forged.bad").status_code == 404


# ── Serializer leak guard (unit) ─────────────────────────────────────
def test_location_mappers_leak_nothing():
    s = _site(9, "RH X", carrier="LEAKCARRIER", static_ip="LEAKIP", psap_id="LEAKPSAP",
              device_serial="LEAKSER", ng911_uri="LEAKNG", notes="LEAKNOTES")
    prot = cs.status_object("Unknown", reason="x")
    assert "LEAK" not in json.dumps(cs.location_summary(s, protection=prot))
    assert "LEAK" not in json.dumps(cs.location_detail(s, protection=prot))
