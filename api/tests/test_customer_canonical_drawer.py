"""Canonical mode: the location drawer's Services & Lines IS the canonical inventory.

REGRESSION FIXTURE (live RH Test smoke, 2026-10-02).  Unlike the generic
canonical tests, this file intentionally uses the Jacksonville #177 and
Patterson telephone numbers / shapes the operator approved, because the
regression is about those exact records:

  * Jacksonville: Elevator 1 (904) 689-0616 and Elevator 2 (904) 689-0656 READY;
    five current lines in an emergency-phone / fax pool (individually
    UNCLASSIFIED); seven old numbers historical under the 2026-09-22 migration;
    six legacy MS130v4 device rows at the linked site.
  * Patterson: one READY FACP, two required paths, no telephone number.

Canonical mode must show only the READY services (no inferred services, devices,
unlinked / historical / pooled numbers, no "monitored" count), while E911 and the
flag-off legacy view stay exactly as they were.  Real SQLite DB + routers.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from app.models.canonical import (
    CommunicationsAsset,
    ConnectionAssetLink,
    LifeSafetyConnection,
    LifeSafetyService,
    ProjectionRun,
)
from app.models.device import Device
from app.models.portfolio_registry import PortfolioBuilding, PortfolioDeviceMapping
from app.models.site import Site
from app.services.canonical import vocab as V
from app.services.customer.refs import encode_ref
from tests._customer_db import client_for, user
from tests.test_customer_canonical_view import canon, make_db  # noqa: F401
from tests.test_customer_self_service import RH, ROUTERS, flags  # noqa: F401

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
JAX, PAT = 177, 200
ELEV = {"9046890616": "Elevator 1", "9046890656": "Elevator 2"}
POOL = ["9046890633", "9046891550", "9046892688", "9046892768", "9047891030"]
HISTORICAL = ["9045829697", "9045829756", "9046249429", "9046490309", "9046490389", "9046490394",
              "9046242986"]


def fmt(n):
    return "(%s) %s-%s" % (n[:3], n[3:6], n[6:])


async def world(Session):
    async with Session() as db:
        db.add_all([
            PortfolioBuilding(id=JAX, tenant_id=RH, canonical_name="Jacksonville Gallery #177",
                              store_number="177", site_type="gallery", status="active",
                              city="Jacksonville", state="FL", approved=True),
            PortfolioBuilding(id=PAT, tenant_id=RH, canonical_name="Patterson Warehouse",
                              site_type="warehouse", status="active", city="Patterson",
                              state="CA", approved=True),
            Site(site_id="RH-177", tenant_id=RH, site_name="Restoration Hardware #177 Jacksonville",
                 customer_name="RH", status="active", e911_street="4790 River City Dr",
                 e911_city="Jacksonville", e911_state="FL", e911_zip="32246",
                 e911_status="pending"),
            PortfolioDeviceMapping(tenant_id=RH, building_id=JAX, kind="true911_device",
                                   value="RH-177", value_normalized="RH177", source="test",
                                   active=True),
        ])
        # six legacy MS130v4 device rows at the linked site (the live smoke rows)
        for i in range(6):
            db.add(Device(device_id="D-177-%d" % i, tenant_id=RH, site_id="RH-177",
                          status="active", device_type="communicator", model="MS130v4"))
        # legacy registry phone mappings for EVERY known number (what the legacy
        # view lists as "not yet linked")
        for n in list(ELEV) + POOL + HISTORICAL:
            db.add(PortfolioDeviceMapping(tenant_id=RH, building_id=JAX, kind="phone", value=n,
                                          value_normalized=n, source="test", active=True))
        db.add(ProjectionRun(id=1, tenant_id=RH, mode="APPLY", run_by="t", started_at=NOW,
                             finished_at=NOW, degraded=False))
        ids = iter(range(1000, 9999))

        def svc(bid, key, stype, conf, lc, name=None):
            sid = next(ids)
            db.add(LifeSafetyService(id=sid, tenant_id=RH, building_id=bid, service_key=key,
                                     service_type=stype, display_name=name, confidence=conf,
                                     approval="NONE", lifecycle=lc, last_projection_run_id=1))
            return sid

        def conn(sid, n):
            cid = next(ids)
            db.add(LifeSafetyConnection(id=cid, tenant_id=RH, service_id=sid, ordinal=n,
                                        connection_type="X", requirement=V.REQUIRED,
                                        provisioning="NOT_EVALUATED", confidence="CONFIRMED",
                                        last_projection_run_id=1))
            return cid

        def asset(atype, value, bid):
            aid = next(ids)
            db.add(CommunicationsAsset(id=aid, tenant_id=RH, asset_type=atype,
                                       normalized_value=value, display_value=value,
                                       lifecycle="CURRENT", placement_confidence="CONFIRMED",
                                       building_id=bid, last_projection_run_id=1))
            return aid

        def link(cid, aid, rel):
            db.add(ConnectionAssetLink(id=next(ids), tenant_id=RH, connection_id=cid,
                                       asset_id=aid, relationship=rel, active=True))
        for n, name in ELEV.items():                                   # READY elevators
            sid = svc(JAX, "ELEV:tel:" + n, V.ELEVATOR, V.CONFIRMED, V.CURRENT, name)
            link(conn(sid, 1), asset(V.TELEPHONE_NUMBER, n, JAX), V.REL_CARRIER_LINE)
        for n in POOL:                                                 # pooled, unclassified
            svc(JAX, "UNCL:tel:" + n, V.UNCLASSIFIED, V.UNRESOLVED, V.CURRENT)
        for n in HISTORICAL:                                           # migrated away
            svc(JAX, "ELEV:tel:" + n, V.ELEVATOR, V.CONFIRMED, V.DECOMMISSIONED)
        svc(JAX, "FACP:radio:7700999", V.FACP, V.PROBABLE, V.CURRENT)  # probable, never shown
        sid = svc(PAT, "FACP:radio:15472201", V.FACP, V.CONFIRMED, V.CURRENT, "Fire alarm panel")
        c1, _c2 = conn(sid, 1), conn(sid, 2)
        link(c1, asset(V.NAPCO_RADIO, "15472201", PAT), V.REL_SERVICE_EQUIPMENT)
        await db.commit()


def run(scenario):
    async def _go():
        engine, Session = await make_db()
        try:
            await world(Session)
            async with client_for(ROUTERS, Session, {"user": user()}) as c:
                return await scenario(c)
        finally:
            await engine.dispose()
    return asyncio.run(_go())


async def _get(c, path):
    r = await c.get(path)
    assert r.status_code == 200, (path, r.status_code, r.text[:300])
    return r.json()["data"]


def jax():
    return encode_ref("bldg", JAX)


def pat():
    return encode_ref("bldg", PAT)


def _without_e911(ws):
    return {k: v for k, v in ws.items() if k != "e911"}


def test_jacksonville_drawer_shows_exactly_the_two_confirmed_elevators(canon):
    async def sc(c):
        ws = await _get(c, f"/api/customer/locations/{jax()}/workspace")
        inv = ws["location"]["service_inventory"]
        assert inv["state"] == "PARTIALLY_READY"
        assert [(s["name"], s["telephone_number"], s["required_paths"]) for s in inv["ready_services"]] \
            == [("Elevator 1", fmt("9046890616"), 1), ("Elevator 2", fmt("9046890656"), 1)]
        assert [(x["name"], x["phone_number"]) for x in ws["connections"]] == [
            ("Elevator 1", fmt("9046890616")), ("Elevator 2", fmt("9046890656"))]
        loc = ws["location"]
        assert (loc["service_count"], loc["connection_count"], loc["unlinked_connection_count"]) \
            == (2, 2, 0)
        assert loc["monitored_service_count"] is None          # READY is not "monitored"
        assert all(x["status"]["status"] == "Unknown" for x in ws["connections"])
    run(sc)


def test_jacksonville_historical_and_pooled_numbers_are_not_customer_inventory(canon):
    async def sc(c):
        ws = await _get(c, f"/api/customer/locations/{jax()}/workspace")
        svcs = await _get(c, f"/api/customer/locations/{jax()}/services")
        text = json.dumps([_without_e911(ws), svcs])
        for n in HISTORICAL + POOL:
            assert n not in text and fmt(n) not in text, n
        assert "MS130v4" not in text and "Monitored device" not in text
        assert svcs["services"] == []                         # no legacy inferred cards
    run(sc)


def test_e911_state_is_unchanged_and_the_flag_off_legacy_view_is_unchanged(canon):
    """E911 STATE / address / provenance are identical in both modes; only the
    eligible service-number set differs (canonical READY numbers vs legacy)."""
    inventory_keys = ("service_numbers", "services", "service_inventory_source")

    async def both(c):
        ws = await _get(c, f"/api/customer/locations/{jax()}/workspace")
        return ws["e911"], ws
    e911_on, _ = run(both)
    canon(on="false")
    e911_off, legacy = run(both)
    strip = lambda e: {k: v for k, v in e.items() if k not in inventory_keys}  # noqa: E731
    assert strip(e911_on) == strip(e911_off)                  # E911 state computation untouched
    assert "service_inventory_source" not in e911_off         # flag off: legacy E911 exactly
    assert "service_inventory" not in legacy["location"]
    legacy_numbers = {x["phone_number"] for x in legacy["connections"]}
    assert fmt(HISTORICAL[0]) in legacy_numbers               # legacy view as before (flag off)


def test_patterson_facp_has_two_required_paths_and_no_telephone_number(canon):
    async def sc(c):
        ws = await _get(c, f"/api/customer/locations/{pat()}/workspace")
        inv = ws["location"]["service_inventory"]
        assert inv["state"] == "READY"
        assert [(s["service"], s["name"], s["required_paths"], s["telephone_number"])
                for s in inv["ready_services"]] == [("Fire Alarm", "Fire alarm panel", 2, None)]
        assert [(x["service"], x["phone_number"]) for x in ws["connections"]] == [("Fire Alarm", None)]
        assert "15472201" not in json.dumps(_without_e911(ws))
    run(sc)


def test_probable_unresolved_and_historical_are_never_confirmed(canon):
    async def sc(c):
        inv = (await _get(c, f"/api/customer/locations/{jax()}"))["service_inventory"]
        assert {s["service"] for s in inv["ready_services"]} == {"Elevator"}
        assert len(inv["ready_services"]) == 2               # not the probable FACP, pool or history
        assert "7700999" not in json.dumps(inv)
    run(sc)
