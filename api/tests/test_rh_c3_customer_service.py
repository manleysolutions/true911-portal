"""PR-C3 — customer service detail + equipment health.

Covers GET /api/customer/services/{service_ref} and
GET /api/customer/services/{service_ref}/equipment (flag gate, RBAC, opaque-ref
404, empty equipment, sentinel-leak) plus the service-protection composition
(engine device label + compliance/status) in services/customer/portfolio.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import customer
from app.services.customer import portfolio as cportfolio
from app.services.customer import serialize as cs
from app.services.assurance.signals import AssuranceLabel

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


def _unit(uid=1, **kw):
    base = dict(id=uid, unit_id="U1", unit_name="Elevator #1 Phone", unit_type="elevator_phone",
                location_description="Elevator #1", floor="1", voice_supported=True,
                video_supported=False, text_supported=False, compliance_status="compliant",
                governing_code_edition="ASME A17.1-2019", status="active", device_id="dev-1",
                line_id=None, sim_id=None, monitoring_station_type="LEAKMON",
                jurisdiction_code="LEAKJUR", notes="LEAKNOTES", video_stream_url="LEAKURL")
    base.update(kw)
    return SimpleNamespace(**base)


def _device(**kw):
    base = dict(device_type="elevator_phone", model="LEAKMODEL", status="active",
                last_heartbeat=NOW, activated_at=None, serial_number="LEAKSER", imei="LEAKIMEI",
                iccid="LEAKICCID", msisdn="LEAKMSISDN", carrier="LEAKCAR", vola_org_id="LEAKVOLA")
    base.update(kw)
    return SimpleNamespace(**base)


def _prot(label="Protected"):
    if label == "Protected":
        return cs.status_object("Protected", as_of="t", evidence=cs.evidence_object("t", ["device reporting"]))
    return cs.status_object(label, as_of="t", reason="reason")


def _da(label, last_hb=NOW, codes=()):
    return SimpleNamespace(device_id="dev-1", label=label, reason_codes=codes, last_heartbeat_at=last_hb)


# ── Service detail endpoint ──────────────────────────────────────────
def test_service_detail_200(monkeypatch):
    _enable(monkeypatch)
    unit, device = _unit(), _device()

    async def _rs(db, t, ref, now):
        return (unit, device, _prot("Protected"), _prot("Protected"))
    monkeypatch.setattr(cportfolio, "resolve_service", _rs)

    r = _client().get(f"/api/customer/services/{cs.encode_ref('svc', 1)}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["service"] == "Elevator emergency phone"
    assert d["name"] == "Elevator #1 Phone"
    assert d["can_call_for_help"] == ["Voice"]
    assert d["service_ref"].startswith("svc_")
    assert d["equipment"]["equipment"] == "Elevator phone unit"
    assert "LEAK" not in r.text


def test_service_detail_no_device_omits_equipment(monkeypatch):
    _enable(monkeypatch)

    async def _rs(db, t, ref, now):
        return (_unit(device_id=None), None, _prot("Unknown"),
                cs.status_object("Unknown", reason="No monitored equipment yet"))
    monkeypatch.setattr(cportfolio, "resolve_service", _rs)
    d = _client().get(f"/api/customer/services/{cs.encode_ref('svc', 1)}").json()["data"]
    assert "equipment" not in d


def test_service_404_forged(monkeypatch):
    _enable(monkeypatch)

    async def _rs(db, t, ref, now):
        return None
    monkeypatch.setattr(cportfolio, "resolve_service", _rs)
    assert _client().get("/api/customer/services/svc_forged.bad").status_code == 404


def test_service_404_flag_off(monkeypatch):
    _enable(monkeypatch, flag="false")
    assert _client().get(f"/api/customer/services/{cs.encode_ref('svc', 1)}").status_code == 404


def test_service_403_billing_role(monkeypatch):
    _enable(monkeypatch)  # CUSTOMER_BILLING lacks CUSTOMER_VIEW_SERVICES
    assert _client(role="CUSTOMER_BILLING").get(
        f"/api/customer/services/{cs.encode_ref('svc', 1)}").status_code == 403


# ── Equipment endpoint ───────────────────────────────────────────────
def test_equipment_200(monkeypatch):
    _enable(monkeypatch)

    async def _rs(db, t, ref, now):
        return (_unit(), _device(), _prot("Protected"), _prot("Protected"))
    monkeypatch.setattr(cportfolio, "resolve_service", _rs)
    r = _client().get(f"/api/customer/services/{cs.encode_ref('svc', 1)}/equipment")
    d = r.json()["data"]
    assert d["equipment"] == "Elevator phone unit"
    assert d["health"] == "Online"
    assert d["protection"]["status"] == "Protected"
    assert "LEAK" not in r.text


def test_equipment_null_when_no_device(monkeypatch):
    _enable(monkeypatch)

    async def _rs(db, t, ref, now):
        return (_unit(device_id=None), None, _prot("Unknown"),
                cs.status_object("Unknown", reason="No monitored equipment yet"))
    monkeypatch.setattr(cportfolio, "resolve_service", _rs)
    d = _client().get(f"/api/customer/services/{cs.encode_ref('svc', 1)}/equipment").json()["data"]
    assert d["equipment"] is None and d["protection"]["status"] == "Unknown"


def test_equipment_403_billing_role(monkeypatch):
    _enable(monkeypatch)  # CUSTOMER_BILLING lacks CUSTOMER_VIEW_DEVICES
    assert _client(role="CUSTOMER_BILLING").get(
        f"/api/customer/services/{cs.encode_ref('svc', 1)}/equipment").status_code == 403


# ── Service-protection composition (no DB) ───────────────────────────
def test_service_protection_protected_with_evidence():
    p = cportfolio._service_protection(_unit(compliance_status="compliant"), _da(AssuranceLabel.PROTECTED), NOW)
    assert p["status"] == "Protected" and p["evidence"]


def test_service_protection_non_compliant_is_critical():
    p = cportfolio._service_protection(_unit(compliance_status="non_compliant"), _da(AssuranceLabel.PROTECTED), NOW)
    assert p["status"] == "Critical"


def test_service_protection_review_is_attention():
    p = cportfolio._service_protection(_unit(compliance_status="review_required"), _da(AssuranceLabel.PROTECTED), NOW)
    assert p["status"] == "Attention Needed"


def test_service_protection_device_critical():
    p = cportfolio._service_protection(_unit(compliance_status="compliant"), _da(AssuranceLabel.CRITICAL), NOW)
    assert p["status"] == "Critical"


def test_service_protection_pending_and_inactive():
    assert cportfolio._service_protection(_unit(status="pending_install"), None, NOW)["status"] == "Pending Install"
    assert cportfolio._service_protection(_unit(status="inactive"), _da(AssuranceLabel.PROTECTED), NOW)["status"] == "Inactive"


def test_service_protection_no_device_is_unknown():
    p = cportfolio._service_protection(_unit(compliance_status="compliant"), None, NOW)
    assert p["status"] == "Unknown"


def test_equipment_protection_no_device_and_protected():
    none_p = cportfolio._protection_from_device_assurance(None, NOW)
    assert none_p["status"] == "Unknown" and none_p["reason"] == "No monitored equipment yet"
    ok_p = cportfolio._protection_from_device_assurance(_da(AssuranceLabel.PROTECTED), NOW)
    assert ok_p["status"] == "Protected" and ok_p["evidence"]
