"""Location Digital Twin — serializers + sub-resource endpoints (Phase 1-9).

Enriched service model, placeholders (documents/photos/inspections), contacts,
timeline vocabulary, per-location building health, and the additive endpoints.
Additive + backward compatible; CUSTOMER_* isolation; no fabrication.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
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


def _unit(**kw):
    base = dict(id=10, unit_id="SU-10", unit_type="fire_alarm", unit_name="FACP",
                location_description="Utility room", floor="1", device_id="DEV-1", line_id="LN-1")
    base.update(kw)
    return SimpleNamespace(**base)


# ── Enriched service model (Phase 2) — additive + backward compatible ──
def test_service_with_equipment_backward_compatible():
    st = cs.status_object("Protected", as_of="t", evidence=cs.evidence_object("t", ["x"]))
    svc = cs.service_with_equipment(_unit(), status=st)   # legacy call: no new kwargs
    assert svc["service"] == "Fire Alarm" and svc["equipment"] == []
    # new fields present with safe defaults
    assert svc["equipment_count"] == 0 and svc["carrier"] is None
    assert svc["phone_numbers"] == [] and svc["last_test"] is None
    assert svc["last_inspection"] is None and svc["attention_items"] == []


def test_service_with_equipment_enriched_fields():
    st = cs.status_object("Attention Needed", as_of="t", reason="A compliance review is in progress.")
    eq = [{"equipment": "Fire alarm communicator", "health": "Online"}]
    svc = cs.service_with_equipment(_unit(), status=st, equipment=eq, carrier="tmobile",
                                    phone_numbers=["6175550100"], last_test=date(2026, 6, 1),
                                    last_inspection=None, attention_items=["A compliance review is in progress."])
    assert svc["equipment_count"] == 1
    assert svc["carrier"] == "T-Mobile"                       # friendly name, not raw
    assert svc["phone_numbers"] == ["6175550100"]
    assert svc["last_test"] == "2026-06-01"
    assert svc["attention_items"] == ["A compliance review is in progress."]


def test_carrier_label_never_raw_ids():
    assert cs.carrier_label("t-mobile") == "T-Mobile"
    assert cs.carrier_label("Telnyx") == "Telnyx"
    assert cs.carrier_label(None) is None


# ── Placeholders + contacts + timeline vocabulary (Phase 3/4) ────────
def test_documents_placeholder_scaffold_empty():
    d = cs.documents_placeholder()
    assert d["items"] == [] and d["available"] is False
    assert "permit" in d["categories"] and "e911_documentation" in d["categories"]


def test_inspections_placeholder_real_only():
    empty = cs.inspections_placeholder(items=[])
    assert empty["items"] == [] and empty["available"] is False
    assert "elevator" in empty["kinds"]
    filled = cs.inspections_placeholder(items=[{"when": "2026-06-01", "kind": "elevator"}])
    assert filled["available"] is True


def test_location_contacts_customer_safe():
    site = SimpleNamespace(poc_name="Gallery Ops", poc_phone="707-555-0142",
                           poc_email="ops@rh.example", notes="LEAK-INTERNAL", customer_id=99)
    c = cs.location_contacts(site)
    assert c["contacts"][0]["name"] == "Gallery Ops" and c["support"] == "Manley Solutions"
    assert "LEAK-INTERNAL" not in json.dumps(c) and "99" not in json.dumps(c["contacts"])


def test_timeline_entry_kinds_and_coercion():
    ok = cs.timeline_entry(kind="alarm_test", when=date(2026, 6, 1), title="Annual alarm test", detail="Passed")
    assert ok["kind"] == "alarm_test" and ok["when"] == "2026-06-01" and ok["detail"] == "Passed"
    coerced = cs.timeline_entry(kind="nonsense", title="x")
    assert coerced["kind"] == "activity"   # unknown kind -> neutral, not fabricated


# ── Building health (Phase 5) — real signals, unknown lowers confidence ──
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

    async def execute(self, stmt):
        return self._results.pop(0)


def test_load_location_health_preview_real_signals(monkeypatch):
    import asyncio
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_PREVIEW", "true")
    monkeypatch.setattr("app.config.settings.CUSTOMER_PREVIEW_TENANT_ALLOWLIST", RH)
    site = SimpleNamespace(id=5, site_id="RH-5", site_name="RH Yountville", tenant_id=RH,
                           e911_street="1 Main", e911_city="Yountville", e911_state="CA",
                           e911_zip="94599", e911_status="validated")
    unit = _unit()
    device = SimpleNamespace(device_id="DEV-1", device_type="fire_alarm", model="SLE",
                             status="active", activated_at=None, msisdn=None, last_heartbeat=None,
                             manufacturer=None, carrier=None, notes=None)  # no telemetry
    # sequence: resolve_site, units, devices, lines, overrides (service build); devices (telemetry)
    db = _FakeDB([_Res([site]), _Res([unit]), _Res([device]), _Res([]), _Res([]), _Res([device])])
    out = asyncio.run(cc.load_location_health(db, RH, cs.encode_ref("loc", 5), NOW))
    h = out["health"]
    # E911 verified (100) + operational services (preview 100) are known;
    # telemetry unknown (no heartbeat) -> confidence < 100, score not fabricated.
    assert h["score"] is not None and 0 <= h["confidence"] < 100
    tel = next(c for c in h["components"] if c["key"] == "telemetry")
    assert tel["known"] is False


# ── Endpoints: gate + RBAC + 404 (loaders monkeypatched) ─────────────
def _ref():
    return cs.encode_ref("loc", 2)


def test_twin_endpoints_200(monkeypatch):
    _enable(monkeypatch)

    async def _doc(db, t, r): return {"location": "X", "items": []}
    async def _photo(db, t, r): return {"location": "X", "items": []}
    async def _contact(db, t, r): return {"location": "X", "contacts": []}
    async def _insp(db, t, r): return {"location": "X", "items": []}
    async def _health(db, t, r, now): return {"location": "X", "health": {"score": 80}}
    monkeypatch.setattr(cc, "load_location_documents", _doc)
    monkeypatch.setattr(cc, "load_location_photos", _photo)
    monkeypatch.setattr(cc, "load_location_contacts", _contact)
    monkeypatch.setattr(cc, "load_location_inspections", _insp)
    monkeypatch.setattr(cc, "load_location_health", _health)
    c = _client()
    for path in ("documents", "photos", "contacts", "inspections", "health"):
        assert c.get(f"/api/customer/locations/{_ref()}/{path}").status_code == 200, path


def test_twin_endpoints_404_unknown_ref(monkeypatch):
    _enable(monkeypatch)

    async def _none3(db, t, r): return None
    async def _none4(db, t, r, now): return None
    monkeypatch.setattr(cc, "load_location_documents", _none3)
    monkeypatch.setattr(cc, "load_location_health", _none4)
    assert _client().get(f"/api/customer/locations/{_ref()}/documents").status_code == 404
    assert _client().get(f"/api/customer/locations/{_ref()}/health").status_code == 404


def test_twin_endpoints_404_flag_off(monkeypatch):
    _enable(monkeypatch, flag="false")
    assert _client().get(f"/api/customer/locations/{_ref()}/documents").status_code == 404


def test_twin_endpoints_403_wrong_role(monkeypatch):
    _enable(monkeypatch)  # internal User lacks CUSTOMER_VIEW_LOCATIONS
    assert _client(role="User").get(f"/api/customer/locations/{_ref()}/contacts").status_code == 403
