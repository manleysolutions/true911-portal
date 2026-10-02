"""Canonical engine - deployment is its own axis, and activity is not location.

An administrative status (Zoho Subscription_Mgmnt "Activated", a True911 or
carrier "active") is CRM/source bookkeeping, never proof of deployment.
DEPLOYED needs BOTH:

  (a) liveness - an operator lifecycle decision, a recent True911 heartbeat, or
      recent NAPCO / T-Mobile activity in an imported snapshot; AND
  (b) deterministic placement at that building - an operator placement or an
      exact registry identifier / telephone mapping.

Recent activity proves the equipment is alive, never WHERE it is.  Building
SHAPES mirror Houston, Princeton, Roseville, Jacksonville and Leawood; every
identifier is SYNTHETIC.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.services.canonical import engine
from app.services.canonical import vocab as V
from tests.test_canonical_engine import (
    RECENT,
    conns,
    decision,
    device,
    live,
    pin,
    site,
    snap,
    svc,
    zrow,
)

NOW = datetime.now(timezone.utc)
STALE = NOW - timedelta(days=V.DEPLOYMENT_ACTIVITY_DAYS + 30)
RADIO = "77187020"
LINE = "2025550190"


def z(facility, ctype=None, *, msisdn=None, starlink=None, status="Activated"):
    return zrow(facility, msisdn, ctype, status=status, starlink=starlink)


def facp(res, bid):
    (s,) = [s for s in res["services"] if s["building_id"] == bid and s["service_type"] == V.FACP]
    return s


def codes(res, code):
    return [f for f in res["findings"] if f["code"] == code]


_NAME = {7: "RH Princeton", 4: "RH Houston #130", 1: "RH Chicago #147", 5: "RH Jacksonville"}


def _radio(bid=7, *, status="Activated", placed=True, **kw):
    """A Fire Alarm radio.  ``placed`` adds the exact registry radio mapping
    (deterministic placement + identity corroboration)."""
    kw.setdefault("mappings", pin(bid, RADIO) if placed else [])
    return snap(zoho_rows=[z(_NAME[bid], "Fire Alarm", starlink=RADIO, status=status)], **kw)


def _line(bid=1, *, placed=True, **kw):
    """An Elevator line placed by Zoho facility, plus (optionally) an exact
    registry telephone mapping."""
    kw.setdefault("mappings", pin(bid, LINE) if placed else [])
    return snap(zoho_rows=[z(_NAME[bid], "Elevator", msisdn=LINE)], **kw)


# ── administrative status is never deployment ─────────────────────────

def test_zoho_activated_alone_does_not_make_a_service_current():
    res = engine.project(_line())                                  # placed, but no liveness
    a = res["assets"]["TELEPHONE_NUMBER:%s" % LINE]
    assert (a["lifecycle"], a["lifecycle_reason"], a["deployment"]) == \
        (V.UNKNOWN, V.REASON_ADMIN_STATUS_ONLY, V.DEPLOYMENT_NOT_ESTABLISHED)
    assert a["source_status"] == "ZOHO:CURRENT"                   # kept as CRM status only
    s = svc(res, "ELEV:tel:%s" % LINE)
    assert (s["confidence"], s["lifecycle"], s["counts"]) == (V.CONFIRMED, V.UNKNOWN, False)


def test_zoho_activated_plus_confirmed_radio_identity_alone_is_not_counted():
    s = facp(engine.project(_radio(napco_radios=[RADIO])), 7)
    assert (s["confidence"], s["provenance"]["napco_backed"]) == (V.CONFIRMED, True)
    assert (s["lifecycle"], s["deployment"], s["counts"]) == \
        (V.UNKNOWN, V.DEPLOYMENT_NOT_ESTABLISHED, False)


def test_confirmed_and_approved_but_undeployed_is_not_counted():
    base = _radio(napco_radios=[RADIO])
    key = facp(engine.project(base), 7)["service_key"]
    base["decisions"] = [decision(V.D_SERVICE_APPROVAL, {"building": "RH Princeton",
                                                         "service_key": key},
                                  {"approval": "APPROVED"})]
    res = engine.project(base)
    assert (facp(res, 7)["approval"], facp(res, 7)["counts"]) == (V.APPROVED, False)
    assert conns(res, 7) == [] and codes(res, "LIFECYCLE_UNKNOWN")


# ── 1-3. activity without deterministic placement -> UNKNOWN ──────────

def test_1_recent_tmobile_activity_without_placement_is_unknown():
    res = engine.project(_line(placed=False, source_activity=live(LINE)))
    a = res["assets"]["TELEPHONE_NUMBER:%s" % LINE]
    assert a["placement_basis"] in V.LOCATION_BASES                # Zoho CRM location text only
    assert (a["lifecycle"], a["lifecycle_reason"], a["deployment"]) == \
        (V.UNKNOWN, V.REASON_PLACEMENT_UNVERIFIED, V.DEPLOYMENT_NOT_ESTABLISHED)
    assert a["liveness_source"] == "T_MOBILE"                      # liveness kept separately
    assert not svc(res, "ELEV:tel:%s" % LINE)["counts"]
    assert codes(res, "ACTIVE_PLACEMENT_UNVERIFIED")


def test_2_recent_napco_signal_without_placement_is_unknown_even_for_confirmed_identity():
    # Zoho + a True911 FACP device corroborate the radio (CONFIRMED identity), but
    # both place it only by facility / site-name text
    dev = device("F7", "S-P", device_type="Fire Alarm Control Panel", starlink_id=RADIO,
                 manufacturer="Napco")
    res = engine.project(_radio(placed=False, devices=[dev], sites=[site("S-P", "RH Princeton")],
                                napco_radios=[RADIO], source_activity=live(RADIO)))
    s = facp(res, 7)
    assert s["confidence"] == V.CONFIRMED
    assert (s["lifecycle"], s["deployment"], s["counts"]) == \
        (V.UNKNOWN, V.DEPLOYMENT_NOT_ESTABLISHED, False)
    assert s["lifecycle_reason"] == V.REASON_PLACEMENT_UNVERIFIED


@pytest.mark.parametrize("hint", [None, "", "Restoration Hardware", "RH", "Fire Alarm",
                                  "RH #147"])   # even a matching store label only SUPPORTS
def test_3_blank_generic_or_matching_label_does_not_establish_placement(hint):
    res = engine.project(_radio(bid=1, placed=False, source_activity=live(RADIO, hint=hint)))
    s = facp(res, 1)
    assert (s["deployment"], s["counts"]) == (V.DEPLOYMENT_NOT_ESTABLISHED, False)


def test_heartbeat_without_trusted_device_placement_is_not_deployment():
    dev = device("F8", "S-P", device_type="Fire Alarm Control Panel", starlink_id=RADIO,
                 manufacturer="Napco", last_heartbeat=RECENT)
    res = engine.project(snap(devices=[dev], sites=[site("S-P", "RH Princeton")]))
    s = facp(res, 7)
    assert (s["deployment"], s["counts"]) == (V.DEPLOYMENT_NOT_ESTABLISHED, False)


# ── 4. a different-store label is a conflict, never carried over ──────

def test_4_activity_under_a_different_store_is_a_placement_conflict():
    res = engine.project(_radio(bid=1, source_activity=live(RADIO, hint="RH #999 Elsewhere")))
    s = facp(res, 1)
    assert (s["deployment"], s["counts"]) == (V.DEPLOYMENT_NOT_ESTABLISHED, False)
    assert [f["building_id"] for f in codes(res, "DEPLOYMENT_LOCATION_CONFLICT")] == [1]


# ── 5. activity + deterministic placement may establish DEPLOYED ──────

@pytest.mark.parametrize("extra,basis,source", [
    ({"source_activity": live(RADIO)}, V.REASON_DEPLOYMENT_ACTIVITY, "NAPCO"),
    ({"source_activity": live(RADIO, hint="RH #147")}, V.REASON_DEPLOYMENT_ACTIVITY, "NAPCO"),
    ({"devices": [device("F9", "S-C", device_type="Fire Alarm Control Panel",
                         starlink_id=RADIO, manufacturer="Napco", last_heartbeat=RECENT)],
      "sites": [site("S-C", "RH Chicago #147")]}, V.REASON_DEPLOYMENT_TELEMETRY, "TRUE911"),
])
def test_5_activity_plus_deterministic_placement_establishes_deployed(extra, basis, source):
    res = engine.project(_radio(bid=1, **extra))
    a = res["assets"]["NAPCO_RADIO:%s" % RADIO]
    assert a["placement_basis"] == V.P_ASSET_IDENTIFIER
    s = facp(res, 1)
    assert (s["lifecycle"], s["deployment"], s["deployment_basis"]) == \
        (V.CURRENT, V.DEPLOYED, basis)
    assert s["counts"] and len(conns(res, 1)) == 2
    assert a["lifecycle_source"] == source


def test_5b_tmobile_activity_plus_registry_telephone_mapping_establishes_deployed():
    s = svc(engine.project(_line(source_activity=live(LINE))), "ELEV:tel:%s" % LINE)
    assert (s["lifecycle"], s["deployment"], s["counts"]) == (V.CURRENT, V.DEPLOYED, True)


def test_5c_operator_placement_plus_activity_establishes_deployed():
    decs = [decision(V.D_SERVICE_CLASSIFICATION, {"building": "RH Chicago", "number": LINE},
                     {"service_type": "ELEVATOR", "label": "Elevator 1"})]
    res = engine.project(_line(placed=False, decisions=decs, source_activity=live(LINE)))
    assert res["assets"]["TELEPHONE_NUMBER:%s" % LINE]["placement_basis"] == V.P_OPERATOR
    assert svc(res, "ELEV:tel:%s" % LINE)["counts"]


# ── 6. Verizon inventory status never establishes DEPLOYED ────────────

@pytest.mark.parametrize("at", [RECENT, None])
def test_6_verizon_active_never_establishes_deployed(at):
    row = dict(live(LINE)[0], source="VERIZON", activity_at=at)
    s = svc(engine.project(_line(source_activity=[row])), "ELEV:tel:%s" % LINE)
    assert (s["lifecycle"], s["deployment"], s["counts"]) == \
        (V.UNKNOWN, V.DEPLOYMENT_NOT_ESTABLISHED, False)


# ── 7-8. operator truth persists; inferred deployment ages out ────────

def _operator_current(value=RADIO):
    return decision(V.D_ASSET_LIFECYCLE, {"asset_type": "NAPCO_RADIO", "value": value},
                    {"lifecycle": "CURRENT"})


def test_7_operator_current_persists_beyond_the_activity_window():
    later = NOW + timedelta(days=400)                              # no activity for 400 days
    res = engine.project(_radio(bid=1, decisions=[_operator_current()]), now=later)
    s = facp(res, 1)
    assert (s["lifecycle"], s["deployment"], s["deployment_basis"], s["counts"]) == \
        (V.CURRENT, V.DEPLOYED, V.REASON_OPERATOR, True)


def test_7b_operator_current_without_deterministic_placement_is_current_but_not_deployed():
    res = engine.project(_radio(bid=1, placed=False, decisions=[_operator_current()]))
    s = facp(res, 1)
    assert (s["lifecycle"], s["deployment"], s["counts"]) == \
        (V.CURRENT, V.DEPLOYMENT_NOT_ESTABLISHED, False)
    assert codes(res, "DEPLOYMENT_PLACEMENT_UNVERIFIED")


def test_8_inferred_deployment_ages_out_without_touching_operator_truth():
    rows = [z("RH Chicago #147", "Fire Alarm", starlink=RADIO),
            z("RH Chicago #147", "Fire Alarm", starlink="77000002")]
    decs = [_operator_current("77000002")]
    base = snap(zoho_rows=rows, mappings=pin(1, RADIO, "77000002"), decisions=decs,
                source_activity=live(RADIO, at=NOW - timedelta(days=1)))
    frozen = copy.deepcopy(decs)

    def by_key(res):
        return {s["service_key"]: s for s in res["services"] if s["service_type"] == V.FACP}
    today = by_key(engine.project(base, now=NOW))
    assert today["FACP:radio:%s" % RADIO]["deployment"] == V.DEPLOYED       # inferred
    assert today["FACP:radio:77000002"]["deployment"] == V.DEPLOYED         # operator
    later = by_key(engine.project(base, now=NOW + timedelta(days=60)))
    assert later["FACP:radio:%s" % RADIO]["deployment"] == V.DEPLOYMENT_NOT_ESTABLISHED
    assert not later["FACP:radio:%s" % RADIO]["counts"]
    assert later["FACP:radio:77000002"]["deployment"] == V.DEPLOYED
    assert later["FACP:radio:77000002"]["counts"]
    assert base["decisions"] == frozen                              # engine never edits truth


@pytest.mark.parametrize("row", [
    live(RADIO, at=STALE)[0],                                      # old signal
    live(RADIO, lifecycle=V.DECOMMISSIONED)[0],                    # terminated SIM
    live(RADIO, at=NOW + timedelta(days=5))[0],                    # future clock
])
def test_invalid_activity_is_not_liveness(row):
    s = facp(engine.project(_radio(bid=1, source_activity=[row])), 1)
    assert (s["lifecycle"], s["counts"]) == (V.UNKNOWN, False)


# ── axes stay independent ─────────────────────────────────────────────

def test_the_four_axes_stay_independent():
    # deployed (mapped + live) but identity only PROBABLE (pairing ambiguous)
    rows = [z("RH Princeton", "Fire Alarm"), z("RH Princeton", "Fire Alarm")]
    res = engine.project(snap(zoho_rows=rows, mappings=pin(7, RADIO, "77000002"),
                              source_activity=live(RADIO, "77000002")))
    f = [s for s in res["services"] if s["building_id"] == 7]
    assert len(f) == 2 and all((s["confidence"], s["deployment"], s["lifecycle"], s["counts"])
                               == (V.PROBABLE, V.DEPLOYED, V.CURRENT, False) for s in f)
    # deployed + confirmed but operator-REJECTED -> not counted
    base = _radio(source_activity=live(RADIO))
    key = facp(engine.project(base), 7)["service_key"]
    base["decisions"] = [decision(V.D_SERVICE_APPROVAL, {"building": "RH Princeton",
                                                         "service_key": key},
                                  {"approval": "REJECTED"})]
    r = facp(engine.project(base), 7)
    assert (r["confidence"], r["deployment"], r["approval"], r["counts"]) == \
        (V.CONFIRMED, V.DEPLOYED, V.REJECTED, False)
    # a negative source status is honoured without activity ...
    s = facp(engine.project(_radio(status="Suspended")), 7)
    assert s["lifecycle"] != V.CURRENT and s["deployment"] == V.DEPLOYMENT_NOT_ESTABLISHED
    # ... and live activity against a de-activated CRM record is surfaced
    res = engine.project(_radio(status="De-activated", source_activity=live(RADIO)))
    assert facp(res, 7)["lifecycle"] == V.CURRENT and codes(res, "LIFECYCLE_CONFLICT")


# ── RH building shapes (synthetic ids) ────────────────────────────────

def test_houston_shape_radio_absent_from_napco_is_never_counted():
    rows = [z("RH Houston #130", "Alarm Panel", starlink="7700387")]
    without = facp(engine.project(snap(zoho_rows=rows, mappings=pin(4, "7700387"))), 4)
    assert (without["confidence"], without["lifecycle"], without["counts"]) == \
        (V.CONFIRMED, V.UNKNOWN, False)
    loaded = facp(engine.project(snap(zoho_rows=rows, mappings=pin(4, "7700387"),
                                      napco_radios=[RADIO])), 4)
    assert (loaded["confidence"], loaded["lifecycle"], loaded["counts"]) == \
        (V.PROBABLE, V.UNKNOWN, False)


@pytest.mark.parametrize("signal,placed,counted", [
    (RECENT, True, True), (RECENT, False, False), (STALE, True, False), (None, True, False)])
def test_princeton_shape_needs_a_recent_signal_and_deterministic_placement(signal, placed,
                                                                           counted):
    act = live(RADIO, at=signal) if signal else []
    s = facp(engine.project(_radio(placed=placed, napco_radios=[RADIO], source_activity=act)), 7)
    assert s["counts"] is counted


def test_roseville_shape_zoho_only_radio_is_probable_and_not_current():
    rows = [z("RH Austin #149", "Alarm Panel", starlink="7700523")]
    s = facp(engine.project(snap(zoho_rows=rows, napco_radios=[RADIO])), 8)
    assert (s["confidence"], s["lifecycle"], s["counts"]) == (V.PROBABLE, V.UNKNOWN, False)


def test_jacksonville_shape_live_lines_count_only_with_operator_or_registry_placement():
    lines = ["2025550601", "2025550602"]
    rows = [z("RH Jacksonville", "Elevator", msisdn=n) for n in lines]
    act = live(*lines)
    plain = engine.project(snap(zoho_rows=rows, source_activity=act))
    assert not [s for s in plain["services"] if s["counts"]]       # Zoho facility only
    decs = [decision(V.D_SERVICE_CLASSIFICATION, {"building": "RH Jacksonville", "number": n},
                     {"service_type": "ELEVATOR", "label": "Elevator %d" % (i + 1)})
            for i, n in enumerate(lines)]
    placed = engine.project(snap(zoho_rows=rows, source_activity=act, decisions=decs))
    assert len([s for s in placed["services"] if s["counts"]]) == 2


def test_leawood_shape_two_never_signalled_radios_without_fire_label_stay_unresolved():
    rows = [z("RH Austin #149", None, starlink="7704689"),
            z("RH Austin #149", None, starlink="7705154")]
    res = engine.project(snap(zoho_rows=rows, napco_radios=["7704689", "7705154"],
                              mappings=pin(8, "7704689", "7705154")))
    f = [s for s in res["services"] if s["building_id"] == 8]
    assert len(f) == 2
    assert all((s["confidence"], s["lifecycle"], s["counts"]) == (V.UNRESOLVED, V.UNKNOWN, False)
               for s in f)
