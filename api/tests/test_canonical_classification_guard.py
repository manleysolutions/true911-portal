"""Canonical engine - PLACEMENT != LIFECYCLE != SERVICE CLASSIFICATION != CERTIFICATION.

Regression for the 15-decision RH preview: a San Rafael-shaped radio became
FACP / CONFIRMED / CURRENT / COUNTED.  Its Zoho record has no Connection Type;
the only "FACP" signal was True911 equipment typing (a NAPCO communicator
typed as fire-alarm hardware).  An operator SOURCE_RECORD BUILDING decision
then placed it and an ASSET_LIFECYCLE CURRENT decision made it current.

Placement and lifecycle decisions are legitimate - but neither, nor equipment
typing, may create, promote, confirm or count an FACP service.  Every
identifier is SYNTHETIC.
"""

from __future__ import annotations

from app.services.canonical import engine
from app.services.canonical import vocab as V
from tests.test_canonical_engine import conns, decision, device, pin, site, snap, svc, zrow

CUR, OLD = "7872590", "7741483"


def z(facility, ctype=None, *, msisdn=None, starlink=None, status="Activated", zid=None):
    r = zrow(facility, msisdn, ctype, status=status, starlink=starlink)
    if zid:
        r["zoho_id"] = zid
    return r


def hw_device(dev_id, site_id, radio, **kw):
    """A NAPCO communicator TYPED as fire-alarm hardware in True911 (equipment
    typing only - no operator classification override)."""
    return device(dev_id, site_id, device_type="Fire Alarm Control Panel",
                  model="SLELTE - Fire (Dual Line)", manufacturer="Napco", starlink_id=radio,
                  **kw)


def placed(rid, building):
    return decision(V.D_SOURCE_RECORD, {"source": "ZOHO", "record_id": rid},
                    {"disposition": "BUILDING", "building": building})


def lifecycle(value, lc, atype="NAPCO_RADIO"):
    return decision(V.D_ASSET_LIFECYCLE, {"asset_type": atype, "value": value},
                    {"lifecycle": lc})


def facp_service(building, ref, *radios):
    return decision(V.D_FACP_SERVICE, {"building": building, "service_ref": ref},
                    {"radios": list(radios)})


def facps(res, bid):
    return {s["service_key"]: s for s in res["services"]
            if s["building_id"] == bid and s["service_type"] == V.FACP}


def codes(res, code):
    return [f for f in res["findings"] if f["code"] == code]


def _san_rafael(decs, *, with_device=True):
    """Two blank-Connection-Type Zoho radio records (old suspended, new active)
    and, as in production, True911 devices equipment-typed as FACP."""
    rows = [z("RH Long Beach", None, starlink=OLD, status="Suspended", zid="OLDREC"),
            z("RH Long Beach", None, starlink=CUR, zid="NEWREC")]
    kw = {}
    if with_device:
        kw = {"sites": [site("S-LB", "RH Long Beach")],
              "devices": [hw_device("D-OLD", "S-LB", OLD), hw_device("D-NEW", "S-LB", CUR)]}
    return engine.project(snap(zoho_rows=rows, decisions=decs, **kw))


# ── 1. CURRENT lifecycle alone does not establish an FACP service ─────

def test_1_current_asset_lifecycle_alone_does_not_establish_an_facp_service():
    res = _san_rafael([lifecycle(CUR, "CURRENT")])
    a = res["assets"]["NAPCO_RADIO:" + CUR]
    assert a["lifecycle"] == V.CURRENT                          # lifecycle IS established
    s = facps(res, 9)["FACP:radio:" + CUR]
    assert s["confidence"] != V.CONFIRMED and not s["counts"]
    assert conns(res, 9) == []
    assert codes(res, "FACP_TYPE_EQUIPMENT_ONLY")


# ── 2. BUILDING placement alone does not establish an FACP service ────

def test_2_building_placement_alone_does_not_establish_an_facp_service():
    res = _san_rafael([placed("NEWREC", "RH Long Beach")])
    a = res["assets"]["NAPCO_RADIO:" + CUR]
    assert (a["building_id"], a["placement_basis"]) == (9, V.P_OPERATOR)   # placement IS set
    s = facps(res, 9)["FACP:radio:" + CUR]
    assert s["confidence"] != V.CONFIRMED and not s["counts"]


def test_2b_the_exact_preview_combination_is_placed_and_current_but_never_counted():
    decs = [placed("NEWREC", "RH Long Beach"), placed("OLDREC", "RH Long Beach"),
            lifecycle(OLD, "HISTORICAL"), lifecycle(CUR, "CURRENT")]
    res = _san_rafael(decs)
    cur, old = res["assets"]["NAPCO_RADIO:" + CUR], res["assets"]["NAPCO_RADIO:" + OLD]
    assert (cur["building_id"], cur["lifecycle"], cur["deployment"]) == (9, V.CURRENT, V.DEPLOYED)
    assert (old["building_id"], old["lifecycle"]) == (9, V.HISTORICAL)
    f = facps(res, 9)
    assert f["FACP:radio:" + CUR]["confidence"] == V.PROBABLE      # a candidate, not certified
    assert f["FACP:radio:" + CUR]["lifecycle"] == V.CURRENT
    assert f["FACP:radio:" + OLD]["lifecycle"] == V.HISTORICAL
    assert not [s for s in f.values() if s["counts"]] and conns(res, 9) == []
    assert res["portfolio"]["confirmed_service_total"] == 0


def test_2c_without_equipment_typing_the_radio_stays_an_unresolved_candidate():
    decs = [placed("NEWREC", "RH Long Beach"), lifecycle(CUR, "CURRENT")]
    s = facps(_san_rafael(decs, with_device=False), 9)["FACP:radio:" + CUR]
    assert (s["confidence"], s["counts"]) == (V.UNRESOLVED, False)


# ── 3. genuine service-type evidence still establishes the service ────

def test_3_explicit_facp_service_decision_still_establishes_and_counts_the_service():
    decs = [placed("NEWREC", "RH Long Beach"), lifecycle(CUR, "CURRENT"),
            facp_service("RH Long Beach", "FACP 1", CUR)]
    res = _san_rafael(decs)
    s = facps(res, 9)["FACP:radio:" + CUR]
    assert (s["confidence"], s["lifecycle"], s["counts"]) == (V.CONFIRMED, V.CURRENT, True)
    assert len(conns(res, 9)) == 2


def test_3b_a_zoho_fire_alarm_label_or_operator_override_is_service_type_evidence():
    rows = [z("RH Long Beach", "Alarm Panel", starlink=CUR)]
    common = dict(sites=[site("S-LB", "RH Long Beach")], mappings=pin(9, CUR),
                  decisions=[lifecycle(CUR, "CURRENT")])
    labelled = engine.project(snap(zoho_rows=rows, devices=[hw_device("D", "S-LB", CUR)],
                                   **common))
    assert facps(labelled, 9)["FACP:radio:" + CUR]["counts"]
    override = engine.project(snap(devices=[hw_device("D", "S-LB", CUR,
                                                      override_service_type="Fire Alarm")],
                                   **common))
    assert facps(override, 9)["FACP:radio:" + CUR]["counts"]


def test_3c_equipment_typing_alone_is_probable_even_with_strong_placement_and_liveness():
    res = engine.project(snap(sites=[site("S-LB", "RH Long Beach")], mappings=pin(9, CUR),
                              devices=[hw_device("D", "S-LB", CUR)],
                              decisions=[lifecycle(CUR, "CURRENT")]))
    s = facps(res, 9)["FACP:radio:" + CUR]
    assert (s["confidence"], s["deployment"], s["counts"]) == (V.PROBABLE, V.DEPLOYED, False)


# ── 4. a PLACEHOLDER record contributes to no current inventory ───────

def test_4_placeholder_record_contributes_nothing_to_current_inventory_or_counts():
    rows = [z("RH Chicago #147", "Elevator", msisdn="2025550186", starlink="7790001", zid="PH1")]
    decs = [decision(V.D_SOURCE_RECORD, {"source": "ZOHO", "record_id": "PH1"},
                     {"disposition": "PLACEHOLDER"}),
            lifecycle("2025550186", "CURRENT", atype="TELEPHONE_NUMBER")]
    res = engine.project(snap(zoho_rows=rows, decisions=decs))
    assert [e["record"] for e in res["excluded_records"]] == ["zoho:PH1"]   # kept for audit
    assert not [a for a in res["assets"].values() if a["records"]]          # no sourced asset
    assert [s for s in res["services"] if s["building_id"] == 1] == []
    assert res["connections"] == []
    b = next(b for b in res["building_summaries"] if b["building_id"] == 1)
    assert sum(b["current_assets"].values()) == 0
    p = res["portfolio"]
    assert (p["confirmed_service_total"], p["confirmed_required_connections"],
            p["probable_services"]) == (0, 0, 0)


# ── 5. Princeton: one FACP, two communicators ─────────────────────────

def test_5_princeton_one_facp_two_radios_with_equipment_typed_devices():
    r1, r2, stale = "77110020", "7756099", "7710020"
    rows = [z("RH Princeton", "Alarm Panel", starlink=r1, zid="REC578"),
            z("RH Princeton", None, starlink=r2, zid="REC903"),
            z("RH Princeton", "Alarm Panel", starlink=stale, zid="REC265")]
    decs = [facp_service("RH Princeton", "FACP 1", r1, r2),
            decision(V.D_SOURCE_RECORD, {"source": "ZOHO", "record_id": "REC265"},
                     {"disposition": "DUPLICATE", "duplicate_of": "REC578"})]
    res = engine.project(snap(zoho_rows=rows, decisions=decs, sites=[site("S-P", "RH Princeton")],
                              devices=[hw_device("P1", "S-P", r1), hw_device("P2", "S-P", r2)]))
    f = facps(res, 7)
    assert list(f) == ["FACP:radio:%s+%s" % tuple(sorted([r1, r2]))]
    (s,) = f.values()
    assert s["confidence"] == V.CONFIRMED
    assert sorted(k for k, _r in s["assets"] if k.startswith("NAPCO_RADIO:")) == \
        sorted(["NAPCO_RADIO:" + r1, "NAPCO_RADIO:" + r2])
    assert not s["counts"]                     # no lifecycle decision: deployment not set


# ── 6. Jacksonville: migration + pool ─────────────────────────────────

def test_6_jacksonville_migration_classification_and_pool():
    legacy = ["2025550%03d" % i for i in range(201, 208)]               # 7 old numbers
    elevators = ["2025550616", "2025550656"]
    pool = ["2025550633", "2025551550", "2025552688", "2025552768", "2025557030"]
    rows = [z("RH Jacksonville", "Elevator", msisdn=n) for n in legacy]
    rows.append(dict(z("RH Jacksonville", "Elevator", msisdn=legacy[4]), zoho_id="DUP"))
    rows += [z("RH Jacksonville", "Voice %d" % i, msisdn=n) for i, n in enumerate(elevators + pool)]
    decs = [decision(V.D_CARRIER_MIGRATION,
                     {"building": "RH Jacksonville", "legacy_numbers": legacy,
                      "replacement_numbers": elevators + pool},
                     {"legacy_carrier": "Old", "replacement_carrier": "New"}, eff="2026-09-22"),
            decision(V.D_SERVICE_CLASSIFICATION, {"building": "RH Jacksonville",
                                                  "number": elevators[0]},
                     {"service_type": "ELEVATOR", "label": "Elevator 1"}),
            decision(V.D_SERVICE_CLASSIFICATION, {"building": "RH Jacksonville",
                                                  "number": elevators[1]},
                     {"service_type": "ELEVATOR", "label": "Elevator 2"}),
            decision(V.D_SERVICE_POOL, {"building": "RH Jacksonville", "pool_ref": "Voice lines"},
                     {"numbers": pool, "service_types": ["EMERGENCY_PHONE", "FAX"]}),
            decision(V.D_SOURCE_RECORD, {"source": "ZOHO", "record_id": "DUP"},
                     {"disposition": "DUPLICATE"})]
    res = engine.project(snap(zoho_rows=rows, decisions=decs))
    for n in legacy:
        a = res["assets"]["TELEPHONE_NUMBER:" + n]
        assert a["lifecycle"] == V.DECOMMISSIONED and a["building_id"] == 5
    counted = sorted(s["display_name"] for s in res["services"] if s["counts"])
    assert counted == ["Elevator 1", "Elevator 2"]
    for n in pool:
        a = res["assets"]["TELEPHONE_NUMBER:" + n]
        assert (a["lifecycle"], a["classification"], a["pool"]) == \
            (V.CURRENT, V.UNCLASSIFIED, "Voice lines")
    assert not [s for s in res["services"] if s["service_type"] == V.EMERGENCY_PHONE]
    assert [e["record"] for e in res["excluded_records"]] == ["zoho:DUP"]
    assert len([s for s in res["services"]
                if s["service_key"] == "ELEV:tel:" + legacy[4]]) == 1   # one number, one service
