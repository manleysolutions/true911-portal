"""Canonical mode: the Confirm E911 review and the submitted attestation carry
ONLY the canonical-safe READY Elevator / Emergency Phone numbers.

REGRESSION FIXTURE (uses the approved Jacksonville #177 / Patterson records - see
test_customer_canonical_drawer.py).  E911 STATE computation, provider
verification, the callback (Device.msisdn) fallback and the raw-city dispatch
fallback are untouched; only which service / telephone inventory may accompany
the confirmation changes, and only in canonical mode.  Real SQLite + routers.
"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.models.customer_self_service import CustomerServiceRequest
from app.models.device import Device
from app.models.line import Line
from app.models.portfolio_registry import PortfolioDeviceMapping
from tests._customer_db import client_for, user
from tests.test_customer_canonical_drawer import (
    ELEV,
    HISTORICAL,
    POOL,
    RH,
    fmt,
    jax,
    pat,
    world,
)
from tests.test_customer_canonical_view import canon, make_db  # noqa: F401
from tests.test_customer_self_service import ROUTERS, flags  # noqa: F401

ATTEST = {"attest": True, "address_confirmed": True, "building_confirmed": True,
          "number_confirmed": True}


async def legacy_extras(Session):
    """Legacy sources that must NOT reintroduce a number in canonical mode: a
    provisioned Line DID, a device MSISDN and a SIM MSISDN mapping, all carrying
    historical / pooled Jacksonville numbers."""
    async with Session() as db:
        db.add(Line(line_id="L-177-OLD", tenant_id=RH, site_id="RH-177", device_id="D-177-0",
                    provider="redpocket", did=HISTORICAL[1], status="active"))
        db.add(Device(device_id="D-177-M", tenant_id=RH, site_id="RH-177", status="active",
                      device_type="elevator", model="MS130v4", msisdn=HISTORICAL[2]))
        db.add(PortfolioDeviceMapping(tenant_id=RH, building_id=177, kind="genesis_msisdn",
                                      value=POOL[0], value_normalized=POOL[0], source="test",
                                      active=True))
        await db.commit()


def run(scenario):
    async def _go():
        engine, Session = await make_db()
        try:
            await world(Session)
            await legacy_extras(Session)
            async with client_for(ROUTERS, Session, {"user": user()}) as c:
                return await scenario(c, Session)
        finally:
            await engine.dispose()
    return asyncio.run(_go())


async def review_and_submit(c, Session, ref):
    ws = (await c.get(f"/api/customer/locations/{ref}/workspace")).json()["data"]
    r = await c.post(f"/api/customer/locations/{ref}/e911/verification", json=ATTEST)
    assert r.status_code in (200, 201), (r.status_code, r.text[:300])
    async with Session() as db:
        req = (await db.execute(select(CustomerServiceRequest).where(
            CustomerServiceRequest.request_type == "e911_verification")
            .order_by(CustomerServiceRequest.id.desc()))).scalars().first()
        snap = json.loads(req.requested_changes)["server_snapshot"]
    return ws["e911"], snap


BAD = [n for n in HISTORICAL + POOL]


def _no_bad_numbers(blob):
    text = json.dumps(blob)
    for n in BAD:
        assert n not in text and fmt(n) not in text, n


def test_jacksonville_review_and_attestation_carry_only_the_two_confirmed_elevators(canon):
    async def sc(c, Session):
        e911, snap = await review_and_submit(c, Session, jax())
        assert e911["service_numbers"] == [fmt(n) for n in ELEV]
        assert e911["services"] == [
            {"service": "Elevator", "name": "Elevator 1", "telephone_number": fmt("9046890616")},
            {"service": "Elevator", "name": "Elevator 2", "telephone_number": fmt("9046890656")}]
        assert e911["service_inventory_source"] == "canonical"
        # the attestation persists EXACTLY the set the customer was shown
        assert snap["service_numbers"] == list(ELEV)
        assert [s["telephone_number"] for s in snap["services"]] == e911["service_numbers"]
        assert snap["service_inventory_source"] == "canonical"
        _no_bad_numbers([e911, snap])                 # no historical / pooled / legacy number
    run(sc)


def test_patterson_fire_alarm_contributes_no_e911_telephone_number(canon):
    async def sc(c, Session):
        e911, snap = await review_and_submit(c, Session, pat())
        assert (e911["service_numbers"], e911["services"]) == ([], [])
        assert (snap["service_numbers"], snap["services"]) == ([], [])
    run(sc)


def test_unavailable_canonical_inventory_fails_closed_never_legacy(canon):
    canon(secret="")                                  # canonical mode on, read fails closed

    async def sc(c, Session):
        e911, snap = await review_and_submit(c, Session, jax())
        assert e911["service_numbers"] == [] and snap["service_numbers"] == []
        assert e911["service_inventory_source"] == snap["service_inventory_source"] \
            == "canonical_unavailable"
        _no_bad_numbers([e911, snap])
        assert e911["state"] != "verified"            # the address workflow is still there
    run(sc)


def test_flag_off_e911_review_and_submission_are_the_existing_behaviour(canon):
    canon(on="false")

    async def sc(c, Session):
        e911, snap = await review_and_submit(c, Session, jax())
        assert "services" not in e911 and "service_inventory_source" not in e911
        assert "services" not in snap and "service_inventory_source" not in snap
        # legacy sources as before: registry phone mappings (historical included)
        assert HISTORICAL[0] in snap["service_numbers"]
        assert fmt(HISTORICAL[0]) in e911["service_numbers"]
    run(sc)
