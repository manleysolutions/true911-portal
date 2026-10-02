"""Canonical engine - governed operator decisions as their own evidence class.

An operator decision may establish canonical truth even where Zoho is stale or
contradictory; it is kept as OPERATOR provenance, never rewritten as source
evidence, and it never edits a source system.  The engine stays generic: these
tests use SYNTHETIC identifiers in the SHAPES of the 2026-10-02 RH decisions
(Princeton 1 FACP / 2 radios, Leawood 2 FACPs, San Rafael move, Raleigh /
Edina placement, Boston wrong-building record, placeholder account,
Jacksonville emergency-phone / fax pool).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.canonical import decisions as D
from app.services.canonical import engine, report
from app.services.canonical import vocab as V
from tests.test_canonical_engine import (
    BUILDINGS,
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
OLD = NOW - timedelta(days=2000)                       # last signal years ago
R1, R2, R_STALE = "77110020", "7756099", "7710020"      # R_STALE: pre-correction value
SERIAL = "209904030000068"


def z(facility, ctype=None, *, msisdn=None, starlink=None, status="Activated", zid=None):
    r = zrow(facility, msisdn, ctype, status=status, starlink=starlink)
    if zid:
        r["zoho_id"] = zid
    return r


def facp_service(building, ref, *radios, label=None):
    return decision(V.D_FACP_SERVICE, {"building": building, "service_ref": ref},
                    {"radios": list(radios), "label": label})


def record(rid, disposition, building=None, source="ZOHO", duplicate_of=None):
    ns = {"disposition": disposition, "duplicate_of": duplicate_of}
    if building:
        ns["building"] = building
    return decision(V.D_SOURCE_RECORD, {"source": source, "record_id": rid}, ns)


def lifecycle(value, lc, atype="NAPCO_RADIO"):
    return decision(V.D_ASSET_LIFECYCLE, {"asset_type": atype, "value": value},
                    {"lifecycle": lc})


def classify(building, number, st, label=None):
    return decision(V.D_SERVICE_CLASSIFICATION, {"building": building, "number": number},
                    {"service_type": st, "label": label})


def facps(res, bid):
    return [s for s in res["services"] if s["building_id"] == bid and s["service_type"] == V.FACP]


def codes(res, code):
    return [f for f in res["findings"] if f["code"] == code]


# ── 1. one FACP service, two communications assets ────────────────────

def _princeton_shape(decs, **kw):
    rows = [z("RH Princeton", "Alarm Panel", starlink=R1),
            z("RH Princeton", None, starlink=R2),                       # no fire label
            z(None, "Alarm Panel", starlink=R_STALE, zid="STALE1")]     # duplicate, no location
    return engine.project(snap(zoho_rows=rows, decisions=decs, napco_radios=[R1, R2], **kw))


def test_1_one_facp_with_two_radios_is_one_service_with_two_assets():
    res = _princeton_shape([facp_service("RH Princeton", "FACP 1", R1, R2),
                            record("STALE1", "DUPLICATE", duplicate_of="R1 record")])
    (s,) = facps(res, 7)
    assert s["service_key"] == "FACP:radio:%s+%s" % tuple(sorted([R1, R2]))
    radios = [k for k, rel in s["assets"] if k.startswith("NAPCO_RADIO:")]
    assert sorted(radios) == sorted(["NAPCO_RADIO:" + R1, "NAPCO_RADIO:" + R2])
    assert s["confidence"] == V.CONFIRMED and V.SRC_OPERATOR in s["provenance"]["sources"]
    assert [e["record"] for e in res["excluded_records"]] == ["zoho:STALE1"]


def test_1b_the_two_radio_service_needs_two_connections_not_four():
    decs = [facp_service("RH Princeton", "FACP 1", R1, R2), record("STALE1", "DUPLICATE"),
            lifecycle(R1, "CURRENT"), lifecycle(R2, "CURRENT")]
    res = _princeton_shape(decs)
    (s,) = facps(res, 7)
    assert s["counts"] and len(conns(res, 7)) == 2


def test_1c_without_the_decision_the_stale_record_and_second_radio_are_not_counted():
    res = _princeton_shape([])
    assert not [s for s in facps(res, 7) if s["counts"]]


# ── 2. two FACP services at one building stay two ─────────────────────

def test_2_two_operator_facp_services_at_one_building_remain_two():
    rows = [z("RH Austin #149", None, starlink="77046892"),
            z("RH Austin #149", None, starlink="77051540")]
    decs = [facp_service("RH Austin", "FACP 1", "77046892"),
            facp_service("RH Austin", "FACP 2", "77051540")]
    res = engine.project(snap(zoho_rows=rows, decisions=decs))
    f = facps(res, 8)
    assert sorted(s["service_key"] for s in f) == ["FACP:radio:77046892", "FACP:radio:77051540"]
    assert all(s["confidence"] == V.CONFIRMED for s in f)   # operator truth, no fire label needed


def test_2b_a_radio_claimed_by_two_operator_services_is_a_conflict():
    decs = [facp_service("RH Austin", "FACP 1", "77046892"),
            facp_service("RH Austin", "FACP 2", "77046892")]
    res = engine.project(snap(zoho_rows=[z("RH Austin #149", None, starlink="77046892")],
                              decisions=decs))
    assert codes(res, "DECISION_CONFLICT")
    assert not [s for s in facps(res, 8) if s["confidence"] == V.CONFIRMED]


# ── 3. a device serial can never become a radio / FACP ────────────────

def test_3_serial_cannot_become_a_radio_even_through_an_operator_decision():
    with pytest.raises(D.DecisionError, match="not a radio id"):
        D.normalize_entry({"type": "FACP_SERVICE",
                           "subject": {"building": "RH Jacksonville", "service_ref": "FACP 1"},
                           "new_state": {"radios": [SERIAL]}, "reason": "x"}, BUILDINGS)
    res = engine.project(snap(zoho_rows=[z("RH Jacksonville", "Elevator", msisdn="2025550171",
                                           starlink=SERIAL)],
                              mappings=pin(5, SERIAL)))
    assert facps(res, 5) == []


# ── 4. a move: historical placement, one current location ─────────────

def test_4_moved_radio_stays_historical_and_only_the_new_one_is_current():
    rows = [z("RH Long Beach", "Alarm Panel", starlink="7741483"),   # old address record
            z("RH Long Beach", "Alarm Panel", starlink="7872590")]   # current address record
    decs = [lifecycle("7741483", "HISTORICAL"), lifecycle("7872590", "CURRENT"),
            facp_service("RH Long Beach", "FACP 1", "7872590")]
    res = engine.project(snap(zoho_rows=rows, decisions=decs))
    by = {s["service_key"]: s for s in facps(res, 9)}
    assert by["FACP:radio:7872590"]["counts"]
    old = by["FACP:radio:7741483"]
    assert old["lifecycle"] == V.HISTORICAL and not old["counts"]
    assert res["assets"]["NAPCO_RADIO:7741483"]["building_id"] == 9    # history kept in place
    assert len([s for s in facps(res, 9) if s["counts"]]) == 1          # one current FACP


# ── 5. operator placement survives stale activity ─────────────────────

def test_5_operator_placement_and_current_survive_stale_activity():
    decs = [classify("RH Chicago", "2025550180", "ELEVATOR"),
            lifecycle("2025550180", "CURRENT", atype="TELEPHONE_NUMBER")]
    res = engine.project(snap(zoho_rows=[z("RH Austin #149", "Elevator", msisdn="2025550180")],
                              decisions=decs, source_activity=live("2025550180", at=OLD)))
    a = res["assets"]["TELEPHONE_NUMBER:2025550180"]
    assert (a["building_id"], a["placement_basis"]) == (1, V.P_OPERATOR)   # wrong source text
    assert a["deployment"] == V.DEPLOYED and svc(res, "ELEV:tel:2025550180")["counts"]


def test_5b_operator_placement_without_recent_activity_establishes_location_not_current():
    # Raleigh shape: radios placed by the operator, no signal for years
    rows = [z("RH Austin #149", "Alarm Panel", starlink="7771872"),
            z("RH Cleveland", "Alarm Panel", starlink="7783291")]          # source says elsewhere
    res = engine.project(snap(zoho_rows=rows,
                              decisions=[facp_service("RH Austin", "FACP 1", "7771872", "7783291")],
                              source_activity=live("7771872", "7783291", at=OLD)))
    (s,) = facps(res, 8)
    assert (s["confidence"], s["lifecycle"], s["counts"]) == (V.CONFIRMED, V.UNKNOWN, False)
    assert res["assets"]["NAPCO_RADIO:7783291"]["building_id"] == 8
    assert facps(res, 3) == []          # the "elsewhere" building gets no service from it


# ── 6. placeholder evidence creates no service ────────────────────────

def test_6_placeholder_record_creates_no_current_service():
    rows = [z("Restoration Hardware Main Account", "Elevator", msisdn="2025550186", zid="PH1")]
    res = engine.project(snap(zoho_rows=rows, decisions=[record("PH1", "PLACEHOLDER")],
                              source_activity=live("2025550186")))
    assert [s for s in res["services"] if s["service_key"].endswith("2025550186")] == []
    assert "TELEPHONE_NUMBER:2025550186" not in res["assets"]
    assert res["excluded_records"][0]["disposition"] == V.REC_PLACEHOLDER
    assert not codes(res, "UNPLACED_ASSET")                 # no noise from a known placeholder


def test_6b_a_placeholder_disposition_is_per_record_not_per_number():
    # independent evidence of the same number (an exact registry mapping) still stands
    rows = [z("Restoration Hardware Main Account", "Elevator", msisdn="2025550186", zid="PH1")]
    res = engine.project(snap(zoho_rows=rows, decisions=[record("PH1", "PLACEHOLDER")],
                              mappings=pin(1, "2025550186")))
    assert res["assets"]["TELEPHONE_NUMBER:2025550186"]["records"][0]["source"] == V.SRC_REGISTRY


# ── 7. wrong-building source association cannot beat the operator ─────

def test_7_operator_record_placement_overrides_a_wrong_building_association():
    rows = [z("RH Houston #130", "Alarm Panel", starlink="7780014", zid="WB1")]
    dev = device("H1", "S-H", device_type="Fire Alarm Control Panel", starlink_id="7780014",
                 manufacturer="Napco")
    res = engine.project(snap(zoho_rows=rows, devices=[dev], sites=[site("S-H", "RH Houston #130")],
                              decisions=[record("WB1", "BUILDING", building="RH Cleveland")]))
    assert res["assets"]["NAPCO_RADIO:7780014"]["building_id"] == 3
    assert res["assets"]["NAPCO_RADIO:7780014"]["placement_basis"] == V.P_OPERATOR
    assert facps(res, 4) == []
    assert [s["building_id"] for s in res["services"] if s["service_type"] == V.FACP] == [3]


def test_7c_a_record_of_a_location_outside_the_portfolio_leaves_every_approved_building():
    rows = [z("RH Houston #130", "Alarm Panel", starlink="7780014", zid="OUT1")]
    out = decision(V.D_SOURCE_RECORD, {"source": "ZOHO", "record_id": "OUT1"},
                   {"disposition": "OUTSIDE_PORTFOLIO", "location": "store 142"})
    res = engine.project(snap(zoho_rows=rows, decisions=[out]))
    assert [s for s in res["services"] if s["service_type"] == V.FACP] == []
    (e,) = res["excluded_records"]
    assert (e["disposition"], e["location"]) == (V.REC_OUTSIDE, "store 142")
    with pytest.raises(D.DecisionError, match="location is required"):
        D.normalize_entry({"type": "SOURCE_RECORD", "subject": {"source": "ZOHO", "record_id": "x"},
                           "new_state": {"disposition": "OUTSIDE_PORTFOLIO"}, "reason": "x"},
                          BUILDINGS)


def test_7b_two_candidate_radio_ids_are_never_merged():
    rows = [z("RH Cleveland", "Alarm Panel", starlink="7780014")]
    res = engine.project(snap(zoho_rows=rows, napco_radios=["77474449"]))
    assert [s["service_key"] for s in facps(res, 3)] == ["FACP:radio:7780014"]
    assert "NAPCO_RADIO:77474449" not in res["assets"]


# ── 8. aggregate knowledge never fabricates per-line classification ───

POOL = ["2025550633", "2025551550", "2025552688", "2025552768", "2025557030"]


def _pool(decs_extra=(), label="Voice"):
    rows = [z("RH Jacksonville", "%s %d" % (label, i + 1), msisdn=n) for i, n in enumerate(POOL)]
    decs = [decision(V.D_SERVICE_POOL, {"building": "RH Jacksonville", "pool_ref": "lines"},
                     {"numbers": POOL, "service_types": ["EMERGENCY_PHONE", "OTHER"],
                      "label": "emergency phone / fax"})] + list(decs_extra)
    decs += [lifecycle(n, "CURRENT", atype="TELEPHONE_NUMBER") for n in POOL]
    return engine.project(snap(zoho_rows=rows, decisions=decs))


def test_8_pool_does_not_make_each_line_an_emergency_phone():
    res = _pool()
    assert not [s for s in res["services"] if s["service_type"] == V.EMERGENCY_PHONE]
    assert all(res["assets"]["TELEPHONE_NUMBER:" + n]["building_id"] == 5 for n in POOL)
    assert all(res["assets"]["TELEPHONE_NUMBER:" + n]["classification"] == V.UNCLASSIFIED
               for n in POOL)
    assert not [s for s in res["services"] if s["counts"]]
    assert codes(res, "SERVICE_POOL_UNASSIGNED")[0]["detail"].startswith("5 of 5")


def test_8b_source_labels_inside_a_pool_are_capped_at_probable():
    res = _pool(label="Emergency Phone")                # Zoho says EPH on every line
    eph = [s for s in res["services"] if s["service_type"] == V.EMERGENCY_PHONE]
    assert len(eph) == 5 and all(s["confidence"] == V.PROBABLE and not s["counts"] for s in eph)


def test_8c_an_explicit_per_line_decision_inside_a_pool_holds():
    res = _pool([classify("RH Jacksonville", POOL[0], "EMERGENCY_PHONE")])
    assert svc(res, "EPH:tel:%s" % POOL[0])["counts"]
    assert len([s for s in res["services"] if s["counts"]]) == 1


# ── carrier migration + duplicate source records (Jacksonville shape) ──

def test_carrier_migration_with_duplicate_legacy_record_makes_one_historical_service():
    legacy = ["2025550389", "2025550390"]
    rows = [z("RH Jacksonville", "Elevator", msisdn=legacy[0]),
            z("RH Jacksonville", "Elevator", msisdn=legacy[0]),           # duplicate record
            z("RH Jacksonville", "Elevator", msisdn=legacy[1]),
            z("RH Jacksonville", "Voice 1", msisdn="2025550616"),
            z("RH Jacksonville", "Voice 2", msisdn="2025550656")]
    decs = [decision(V.D_CARRIER_MIGRATION,
                     {"building": "RH Jacksonville", "legacy_numbers": legacy,
                      "replacement_numbers": ["2025550616", "2025550656"]},
                     {"legacy_carrier": "Old", "replacement_carrier": "New"}, eff="2026-09-22"),
            classify("RH Jacksonville", "2025550616", "ELEVATOR"),
            classify("RH Jacksonville", "2025550656", "ELEVATOR")]
    res = engine.project(snap(zoho_rows=rows, decisions=decs))
    old = [s for s in res["services"] if s["service_key"] == "ELEV:tel:%s" % legacy[0]]
    assert len(old) == 1 and old[0]["lifecycle"] == V.DECOMMISSIONED
    assert len([s for s in res["services"] if s["counts"]]) == 2


def test_operator_classification_overrides_a_misleading_source_label():
    # Houston shape: a telephone line labelled "Alarm Panel" that is an elevator
    res = engine.project(snap(zoho_rows=[z("RH Houston #130", "Alarm Panel", msisdn="2025550164")],
                              decisions=[classify("RH Houston", "2025550164", "ELEVATOR")]))
    assert res["assets"]["TELEPHONE_NUMBER:2025550164"]["classification"] == V.ELEVATOR
    assert facps(res, 4) == []


def test_operator_facp_is_not_capped_by_napco_silence_but_the_gap_is_reported():
    res = engine.project(snap(zoho_rows=[z("RH Austin #149", None, starlink="77046892")],
                              decisions=[facp_service("RH Austin", "FACP 1", "77046892")],
                              napco_radios=[R1]))
    (s,) = facps(res, 8)
    assert s["confidence"] == V.CONFIRMED and s["provenance"]["napco_evidence"] == "ABSENT"
    assert codes(res, "RADIO_NOT_IN_NAPCO")


def test_operator_radio_no_source_reports_still_gets_an_asset_with_operator_provenance():
    res = engine.project(snap(decisions=[facp_service("RH Austin", "FACP 1", "77046892")]))
    (s,) = facps(res, 8)
    assert s["provenance"]["sources"] == [V.SRC_OPERATOR]
    assert codes(res, "OPERATOR_ASSET_WITHOUT_SOURCE")


def test_report_lists_excluded_records_and_pools():
    text = report.render(_pool())
    assert "OPERATOR SERVICE POOLS" in text and "EXCLUDED SOURCE RECORDS" in text


# ── decision validation ───────────────────────────────────────────────

@pytest.mark.parametrize("entry,msg", [
    ({"type": "FACP_SERVICE", "subject": {"building": "RH Austin"},
      "new_state": {"radios": [R1]}, "reason": "x"}, "service_ref"),
    ({"type": "FACP_SERVICE", "subject": {"building": "RH Austin", "service_ref": "F"},
      "new_state": {"radios": [R1, R1]}, "reason": "x"}, "duplicates"),
    ({"type": "SOURCE_RECORD", "subject": {"source": "NAPCO", "record_id": "1"},
      "new_state": {"disposition": "DUPLICATE"}, "reason": "x"}, "ZOHO or TRUE911"),
    ({"type": "SOURCE_RECORD", "subject": {"source": "ZOHO", "record_id": "1"},
      "new_state": {"disposition": "BUILDING", "building": "Nowhere"}, "reason": "x"}, "matched 0"),
    ({"type": "SERVICE_POOL", "subject": {"building": "RH Austin", "pool_ref": "p"},
      "new_state": {"numbers": ["2025550101"], "service_types": ["FACP"]}, "reason": "x"},
     "subset"),
])
def test_new_decision_types_are_validated(entry, msg):
    with pytest.raises(D.DecisionError, match=msg):
        D.normalize_entry(entry, BUILDINGS)


def test_changing_an_operator_radio_set_supersedes_rather_than_adding_a_service():
    a = facp_service("RH Austin", "FACP 1", R1)
    b = facp_service("RH Austin", "FACP 1", R1, R2)
    assert a["decision_key"] == b["decision_key"] and a["new_state"] != b["new_state"]
