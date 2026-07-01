"""Life Safety Service intelligence — inference engine + internal ops (Phase 1-9).

Inference rules, service grouping (multi-device), confidence, manual override,
and the internal approve/override/merge/split flow (persisted + logged as
append-only ActionAudit).  CUSTOMER_* isolation from the internal surface.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import service_classification as sc_router
from app.services import service_classification as scs
from app.services.customer import service_inference as si

RH = "restoration-hardware"


# ── Phase 1/2: classification rules ──────────────────────────────────
@pytest.mark.parametrize("item,expect", [
    ({"model": "MS130", "notes": "Fire Adapter FACP"}, "Fire Alarm"),
    ({"model": "LM150", "device_type": "ata", "notes": "elevator phone"}, "Elevator"),
    ({"device_type": "emergency_call_station"}, "Emergency Phone"),   # underscore enum
    ({"notes": "Area of Refuge station"}, "Area of Refuge"),
    ({"model": "generator monitor"}, "Generator Monitoring"),
    ({"notes": "public safety DAS / BDA"}, "BDA/DAS"),
    ({"notes": "mass notification paging"}, "Mass Notification"),
    ({"notes": "burglar intrusion panel"}, "Burglar Alarm"),
    ({"model": "mystery-box-9000"}, "Life Safety Service"),           # unclassified
])
def test_classify_service_types(item, expect):
    stype, conf, _src = si.classify(item)
    assert stype == expect


def test_classify_confidence_levels():
    assert si.classify({"unit_type": "fire_alarm"})[1] == "Confirmed"   # ServiceUnit anchor
    assert si.classify({"model": "MS130 fire alarm"})[1] == "High"      # specific keyword
    assert si.classify({"notes": "some alarm"})[1] == "Medium"          # generic keyword
    assert si.classify({"model": "unknown"})[1] == "Low"               # no signal


# ── Grouping: one service, many devices; distinct locations split ────
def test_grouping_multi_device_and_split():
    items = [
        {"device_id": "d1", "model": "MS130", "notes": "FACP fire", "where": "Utility"},
        {"device_id": "d2", "notes": "fire alarm communicator", "where": "Utility"},  # same service
        {"device_id": "d3", "notes": "elevator phone", "where": "Elevator 1"},
        {"device_id": "d4", "notes": "elevator phone", "where": "Elevator 2"},
    ]
    svcs = si.infer_services(items)
    fire = [s for s in svcs if s["service_type"] == "Fire Alarm"]
    elevators = [s for s in svcs if s["service_type"] == "Elevator"]
    assert len(fire) == 1 and set(fire[0]["device_ids"]) == {"d1", "d2"}   # multi-device service
    assert len(elevators) == 2                                             # distinct where -> distinct


def test_override_wins_and_empty_units_surface():
    svcs = si.infer_services([{"device_id": "d1", "model": "x"}], overrides={"d1": "Burglar Alarm"})
    assert svcs[0]["service_type"] == "Burglar Alarm" and svcs[0]["confidence"] == "Confirmed"
    # a ServiceUnit with no device still surfaces as a service (0 equipment)
    empty = si.infer_services([], empty_units=[{"unit_type": "fire_alarm", "where": "Roof"}])
    assert empty and empty[0]["service_type"] == "Fire Alarm" and empty[0]["equipment"] == []


# ── Phase 8: internal ops (persist + log via ActionAudit) ────────────
class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

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
        self.added = []
        self.committed = False

    async def execute(self, stmt):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def _user(role="Admin", tenant=RH):
    return SimpleNamespace(role=role, tenant_id=tenant, email="ops@manley.example", name="Ops", id=1)


def test_record_override_writes_audit_per_device():
    import asyncio
    db = _FakeDB([])
    out = asyncio.run(scs.record_override(db, _user(), site_id="RH-5", service_type="Fire Alarm",
                                          device_ids=["d1", "d2"], operation="merge", reason="both feed FACP"))
    assert out["logged"] == 2 and out["operation"] == "merge"
    assert len(db.added) == 2 and db.committed is True
    # every override is an append-only audit record with structured details
    a = db.added[0]
    assert a.action_type == si.OVERRIDE_ACTION and a.site_id == "RH-5"
    d = json.loads(a.details)
    assert d["service_type"] == "Fire Alarm" and d["operation"] == "merge" and d["device_id"] in ("d1", "d2")


def test_record_override_rejects_unknown_service_type():
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(scs.record_override(_FakeDB([]), _user(), site_id="RH-5",
                                        service_type="Not A Service", device_ids=["d1"], operation="override"))


def test_load_overrides_latest_wins():
    import asyncio
    # rows are returned newest-first (id desc); first seen per device wins
    rows = [
        SimpleNamespace(details=json.dumps({"device_id": "d1", "service_type": "Elevator"})),
        SimpleNamespace(details=json.dumps({"device_id": "d1", "service_type": "Fire Alarm"})),  # older
    ]
    out = asyncio.run(scs.load_overrides(_FakeDB([_Res(rows)]), RH, "RH-5"))
    assert out == {"d1": "Elevator"}


# ── Phase 8 endpoints: internal-only (CUSTOMER_* isolated) ───────────
def _client(role="Admin", db=None):
    app = FastAPI()
    app.include_router(sc_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: (db or object())
    app.dependency_overrides[get_current_user] = lambda: _user(role=role)
    return TestClient(app, raise_server_exceptions=False)


def test_classification_endpoint_rbac(monkeypatch):
    async def _infer(db, t, sid):
        return {"site_id": sid, "site_name": "RH", "services": [], "override_count": 0}
    monkeypatch.setattr(scs, "infer_site_classification", _infer)
    # internal roles allowed; customer roles blocked (isolation)
    assert _client(role="Admin").get("/api/service-classification/RH-5").status_code == 200
    assert _client(role="DataSteward").get("/api/service-classification/RH-5").status_code == 200
    assert _client(role="CUSTOMER_ADMIN").get("/api/service-classification/RH-5").status_code == 403
    assert _client(role="User").get("/api/service-classification/RH-5").status_code == 403


def test_override_endpoint_writes_and_validates(monkeypatch):
    async def _site_ok(db, t, sid):
        return SimpleNamespace(site_id=sid)

    async def _rec(db, user, *, site_id, service_type, device_ids, operation, reason):
        return {"site_id": site_id, "operation": operation, "service_type": service_type,
                "devices": device_ids, "logged": len(device_ids)}
    monkeypatch.setattr(scs, "_site", _site_ok)
    monkeypatch.setattr(scs, "record_override", _rec)
    r = _client(role="Admin").post("/api/service-classification/override",
                                   json={"site_id": "RH-5", "service_type": "Elevator", "device_id": "d1"})
    assert r.status_code == 200 and r.json()["logged"] == 1

    # no device -> 422
    bad = _client(role="Admin").post("/api/service-classification/override",
                                     json={"site_id": "RH-5", "service_type": "Elevator"})
    assert bad.status_code == 422

    # customer role cannot override (isolation)
    denied = _client(role="CUSTOMER_ADMIN").post("/api/service-classification/override",
                                                 json={"site_id": "RH-5", "service_type": "Elevator", "device_id": "d1"})
    assert denied.status_code == 403


def test_override_endpoint_404_unknown_site(monkeypatch):
    async def _site_none(db, t, sid):
        return None
    monkeypatch.setattr(scs, "_site", _site_none)
    r = _client(role="Admin").post("/api/service-classification/override",
                                   json={"site_id": "NOPE", "service_type": "Elevator", "device_id": "d1"})
    assert r.status_code == 404
