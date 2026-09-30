"""Canonical Life-Safety Service & Connection engine (D-023) - pure tests.

Every identifier here is SYNTHETIC (555-01xx numbers, NAP-/TEST- radio ids,
89010000... SIMs).  No real customer identifier may appear in this file.
"""

from __future__ import annotations

import pytest

from app.services.canonical import decisions as D
from app.services.canonical import engine
from app.services.canonical import vocab as V

T = "tenant-test"

BUILDINGS = [
    {"id": 1, "name": "RH Chicago", "store_number": "147", "address": "1 Test St",
     "city": "Chicago", "state": "IL"},
    {"id": 2, "name": "RH Memphis", "store_number": None, "address": "2 Test Ave",
     "city": "Memphis", "state": "TN"},
    {"id": 3, "name": "RH Cleveland", "store_number": "120", "address": "3 Test Rd",
     "city": "Cleveland", "state": "OH"},
    {"id": 4, "name": "RH Houston", "store_number": "130", "address": "4 Test Blvd",
     "city": "Houston", "state": "TX"},
    {"id": 5, "name": "RH Jacksonville", "store_number": "140", "address": "5 Test Way",
     "city": "Jacksonville", "state": "FL"},
    {"id": 6, "name": "RH NYC Guesthouse", "store_number": None, "address": "6 Test Pl",
     "city": "New York", "state": "NY"},
    {"id": 7, "name": "RH Princeton", "store_number": None, "address": "7 Test Pike",
     "city": "Princeton", "state": "NJ"},
    {"id": 8, "name": "RH Austin", "store_number": "149", "address": "8 Test Ave",
     "city": "Austin", "state": "TX"},
    {"id": 9, "name": "RH Long Beach", "store_number": None, "address": "9 Test Ln",
     "city": "Long Beach", "state": "CA"},
    {"id": 10, "name": "RH West Palm", "store_number": None, "address": "10 Test Ct",
     "city": "West Palm Beach", "state": "FL"},
]


def snap(**kw) -> dict:
    s = {"tenant_id": T, "buildings": BUILDINGS, "aliases": [], "mappings": [],
         "fused_groups": [], "sites": [], "devices": [], "lines": [], "units": [],
         "zoho_rows": [], "decisions": [], "generic_names": ["Restoration Hardware"],
         "sources": {"zoho": {"status": "ok", "required": True},
                     "true911": {"status": "ok", "required": True}}}
    s.update(kw)
    return s


_zid = iter(range(1000, 9999))


def zrow(facility=None, msisdn=None, ctype=None, status="Active", account=None, parent=None,
         starlink=None, sim=None):
    return {"zoho_id": "Z%d" % next(_zid), "facility": facility, "account": account,
            "parent": parent, "msisdn": msisdn, "connection_type": ctype,
            "subscription_type": None, "activation": status, "starlink": starlink,
            "sim": sim, "imei": None, "serial": None, "modified": "2026-09-01T00:00:00+00:00"}


def site(site_id, name, street=None, city=None, state=None):
    return {"site_id": site_id, "site_name": name, "status": "active", "street": street,
            "city": city, "state": state}


def device(device_id, site_id, *, device_type=None, model=None, starlink_id=None, msisdn=None,
           status="active", iccid=None, manufacturer=None):
    return {"device_id": device_id, "site_id": site_id, "status": status,
            "device_type": device_type, "model": model, "manufacturer": manufacturer,
            "identifier_type": None, "msisdn": msisdn, "iccid": iccid, "imei": None,
            "serial": None, "starlink_id": starlink_id, "notes": None, "carrier": None,
            "last_heartbeat": None, "override_service_type": None}


def decision(dtype, subject, new_state, reason="operator ground truth", eff=None):
    d = D.normalize_entry({"type": dtype, "subject": subject, "new_state": new_state,
                           "reason": reason, "effective_date": eff}, BUILDINGS)
    return d


def svc(res, key):
    return next(s for s in res["services"] if s["service_key"] == key)


def conns(res, bid):
    return [c for c in res["connections"] if c["building_id"] == bid]


def asset(res, atype, value):
    return res["assets"]["%s:%s" % (atype, value)]


# ── cardinality ──────────────────────────────────────────────────────

def test_confirmed_elevator_requires_exactly_one_connection():
    res = engine.project(snap(zoho_rows=[zrow("RH Chicago #147", "2025550101", "Elevator")]))
    s = svc(res, "ELEV:tel:2025550101")
    assert (s["service_type"], s["confidence"], s["lifecycle"], s["counts"]) == \
        (V.ELEVATOR, V.CONFIRMED, V.CURRENT, True)
    c = conns(res, 1)
    assert len(c) == 1 and c[0]["provisioning"] == V.ASSET_LINKED
    assert c[0]["links"] == [("TELEPHONE_NUMBER:2025550101", V.REL_CARRIER_LINE)]


def test_confirmed_emergency_phone_requires_exactly_one_connection():
    res = engine.project(snap(zoho_rows=[zrow("RH Chicago #147", "2025550102", "Emergency Phone")]))
    assert svc(res, "EPH:tel:2025550102")["counts"]
    assert len(conns(res, 1)) == 1


def _facp_device(dev_id, site_id, nap, **kw):
    return device(dev_id, site_id, device_type="Fire Alarm Control Panel", model="StarLink",
                  starlink_id=nap, manufacturer="Napco", **kw)


def test_confirmed_facp_requires_exactly_two_connections_and_fabricates_no_number():
    res = engine.project(snap(sites=[site("S-147", "RH Chicago #147")],
                              devices=[_facp_device("F1", "S-147", "NAP-0001")]))
    s = svc(res, "FACP:napco:NAP0001")
    assert (s["confidence"], s["lifecycle"], s["counts"]) == (V.CONFIRMED, V.CURRENT, True)
    c = conns(res, 1)
    assert [x["ordinal"] for x in c] == [1, 2]
    assert all(x["connection_type"] == "FACP_PATH" for x in c)
    # no telephone number was invented for either FACP path
    assert not [a for a in res["assets"].values() if a["asset_type"] == V.TELEPHONE_NUMBER]
    for x in c:
        assert all(not k.startswith("TELEPHONE_NUMBER") for k, _r in x["links"])
        assert x["provisioning"] == V.NOT_EVALUATED


def test_nyc_guesthouse_four_facps_make_eight_connections():
    devs = [_facp_device("G%d" % i, "S-G", "NAP-G%d" % i) for i in range(1, 5)]
    res = engine.project(snap(sites=[site("S-G", "RH NYC Guesthouse", "6 Test Pl", "New York", "NY")],
                              devices=devs))
    facps = [s for s in res["services"] if s["building_id"] == 6 and s["service_type"] == V.FACP]
    assert len(facps) == 4 and all(s["counts"] for s in facps)
    assert len(conns(res, 6)) == 8
    assert res["portfolio"]["confirmed_required_connections"] == 8


def _princeton(with_identifiers=True):
    maps = [{"id": 1, "building_id": 7, "kind": "napco_radio", "value": "NAP-P1"},
            {"id": 2, "building_id": 7, "kind": "napco_radio", "value": "NAP-P2"}]
    rows = [zrow("RH Princeton", None, "Fire Alarm", starlink="NAP-P1" if with_identifiers else None),
            zrow("RH Princeton", None, "Fire Alarm", starlink="NAP-P2" if with_identifiers else None)]
    return snap(mappings=maps, zoho_rows=rows)


def test_princeton_two_facps_make_four_connections_when_joins_support_it():
    res = engine.project(_princeton(True))
    facps = [s for s in res["services"] if s["building_id"] == 7]
    assert sorted(s["confidence"] for s in facps) == [V.CONFIRMED, V.CONFIRMED]
    assert len(conns(res, 7)) == 4


def test_princeton_without_joining_identifiers_stays_probable_and_uncounted():
    res = engine.project(_princeton(False))
    facps = [s for s in res["services"] if s["building_id"] == 7]
    assert facps and all(s["confidence"] == V.PROBABLE and not s["counts"] for s in facps)
    assert conns(res, 7) == []
    b = next(b for b in res["building_summaries"] if b["building_id"] == 7)
    assert b["probable_additional_connections"] == 4


# ── classification ───────────────────────────────────────────────────

def test_multi_number_device_classification_is_not_propagated():
    dev = device("E1", "S-147", model="LM150 elevator phone")
    lines = [{"line_id": "L1", "device_id": "E1", "did": "2025550111", "status": "active",
              "line_type": None, "description": None, "notes": None},
             {"line_id": "L2", "device_id": "E1", "did": "2025550112", "status": "active",
              "line_type": None, "description": None, "notes": None}]
    res = engine.project(snap(sites=[site("S-147", "RH Chicago #147")], devices=[dev], lines=lines))
    for n in ("2025550111", "2025550112"):
        a = asset(res, V.TELEPHONE_NUMBER, n)
        assert a["classification"] == V.UNCLASSIFIED
    assert not [s for s in res["services"] if s["service_type"] == V.ELEVATOR]
    assert any(f["code"] == "MULTI_NUMBER_DEVICE" for f in res["findings"])


def test_single_number_equipment_inference_is_only_probable():
    dev = device("E2", "S-147", model="LM150 elevator phone", msisdn="2025550113")
    res = engine.project(snap(sites=[site("S-147", "RH Chicago #147")], devices=[dev]))
    s = svc(res, "ELEV:tel:2025550113")
    assert s["confidence"] == V.PROBABLE and not s["counts"]
    assert conns(res, 1) == []


@pytest.mark.parametrize("label", ["Fax line", "Front desk", "POS terminal", "Internet data "])
def test_desk_fax_and_data_lines_are_not_life_safety(label):
    res = engine.project(snap(zoho_rows=[zrow("RH Chicago #147", "2025550120", label)]))
    assert asset(res, V.TELEPHONE_NUMBER, "2025550120")["classification"] == V.OTHER
    assert res["services"] == [] and res["connections"] == []


def test_explicit_label_conflict_is_unresolved():
    res = engine.project(snap(zoho_rows=[zrow("RH Chicago #147", "2025550121", "Elevator"),
                                         zrow("RH Chicago #147", "2025550121", "Emergency Phone")]))
    assert asset(res, V.TELEPHONE_NUMBER, "2025550121")["classification"] == V.UNCLASSIFIED
    assert res["connections"] == []


# ── placement ────────────────────────────────────────────────────────

MEMPHIS_PARENT = "Restoration Hardware MEMPHIS"


def _memphis_alias():
    # a historical account alias that equals the generic Zoho parent name
    return [{"id": 50, "building_id": 2, "kind": "zoho_account", "value": MEMPHIS_PARENT}]


def test_generic_parent_account_cannot_place_into_memphis():
    rows = [zrow(None, "2025550130", "Elevator", account=MEMPHIS_PARENT, parent=MEMPHIS_PARENT)]
    res = engine.project(snap(mappings=_memphis_alias(), zoho_rows=rows))
    a = asset(res, V.TELEPHONE_NUMBER, "2025550130")
    assert a["building_id"] is None and a["placement_confidence"] == V.UNRESOLVED
    assert res["services"] == [] and res["connections"] == []


def test_specific_facility_overrides_parent_account():
    rows = [zrow("RH Cleveland", "2025550131", "Elevator", parent=MEMPHIS_PARENT)]
    res = engine.project(snap(mappings=_memphis_alias(), zoho_rows=rows))
    a = asset(res, V.TELEPHONE_NUMBER, "2025550131")
    assert (a["building_id"], a["placement_confidence"]) == (3, V.CONFIRMED)
    assert svc(res, "ELEV:tel:2025550131")["building_id"] == 3


def test_specific_account_alias_places_when_no_facility():
    aliases = [{"building_id": 8, "alias": "RH Austin Gallery"}]
    rows = [zrow(None, "2025550132", "Elevator", account="RH Austin Gallery", parent=MEMPHIS_PARENT)]
    res = engine.project(snap(aliases=aliases, mappings=_memphis_alias(), zoho_rows=rows))
    assert asset(res, V.TELEPHONE_NUMBER, "2025550132")["building_id"] == 8


def test_historical_site_link_alone_is_only_probable():
    maps = [{"id": 1, "building_id": 1, "kind": "true911_device", "value": "S-X"}]
    dev = device("X1", "S-X", msisdn="2025550133")
    lines = [{"line_id": "LX", "device_id": "X1", "did": "2025550133", "status": "active",
              "line_type": "Elevator", "description": None, "notes": None}]
    res = engine.project(snap(mappings=maps, sites=[site("S-X", "Unnamed site")], devices=[dev],
                              lines=lines))
    a = asset(res, V.TELEPHONE_NUMBER, "2025550133")
    assert (a["building_id"], a["placement_confidence"]) == (1, V.PROBABLE)
    assert not svc(res, "ELEV:tel:2025550133")["counts"]


# ── confidence / approval separation ─────────────────────────────────

def test_probable_and_unresolved_are_never_confirmed():
    maps = [{"id": 1, "building_id": 7, "kind": "napco_radio", "value": "NAP-U1"}]
    res = engine.project(snap(mappings=maps,
                              zoho_rows=[zrow("RH Houston #130", None, "Fire Alarm")]))
    h = [s for s in res["services"] if s["building_id"] == 4]
    p = [s for s in res["services"] if s["building_id"] == 7]
    assert [s["confidence"] for s in h] == [V.PROBABLE]
    assert [s["confidence"] for s in p] == [V.UNRESOLVED]
    assert res["connections"] == []
    assert res["portfolio"]["confirmed_service_total"] == 0


def test_operator_approval_and_rejection_are_separate_from_confidence():
    rows = [zrow("RH Houston #130", None, "Fire Alarm"),
            zrow("RH Chicago #147", "2025550140", "Elevator")]
    base = engine.project(snap(zoho_rows=rows))
    fkey = next(s["service_key"] for s in base["services"] if s["building_id"] == 4)
    decs = [decision(V.D_SERVICE_APPROVAL, {"building": "RH Houston", "service_key": fkey},
                     {"approval": "APPROVED"}),
            decision(V.D_SERVICE_APPROVAL, {"building": "RH Chicago",
                                            "service_key": "ELEV:tel:2025550140"},
                     {"approval": "REJECTED"})]
    res = engine.project(snap(zoho_rows=rows, decisions=decs))
    f = svc(res, fkey)
    assert (f["confidence"], f["approval"], f["counts"]) == (V.PROBABLE, V.APPROVED, True)
    e = svc(res, "ELEV:tel:2025550140")
    assert (e["confidence"], e["approval"], e["counts"]) == (V.CONFIRMED, V.REJECTED, False)
    assert len(conns(res, 4)) == 2 and conns(res, 1) == []


def test_degraded_source_caps_confirmed_and_is_reported():
    s = snap(zoho_rows=[zrow("RH Chicago #147", "2025550150", "Elevator")])
    s["sources"]["zoho"] = {"status": "unavailable: timeout", "required": True}
    res = engine.project(s)
    assert res["degraded"] is True
    assert svc(res, "ELEV:tel:2025550150")["confidence"] == V.PROBABLE
    assert res["connections"] == []
    assert any(f["code"] == "SOURCE_UNAVAILABLE" for f in res["findings"])


def test_engine_never_touches_e911():
    res = engine.project(snap(zoho_rows=[zrow("RH Chicago #147", "2025550151", "Elevator")]))
    blob = repr({k: v for k, v in res.items() if k != "records"}).lower().replace("true911", "")
    assert "e911" not in blob and "verified" not in blob


# ── Jacksonville carrier migration ───────────────────────────────────

LEGACY = ["20255502%02d" % i for i in range(1, 7)]           # 6 synthetic legacy lines
REPL = ["20255503%02d" % i for i in range(1, 8)]             # 7 synthetic replacements


def _jacksonville():
    rows = [zrow("RH Jacksonville", n, "Elevator") for n in LEGACY]   # still "Active"
    rows += [zrow("RH Jacksonville", n, "Voice %d" % (i + 1)) for i, n in enumerate(REPL)]
    decs = [
        decision(V.D_CARRIER_MIGRATION,
                 {"building": "RH Jacksonville", "legacy_numbers": LEGACY,
                  "replacement_numbers": REPL},
                 {"legacy_carrier": "Legacy MVNO", "replacement_carrier": "New Carrier"},
                 eff="2026-06-01"),
        decision(V.D_SERVICE_CLASSIFICATION, {"building": "RH Jacksonville", "number": REPL[0]},
                 {"service_type": "ELEVATOR", "label": "Elevator 1"}),
        decision(V.D_SERVICE_CLASSIFICATION, {"building": "RH Jacksonville", "number": REPL[1]},
                 {"service_type": "ELEVATOR", "label": "Elevator 2"}),
    ]
    return engine.project(snap(zoho_rows=rows, decisions=decs))


def test_jacksonville_legacy_lines_are_never_current():
    res = _jacksonville()
    for n in LEGACY:
        a = asset(res, V.TELEPHONE_NUMBER, n)
        assert (a["lifecycle"], a["lifecycle_reason"]) == (V.DECOMMISSIONED, V.REASON_CARRIER_MIGRATION)
        assert a["building_id"] == 5 and a["carrier"] == "Legacy MVNO"
        assert not svc(res, "ELEV:tel:%s" % n)["counts"]      # historical, still queryable


def test_jacksonville_seven_replacements_are_current_inventory():
    res = _jacksonville()
    for n in REPL:
        a = asset(res, V.TELEPHONE_NUMBER, n)
        assert a["lifecycle"] == V.CURRENT and a["building_id"] == 5
    b = next(b for b in res["building_summaries"] if b["building_id"] == 5)
    assert b["current_assets"][V.TELEPHONE_NUMBER] == 7
    assert b["historical_assets"] == 6


def test_jacksonville_only_two_elevators_and_voice_lines_are_not_emergency_phones():
    res = _jacksonville()
    counted = [s for s in res["services"] if s["building_id"] == 5 and s["counts"]]
    assert sorted(s["display_name"] for s in counted) == ["Elevator 1", "Elevator 2"]
    assert all(s["service_type"] == V.ELEVATOR for s in counted)
    assert len(conns(res, 5)) == 2
    assert not [s for s in res["services"] if s["service_type"] == V.EMERGENCY_PHONE]
    uncl = [s for s in res["services"] if s["building_id"] == 5 and s["service_type"] == V.UNCLASSIFIED]
    assert len(uncl) == 5 and not any(s["counts"] for s in uncl)
    assert res["lifecycle_events"][0]["event_type"] == V.REASON_CARRIER_MIGRATION


# ── Memphis strict reconciliation ────────────────────────────────────

def _memphis():
    maps = _memphis_alias() + [
        {"id": 60, "building_id": 2, "kind": "true911_device", "value": "S-HOU"},
        {"id": 61, "building_id": 2, "kind": "true911_device", "value": "S-TOR"},
        {"id": 62, "building_id": 2, "kind": "phone", "value": "2025550405"},
        {"id": 63, "building_id": 2, "kind": "phone", "value": "2025550409"},
    ]
    aliases = [{"building_id": 2, "alias": "RH West Palm"}]       # historical merge alias
    rows = [
        zrow("RH Memphis", "2025550400", "Elevator", parent=MEMPHIS_PARENT),     # genuine
        zrow("RH Cleveland", "2025550401", "Elevator", parent=MEMPHIS_PARENT),
        zrow("RH MDC", "2025550402", "Elevator", parent=MEMPHIS_PARENT),
        zrow("RH Austin #149", "2025550403", "Elevator", parent=MEMPHIS_PARENT),
        zrow("RH Long Beach", "2025550404", "Elevator", parent=MEMPHIS_PARENT),
        zrow("Linden House", "2025550405", "Elevator", parent=MEMPHIS_PARENT),
        zrow("RH West Palm", "2025550407", "Elevator", parent=MEMPHIS_PARENT),
        zrow("RH Cleveland", "2025550409", "Elevator"),     # registry maps it to Memphis
    ]
    sites = [site("S-HOU", "RH Houston #130"), site("S-TOR", "RH Toronto")]
    devs = [device("HOU1", "S-HOU", msisdn="2025550406"), device("TOR1", "S-TOR", msisdn="2025550408")]
    lines = [{"line_id": "LH", "device_id": "HOU1", "did": "2025550406", "status": "active",
              "line_type": "Elevator", "description": None, "notes": None},
             {"line_id": "LT", "device_id": "TOR1", "did": "2025550408", "status": "active",
              "line_type": "Elevator", "description": None, "notes": None}]
    decs = [decision(V.D_BUILDING_IDENTITY_SUSPECT, {"building": "RH Memphis"}, {"suspect": True})]
    return engine.project(snap(mappings=maps, aliases=aliases, zoho_rows=rows, sites=sites,
                               devices=devs, lines=lines, decisions=decs))


CONTAMINATED = {"2025550401": 3, "2025550402": None, "2025550403": 8, "2025550404": 9,
                "2025550405": None, "2025550406": 4, "2025550407": 10, "2025550408": None,
                "2025550409": 3}


@pytest.mark.parametrize("number,expected", sorted(CONTAMINATED.items()))
def test_memphis_contaminated_records_cannot_remain_in_memphis(number, expected):
    res = _memphis()
    a = asset(res, V.TELEPHONE_NUMBER, number)
    assert a["building_id"] != 2
    assert a["building_id"] == expected
    assert not [s for s in res["services"] if s["building_id"] == 2
                and s["service_key"].endswith(number)]


def test_memphis_genuine_record_is_confirmed_and_report_lists_imports():
    res = _memphis()
    assert asset(res, V.TELEPHONE_NUMBER, "2025550400")["building_id"] == 2
    assert svc(res, "ELEV:tel:2025550400")["counts"]
    rep = res["suspect_reports"][0]
    assert rep["name"] == "RH Memphis"
    assert rep["confirmed_services"] == ["ELEV:tel:2025550400"]
    imported = {e["record"] for e in rep["suspect_imports"]}
    unmatched = {e["record"] for e in rep["unmatched_or_ambiguous"]}
    assert "device:HOU1" in imported
    houston = next(e for e in rep["suspect_imports"] if e["record"] == "device:HOU1")
    assert houston["placed_to"] == "RH Houston"
    assert "device:TOR1" in unmatched
    assert all("2025550400" not in e["numbers"] for e in rep["suspect_imports"])


def test_memphis_report_is_rendered_by_the_dry_run_report():
    from app.services.canonical import report
    text = report.render(_memphis())
    assert "RH MEMPHIS RECONCILIATION" in text
    assert "nothing was written" in text


# ── operator decision validation ─────────────────────────────────────

@pytest.mark.parametrize("entry,msg", [
    ({"type": "NOPE", "subject": {}, "new_state": {}, "reason": "x"}, "unknown decision type"),
    ({"type": "BUILDING_IDENTITY_SUSPECT", "subject": {"building": "RH Memphis"},
      "new_state": {"suspect": True}}, "reason is required"),
    ({"type": "BUILDING_IDENTITY_SUSPECT", "subject": {"building": "Nowhere"},
      "new_state": {}, "reason": "x"}, "matched 0 buildings"),
    ({"type": "SERVICE_CLASSIFICATION", "subject": {"building": "RH Chicago", "number": "12"},
      "new_state": {"service_type": "ELEVATOR"}, "reason": "x"}, "not a telephone number"),
    ({"type": "SERVICE_CLASSIFICATION", "subject": {"building": "RH Chicago",
                                                    "number": "2025550101"},
      "new_state": {"service_type": "FACP"}, "reason": "x"}, "service_type"),
    ({"type": "CARRIER_MIGRATION", "subject": {"building": "RH Jacksonville",
                                               "legacy_numbers": ["2025550101"],
                                               "replacement_numbers": ["2025550101"]},
      "new_state": {}, "reason": "x"}, "both legacy and replacement"),
])
def test_invalid_decisions_are_rejected(entry, msg):
    with pytest.raises(D.DecisionError, match=msg):
        D.normalize_entry(entry, BUILDINGS)


def test_duplicate_decisions_in_one_file_are_rejected():
    e = {"type": "BUILDING_IDENTITY_SUSPECT", "subject": {"building": "RH Memphis"},
         "new_state": {"suspect": True}, "reason": "x"}
    out, errors = D.normalize_all([e, dict(e)], BUILDINGS)
    assert len(out) == 1 and "duplicates" in errors[0]


def test_decision_keys_are_deterministic():
    a = decision(V.D_SERVICE_CLASSIFICATION, {"building": "RH Chicago", "number": "(202) 555-0101"},
                 {"service_type": "ELEVATOR"})
    b = decision(V.D_SERVICE_CLASSIFICATION, {"building_id": 1, "number": "2025550101"},
                 {"service_type": "EMERGENCY_PHONE"})
    assert a["decision_key"] == b["decision_key"]
    merged = D.overlay([a], [b])
    assert merged == [b]
