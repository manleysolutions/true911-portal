"""Building Workspace — contributions, separated health, maturity, de-branding.

Covers the collaborative additions (Phase 2/4/6/7): the append-only contribution
workflow (never writes protected data), the separated-health serializer (composite
shown after its factors, unknowns lower confidence), the Digital-Twin maturity tier
(Bronze/Silver/Gold/Platinum), the CUSTOMER_CONTRIBUTE gate, and the no-operating-
company-reference invariant for the customer plane.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import customer
from app.services import e911_review
from app.services.customer import command_center as cc
from app.services.customer import contributions as contrib
from app.services.customer import preview as cpreview
from app.services.customer import serialize as cs

RH = "restoration-hardware"
NOW = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


def _user(role="CUSTOMER_ADMIN", tenant=RH):
    return SimpleNamespace(role=role, tenant_id=tenant, email="judy@rh.example", name="Judy", id=1)


def _enable(monkeypatch, flag="true", allow=RH):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_API", flag)
    monkeypatch.setattr("app.config.settings.CUSTOMER_API_TENANT_ALLOWLIST", allow)


def _client(role="CUSTOMER_ADMIN", tenant=RH):
    app = FastAPI()
    app.include_router(customer.router, prefix="/api/customer")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: _user(role=role, tenant=tenant)
    return TestClient(app, raise_server_exceptions=False)


# ── Separated health (Phase 4): factors known/unknown, composite after ──
def test_separated_health_weighted_over_known_only():
    h = cs.separated_health(operational=100.0, completeness=50.0,
                            compliance=None, documentation=0.0)
    # known weight = 40 + 25 + 15 = 80; composite = (40*100 + 25*50 + 15*0)/80
    assert h["composite"] == 65.6
    assert h["confidence"] == 80.0
    assert len(h["factors"]) == 4
    comp = next(f for f in h["factors"] if f["key"] == "compliance")
    assert comp["known"] is False and comp["value"] is None
    op = next(f for f in h["factors"] if f["key"] == "operational_health")
    assert op["weight"] == 40 and op["value"] == 100.0


def test_separated_health_all_unknown_is_none_not_zero():
    h = cs.separated_health()
    assert h["composite"] is None and h["confidence"] == 0.0
    assert all(f["known"] is False for f in h["factors"])


# ── Maturity tier (Phase 7): Bronze/Silver/Gold/Platinum ─────────────
def test_building_maturity_tiers():
    assert cs.building_maturity({})["tier"] == "Bronze"
    assert cs.building_maturity({"contacts": True})["tier"] == "Bronze"           # 1
    assert cs.building_maturity({d: True for d in cs.MATURITY_DIMENSIONS[:3]})["tier"] == "Silver"  # 3
    assert cs.building_maturity({d: True for d in cs.MATURITY_DIMENSIONS[:5]})["tier"] == "Gold"    # 5
    full = cs.building_maturity({d: True for d in cs.MATURITY_DIMENSIONS})
    assert full["tier"] == "Platinum" and full["met"] == 7 and full["score"] == 100.0
    assert full["next_steps"] == []


def test_building_maturity_next_steps_are_unmet():
    m = cs.building_maturity({"contacts": True, "e911": True})
    assert m["met"] == 2 and m["total"] == 7
    assert "Site contacts" not in m["next_steps"]           # met -> not a next step
    assert "Documentation" in m["next_steps"]


# ── Contribution workflow (append-only, never writes protected data) ──
class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self_inner):
                return list(rows)
        return _S()


class _CaptureDB:
    """Fake session that captures added ActionAudit rows and replays them."""
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    async def commit(self):
        pass

    async def execute(self, stmt):
        return _Res(self.rows)


def test_record_contribution_writes_append_only_event():
    db = _CaptureDB()
    site = SimpleNamespace(site_id="RH-5")
    out = asyncio.run(contrib.record_contribution(
        db, _user(), site, ctype="contact",
        payload={"name": "Pat", "phone": "555-0100"}, note="front desk"))
    assert out["type"] == "contact" and out["status"] == "submitted"
    assert "awaiting review" in out["message"].lower()
    # exactly one append-only audit row, carrying the payload, tenant-scoped
    assert len(db.rows) == 1
    row = db.rows[0]
    assert row.action_type == contrib.CONTRIBUTION_ACTION and row.site_id == "RH-5"
    assert row.tenant_id == RH
    d = json.loads(row.details)
    assert d["payload"]["name"] == "Pat" and d["status"] == "submitted"


def test_record_note_is_recorded_not_submitted():
    db = _CaptureDB()
    out = asyncio.run(contrib.record_contribution(
        db, _user(), SimpleNamespace(site_id="RH-5"), ctype="note", payload={}, note="hi"))
    assert out["status"] == "recorded"


def test_record_contribution_rejects_unknown_type():
    db = _CaptureDB()
    try:
        asyncio.run(contrib.record_contribution(
            db, _user(), SimpleNamespace(site_id="RH-5"), ctype="bogus", payload={}))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "bogus" in str(e)
    assert db.rows == []                                    # nothing written


def test_list_and_counts_roundtrip():
    db = _CaptureDB()
    site = SimpleNamespace(site_id="RH-5")
    asyncio.run(contrib.record_contribution(db, _user(), site, ctype="contact", payload={"name": "A"}))
    asyncio.run(contrib.record_contribution(db, _user(), site, ctype="contact", payload={"name": "B"}))
    asyncio.run(contrib.record_contribution(db, _user(), site, ctype="photo", payload={"filename": "x.jpg"}))
    listed = asyncio.run(contrib.list_contributions(db, RH, "RH-5"))
    assert listed["count"] == 3 and listed["by_type"]["contact"] == 2 and listed["by_type"]["photo"] == 1
    assert listed["contributions"][0]["payload"]              # payload exposed for the UI
    counts = asyncio.run(contrib.contribution_counts(db, RH, "RH-5"))
    assert counts == {"contact": 2, "photo": 1}


# ── Endpoints: gate + RBAC + 404 + 422 ───────────────────────────────
def test_add_contribution_endpoint_ok(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(customer.cportfolio, "resolve_site",
                        lambda db, tenant, ref: _async(SimpleNamespace(site_id="RH-5")))

    async def _rec(db, user, site, *, ctype, payload, note=""):
        assert ctype == "contact"
        return {"contribution_id": "CTR-1", "type": ctype, "status": "submitted", "message": "ok"}
    monkeypatch.setattr(contrib, "record_contribution", _rec)
    ref = cs.encode_ref("loc", 5)
    r = _client().post(f"/api/customer/locations/{ref}/contributions",
                       json={"type": "contact", "payload": {"name": "Pat"}})
    assert r.status_code == 200 and r.json()["data"]["contribution_id"] == "CTR-1"


def test_add_contribution_unknown_type_is_422(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(customer.cportfolio, "resolve_site",
                        lambda db, tenant, ref: _async(SimpleNamespace(site_id="RH-5")))

    async def _rec(db, user, site, *, ctype, payload, note=""):
        raise ValueError(f"Unknown contribution type '{ctype}'")
    monkeypatch.setattr(contrib, "record_contribution", _rec)
    ref = cs.encode_ref("loc", 5)
    r = _client().post(f"/api/customer/locations/{ref}/contributions", json={"type": "bogus"})
    assert r.status_code == 422


def test_add_contribution_404_when_location_missing(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(customer.cportfolio, "resolve_site", lambda db, tenant, ref: _async(None))
    ref = cs.encode_ref("loc", 5)
    r = _client().post(f"/api/customer/locations/{ref}/contributions", json={"type": "note", "note": "x"})
    assert r.status_code == 404


def test_add_contribution_forbidden_for_readonly_role(monkeypatch):
    _enable(monkeypatch)                                    # VIEWER lacks CUSTOMER_CONTRIBUTE
    ref = cs.encode_ref("loc", 5)
    r = _client(role="CUSTOMER_VIEWER").post(
        f"/api/customer/locations/{ref}/contributions", json={"type": "note", "note": "x"})
    assert r.status_code == 403


def test_list_contributions_visible_to_readonly(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(customer.cportfolio, "resolve_site",
                        lambda db, tenant, ref: _async(SimpleNamespace(site_id="RH-5")))
    monkeypatch.setattr(contrib, "list_contributions",
                        lambda db, tenant, sid: _async({"count": 0, "by_type": {}, "contributions": []}))
    ref = cs.encode_ref("loc", 5)
    r = _client(role="CUSTOMER_VIEWER").get(f"/api/customer/locations/{ref}/contributions")
    assert r.status_code == 200 and r.json()["data"]["count"] == 0


def test_add_contribution_404_flag_off(monkeypatch):
    _enable(monkeypatch, flag="false")
    ref = cs.encode_ref("loc", 5)
    r = _client().post(f"/api/customer/locations/{ref}/contributions", json={"type": "note"})
    assert r.status_code == 404


# ── De-branding invariant (Phase 3): no operating-company references ──
def test_no_operating_company_reference_in_customer_plane():
    for mod in (cs, e911_review, cpreview, contrib, cc):
        src = inspect.getsource(mod)
        assert "Manley" not in src, f"operating-company reference leaked in {mod.__name__}"


def _async(value):
    async def _c():
        return value
    return _c()
