"""Customer Portfolio-Registry read model — mode gating, aggregation, redaction.

No DB fixture exists, so these mock the query seams (visible rows / load_portfolio /
link indexes / service inference) and test the pure aggregation + serializer.  Pins:
flag OFF -> legacy (None), flag ON + no buildings -> fallback (None), approved
visible, pending hidden by default / visible under preview, and that no source-system
internals (Zoho / Napco / Genesis / ICCID / IMEI / raw aliases) ever leak.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services.customer import command_center as cc
from app.services.customer import portfolio as cportfolio
from app.services.customer import portfolio_registry_view as prv
from app.services.customer import serialize as cs

RH = "restoration-hardware"
NOW = __import__("datetime").datetime(2026, 7, 2, 12, 0, tzinfo=__import__("datetime").timezone.utc)


def _flags_on(monkeypatch, *, registry="true", allow=RH, show_pending="false",
              preview="false", preview_allow=RH):
    monkeypatch.setattr("app.config.settings.FEATURE_CUSTOMER_PORTFOLIO_REGISTRY", registry)
    monkeypatch.setattr("app.config.settings.CUSTOMER_PORTFOLIO_REGISTRY_TENANT_ALLOWLIST", allow)
    monkeypatch.setattr("app.config.settings.CUSTOMER_SHOW_PENDING_PORTFOLIO_BUILDINGS", show_pending)
    monkeypatch.setattr("app.config.settings.CUSTOMER_PORTFOLIO_PREVIEW_PENDING", preview)
    monkeypatch.setattr("app.config.settings.CUSTOMER_PORTFOLIO_PREVIEW_TENANT_ALLOWLIST", preview_allow)


def _building(**kw):
    base = dict(id=1, tenant_id=RH, canonical_name="Restoration Hardware #147 Chicago",
                store_number="147", site_type="gallery", status="active",
                address="123 Michigan Ave", city="Chicago", state="IL", zip="60601",
                approved=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _site(**kw):
    base = dict(site_id="RH-147", site_name="Restoration Hardware #147 Chicago",
                e911_street="123 Michigan Ave", e911_city="Chicago", e911_state="IL",
                e911_zip="60601", e911_status="validated", lat=41.88, lng=-87.62, poc_name="Pat")
    base.update(kw)
    return SimpleNamespace(**base)


def _svc(status="Protected", equipment=2, phones=("3125550100",), service="Fire Alarm"):
    return {"service": service, "status": {"status": status}, "equipment_count": equipment,
            "phone_numbers": list(phones)}


def _prot(status):
    """A plain protection dict (bypasses the no-false-green evidence rule for tests)."""
    return {"status": status, "as_of": NOW.isoformat(), "reason": None}


def _wire(monkeypatch, rows, sites_portfolio, services):
    """Patch the DB seams so load_customer_buildings runs the pure aggregation."""
    async def _vis(db, tenant):
        return rows
    async def _lp(db, tenant, now):
        return sites_portfolio
    async def _idx(db, tenant, sp):
        site_by_id = {s.site_id: (s, p) for s, p in sp}
        by_store, by_addr = {}, {}
        for s, _p in sp:
            st = prv._site_store_number(s.site_name)
            if st:
                by_store.setdefault(st, []).append(s.site_id)
        return site_by_id, by_store, by_addr, {}
    async def _svcs(db, tenant, site, now):
        return services
    monkeypatch.setattr(prv, "_visible_building_rows", _vis)
    monkeypatch.setattr(cportfolio, "load_portfolio", _lp)
    monkeypatch.setattr(prv, "_link_indexes", _idx)
    monkeypatch.setattr(cc, "_build_location_services", _svcs)


# ── mode gating ──────────────────────────────────────────────────────
def test_flag_off_returns_none_legacy(monkeypatch):
    _flags_on(monkeypatch, registry="false")
    assert asyncio.run(prv.load_customer_buildings(object(), RH, NOW)) is None


def test_flag_on_wrong_tenant_returns_none(monkeypatch):
    _flags_on(monkeypatch, allow="someone-else")
    assert prv.registry_mode_enabled(RH) is False
    assert asyncio.run(prv.load_customer_buildings(object(), RH, NOW)) is None


def test_flag_on_no_buildings_falls_back_to_legacy(monkeypatch):
    _flags_on(monkeypatch)
    _wire(monkeypatch, rows=[], sites_portfolio=[], services=[])
    assert asyncio.run(prv.load_customer_buildings(object(), RH, NOW)) is None   # -> legacy


# ── aggregation (approved building) ──────────────────────────────────
def test_approved_building_aggregates_from_linked_site(monkeypatch):
    _flags_on(monkeypatch)
    prot = _prot("Protected")
    _wire(monkeypatch, rows=[(_building(), False)],
          sites_portfolio=[(_site(), prot)], services=[_svc()])
    recs = asyncio.run(prv.load_customer_buildings(object(), RH, NOW))
    assert len(recs) == 1
    r = recs[0]
    assert r["equipment_count"] == 2 and r["phone_count"] == 1
    assert r["e911_verified"] is True and r["protection"]["status"] == "Protected"
    assert r["confidence"] == prv._HIGH_CONFIDENCE
    # serialized customer-safe building
    out = cs.portfolio_building(r)
    assert out["display_name"] == "Chicago Gallery #147"
    assert out["life_safety_services_count"] == 1 and out["confidence"] == "High"
    assert out["customer_visible_status"] == "Protected"


def test_pending_hidden_by_default_visible_under_preview(monkeypatch):
    # default: pending building NOT visible -> fallback (None)
    _flags_on(monkeypatch)   # show_pending false, preview false
    assert prv._include_pending(RH) is False
    # preview ON: pending building visible
    _flags_on(monkeypatch, preview="true")
    assert prv._include_pending(RH) is True
    _wire(monkeypatch, rows=[(_building(approved=False), True)],
          sites_portfolio=[(_site(), _prot("Protected"))],
          services=[_svc()])
    recs = asyncio.run(prv.load_customer_buildings(object(), RH, NOW))
    assert len(recs) == 1 and recs[0]["pending"] is True
    out = cs.portfolio_building(recs[0])
    # calm wording — never "pending review"; street hidden for pending
    assert out["customer_visible_status"] == "Portfolio record being finalized"
    assert "pending review" not in json.dumps(out).lower()
    assert out["service_address"] is None


# ── dashboard / summary / search ─────────────────────────────────────
def _records(monkeypatch, statuses=("Protected", "Attention Needed")):
    _flags_on(monkeypatch)
    rows = [(_building(id=i + 1, store_number=str(140 + i),
                       canonical_name=f"Restoration Hardware #{140+i} City{i}"), False)
            for i in range(len(statuses))]
    sites = [(_site(site_id=f"RH-{140+i}", site_name=f"Restoration Hardware #{140+i} City{i}",
                    e911_status="validated" if statuses[i] == "Protected" else "pending"),
              _prot(statuses[i])) for i in range(len(statuses))]

    async def _vis(db, tenant):
        return rows
    async def _lp(db, tenant, now):
        return sites
    async def _idx(db, tenant, sp):
        sbi = {s.site_id: (s, p) for s, p in sp}
        bystore = {}
        for s, _p in sp:
            bystore.setdefault(prv._site_store_number(s.site_name), []).append(s.site_id)
        return sbi, bystore, {}, {}
    async def _svcs(db, tenant, site, now):
        return [_svc(status="Protected" if "pending" not in (site.e911_status or "") else "Attention Needed")]
    monkeypatch.setattr(prv, "_visible_building_rows", _vis)
    monkeypatch.setattr(cportfolio, "load_portfolio", _lp)
    monkeypatch.setattr(prv, "_link_indexes", _idx)
    monkeypatch.setattr(cc, "_build_location_services", _svcs)
    return asyncio.run(prv.load_customer_buildings(object(), RH, NOW))


def test_dashboard_counts_buildings(monkeypatch):
    recs = _records(monkeypatch, statuses=("Protected", "Protected", "Attention Needed"))
    d = prv.dashboard(recs, "Restoration Hardware", NOW)
    assert d["portfolio"]["total"] == 3 and d["portfolio"]["protected"] == 2
    assert d["portfolio"]["attention_needed"] == 1


def test_summary_uses_registry_services_and_devices(monkeypatch):
    recs = _records(monkeypatch, statuses=("Protected", "Protected"))
    s = prv.summary(recs, "Restoration Hardware", NOW)
    assert s["locations_total"] == 2 and s["life_safety_services"] == 2
    assert s["total_devices"] == 4 and s["total_phone_numbers"] >= 1   # KPIs no longer 0
    assert s["monthly_health_score"]["score"] is not None              # not 0/100 placeholder


def test_search_matches_canonical_store_city(monkeypatch):
    recs = _records(monkeypatch, statuses=("Protected",))
    assert prv.search(recs, "140")["results"]           # store number
    assert prv.search(recs, "city0")["results"]         # city
    assert prv.search(recs, "zzz-nope")["results"] == []


def test_location_detail_uses_building_ref(monkeypatch):
    recs = _records(monkeypatch, statuses=("Protected",))
    ref = recs[0]["building_ref"]
    detail = prv.building_detail(recs, ref)
    assert detail is not None and detail["building_ref"] == ref
    assert prv.building_detail(recs, "loc_forged.bad") is None   # wrong-kind ref -> None


# ── redaction: no source-system internals ever leak ─────────────────
def test_serializer_hides_source_internals(monkeypatch):
    recs = _records(monkeypatch, statuses=("Protected",))
    blob = json.dumps([cs.portfolio_building(r) for r in recs]).lower()
    for banned in ("zoho", "napco", "genesis", "iccid", "imei", "radio_number",
                   "review", "alias", "starlink"):
        assert banned not in blob, f"leaked source-system term: {banned}"


# ── pure serializer / display-name / confidence bucket ───────────────
def test_display_name_examples():
    assert cs.building_display_name("RH #147 Chicago", "147", "Chicago", "gallery") == "Chicago Gallery #147"
    assert cs.building_display_name("RH Linden House", None, None, "special") == "Linden House Gallery"
    assert cs.building_display_name("Restoration Hardware Beverly Modern", None, None, "special") == "Beverly Modern Gallery"
    assert cs.building_display_name("RH Hollywood", None, "Hollywood", "gallery") == "Hollywood Gallery"


def test_confidence_bucket():
    assert cs.confidence_bucket(100) == "High" and cs.confidence_bucket(60) == "Medium"
    assert cs.confidence_bucket(30) == "Needs review" and cs.confidence_bucket(None) == "Needs review"
