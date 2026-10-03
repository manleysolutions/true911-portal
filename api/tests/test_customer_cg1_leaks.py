"""CG-1 customer read-model leak fixes (#186b prerequisite).

L1  customer refs are opaque authenticated encryption - no db id, telephone
    number or canonical key is recoverable from a browser-visible ref;
    wrong-kind / tampered / malformed / other-key refs fail closed.
L2  internal record-name markers ("RESEARCH REQUIRED ...") never reach a customer.
L3  a device / SIM MSISDN (Device.msisdn, genesis_msisdn) is never presented as a
    customer telephone number merely as a fallback.
L4  only ACTIVE buildings reach a customer.

Real SQLite DB, real routers.  SYNTHETIC identifiers only.
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest

from app.models.device import Device
from app.models.portfolio_registry import PortfolioBuilding, PortfolioDeviceMapping
from app.models.site import Site
from app.services.customer import refs as R
from app.services.customer.refs import encode_ref
from tests._customer_db import client_for, make_db, user
from tests.test_customer_self_service import OTHER, RH, ROUTERS, flags, seed  # noqa: F401

RESEARCH = encode_ref("bldg", 30)
INACTIVE = encode_ref("bldg", 31)
MSISDN_ONLY = encode_ref("bldg", 32)
SECRET = "s" * 48


# ── L1: refs ──────────────────────────────────────────────────────────

def _payload_bytes(ref):
    body = ref.split("_", 1)[1][2:]
    return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))


@pytest.mark.parametrize("secret", ["", SECRET])
def test_l1_ref_round_trips_and_reveals_nothing(monkeypatch, secret):
    monkeypatch.setattr("app.config.settings.CUSTOMER_REF_SECRET", secret)
    for kind, raw in (("loc", 42), ("bldg", 7), ("conn", "bldg:12|tel:3125550100"),
                      ("svc", "i:FACP:radio:77110020")):
        ref = encode_ref(kind, raw)
        assert R.decode_ref(kind, ref) == str(raw)
        blob = _payload_bytes(ref)
        for needle in (str(raw), "3125550100", "77110020", "bldg:12", "FACP"):
            assert needle.encode() not in blob
        assert needle not in ref
        assert ref.startswith("%s_2%s" % (kind, "k" if secret else "t"))


@pytest.mark.parametrize("bad", [
    lambda r: r.replace("loc_", "svc_", 1),          # wrong kind
    lambda r: r[:-3] + ("AAA" if not r.endswith("AAA") else "BBB"),   # tampered
    lambda r: r[:8],                                 # truncated
    lambda r: "loc_1" + r[5:],                       # wrong version
    lambda r: "garbage", lambda r: "", lambda r: None, lambda r: "loc_",
])
def test_l1_bad_refs_fail_closed(bad):
    ref = encode_ref("loc", 42)
    assert R.decode_ref("loc", bad(ref)) is None


def test_l1_refs_of_another_key_fail_closed(monkeypatch):
    transitional = encode_ref("loc", 42)
    monkeypatch.setattr("app.config.settings.CUSTOMER_REF_SECRET", SECRET)
    assert R.decode_ref("loc", transitional) is None          # key changed -> rejected
    dedicated = encode_ref("loc", 42)
    monkeypatch.setattr("app.config.settings.CUSTOMER_REF_SECRET", "x" * 48)
    assert R.decode_ref("loc", dedicated) is None             # rotated -> rejected


def test_l1_dedicated_secret_detection(monkeypatch):
    for value, ok in (("", False), ("short", False), (SECRET, True)):
        monkeypatch.setattr("app.config.settings.CUSTOMER_REF_SECRET", value)
        assert R.dedicated_secret_configured() is ok


# ── L2 / L3 / L4 through the real customer API ────────────────────────

async def _extra(Session):
    async with Session() as db:
        db.add_all([
            PortfolioBuilding(id=30, tenant_id=RH, canonical_name="RESEARCH REQUIRED Gallery #653",
                              store_number="653", site_type="gallery", status="active",
                              approved=True),
            # the production shape: the internal flag recorded in BOTH the name
            # and the CITY field
            PortfolioBuilding(id=33, tenant_id=RH, canonical_name="RESEARCH REQUIRED Gallery",
                              site_type="gallery", status="active", city="RESEARCH REQUIRED",
                              state="RESEARCH REQUIRED", approved=True),
            PortfolioBuilding(id=34, tenant_id=RH,
                              canonical_name="RESEARCH REQUIRED Distribution Center",
                              site_type="distribution_center", status="active",
                              city="RESEARCH REQUIRED", approved=True),
            PortfolioBuilding(id=35, tenant_id=RH, canonical_name="RESEARCH REQUIRED Gallery #653",
                              store_number="653", site_type="store", status="active",
                              city="RESEARCH REQUIRED", approved=True),
            PortfolioBuilding(id=31, tenant_id=RH, canonical_name="Retired Gallery #900",
                              store_number="900", site_type="gallery", status="inactive",
                              approved=True),
            PortfolioBuilding(id=32, tenant_id=RH, canonical_name="Phoenix Gallery #610",
                              store_number="610", site_type="gallery", status="active",
                              city="Phoenix", approved=True),
            Site(site_id="RH-610", tenant_id=RH, site_name="Restoration Hardware #610 Phoenix",
                 customer_name="RH", status="active", e911_street="1 Camelback Rd",
                 e911_city="Phoenix", e911_state="AZ", e911_zip="85016", e911_status="pending"),
            # only an MSISDN (device) and a SIM MSISDN (genesis mapping) - no line, no
            # registry phone mapping: neither is a customer telephone number
            Device(device_id="D-610", tenant_id=RH, site_id="RH-610", status="active",
                   device_type="elevator", model="MS130v4", msisdn="6025550199"),
            PortfolioDeviceMapping(tenant_id=RH, building_id=32, kind="genesis_msisdn",
                                   value="6025550198", value_normalized="6025550198",
                                   source="test", active=True),
            PortfolioDeviceMapping(tenant_id=RH, building_id=32, kind="true911_device",
                                   value="RH-610", value_normalized="RH610", source="test",
                                   active=True),
        ])
        await db.commit()


ROUTES = ["/api/customer/dashboard", "/api/customer/portfolio/summary",
          "/api/customer/portfolio/services", "/api/customer/portfolio/health",
          "/api/customer/locations", "/api/customer/search?q=gallery",
          "/api/customer/action-center"]
PER_LOCATION = ["/api/customer/locations/{ref}", "/api/customer/locations/{ref}/services",
                "/api/customer/locations/{ref}/workspace"]


def run(scenario):
    async def _go():
        engine, Session = await make_db()
        try:
            await seed(Session)
            await _extra(Session)
            state = {"user": user()}
            async with client_for(ROUTERS, Session, state) as c:
                return await scenario(c)
        finally:
            await engine.dispose()
    return asyncio.run(_go())


async def _all_text(c, refs):
    out = []
    for path in ROUTES:
        r = await c.get(path)
        assert r.status_code == 200, (path, r.status_code)
        out.append(r.text)
    for ref in refs:
        for path in PER_LOCATION:
            r = await c.get(path.format(ref=ref))
            assert r.status_code == 200, (path, ref, r.status_code)
            out.append(r.text)
    return "\n".join(out)


def test_l2_internal_name_markers_never_reach_the_customer(flags):
    async def sc(c):
        text = await _all_text(c, [RESEARCH])
        assert "RESEARCH" not in text.upper().replace("RESEARCHED", "")
        assert "Gallery #653" in text                          # the real name survives
    run(sc)


MARKER_CITY = [encode_ref("bldg", i) for i in (33, 34, 35)]


@pytest.mark.parametrize("name,city,store,site_type,expected", [
    ("RESEARCH REQUIRED Gallery", "RESEARCH REQUIRED", None, "gallery", "Gallery"),
    ("RESEARCH REQUIRED Distribution Center", "RESEARCH REQUIRED", None, "distribution_center",
     "Distribution Center"),
    ("RESEARCH REQUIRED Gallery #653", "RESEARCH REQUIRED", "653", "store", "Gallery #653"),
    ("RESEARCH REQUIRED Gallery #653", None, "653", "store", "Gallery #653"),
    ("Chicago Gallery #147", "Chicago", "147", "gallery", "Chicago Gallery #147"),   # unchanged
])
def test_l2_marker_in_name_or_city_never_reaches_a_display_name(name, city, store, site_type,
                                                                 expected):
    from app.services.customer import serialize as cs
    assert cs.building_display_name(name, store, city, site_type) == expected
    assert cs.customer_text("RESEARCH REQUIRED") is None
    assert cs.customer_text("Chicago") == "Chicago"


def test_l2_marker_city_buildings_are_clean_on_every_customer_route(flags):
    async def sc(c):
        text = await _all_text(c, MARKER_CITY)
        assert "RESEARCH" not in text.upper()
        items = {i["display_name"]: i for i in
                 (await c.get("/api/customer/locations?page_size=100")).json()["data"]["items"]}
        for want in ("Gallery", "Distribution Center", "Gallery #653"):
            assert want in items
            assert items[want]["city"] is None and items[want]["canonical_name"] == want
        found = (await c.get("/api/customer/search?q=research")).json()["data"]["results"]
        assert found == []                           # an internal flag is not searchable
    run(sc)


def test_l2_the_registry_record_itself_is_untouched(flags):
    async def sc(c):
        await _all_text(c, MARKER_CITY)
    run(sc)

    async def check():
        from sqlalchemy import select
        engine, Session = await make_db()
        try:
            await seed(Session)
            await _extra(Session)
            async with Session() as db:
                b = (await db.execute(select(PortfolioBuilding).where(
                    PortfolioBuilding.id == 35))).scalar_one()
                assert (b.canonical_name, b.city) == ("RESEARCH REQUIRED Gallery #653",
                                                      "RESEARCH REQUIRED")
        finally:
            await engine.dispose()
    asyncio.run(check())


def test_l3_device_and_sim_msisdn_are_never_customer_numbers(flags):
    async def sc(c):
        text = await _all_text(c, [MSISDN_ONLY])
        for n in ("6025550199", "6025550198", "(602) 555-0199", "(602) 555-0198"):
            assert n not in text
    run(sc)


def test_l3_provisioned_registry_phone_numbers_still_show(flags):
    async def sc(c):
        from tests.test_customer_self_service import B1
        ws = (await c.get(f"/api/customer/locations/{B1}/workspace")).json()["data"]
        assert "(312) 555-0100" in json.dumps(ws)              # an explicit phone mapping
    run(sc)


def test_l4_inactive_buildings_are_never_shown(flags):
    async def sc(c):
        text = await _all_text(c, [])
        assert "Retired Gallery" not in text and "#900" not in text
        for path in PER_LOCATION:
            assert (await c.get(path.format(ref=INACTIVE))).status_code == 404
    run(sc)


def test_refs_never_cross_tenants(flags):
    async def sc(c):
        other = encode_ref("bldg", 3)                          # OTHER tenant's building
        for path in PER_LOCATION:
            assert (await c.get(path.format(ref=other))).status_code == 404
        assert OTHER not in await _all_text(c, [])
    run(sc)


def test_customer_payloads_carry_no_raw_building_ids(flags):
    async def sc(c):
        data = (await c.get("/api/customer/locations")).json()["data"]
        for item in data["items"]:
            assert "id" not in item and "_site_ids" not in item
            assert R.decode_ref("bldg", item["building_ref"]) is not None
    run(sc)
