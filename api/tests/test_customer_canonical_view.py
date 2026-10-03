"""#186b canonical customer service-inventory read model (real SQLite + routers).

READY only for a service of the latest clean APPLY run that is a life-safety
type, not REJECTED, CONFIRMED (or APPROVED), CURRENT, with >= 1 REQUIRED
connection, at an approved, active, non-suspect building.  Probable /
unresolved / unclassified only ever make a building BEING_FINALIZED; historical
and rejected services are never shown; no service / connection grand totals;
FACP never carries a telephone number; E911 is untouched; flag off (or a missing
durable ref secret, or no clean run) changes nothing.  SYNTHETIC identifiers.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.canonical import (
    CommunicationsAsset,
    ConnectionAssetLink,
    LifeSafetyConnection,
    LifeSafetyService,
    OperatorDecision,
    ProjectionRun,
)
from app.models.portfolio_registry import PortfolioBuilding
from app.services.canonical import vocab as V
from app.services.customer import canonical_view as cv
from tests import _customer_db as cdb
from tests._customer_db import client_for, user
from app.services.customer.refs import encode_ref
from tests.test_customer_self_service import RH, ROUTERS, flags, seed  # noqa: F401

SECRET = "c" * 48
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
CANONICAL = [m.__table__ for m in (ProjectionRun, CommunicationsAsset, LifeSafetyService,
                                   LifeSafetyConnection, ConnectionAssetLink, OperatorDecision)]
RADIO, SIM, ELEV_TEL, FACP_TEL = "77110020", "8901000000000000077", "3125550142", "3125550143"
EMPTY = 40                                           # an approved building with no services


async def make_db():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                              connect_args={"check_same_thread": False})
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=cdb.TABLES + CANONICAL))
    return eng, async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)


async def canonical_world(Session, *, run_degraded=False, run_finished=True, suspect_b1=False):
    async with Session() as db:
        db.add(PortfolioBuilding(id=EMPTY, tenant_id=RH, canonical_name="Quiet Gallery #700",
                                 store_number="700", site_type="gallery", status="active",
                                 approved=True))
        db.add(ProjectionRun(id=1, tenant_id=RH, mode="APPLY", run_by="t", started_at=NOW,
                             finished_at=NOW, degraded=False))                 # older run
        db.add(ProjectionRun(id=2, tenant_id=RH, mode="APPLY", run_by="t", started_at=NOW,
                             finished_at=NOW if run_finished else None, degraded=run_degraded))
        assets = [(1, V.TELEPHONE_NUMBER, ELEV_TEL), (2, V.NAPCO_RADIO, RADIO),
                  (3, V.SIM_ICCID, SIM), (4, V.TELEPHONE_NUMBER, FACP_TEL)]
        for aid, t, v in assets:
            db.add(CommunicationsAsset(id=aid, tenant_id=RH, asset_type=t, normalized_value=v,
                                       display_value=v, lifecycle="CURRENT",
                                       placement_confidence="CONFIRMED", building_id=1,
                                       last_projection_run_id=2))

        def svc(sid, bid, key, stype, conf, lc, approval="NONE", run=2, name=None):
            db.add(LifeSafetyService(id=sid, tenant_id=RH, building_id=bid, service_key=key,
                                     service_type=stype, display_name=name, confidence=conf,
                                     approval=approval, lifecycle=lc, last_projection_run_id=run))

        def conn(cid, sid, n, run=2, req=V.REQUIRED):
            db.add(LifeSafetyConnection(id=cid, tenant_id=RH, service_id=sid, ordinal=n,
                                        connection_type="X", requirement=req,
                                        provisioning="NOT_EVALUATED", confidence="CONFIRMED",
                                        last_projection_run_id=run))

        def link(lid, cid, aid, rel):
            db.add(ConnectionAssetLink(id=lid, tenant_id=RH, connection_id=cid, asset_id=aid,
                                       relationship=rel, active=True))
        # building 1: a READY elevator (with its carrier line), a READY FACP (2 paths;
        # a carrier-line link is present but an FACP never shows a number) and a
        # PROBABLE FACP -> PARTIALLY_READY
        svc(10, 1, "ELEV:tel:" + ELEV_TEL, V.ELEVATOR, V.CONFIRMED, V.CURRENT, name="Elevator 1")
        conn(100, 10, 1)
        link(1000, 100, 1, V.REL_CARRIER_LINE)
        svc(11, 1, "FACP:radio:" + RADIO, V.FACP, V.CONFIRMED, V.CURRENT, name="Fire alarm panel")
        conn(110, 11, 1)
        conn(111, 11, 2)
        link(1100, 110, 2, V.REL_SERVICE_EQUIPMENT)
        link(1101, 110, 3, V.REL_SERVICE_EQUIPMENT)
        link(1102, 111, 4, V.REL_CARRIER_LINE)
        svc(12, 1, "FACP:radio:7700001", V.FACP, V.PROBABLE, V.CURRENT)
        # building 2: historical (never shown), rejected (never shown), stale-run
        # (ignored) and an UNCLASSIFIED current line -> BEING_FINALIZED
        svc(20, 2, "ELEV:tel:5125550001", V.ELEVATOR, V.CONFIRMED, V.DECOMMISSIONED)
        svc(21, 2, "ELEV:tel:5125550002", V.ELEVATOR, V.CONFIRMED, V.CURRENT, approval=V.REJECTED)
        conn(210, 21, 1)
        svc(22, 2, "ELEV:tel:5125550003", V.ELEVATOR, V.CONFIRMED, V.CURRENT, run=1)
        conn(220, 22, 1, run=1)
        svc(23, 2, "UNCL:tel:5125550004", V.UNCLASSIFIED, V.UNRESOLVED, V.CURRENT)
        if suspect_b1:
            db.add(OperatorDecision(tenant_id=RH, decision_type=V.D_BUILDING_IDENTITY_SUSPECT,
                                    decision_key="BUILDING_IDENTITY_SUSPECT:b1",
                                    subject=json.dumps({"building_id": 1}),
                                    new_state=json.dumps({"suspect": True}), reason="x",
                                    source="OPERATOR", recorded_by="t", recorded_at=NOW,
                                    input_fingerprint="f"))
        await db.commit()


@pytest.fixture
def canon(monkeypatch, flags):
    def set_canon(*, on="true", tenants=RH, secret=SECRET):
        s = "app.config.settings."
        monkeypatch.setattr(s + "FEATURE_CANONICAL_SERVICE_MODEL", on)
        monkeypatch.setattr(s + "CANONICAL_SERVICE_MODEL_TENANT_ALLOWLIST", tenants)
        monkeypatch.setattr(s + "CUSTOMER_REF_SECRET", secret)
    set_canon()
    return set_canon


def run(scenario, **world):
    async def _go():
        engine, Session = await make_db()
        try:
            await seed(Session)
            await canonical_world(Session, **world)
            state = {"user": user()}
            async with client_for(ROUTERS, Session, state) as c:
                return await scenario(c)
        finally:
            await engine.dispose()
    return asyncio.run(_go())


async def _get(c, path):
    r = await c.get(path)
    assert r.status_code == 200, (path, r.status_code, r.text[:200])
    return r.json()["data"]


def b1():
    return encode_ref("bldg", 1)        # minted with the CURRENT key (refs rotate with it)


def b2():
    return encode_ref("bldg", 2)


def _all():
    return ["/api/customer/dashboard", "/api/customer/portfolio/summary",
            "/api/customer/portfolio/services", "/api/customer/locations",
            f"/api/customer/locations/{b1()}", f"/api/customer/locations/{b1()}/services",
            f"/api/customer/locations/{b1()}/workspace", f"/api/customer/locations/{b2()}/workspace"]


async def _everything(c):
    return {p: await _get(c, p) for p in _all()}      # refs are deterministic per key


def _block(data):
    return data["service_inventory"]


# ── gating: off / no secret / no clean run => nothing changes ─────────

@pytest.mark.parametrize("variant", ["flag_off", "not_allowlisted", "no_secret"])
def test_inventory_is_absent_unless_fully_enabled(canon, variant):
    canon(**{"flag_off": {"on": "false"}, "not_allowlisted": {"tenants": "someone-else"},
             "no_secret": {"secret": ""}}[variant])

    async def sc(c):
        everything = await _everything(c)
        assert '"service_inventory":' not in json.dumps(everything)
        ws = everything[f"/api/customer/locations/{b1()}/workspace"]
        if variant == "no_secret":
            # canonical mode IS on: E911 fails closed - never the legacy numbers
            assert ws["e911"]["service_inventory_source"] == "canonical_unavailable"
            assert ws["e911"]["service_numbers"] == []
        else:
            assert "service_inventory_source" not in ws["e911"]   # legacy E911 exactly
    run(sc)


@pytest.mark.parametrize("world", [{"run_degraded": True}, {"run_finished": False}])
def test_no_clean_apply_run_means_no_inventory(canon, world):
    async def sc(c):
        everything = await _everything(c)
        assert '"service_inventory":' not in json.dumps(everything)
        ws = everything[f"/api/customer/locations/{b1()}/workspace"]
        assert ws["e911"]["service_inventory_source"] == "canonical_unavailable"
        assert ws["e911"]["service_numbers"] == []
    run(sc, **world)


def test_flag_off_payloads_are_identical_to_no_canonical_data(canon):
    """With the flag off, canonical rows in the DB change no customer byte."""
    canon(on="false")

    async def with_rows(c):
        return await _everything(c)

    async def _go_plain():
        engine, Session = await make_db()
        try:
            await seed(Session)
            async with Session() as db:
                db.add(PortfolioBuilding(id=EMPTY, tenant_id=RH, canonical_name="Quiet Gallery #700",
                                         store_number="700", site_type="gallery",
                                         status="active", approved=True))
                await db.commit()
            async with client_for(ROUTERS, Session, {"user": user()}) as c:
                return await _everything(c)
        finally:
            await engine.dispose()

    import re

    def strip(d):                                   # request timestamps differ per call
        return re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+(?:\+00:00|Z)?", "<ts>", json.dumps(d, sort_keys=True))
    assert strip(run(with_rows)) == strip(asyncio.run(_go_plain()))


# ── states and DTO ────────────────────────────────────────────────────

def test_ready_partially_ready_being_finalized_and_no_services(canon):
    async def sc(c):
        blk1 = _block(await _get(c, f"/api/customer/locations/{b1()}"))
        assert blk1["state"] == cv.PARTIALLY_READY
        assert blk1["message"] == cv.MESSAGES[cv.PARTIALLY_READY]
        assert [(s["service"], s["name"], s["required_paths"], s["telephone_number"])
                for s in blk1["ready_services"]] == [
            ("Elevator", "Elevator 1", 1, "(312) 555-0142"),
            ("Fire Alarm", "Fire alarm panel", 2, None)]           # FACP: never a number
        blk2 = _block((await _get(c, f"/api/customer/locations/{b2()}/workspace"))["location"])
        assert (blk2["state"], blk2["ready_services"]) == (cv.BEING_FINALIZED, [])
        items = (await _get(c, "/api/customer/locations"))["items"]
        states = {it["display_name"]: it["service_inventory"]["state"] for it in items}
        assert cv.NO_SERVICES in states.values()
        assert all(set(it["service_inventory"]) == {"state", "message"} for it in items)
    run(sc)


def test_portfolio_rollup_has_no_service_or_connection_totals(canon):
    async def sc(c):
        p = _block(await _get(c, "/api/customer/portfolio/summary"))
        assert p["locations_partially_ready"] == 1 and p["locations_ready"] == 0
        assert p["locations_being_finalized"] == 1 and p["records_being_finalized"] is True
        assert p["ready_services_by_type"] == [{"service": "Elevator", "count": 1},
                                               {"service": "Fire Alarm", "count": 1}]
        assert not any(k in p for k in ("total_services", "connections", "service_total",
                                        "probable_services", "unresolved_services"))
        assert _block(await _get(c, "/api/customer/portfolio/services")) == p
    run(sc)


def test_historical_rejected_stale_and_probable_are_never_listed(canon):
    async def sc(c):
        text = json.dumps(await _everything(c))
        for n in ("5125550001", "5125550002", "5125550003", "5125550004", "7700001"):
            assert n not in text
    run(sc)


def test_suspect_building_is_never_ready(canon):
    async def sc(c):
        blk1 = _block(await _get(c, f"/api/customer/locations/{b1()}"))
        assert (blk1["state"], blk1["ready_services"]) == (cv.BEING_FINALIZED, [])
    run(sc, suspect_b1=True)


def test_no_internal_identifiers_reach_the_customer(canon):
    async def sc(c):
        text = json.dumps(await _everything(c))
        for leak in (RADIO, SIM, FACP_TEL, "FACP:", "ELEV:", "UNCL:", "radio:", '"service_key"',
                     "NAPCO", "certif"):
            assert leak not in text, leak
        blk1 = _block(await _get(c, f"/api/customer/locations/{b1()}"))
        for s in blk1["ready_services"]:
            assert s["service_ref"].startswith("lss_2k")       # opaque, dedicated key
    run(sc)


def test_e911_is_identical_with_and_without_the_inventory(canon):
    async def e911(c):
        items = (await _get(c, "/api/customer/locations"))["items"]
        summary = await _get(c, "/api/customer/portfolio/summary")
        return ([(i["building_ref"], i["emergency_address_state"]) for i in items],
                summary["e911_verified_locations"], summary["e911_verification_pct"])
    on = run(e911)
    canon(on="false")
    assert run(e911) == on


# ── pure rules ────────────────────────────────────────────────────────

@pytest.mark.parametrize("svc,expected", [
    (dict(service_type=V.FACP, confidence=V.CONFIRMED, approval="NONE", lifecycle=V.CURRENT,
          required_paths=2), cv.READY),
    (dict(service_type=V.ELEVATOR, confidence=V.PROBABLE, approval=V.APPROVED,
          lifecycle=V.CURRENT, required_paths=1), cv.READY),
    (dict(service_type=V.ELEVATOR, confidence=V.CONFIRMED, approval="NONE", lifecycle=V.UNKNOWN,
          required_paths=0), "FINALIZING"),
    (dict(service_type=V.ELEVATOR, confidence=V.CONFIRMED, approval="NONE", lifecycle=V.CURRENT,
          required_paths=0), "FINALIZING"),
    (dict(service_type=V.UNCLASSIFIED, confidence=V.UNRESOLVED, approval="NONE",
          lifecycle=V.CURRENT, required_paths=0), "FINALIZING"),
    (dict(service_type=V.ELEVATOR, confidence=V.CONFIRMED, approval="NONE",
          lifecycle=V.HISTORICAL, required_paths=0), "EXCLUDED"),
    (dict(service_type=V.ELEVATOR, confidence=V.CONFIRMED, approval=V.REJECTED,
          lifecycle=V.CURRENT, required_paths=1), "EXCLUDED"),
])
def test_classification_rules(svc, expected):
    assert cv.classify(svc) == expected


def test_pending_or_inactive_buildings_are_never_ready():
    inv = {"by_building": {1: [dict(id=1, service_type=V.ELEVATOR, display_name=None,
                                    confidence=V.CONFIRMED, approval="NONE",
                                    lifecycle=V.CURRENT, required_paths=1, telephone=None)]},
           "suspect": set(), "as_of": None}
    for kw in ({"approved": False, "active": True, "pending": False},
               {"approved": True, "active": False, "pending": False},
               {"approved": True, "active": True, "pending": True}):
        assert cv.building_inventory(inv, 1, **kw)["state"] == cv.BEING_FINALIZED


# ── the read-only operator preview ────────────────────────────────────

def test_preview_script_shows_the_customer_view_writes_nothing_and_scans_clean(canon):
    from sqlalchemy import func, select

    from scripts import canonical_customer_preview as pv
    canon(on="false", secret="")                     # preview works whatever the flag says

    async def _go():
        engine, Session = await make_db()
        try:
            await seed(Session)
            await canonical_world(Session)

            async def counts():
                async with Session() as db:
                    return [(await db.execute(select(func.count()).select_from(m))).scalar()
                            for m in (LifeSafetyService, LifeSafetyConnection, ProjectionRun,
                                      CommunicationsAsset, OperatorDecision, PortfolioBuilding)]
            before = await counts()
            async with Session() as db:
                res = await pv.preview(db, RH)
                await db.rollback()
            assert await counts() == before
            return res
        finally:
            await engine.dispose()
    res = asyncio.run(_go())
    assert res["would_be_served"]["served_now"] is False
    assert res["leak_scan"] == []
    states = {loc["location"]: loc["service_inventory"]["state"]
              for loc in res["payload"]["locations"]}
    assert states["Chicago Gallery #147"] == cv.PARTIALLY_READY
    assert res["payload"]["portfolio"]["locations_partially_ready"] == 1
    text = pv.render(res)
    assert "READY  Fire Alarm | Fire alarm panel | required_paths=2 | telephone=-" in text
    assert "LEAK SCAN ===\nCLEAN" in text and RADIO not in text


def test_preview_leak_scan_detects_internal_values():
    from scripts import canonical_customer_preview as pv
    assert pv.leak_scan({"x": "FACP:radio:1"}, [])
    assert pv.leak_scan({"x": "RESEARCH REQUIRED Gallery"}, [])
    assert pv.leak_scan({"x": "radio 77110020"}, ["77110020"])
    assert pv.leak_scan({"x": "Elevator 1"}, ["77110020"]) == []


def test_preview_with_marker_names_and_cities_scans_clean(canon):
    """The production failure: buildings whose NAME and CITY carry the internal
    flag.  The strict leak scan must pass because the names are clean - not
    because the scan was weakened."""
    from scripts import canonical_customer_preview as pv

    async def _go():
        engine, Session = await make_db()
        try:
            await seed(Session)
            await canonical_world(Session)
            async with Session() as db:
                for bid, name, st, store in (
                        (50, "RESEARCH REQUIRED Gallery", "gallery", None),
                        (51, "RESEARCH REQUIRED Distribution Center", "distribution_center", None),
                        (52, "RESEARCH REQUIRED Gallery #653", "store", "653")):
                    db.add(PortfolioBuilding(id=bid, tenant_id=RH, canonical_name=name,
                                             store_number=store, site_type=st, status="active",
                                             city="RESEARCH REQUIRED", approved=True))
                await db.commit()
            async with Session() as db:
                res = await pv.preview(db, RH)
                await db.rollback()
            return res
        finally:
            await engine.dispose()
    res = asyncio.run(_go())
    names = [loc["location"] for loc in res["payload"]["locations"]]
    assert {"Gallery", "Distribution Center", "Gallery #653"} <= set(names)
    assert res["leak_scan"] == []
    assert "RESEARCH" not in pv.render(res).upper()
    # and the scan is still strict: the literal marker anywhere fails it
    assert pv.leak_scan({"location": "RESEARCH REQUIRED Gallery"}, [])
    assert pv.leak_scan({"x": {"y": ["RESEARCH REQUIRED Distribution Center"]}}, [])
