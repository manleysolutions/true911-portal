"""RH go-live UX / action-semantics corrections (real SQLite DB).

Pins the customer meaning of what the console shows on the first session:
  * E911: an actionable confirmation (address on file -> Verify E911) is never
    merged with a record that has NO dispatch address yet ("being prepared");
    dashboard and location page agree because both read ONE dispatch address.
  * Building -> Life-Safety Service -> Connection: a number not linked to a
    monitored service is a connection, never presented as a second service.
  * Data Completeness (what True911 knows) vs Operational Readiness (what the
    customer has supplied) carry distinct labels; supplied contacts count.
  * Side effects of the smoke-test flows: contact clears the missing-contact
    action, rename touches nothing technical, a request provisions nothing, an
    E911 confirmation goes pending and never moves the verified percentage.
"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.models.device import Device
from app.models.line import Line
from app.models.portfolio_registry import PortfolioBuilding, PortfolioDeviceMapping
from app.models.site import Site
from app.services.customer import serialize as cs
from app.services.customer.refs import encode_ref
from tests._customer_db import client_for, make_db, user
from tests.test_customer_self_service import B1, B2, RH, ROUTERS, flags, seed  # noqa: F401

B_NOADDR = [encode_ref("bldg", i) for i in (10, 11, 12)]
B_SITE_ONLY = encode_ref("bldg", 20)


async def _extra(Session):
    """Three buildings with NO dispatch address anywhere (not_verified), one whose
    only address is the linked site's official E911 record, and a second number
    on Chicago that is not attached to any monitored service."""
    async with Session() as db:
        for i, city in zip((10, 11, 12), ("Nashville", "Tulsa", "Omaha")):
            db.add(PortfolioBuilding(id=i, tenant_id=RH, canonical_name=f"{city} Gallery",
                                     store_number=str(700 + i), site_type="gallery",
                                     status="active", city=city, approved=True))
        db.add(PortfolioBuilding(id=20, tenant_id=RH, canonical_name="Denver Gallery #150",
                                 store_number="150", site_type="gallery", status="active",
                                 city="Denver", approved=True))
        db.add(Site(site_id="RH-150", tenant_id=RH, site_name="Restoration Hardware #150 Denver",
                    customer_name="RH", status="active", e911_street="3000 E 1st Ave",
                    e911_city="Denver", e911_state="CO", e911_zip="80206", e911_status="pending"))
        db.add(PortfolioDeviceMapping(tenant_id=RH, building_id=1, kind="phone",
                                      value="3125550177", value_normalized="3125550177",
                                      source="test", active=True))
        # the monitored service's number is a provisioned line (Line.did) - a
        # device MSISDN is never used as the customer's number (CG-1 L3)
        db.add(Line(line_id="L-147-1", tenant_id=RH, site_id="RH-147", device_id="D-147-1",
                    provider="t-mobile", did="3125550100", status="active"))
        await db.commit()


def run(scenario):
    async def _go():
        engine, Session = await make_db()
        try:
            await seed(Session)
            await _extra(Session)
            state = {"user": user()}
            async with client_for(ROUTERS, Session, state) as c:
                return await scenario(c, Session, state)
        finally:
            await engine.dispose()
    return asyncio.run(_go())


async def _ac(c):
    return (await c.get("/api/customer/action-center")).json()["data"]


async def _ws(c, ref):
    return (await c.get(f"/api/customer/locations/{ref}/workspace")).json()["data"]


# ══════════════════════════════════════════════════════════════════════
# 1. E911 — actionable confirmations vs records being prepared
# ══════════════════════════════════════════════════════════════════════
def test_confirmations_and_not_ready_are_separate_but_sum_to_attention(flags):
    async def sc(c, Session, state):
        ac = await _ac(c)
        n = ac["counts"]
        # B1, B2 and the site-address-only building can confirm; 3 have no address
        assert n["e911_confirmation_required"] == 3
        assert n["e911_not_ready"] == 3
        assert n["e911_attention"] == 6 == n["e911_verification_required"]
        confirm = {r["location_ref"] for r in ac["e911_confirmation_required"]}
        not_ready = {r["location_ref"] for r in ac["e911_not_ready"]}
        assert confirm == {B1, B2, B_SITE_ONLY} and not_ready == set(B_NOADDR)
        # actionable rows carry Verify E911; not-ready rows carry NO action and
        # are never worded as a confirmation
        assert all(r["action"] == "verify_e911" for r in ac["e911_confirmation_required"])
        for r in ac["e911_not_ready"]:
            assert r["action"] is None and r["state"] == "not_verified"
            assert "confirm" not in r["label"].lower() and "confirm" not in r["reason"].lower()
    run(sc)


def test_dashboard_and_location_page_use_the_same_state_and_words(flags):
    async def sc(c, Session, state):
        ac = await _ac(c)
        rows = {r["location_ref"]: r for r in ac["e911_verification_required"]}
        for ref in (B1, B_SITE_ONLY, *B_NOADDR):
            ws = await _ws(c, ref)
            assert ws["e911"]["state"] == rows[ref]["state"], ref
            assert ws["e911"]["label"] == rows[ref]["label"], ref
            actions = {a["action"] for a in ws["location"]["outstanding_actions"]}
            assert ("verify_e911" in actions) == (rows[ref]["action"] == "verify_e911"), ref
        # the site-only building shows the OFFICIAL record as its dispatch address
        ws = await _ws(c, B_SITE_ONLY)
        assert ws["e911"]["dispatch_address"] == "3000 E 1st Ave, Denver, CO 80206"
        assert ws["e911"]["state"] == "customer_confirmation_required"
        # a not-ready building offers nothing to confirm
        ws = await _ws(c, B_NOADDR[0])
        assert ws["e911"]["dispatch_address"] is None and ws["e911"]["customer_action"] is None
    run(sc)


def test_e911_confirmation_goes_pending_and_never_moves_verified_pct(flags):
    async def sc(c, Session, state):
        before = (await c.get("/api/customer/portfolio/summary")).json()["data"]
        r = await c.post(f"/api/customer/locations/{B1}/e911/verification",
                         json={"number_confirmed": True, "address_confirmed": True,
                               "building_confirmed": True, "attest": True})
        assert r.json()["data"]["e911"]["state"] == "customer_submitted"
        after = (await c.get("/api/customer/portfolio/summary")).json()["data"]
        assert after["e911_verification_pct"] == before["e911_verification_pct"] == 0.0
        site = (await _get(Session, Site, Site.site_id == "RH-147"))[0]
        assert site.e911_status == "pending"                      # no auto-verification
        ac = await _ac(c)
        assert B1 not in {x["location_ref"] for x in ac["e911_confirmation_required"]}
        assert ac["counts"]["e911_attention"] == 5
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# 2. Service -> connection hierarchy
# ══════════════════════════════════════════════════════════════════════
def test_one_service_with_two_connections_is_labelled_as_such(flags):
    async def sc(c, Session, state):
        ws = await _ws(c, B1)
        loc = ws["location"]
        assert loc["service_count"] == 1 and loc["connection_count"] == 2
        assert loc["unlinked_connection_count"] == 1
        linked = [x for x in ws["connections"] if x["service"]]
        unlinked = [x for x in ws["connections"] if x["service"] is None]
        assert len(linked) == 1 and len(unlinked) == 1
        assert unlinked[0]["name"] == "Additional line"
        assert unlinked[0]["service_label"] == "Not yet linked to a life-safety service"
        assert unlinked[0]["phone_number"] == "(312) 555-0177"
        assert unlinked[0]["status"]["status"] == "Unknown"            # never green
        assert all(x["name"] != "Life Safety Line" for x in ws["connections"])
        # the physical-device KPI is unaffected by an extra number (no regression)
        assert loc["device_count"] == 1
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# 3. Data Completeness vs Operational Readiness
# ══════════════════════════════════════════════════════════════════════
def test_completeness_and_readiness_have_distinct_labels():
    h = cs.separated_health(operational=100, completeness=100, compliance=None, documentation=0)
    labels = {f["key"]: f["label"] for f in h["factors"]}
    assert labels["digital_twin_completeness"] == "Data Completeness"
    m = cs.building_maturity({})
    assert m["tier"] == "Bronze" and m["met"] == 0 and m["total"] == 7
    assert all("complet" not in d["label"].lower() for d in m["dimensions"])


def test_supplied_contact_clears_action_and_counts_toward_readiness(flags):
    async def sc(c, Session, state):
        h0 = (await c.get(f"/api/customer/locations/{B2}/health")).json()["data"]
        met0 = {d["key"]: d["met"] for d in h0["maturity"]["dimensions"]}
        assert met0["contacts"] is False
        assert B2 in {x["location_ref"] for x in (await _ac(c))["missing_contact_information"]}
        r = await c.put(f"/api/customer/locations/{B2}/contacts",
                        json={"contacts": {"facility": {"name": "Pat", "phone": "5125550100"}}})
        assert r.status_code == 200
        assert B2 not in {x["location_ref"] for x in (await _ac(c))["missing_contact_information"]}
        h1 = (await c.get(f"/api/customer/locations/{B2}/health")).json()["data"]
        met1 = {d["key"]: d["met"] for d in h1["maturity"]["dimensions"]}
        assert met1["contacts"] is True and h1["maturity"]["met"] == h0["maturity"]["met"] + 1
        act = (await c.get(f"/api/customer/locations/{B2}/activity")).json()["data"]["activity"]
        assert act[0]["by"] == "Judy" and act[0]["when"]
    run(sc)


# ══════════════════════════════════════════════════════════════════════
# 4. Smoke-test side effects
# ══════════════════════════════════════════════════════════════════════
async def _get(Session, model, *where):
    async with Session() as db:
        return (await db.execute(select(model).where(*where))).scalars().all()


def _tech(devs, maps, sites):
    return ([(d.device_id, d.msisdn, d.iccid, d.imei, d.carrier, d.status) for d in devs],
            sorted((m.kind, m.value, m.building_id, m.active) for m in maps),
            [(s.site_id, s.e911_street, s.e911_status) for s in sites])


def test_rename_note_and_request_touch_nothing_technical(flags):
    async def sc(c, Session, state):
        snap = _tech(await _get(Session, Device), await _get(Session, PortfolioDeviceMapping),
                     await _get(Session, Site))
        ws = await _ws(c, B1)
        conn = next(x for x in ws["connections"] if x["service"])
        r = await c.patch(f"/api/customer/locations/{B1}/connections/{conn['connection_ref']}",
                          json={"changes": {"friendly_name": "Passenger Elevator 1"}})
        assert r.status_code == 200 and r.json()["data"]["requested"] == []
        r = await c.patch(f"/api/customer/locations/{B1}/profile",
                          json={"changes": {"location_notes": "Elevator room behind stockroom"}})
        assert r.status_code == 200
        for rtype in ("add_service", "change_service_type"):
            r = await c.post(f"/api/customer/locations/{B1}/requests",
                             json={"request_type": rtype, "notes": "Please arrange"})
            assert r.json()["data"]["status"] == "submitted"
        assert _tech(await _get(Session, Device), await _get(Session, PortfolioDeviceMapping),
                     await _get(Session, Site)) == snap
        ws = await _ws(c, B1)
        renamed = next(x for x in ws["connections"] if x["connection_ref"] == conn["connection_ref"])
        assert renamed["name"] == "Passenger Elevator 1"
        assert renamed["phone_number"] == conn["phone_number"]
        summaries = [a["summary"] for a in ws["activity"]]
        for s in ("Updated connection name", "Updated location notes", "Add service requested",
                  "Change service type requested"):
            assert s in summaries
        assert all(a["by"] == "Judy" and a["when"] for a in ws["activity"])
    run(sc)


def test_summary_keys_and_device_count_do_not_regress(flags):
    async def sc(c, Session, state):
        s = (await c.get("/api/customer/portfolio/summary")).json()["data"]
        assert s["devices"] == s["total_devices"] == 2
        assert "sites_requiring_attention" in s and "critical_sites" in s
        assert s["locations_total"] == 6
    run(sc)


def test_json_payload_has_no_internal_terms(flags):
    async def sc(c, Session, state):
        dump = json.dumps(await _ac(c)) + json.dumps(await _ws(c, B1))
        for term in ("napco", "genesis", "zoho", "iccid", "imei", "msisdn",
                     "portfolioreviewitem", "source confidence"):
            assert term not in dump.lower(), term
    run(sc)


def test_e911_state_counts_reconcile_every_location_without_inventing_verified(flags):
    """The E911 tile must account for EVERY location using the authoritative
    per-location state (presentation only): confirm + preparing + the rest ==
    locations, and the confirm / preparing figures match the action lists."""
    async def sc(c, Session, state):
        n = (await _ac(c))["counts"]
        st = n["e911_states"]
        assert sum(st.values()) == n["locations"]
        assert st["customer_confirmation_required"] + st["failed"] == n["e911_confirmation_required"]
        assert st["not_verified"] == n["e911_not_ready"]
        assert st["verified"] == 0                       # no official record in this world
        assert set(st) == {"not_verified", "customer_confirmation_required", "customer_submitted",
                           "verification_pending", "requires_review", "failed", "verified"}
    run(sc)
