"""RH urgent go-live customer login preview.

Proves the four contract points of the preview feature:

  1. An RH customer sees locations / services / devices as Active/Green while
     preview is enabled (before live telemetry), evidenced by an honest operator
     attestation — not fabricated telemetry, no "pending" labels.
  2. The E911 axis is UNAFFECTED by preview and comes from real stored data:
     the emergency address, per-endpoint detail (where / service type / callback
     number) and the ``verified`` flag are all derived from stored records; the
     flag is true ONLY when the stored ``e911_status`` is actually verified.
  3. Missing / unverified E911 data is surfaced INTERNALLY for correction
     (``services.e911_gaps``) — the fix-before-verify worklist.
  4. Internal / raw state is never mutated and, with preview OFF, behaviour is
     exactly the pre-preview behaviour (no false green without evidence).

Two-key gate (mirrors the customer API): FEATURE_CUSTOMER_PREVIEW == "true" AND
tenant in CUSTOMER_PREVIEW_TENANT_ALLOWLIST.  Rollback = flip either off.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.routers import customer, e911 as e911_router
from app.services import e911_gaps
from app.services.customer import portfolio as cportfolio
from app.services.customer import preview as cpreview
from app.services.customer import serialize as cs

RH = "restoration-hardware"
OTHER = "acme-corp"
NOW = datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


# ── Fakes ────────────────────────────────────────────────────────────
class _Res:
    """Minimal stand-in for a SQLAlchemy Result: supports both
    ``scalars().all()`` and ``scalar_one_or_none()``."""

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
    """Returns queued results in call order."""

    def __init__(self, results):
        self._results = list(results)

    async def execute(self, stmt):
        return self._results.pop(0)


def _user(role="CUSTOMER_ADMIN", tenant=RH):
    return SimpleNamespace(role=role, tenant_id=tenant, email="judy@rh.example",
                           name="Judy", id=1)


def _enable_api(monkeypatch, flag="true", allow=RH):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_API", flag)
    monkeypatch.setattr("app.config.settings.CUSTOMER_API_TENANT_ALLOWLIST", allow)


def _enable_preview(monkeypatch, flag="true", allow=RH):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_PREVIEW", flag)
    monkeypatch.setattr("app.config.settings.CUSTOMER_PREVIEW_TENANT_ALLOWLIST", allow)


def _client(router, prefix, db, role="CUSTOMER_ADMIN", tenant=RH):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _user(role=role, tenant=tenant)
    return TestClient(app, raise_server_exceptions=False)


def _site(sid=1, name="RH Yountville", **kw):
    base = dict(id=sid, site_id=f"RH-{sid}", site_name=name, building_type="Gallery",
                customer_name="Restoration Hardware",
                e911_street="6725 Washington St", e911_city="Yountville",
                e911_state="CA", e911_zip="94599", e911_status="pending",
                status="active", e911_confirmation_required=False,
                poc_name="Ops", poc_phone="707-555-0142", poc_email="ops@rh.example",
                # sentinels that must never leak to the customer:
                device_serial="LEAKSERIAL", carrier="LEAKCARRIER", psap_id="LEAKPSAP")
    base.update(kw)
    return SimpleNamespace(**base)


def _unit(uid=10, **kw):
    base = dict(id=uid, unit_id=f"SU-{uid}", tenant_id=RH, site_id="RH-1",
                unit_name="Elevator #1 phone", unit_type="elevator_phone",
                location_description="Elevator #1, South Tower", floor="1",
                status="active", compliance_status="compliant",
                governing_code_edition="ASME A17.1",
                voice_supported=True, video_supported=False, text_supported=False,
                device_id="DEV-1", line_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _device(**kw):
    base = dict(device_id="DEV-1", tenant_id=RH, device_type="elevator_phone",
                status="inactive", last_heartbeat=None, activated_at=None,
                msisdn="7075550142", iccid="LEAKICCID", imei="LEAKIMEI")
    base.update(kw)
    return SimpleNamespace(**base)


# ── 1. Two-key gate ──────────────────────────────────────────────────
def test_preview_enabled_requires_both_keys(monkeypatch):
    _enable_preview(monkeypatch, flag="false", allow=RH)
    assert cpreview.preview_enabled(RH) is False
    _enable_preview(monkeypatch, flag="true", allow="")  # tenant not allowlisted
    assert cpreview.preview_enabled(RH) is False
    _enable_preview(monkeypatch, flag="true", allow=OTHER)
    assert cpreview.preview_enabled(RH) is False
    _enable_preview(monkeypatch, flag="true", allow=RH)
    assert cpreview.preview_enabled(RH) is True
    assert cpreview.preview_enabled(OTHER) is False  # other tenant unaffected


def test_preview_protection_is_evidenced_green():
    p = cpreview.preview_protection(NOW)
    assert p["status"] == "Protected"          # survives no-false-green recode
    assert p["evidence"]["signals"] == [cpreview.PREVIEW_SIGNAL]
    assert p["evidence"]["source"] == "operator"
    # No "pending / api / telemetry" language shown to the customer.
    blob = json.dumps(p).lower()
    for banned in ("pending", "api ", "telemetry"):
        assert banned not in blob


# ── 1. Locations / devices Active/Green under preview ────────────────
def test_load_portfolio_preview_all_protected(monkeypatch):
    _enable_preview(monkeypatch)
    sites = [_site(1, "RH A", status="inactive"), _site(2, "RH B", e911_status="pending")]
    db = _FakeDB([_Res(sites)])  # preview short-circuits: only the Site query runs

    called = {"assurance": False}

    async def _boom(*a, **k):
        called["assurance"] = True
        raise AssertionError("assurance must not run in preview")

    monkeypatch.setattr(cportfolio, "load_site_assurance_signals", _boom)

    import asyncio
    out = asyncio.run(cportfolio.load_portfolio(db, RH, NOW))
    assert called["assurance"] is False
    assert [p["status"] for _s, p in out] == ["Protected", "Protected"]
    assert all(p["evidence"]["signals"] == [cpreview.PREVIEW_SIGNAL] for _s, p in out)
    # raw Site rows are never mutated by the presentation override
    assert sites[0].status == "inactive"


def test_service_endpoint_device_green_under_preview(monkeypatch):
    _enable_api(monkeypatch)
    _enable_preview(monkeypatch)
    unit, device = _unit(), _device(status="inactive", last_heartbeat=None)
    db = _FakeDB([_Res([unit]), _Res([device])])  # resolve_service: unit, then device
    r = _client(customer.router, "/api/customer", db).get(
        f"/api/customer/services/{cs.encode_ref('svc', unit.id)}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["protection"]["status"] == "Protected"
    assert d["equipment"]["health"] == "Online"          # green despite status=inactive
    assert d["equipment"]["protection"]["status"] == "Protected"
    assert d["equipment"]["last_seen"] is None            # NOT fabricated
    # raw device untouched + no identifier leak
    assert device.status == "inactive"
    assert "LEAKICCID" not in r.text and "LEAKIMEI" not in r.text


# ── 4. Preview OFF == original no-false-green behaviour ──────────────
def test_equipment_offline_when_preview_off():
    off = cs.equipment_from_device(_device(status="inactive"), protection={"status": "Unknown"},
                                   preview=False)
    assert off["health"] == "Offline"
    on = cs.equipment_from_device(_device(status="inactive"), protection={"status": "Protected"},
                                  preview=True)
    assert on["health"] == "Online" and on["last_seen"] is None


# ── 2. E911 comes from REAL stored data (preview does not touch it) ──
def test_e911_verified_flag_only_true_when_stored_verified():
    assert cs.e911_summary(_site(e911_status="pending"))["verification"]["verified"] is False
    assert cs.e911_summary(_site(e911_status="validated"))["verification"]["verified"] is True
    assert cs.e911_summary(_site(e911_status="verified"))["verification"]["verified"] is True


def test_e911_endpoint_item_real_fields_where_applicable():
    full = cs.e911_endpoint_item(_unit(), callback_number="7075550142")
    assert full == {"service_type": "Elevator emergency phone",
                    "where": "Elevator #1, South Tower", "floor": "1",
                    "callback_number": "7075550142"}
    # "where applicable": absent floor / location / callback are dropped, never faked
    sparse = cs.e911_endpoint_item(_unit(floor=None, location_description=None),
                                   callback_number=None)
    assert sparse == {"service_type": "Elevator emergency phone"}


def test_load_e911_endpoints_pulls_line_then_device(monkeypatch):
    # unit A: linked line -> Line.did wins; unit B: no line -> Device.msisdn
    unit_a = _unit(10, unit_id="SU-10", line_id="LN-1", device_id="DEV-9")
    unit_b = _unit(11, unit_id="SU-11", line_id=None, device_id="DEV-1")
    db = _FakeDB([
        _Res([unit_a, unit_b]),   # ServiceUnit list
        _Res(["6135550001"]),     # Line.did for unit_a
        _Res(["7075550142"]),     # Device.msisdn for unit_b
    ])
    import asyncio
    eps = asyncio.run(cportfolio.load_e911_endpoints(db, RH, "RH-1"))
    assert eps[0]["callback_number"] == "6135550001"   # line preferred
    assert eps[1]["callback_number"] == "7075550142"   # device fallback


def test_e911_endpoint_preview_does_not_verify(monkeypatch):
    _enable_api(monkeypatch)
    _enable_preview(monkeypatch)  # preview ON — E911 must still tell the truth
    site = _site(2, "RH Boston", e911_status="pending", status="active")

    async def _rsite(db, t, ref):
        return site

    async def _rhist(db, t, sid):
        return []

    async def _reps(db, t, sid):
        return [cs.e911_endpoint_item(_unit(), callback_number="7075550142")]

    monkeypatch.setattr(cportfolio, "resolve_site", _rsite)
    monkeypatch.setattr(cportfolio, "load_e911_history", _rhist)
    monkeypatch.setattr(cportfolio, "load_e911_endpoints", _reps)
    d = _client(customer.router, "/api/customer", object()).get(
        f"/api/customer/locations/{cs.encode_ref('loc', 2)}/e911").json()["data"]
    assert d["verification"]["verified"] is False        # not faked green
    assert d["verification"]["is_critical"] is True       # active + unverified
    assert d["emergency_dispatch_address"] == "6725 Washington St, Yountville, CA 94599"
    assert d["emergency_endpoints"][0]["callback_number"] == "7075550142"


# ── Dashboard polish: map points + location devices (customer-safe) ──
def test_location_summary_map_point_only_when_valid():
    prot = cs.status_object("Unknown", reason="x")
    assert cs.location_summary(_site(1), protection=prot)["map_point"] is None  # no coords
    valid = cs.location_summary(_site(1, lat=38.5, lng=-97.0), protection=prot)
    assert valid["map_point"] == {"lat": 38.5, "lng": -97.0}
    # 0,0 (null island) and out-of-range are rejected, never plotted
    assert cs.location_summary(_site(1, lat=0.0, lng=0.0), protection=prot)["map_point"] is None
    assert cs.location_summary(_site(1, lat=999.0, lng=1.0), protection=prot)["map_point"] is None


def test_location_device_customer_safe_and_preview_online():
    dev = _device(status="inactive", model="StarLink SLE", last_heartbeat=None)
    prot = cs.status_object("Protected", as_of="t", evidence=cs.evidence_object("t", ["x"]))
    on = cs.location_device(dev, protection=prot, preview=True, identifier="6175550100")
    assert on["health"] == "Online"                      # preview greens health
    assert on["model"] == "StarLink SLE"                  # model shown when present
    assert on["identifier"] == "6175550100"
    # No raw identifiers leak (serial/iccid/imei/firmware/carrier)
    assert "LEAKICCID" not in json.dumps(on) and "LEAKIMEI" not in json.dumps(on)
    # Absent model/identifier are omitted (never fabricated)
    bare = cs.location_device(_device(model=None), protection=prot, preview=False, identifier=None)
    assert "model" not in bare and "identifier" not in bare
    assert bare["health"] == "Offline"                    # inactive + no preview


# ── 3. Missing E911 surfaced internally for correction ──────────────
def test_compute_site_e911_gaps_flags_missing_and_unverified():
    # complete + verified -> no gap
    good = _site(e911_status="validated")
    assert e911_gaps.compute_site_e911_gaps(
        good, [(_unit(), "7075550142")]) is None
    # unverified address-complete site -> verification gap only
    g1 = e911_gaps.compute_site_e911_gaps(_site(e911_status="pending"),
                                          [(_unit(), "7075550142")])
    assert g1["missing"] == ["e911_verification"] and g1["e911_verified"] is False
    # missing address + endpoint with no callback / no location
    bare_site = _site(e911_street=None, e911_status="pending")
    bare_unit = _unit(unit_type="", floor=None, location_description=None)
    g2 = e911_gaps.compute_site_e911_gaps(bare_site, [(bare_unit, None)])
    assert "service_address" in g2["missing"]
    assert g2["endpoint_gaps"][0]["missing"] == ["service_type", "location", "callback_number"]


def test_list_e911_gaps_omits_complete_sites(monkeypatch):
    verified_site = _site(1, "RH Verified", e911_status="validated")
    pending_site = _site(2, "RH Pending", e911_status="pending")
    db = _FakeDB([
        _Res([verified_site, pending_site]),  # Site list
        _Res([]),                             # units for verified_site
        _Res([]),                             # units for pending_site
    ])
    import asyncio
    gaps = asyncio.run(e911_gaps.list_e911_gaps(db, RH))
    assert [g["site_name"] for g in gaps] == ["RH Pending"]  # verified omitted


def test_e911_gaps_endpoint_rbac(monkeypatch):
    async def _lg(db, tenant):
        return [{"site_id": "RH-2", "site_name": "RH Pending", "e911_verified": False,
                 "missing": ["e911_verification"], "endpoint_gaps": []}]

    monkeypatch.setattr(e911_router, "list_e911_gaps", _lg)
    # Admin holds UPDATE_E911 -> 200
    ok = _client(e911_router.router, "/api", object(), role="Admin").get("/api/e911-changes/gaps")
    assert ok.status_code == 200
    assert ok.json()["gap_count"] == 1
    # a customer role does NOT hold UPDATE_E911 -> 403 (internal-only worklist)
    denied = _client(e911_router.router, "/api", object(), role="CUSTOMER_ADMIN").get(
        "/api/e911-changes/gaps")
    assert denied.status_code == 403
