"""Customer Command Center — serializers + endpoints (Phase 1/3/4/6/8).

Pure allow-list serializer tests (health score, portfolio summary, service-first
grouping, timeline, catalog) + endpoint tests (flag gate, RBAC, shapes, 404).
No fabrication; CUSTOMER_* isolation preserved.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import customer
from app.services.customer import command_center as cc
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


# ── Service catalog + region (service-first vocabulary) ──────────────
def test_service_catalog_is_enterprise_not_jargon():
    assert cs.enterprise_service_label("fire_alarm") == "Fire Alarm"
    assert cs.enterprise_service_label("area_of_refuge") == "Area of Refuge"
    assert cs.enterprise_service_label("bda_das") == "BDA/DAS"
    assert cs.enterprise_service_label("generator") == "Generator Monitoring"
    assert cs.enterprise_service_label("elevator_phone") == "Elevator"
    # unknown/None -> generic, never a raw model string
    assert cs.enterprise_service_label("lm150") == "Life Safety Service"
    assert cs.enterprise_service_label(None) == "Life Safety Service"


def test_us_region_derivation():
    assert cs.us_region("CA") == "West"
    assert cs.us_region("ny") == "Northeast"
    assert cs.us_region("TX") == "South"
    assert cs.us_region("ZZ") is None


# ── Health score (Phase 6): unknowns reduce confidence, never fabricated ──
def test_health_score_weighted_over_known_only():
    h = cs.health_score({"e911_verified": 100.0, "service_coverage": 50.0,
                         "telemetry": None, "alarm_testing": None, "carrier": None})
    # known weight = 30 + 25 = 55; score = (30*100 + 25*50)/55
    assert h["score"] == 77.3
    assert h["confidence"] == 55.0          # 55 of 100 total weight known
    assert h["grade"] == "Good"
    # unknown components are flagged, not invented
    tel = next(c for c in h["components"] if c["key"] == "telemetry")
    assert tel["known"] is False and tel["value"] is None


def test_health_score_all_unknown_is_unknown_not_zero():
    h = cs.health_score({k: None for k in
                         ("e911_verified", "service_coverage", "telemetry", "alarm_testing", "carrier")})
    assert h["score"] is None and h["confidence"] == 0.0 and h["grade"] == "Unknown"


def test_health_score_full_confidence():
    h = cs.health_score({"e911_verified": 100.0, "service_coverage": 100.0,
                         "telemetry": 100.0, "alarm_testing": 100.0, "carrier": 100.0})
    assert h["score"] == 100.0 and h["confidence"] == 100.0 and h["grade"] == "Excellent"


# ── Portfolio summary (Phase 1) ──────────────────────────────────────
def test_portfolio_summary_percentages_and_shape():
    counts = {"total": 42, "protected": 39, "attention_needed": 2, "critical": 1,
              "pending_install": 0, "inactive": 0, "unknown": 0}
    health = cs.health_score({"e911_verified": 90.0})
    s = cs.portfolio_summary(
        company="Restoration Hardware", counts=counts, services=51, protected_services=48,
        devices=51, phone_numbers=47, e911_verified=40, e911_with_address=42, health=health,
        recent_activity=[{"when": "2026-07-14", "kind": "e911_verified", "title": "x", "by": "Manley Solutions"}],
        upcoming_maintenance=[], as_of=NOW.isoformat())
    assert s["portfolio_name"] == "Restoration Hardware"
    assert s["locations_total"] == 42 and s["locations_protected"] == 39
    assert s["life_safety_services"] == 51 and s["protected_services"] == 48
    assert s["total_phone_numbers"] == 47
    assert s["e911_verification_pct"] == round(100 * 40 / 42, 1)
    assert s["service_availability_pct"] == round(100 * 48 / 51, 1)
    assert s["monthly_health_score"]["grade"] in ("Good", "Fair", "Excellent", "Needs attention", "Unknown")
    assert s["upcoming_maintenance"] == []


def test_portfolio_summary_pct_none_when_nothing_to_measure():
    s = cs.portfolio_summary(company="X", counts={"total": 0}, services=0, protected_services=0,
                             devices=0, phone_numbers=0, e911_verified=0, e911_with_address=0,
                             health=cs.health_score({}), recent_activity=[], upcoming_maintenance=[],
                             as_of=NOW.isoformat())
    assert s["e911_verification_pct"] is None and s["service_availability_pct"] is None


# ── Service-first grouping (Phase 4) ─────────────────────────────────
def _unit(**kw):
    base = dict(id=10, unit_id="SU-10", unit_type="fire_alarm", unit_name="FACP",
                location_description="Utility room", floor="1")
    base.update(kw)
    return SimpleNamespace(**base)


def test_service_with_equipment_groups_equipment_under_service():
    status = cs.status_object("Protected", as_of="t", evidence=cs.evidence_object("t", ["x"]))
    dev = SimpleNamespace(device_type="fire_alarm", status="active", activated_at=None,
                          model="SLE", msisdn="6175550100", iccid="LEAKICCID", imei="LEAKIMEI")
    eq = cs.location_device(dev, protection=status, preview=True, identifier="6175550100")
    svc = cs.service_with_equipment(_unit(), status=status, equipment=[eq])
    assert svc["service"] == "Fire Alarm"          # enterprise service name
    assert svc["equipment"][0]["equipment"] == "Fire alarm communicator"
    assert svc["status"]["status"] == "Protected"
    # no raw identifiers leak through the service card
    assert "LEAKICCID" not in json.dumps(svc) and "LEAKIMEI" not in json.dumps(svc)


def test_timeline_item_real_only():
    log = SimpleNamespace(applied_at=NOW, requested_at=NOW, status="validated",
                          requester_name="Manley Tech", requested_by="internal@x", correlation_id="LEAK")
    it = cs.timeline_item(log)
    assert it["kind"] == "e911_verified" and it["title"] == "Emergency address verified"
    assert it["by"] == "Manley Tech"
    assert "LEAK" not in json.dumps(it) and "internal@x" not in json.dumps(it)


# ── Endpoints: gate + RBAC + shape + 404 (loaders monkeypatched) ─────
def test_portfolio_summary_endpoint(monkeypatch):
    _enable(monkeypatch)

    async def _ls(db, tenant, now):
        return {"portfolio_name": "RH", "locations_total": 42, "monthly_health_score": {"score": 80}}
    monkeypatch.setattr(cc, "load_portfolio_summary", _ls)
    r = _client().get("/api/customer/portfolio/summary")
    assert r.status_code == 200 and r.json()["data"]["locations_total"] == 42


def test_portfolio_summary_404_flag_off(monkeypatch):
    _enable(monkeypatch, flag="false")
    assert _client().get("/api/customer/portfolio/summary").status_code == 404


def test_health_endpoint(monkeypatch):
    _enable(monkeypatch)

    async def _lh(db, tenant, now):
        return {"as_of": "t", "health": {"score": 72, "confidence": 60}}
    monkeypatch.setattr(cc, "load_portfolio_health", _lh)
    r = _client().get("/api/customer/portfolio/health")
    assert r.status_code == 200 and r.json()["data"]["health"]["confidence"] == 60


def test_search_endpoint_and_scope(monkeypatch):
    _enable(monkeypatch)

    async def _sp(db, tenant, q, now):
        assert tenant == RH
        return {"query": q, "results": [{"location_ref": "loc_x", "location": "RH Boston"}]}
    monkeypatch.setattr(cc, "search_portfolio", _sp)
    r = _client().get("/api/customer/search?q=boston")
    assert r.status_code == 200
    assert r.json()["data"]["results"][0]["location"] == "RH Boston"


def test_location_services_200_and_404(monkeypatch):
    _enable(monkeypatch)

    async def _found(db, tenant, ref, now):
        return {"location": "RH Boston", "services": []}
    monkeypatch.setattr(cc, "load_location_services", _found)
    ref = cs.encode_ref("loc", 2)
    assert _client().get(f"/api/customer/locations/{ref}/services").status_code == 200

    async def _none(db, tenant, ref, now):
        return None
    monkeypatch.setattr(cc, "load_location_services", _none)
    assert _client().get(f"/api/customer/locations/{ref}/services").status_code == 404


def test_timeline_200(monkeypatch):
    _enable(monkeypatch)

    async def _tl(db, tenant, ref):
        return {"location": "RH", "timeline": []}
    monkeypatch.setattr(cc, "load_location_timeline", _tl)
    ref = cs.encode_ref("loc", 2)
    assert _client().get(f"/api/customer/locations/{ref}/timeline").status_code == 200


def test_command_center_403_for_wrong_role(monkeypatch):
    _enable(monkeypatch)  # internal "User" lacks CUSTOMER_VIEW_DASHBOARD
    monkeypatch.setattr(cc, "load_portfolio_summary", lambda *a, **k: {})
    assert _client(role="User").get("/api/customer/portfolio/summary").status_code == 403


# ── Loader-level (fake DB): search + service-first grouping ──────────
class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self_inner):
                return list(rows)
        return _S()

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, stmt):
        return self._results.pop(0)


def test_search_portfolio_scopes_and_dedupes(monkeypatch):
    import asyncio
    site = SimpleNamespace(id=7, site_id="RH-7", site_name="RH Boston",
                           e911_city="Boston", e911_state="MA", e911_street="1 Main",
                           e911_zip="02116", e911_status="validated", lat=None, lng=None)
    db = _FakeDB([
        _Res([("RH-7",)]),   # sites by name/city/state/id
        _Res([("RH-7",)]),   # service units (same site -> dedupe)
        _Res([]),            # devices by msisdn
        _Res([("RH-7",)]),   # lines by did
        _Res([site]),        # final Site load
    ])
    out = asyncio.run(cc.search_portfolio(db, RH, "boston", NOW))
    assert out["query"] == "boston"
    assert len(out["results"]) == 1                       # deduped to one location
    assert out["results"][0]["location"] == "RH Boston"
    assert out["results"][0]["emergency_address_state"] == "Verified"


def test_search_empty_query_returns_nothing():
    import asyncio
    out = asyncio.run(cc.search_portfolio(_FakeDB([]), RH, "  ", NOW))
    assert out["results"] == []


def test_load_location_services_groups_equipment_preview(monkeypatch):
    import asyncio
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_PREVIEW", "true")
    monkeypatch.setattr("app.config.settings.CUSTOMER_PREVIEW_TENANT_ALLOWLIST", RH)
    site = SimpleNamespace(id=5, site_id="RH-5", site_name="RH Yountville", tenant_id=RH)
    unit = SimpleNamespace(id=10, unit_id="SU-10", unit_type="fire_alarm", unit_name="FACP",
                           location_description="Utility", floor="1", device_id="DEV-1", line_id="LN-1")
    device = SimpleNamespace(device_id="DEV-1", device_type="fire_alarm", status="inactive",
                             activated_at=None, model="SLE", msisdn="6175550100")
    db = _FakeDB([
        _Res([site]),          # resolve_site
        _Res([unit]),          # service units
        _Res([device]),        # devices for site
        _Res([SimpleNamespace(line_id="LN-1", did="6175559999")]),  # lines for site
    ])
    out = asyncio.run(cc.load_location_services(db, RH, cs.encode_ref("loc", 5), NOW))
    assert out["location"] == "RH Yountville"
    svc = out["services"][0]
    assert svc["service"] == "Fire Alarm"                  # enterprise, not model
    assert svc["status"]["status"] == "Protected"          # preview greens the service
    eq = svc["equipment"][0]
    assert eq["health"] == "Online"                        # preview greens equipment
    assert eq["identifier"] == "6175559999"                # line DID preferred over msisdn
    assert eq["model"] == "SLE"
