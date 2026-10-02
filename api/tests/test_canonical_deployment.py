"""Canonical engine - deployment is its own axis.

An administrative status (Zoho Subscription_Mgmnt "Activated", a True911 or
carrier "active") is CRM/source bookkeeping, never proof that equipment is
installed and serving a building.  CURRENT needs independent deployment
evidence: an operator lifecycle decision, recent True911 telemetry, or recent
source-native activity (NAPCO last signal, carrier last CDR) in an imported
snapshot.  Building SHAPES mirror Houston, Princeton, Roseville and Leawood;
every identifier is SYNTHETIC.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.canonical import engine
from app.services.canonical import vocab as V
from tests.test_canonical_engine import RECENT, conns, decision, device, live, site, snap, svc, zrow

STALE = datetime.now(timezone.utc) - timedelta(days=V.DEPLOYMENT_ACTIVITY_DAYS + 30)


def z(facility, ctype=None, *, msisdn=None, starlink=None, status="Activated"):
    return zrow(facility, msisdn, ctype, status=status, starlink=starlink)


def reg(mid, bid, value, kind="napco_radio"):
    return {"id": mid, "building_id": bid, "kind": kind, "value": value}


def facp(res, bid):
    (s,) = [s for s in res["services"] if s["building_id"] == bid and s["service_type"] == V.FACP]
    return s


def codes(res, code):
    return [f for f in res["findings"] if f["code"] == code]


def _radio(bid=7, *, status="Activated", **kw):
    """A Fire Alarm radio corroborated by Zoho + the registry (CONFIRMED identity)."""
    name = {7: "RH Princeton", 4: "RH Houston #130", 1: "RH Chicago #147"}[bid]
    return snap(zoho_rows=[z(name, "Fire Alarm", starlink="77187020", status=status)],
                mappings=[reg(1, bid, "77187020")], **kw)


# ── 1. Zoho "Activated" alone does not make anything CURRENT ──────────

def test_1_zoho_activated_alone_does_not_make_a_service_current():
    res = engine.project(snap(zoho_rows=[z("RH Chicago #147", "Elevator", msisdn="2025550190")]))
    a = res["assets"]["TELEPHONE_NUMBER:2025550190"]
    assert (a["lifecycle"], a["lifecycle_reason"], a["deployment"]) == \
        (V.UNKNOWN, V.REASON_ADMIN_STATUS_ONLY, V.DEPLOYMENT_NOT_ESTABLISHED)
    assert a["source_status"] == "ZOHO:CURRENT"                   # kept, as CRM status only
    s = svc(res, "ELEV:tel:2025550190")
    assert (s["confidence"], s["lifecycle"], s["counts"]) == (V.CONFIRMED, V.UNKNOWN, False)
    assert res["connections"] == []


def test_1b_a_true911_or_carrier_active_status_alone_is_not_deployment_either():
    dev = device("E9", "S-147", model="LM150 elevator phone", msisdn="2025550191")
    res = engine.project(snap(sites=[site("S-147", "RH Chicago #147")], devices=[dev],
                              zoho_rows=[z("RH Chicago #147", "Elevator", msisdn="2025550191")],
                              source_activity=live("2025550191", at=STALE)))   # old CDR only
    assert res["assets"]["TELEPHONE_NUMBER:2025550191"]["lifecycle"] == V.UNKNOWN
    assert res["connections"] == []


# ── 2/3. radio identity alone, confirmed identity, unknown deployment ─

def test_2_zoho_activated_plus_radio_identity_alone_is_not_counted():
    s = facp(engine.project(_radio()), 7)
    assert s["confidence"] == V.CONFIRMED                          # identity is supported
    assert (s["lifecycle"], s["deployment"], s["counts"]) == \
        (V.UNKNOWN, V.DEPLOYMENT_NOT_ESTABLISHED, False)
    assert s["lifecycle_reason"] == V.REASON_ADMIN_STATUS_ONLY


def test_3_confirmed_napco_backed_radio_with_unknown_deployment_is_not_counted_even_if_approved():
    base = _radio(napco_radios=["77187020"])
    key = facp(engine.project(base), 7)["service_key"]
    base["decisions"] = [decision(V.D_SERVICE_APPROVAL, {"building": "RH Princeton",
                                                         "service_key": key},
                                  {"approval": "APPROVED"})]
    res = engine.project(base)
    s = facp(res, 7)
    assert (s["confidence"], s["approval"], s["provenance"]["napco_backed"]) == \
        (V.CONFIRMED, V.APPROVED, True)
    assert (s["lifecycle"], s["counts"]) == (V.UNKNOWN, False)
    assert conns(res, 7) == []
    assert [f["subject"] for f in codes(res, "LIFECYCLE_UNKNOWN")] == [key]


# ── 4. independent current/deployment evidence can make it CURRENT ────

@pytest.mark.parametrize("extra,basis,source", [
    ({"source_activity": live("77187020")}, V.REASON_DEPLOYMENT_ACTIVITY, "NAPCO"),
    ({"devices": [device("F9", "S-P", device_type="Fire Alarm Control Panel",
                         starlink_id="77187020", manufacturer="Napco", last_heartbeat=RECENT)],
      "sites": [site("S-P", "RH Princeton")]}, V.REASON_DEPLOYMENT_TELEMETRY, "TRUE911"),
    ({"decisions": [decision(V.D_ASSET_LIFECYCLE, {"asset_type": "NAPCO_RADIO",
                                                   "value": "77187020"},
                             {"lifecycle": "CURRENT"})]}, V.REASON_OPERATOR, "OPERATOR"),
])
def test_4_independent_deployment_evidence_makes_the_service_current(extra, basis, source):
    res = engine.project(_radio(**extra))
    s = facp(res, 7)
    assert (s["lifecycle"], s["deployment"], s["deployment_basis"]) == \
        (V.CURRENT, V.DEPLOYED, basis)
    assert s["counts"] and len(conns(res, 7)) == 2
    assert res["assets"]["NAPCO_RADIO:77187020"]["lifecycle_source"] == source


def test_4b_recent_carrier_activity_makes_an_elevator_line_current():
    res = engine.project(snap(zoho_rows=[z("RH Chicago #147", "Elevator", msisdn="2025550192")],
                              source_activity=live("2025550192")))
    s = svc(res, "ELEV:tel:2025550192")
    assert (s["lifecycle"], s["deployment"], s["counts"]) == (V.CURRENT, V.DEPLOYED, True)


@pytest.mark.parametrize("row", [
    live("77187020", at=STALE)[0],                                 # old signal
    live("77187020", lifecycle=V.DECOMMISSIONED)[0],               # terminated SIM
    live("77187020", at=datetime.now(timezone.utc) + timedelta(days=5))[0],   # future clock
    live("77187020", hint="Restoration Hardware #999 Elsewhere")[0],          # another store
])
def test_4c_invalid_activity_is_not_deployment_evidence(row):
    res = engine.project(_radio(bid=1, source_activity=[row]))
    s = facp(res, 1)
    assert (s["lifecycle"], s["counts"]) == (V.UNKNOWN, False)


def test_4d_activity_reported_under_another_store_is_flagged_as_possibly_moved():
    res = engine.project(_radio(bid=1, source_activity=live("77187020", hint="RH #999")))
    assert [f["building_id"] for f in codes(res, "DEPLOYMENT_LOCATION_CONFLICT")] == [1]
    ok = engine.project(_radio(bid=1, source_activity=live("77187020", hint="RH #147")))
    assert facp(ok, 1)["counts"]                                   # same store: fine


# ── 5. confidence, approval, lifecycle and deployment are independent ─

def test_5_the_four_axes_stay_independent():
    # deployed but identity only PROBABLE (Zoho-only radio) -> CURRENT, not counted
    p = facp(engine.project(snap(zoho_rows=[z("RH Princeton", "Fire Alarm", starlink="77187020")],
                                 source_activity=live("77187020"))), 7)
    assert (p["confidence"], p["deployment"], p["lifecycle"], p["counts"]) == \
        (V.PROBABLE, V.DEPLOYED, V.CURRENT, False)
    # deployed + confirmed but operator-REJECTED -> not counted
    base = _radio(source_activity=live("77187020"))
    key = facp(engine.project(base), 7)["service_key"]
    base["decisions"] = [decision(V.D_SERVICE_APPROVAL, {"building": "RH Princeton",
                                                         "service_key": key},
                                  {"approval": "REJECTED"})]
    r = facp(engine.project(base), 7)
    assert (r["confidence"], r["deployment"], r["approval"], r["counts"]) == \
        (V.CONFIRMED, V.DEPLOYED, V.REJECTED, False)
    # a negative source status is still honoured without activity ...
    s = facp(engine.project(_radio(status="Suspended")), 7)
    assert s["lifecycle"] not in (V.CURRENT,) and s["deployment"] == V.DEPLOYMENT_NOT_ESTABLISHED
    # ... and live activity against a de-activated CRM record is surfaced, not hidden
    res = engine.project(_radio(status="De-activated", source_activity=live("77187020")))
    assert facp(res, 7)["lifecycle"] == V.CURRENT
    assert codes(res, "LIFECYCLE_CONFLICT")


# ── RH building shapes (synthetic ids) ────────────────────────────────

def test_houston_shape_unsignalled_radio_absent_from_napco_is_never_counted():
    # Zoho Alarm Panel radio + True911/registry claim; not in the NAPCO snapshot
    rows = [z("RH Houston #130", "Alarm Panel", starlink="7700387")]
    maps = [reg(1, 4, "7700387")]
    without = facp(engine.project(snap(zoho_rows=rows, mappings=maps)), 4)
    assert (without["confidence"], without["lifecycle"], without["counts"]) == \
        (V.CONFIRMED, V.UNKNOWN, False)                         # identity yes, deployment no
    loaded = facp(engine.project(snap(zoho_rows=rows, mappings=maps, napco_radios=["77187020"])), 4)
    assert (loaded["confidence"], loaded["lifecycle"], loaded["counts"]) == \
        (V.PROBABLE, V.UNKNOWN, False)


@pytest.mark.parametrize("signal,counted", [(RECENT, True), (STALE, False), (None, False)])
def test_princeton_shape_counts_only_with_a_recent_napco_signal(signal, counted):
    act = live("77187020", at=signal) if signal else []
    s = facp(engine.project(_radio(napco_radios=["77187020"], source_activity=act)), 7)
    assert s["confidence"] == V.CONFIRMED and s["counts"] is counted
    assert s["lifecycle"] == (V.CURRENT if counted else V.UNKNOWN)


def test_roseville_shape_zoho_only_radio_is_probable_and_not_current():
    rows = [z("RH Austin #149", "Alarm Panel", starlink="7700523")]
    s = facp(engine.project(snap(zoho_rows=rows, napco_radios=["77187020"])), 8)
    assert (s["confidence"], s["lifecycle"], s["counts"]) == (V.PROBABLE, V.UNKNOWN, False)


def test_leawood_shape_two_never_signalled_radios_without_fire_label_stay_unresolved():
    rows = [z("RH Austin #149", None, starlink="7704689"),
            z("RH Austin #149", None, starlink="7705154")]
    res = engine.project(snap(zoho_rows=rows, napco_radios=["7704689", "7705154"]))
    f = [s for s in res["services"] if s["building_id"] == 8]
    assert len(f) == 2
    assert all((s["confidence"], s["lifecycle"], s["counts"]) == (V.UNRESOLVED, V.UNKNOWN, False)
               for s in f)
