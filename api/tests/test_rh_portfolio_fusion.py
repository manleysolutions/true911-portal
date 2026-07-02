"""True911 Portfolio Fusion Engine — adapters, cross-source device matching, twins.

Pure-function tests (no DB, no vendor APIs): the four source adapters, entity
resolution into buildings, cross-source device matching (radio# / IMEI / ICCID /
MSISDN / store# / address), Building Digital Twin synthesis, source confidence,
missing/duplicate assets, and the CSV/JSON/MD + executive-dashboard outputs.
Read-only throughout — nothing is written to any source.
"""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import pytest

from scripts import rh_portfolio_fusion as fz


# ── adapters ─────────────────────────────────────────────────────────
def _zrow(**kw):
    base = dict(account_name="Restoration Hardware #177 Jacksonville", facility_name=None,
                street="10300 Southside Blvd", city="Jacksonville", state="FL", zip="32256",
                connection_type="Alarm Panel", imei=None, sim="8901260882237499857",
                msisdn=None, starlink_id="9743676")
    base.update(kw)
    return base


def test_adapt_zoho_builds_building_and_device():
    recs = fz.adapt_zoho([_zrow()])
    assert len(recs) == 1
    r = recs[0]
    assert r["source"] == "zoho" and r["store_number"] == "177" and r["state"] == "FL"
    assert r["service_types"] == ["alarm"]
    d = r["devices"][0]
    assert d["kind"] == "napco_radio" and d["iccid"] == "8901260882237499857"
    assert d["starlink_id"] == "9743676"


def test_adapt_napco_from_vendor_record():
    vr = SimpleNamespace(vendor="napco", radio_number="9743676", iccid="8901260882237499857",
                         subscriber_name="Restoration Hardware #177 Jacksonville",
                         site_hint="Restoration Hardware #177 Jacksonville")
    r = fz.adapt_napco([vr])[0]
    assert r["source"] == "napco" and r["store_number"] == "177"
    d = r["devices"][0]
    assert d["kind"] == "napco_radio" and d["radio_number"] == "9743676"
    assert d["service_type"] == "alarm"


def test_adapt_napco_recognizes_known_special():
    vr = SimpleNamespace(vendor="napco", radio_number="R1", iccid="I1",
                         subscriber_name="Restoration Hardware - MDC", site_hint=None)
    r = fz.adapt_napco([vr])[0]
    assert r["site_type"] == "distribution_center"       # known-alias typing flows into napco


def test_load_genesis_csv_tolerant_columns(tmp_path):
    p = tmp_path / "genesis.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Phone Number", "SIM ICCID", "IMEI", "Device Model", "Site Name"])
        w.writerow(["614-209-8841", "8901260882237499857", "868105041862416", "MS130v4", "RH MDC"])
    rows = fz.load_genesis_csv(str(p))
    assert rows[0]["msisdn"] == "6142098841" or rows[0]["msisdn"] == "614-209-8841"
    assert rows[0]["iccid"] == "8901260882237499857" and rows[0]["imei"] == "868105041862416"
    recs = fz.adapt_genesis(rows)
    assert recs[0]["source"] == "genesis" and recs[0]["devices"][0]["kind"] == "ms130"


def test_adapt_genesis_skips_rows_without_identifiers():
    assert fz.adapt_genesis([{"iccid": None, "msisdn": None, "imei": None, "name": "x"}]) == []


def test_adapt_true911_devices_lines_units():
    t = {"tenant": "rh",
         "sites": [{"site_id": "RH-1", "name": "RH #1 Tracy", "street": "1 A St", "city": "Tracy",
                    "state": "CA", "zip": "95376", "e911_status": "validated"}],
         "devices": [{"device_id": "D1", "site_id": "RH-1", "model": "SLE", "device_type": "fire_alarm",
                      "imei": None, "iccid": "IC1", "msisdn": None, "starlink_id": "RAD1",
                      "serial_number": "RAD1", "identifier_type": "starlink"}],
         "units": [{"unit_id": "U1", "site_id": "RH-1", "unit_type": "fire_alarm",
                    "device_id": "D1", "line_id": None}],
         "lines": [{"line_id": "L1", "site_id": "RH-1", "did": "2095551234", "sim_iccid": None}]}
    r = fz.adapt_true911(t)[0]
    assert r["source"] == "true911" and r["store_number"] == "1" and r["site_id"] == "RH-1"
    assert r["e911_status"] == "validated" and "fire_alarm" in r["service_types"]
    kinds = {d["kind"] for d in r["devices"]}
    assert "napco_radio" in kinds and "line" in kinds     # device + DID line


# ── cross-source device matching / fusion ────────────────────────────
def _t911(**kw):
    base = {"tenant": "rh",
            "sites": [{"site_id": "RH-177", "name": "Restoration Hardware #177 Jacksonville",
                       "street": "10300 Southside Blvd", "city": "Jacksonville", "state": "FL",
                       "zip": "32256", "e911_status": "validated"}],
            "devices": [{"device_id": "D1", "site_id": "RH-177", "model": "SLE",
                         "device_type": "fire_alarm", "imei": None, "iccid": "8901260882237499857",
                         "msisdn": None, "starlink_id": "9743676", "serial_number": "9743676",
                         "identifier_type": "starlink"}],
            "units": [{"unit_id": "U1", "site_id": "RH-177", "unit_type": "fire_alarm",
                       "device_id": "D1", "line_id": None}],
            "lines": []}
    base.update(kw)
    return base


def test_fusion_joins_by_iccid_and_store_number():
    zoho = [_zrow()]
    napco = [SimpleNamespace(vendor="napco", radio_number="9743676", iccid="8901260882237499857",
                             subscriber_name="Restoration Hardware #177 Jacksonville", site_hint=None)]
    rep = fz.fuse_portfolio(zoho_rows=zoho, napco_records=napco, true911=_t911(), tenant="rh")
    assert rep["summary"]["buildings"] == 1                # all three collapse to one building
    t = rep["buildings"][0]
    assert set(t["sources"]) == {"zoho", "napco", "true911"}
    assert len(t["devices"]) == 1                          # 3 device rows merged by shared ICCID
    assert t["devices"][0]["in_true911"] is True


def test_fusion_joins_by_msisdn_across_genesis_and_true911():
    t911 = _t911(devices=[{"device_id": "D9", "site_id": "RH-177", "model": "MS130v4",
                           "device_type": "cellular", "imei": None, "iccid": None,
                           "msisdn": "6142098841", "starlink_id": None, "serial_number": None,
                           "identifier_type": "cellular"}])
    genesis = [{"iccid": None, "msisdn": "614-209-8841", "imei": None, "model": "MS130v4",
                "name": None, "street": None, "city": None, "state": None, "zip": None}]
    rep = fz.fuse_portfolio(genesis_rows=genesis, true911=t911, tenant="rh")
    assert rep["summary"]["buildings"] == 1                # matched on the phone number
    assert rep["buildings"][0]["devices"][0]["in_true911"] is True


def test_fusion_separate_buildings_when_no_shared_key():
    zoho = [_zrow(account_name="Restoration Hardware #140 Houston", street="1 Tex St",
                  city="Houston", state="TX", zip="77001", sim="OTHERICCID", starlink_id="OTHERRAD")]
    rep = fz.fuse_portfolio(zoho_rows=zoho, true911=_t911(), tenant="rh")
    assert rep["summary"]["buildings"] == 2                # #140 and #177 stay distinct


# ── twin synthesis: identity, category, confidence ───────────────────
def test_twin_identity_prefers_true911_and_known_registry():
    napco = [SimpleNamespace(vendor="napco", radio_number="R1", iccid="ICMDC",
                             subscriber_name="Restoration Hardware - MDC", site_hint=None)]
    genesis = [{"iccid": "ICMDC", "msisdn": None, "imei": None, "model": "MS130v4",
                "name": "RH MDC", "street": None, "city": None, "state": None, "zip": None}]
    rep = fz.fuse_portfolio(napco_records=napco, genesis_rows=genesis, tenant="rh")
    t = rep["buildings"][0]
    assert t["canonical_name"] == "RH MDC (Distribution Center)"   # known-registry canonical
    assert t["building_category"] == "Distribution" and t["site_type"] == "distribution_center"


def test_source_confidence_weighted_by_corroboration():
    # all four sources on one building -> capped 100
    zoho = [_zrow()]
    napco = [SimpleNamespace(vendor="napco", radio_number="9743676", iccid="8901260882237499857",
                             subscriber_name="RH #177", site_hint=None)]
    genesis = [{"iccid": "8901260882237499857", "msisdn": None, "imei": None, "model": "MS130v4",
                "name": None, "street": None, "city": None, "state": None, "zip": None}]
    rep = fz.fuse_portfolio(zoho_rows=zoho, napco_records=napco, genesis_rows=genesis,
                            true911=_t911(), tenant="rh")
    t = rep["buildings"][0]
    assert set(t["sources"]) == {"zoho", "napco", "genesis", "true911"}
    assert t["source_confidence"] == 100
    # zoho-only building has low confidence
    z2 = fz.fuse_portfolio(zoho_rows=[_zrow(account_name="RH #900 X", street="9 X", city="Y",
                                            state="TX", zip="70000", sim="ZZ", starlink_id="ZR")],
                           tenant="rh")
    assert z2["buildings"][0]["source_confidence"] == 25


def test_building_category_mapping():
    assert fz.building_category("warehouse") == "Warehouse"
    assert fz.building_category("gallery") == "Retail"
    assert fz.building_category("distribution_center") == "Distribution"
    assert fz.building_category(None) == "Commercial"


# ── missing / duplicate assets ───────────────────────────────────────
def test_missing_true911_and_device_not_in_true911():
    genesis = [{"iccid": "NEWIC", "msisdn": None, "imei": "NEWIMEI", "model": "MS130v4",
                "name": "RH #500 Nowhere", "street": None, "city": None, "state": None, "zip": None}]
    rep = fz.fuse_portfolio(genesis_rows=genesis, true911={"tenant": "rh", "sites": [], "devices": [],
                                                           "units": [], "lines": []}, tenant="rh")
    t = rep["buildings"][0]
    assert any("No True911 site" in m for m in t["missing_assets"])
    assert any("not in True911" in m for m in t["missing_assets"])
    assert rep["summary"]["devices_missing_in_true911"] == 1


def test_missing_service_unit_and_e911_unverified():
    t911 = _t911(units=[], sites=[{"site_id": "RH-177", "name": "Restoration Hardware #177 Jacksonville",
                                   "street": "10300 Southside Blvd", "city": "Jacksonville",
                                   "state": "FL", "zip": "32256", "e911_status": "pending"}])
    rep = fz.fuse_portfolio(zoho_rows=[_zrow()], true911=t911, tenant="rh")
    t = rep["buildings"][0]
    assert any("No service unit" in m for m in t["missing_assets"])
    assert any("E911 not verified" in m for m in t["missing_assets"])
    assert t["e911"]["verified"] is False


def test_duplicate_true911_sites_in_one_building():
    t911 = _t911()
    t911["sites"].append({"site_id": "RH-177b", "name": "Restoration Hardware #177 Jacksonville",
                          "street": "10300 Southside Blvd", "city": "Jacksonville", "state": "FL",
                          "zip": "32256", "e911_status": "validated"})
    rep = fz.fuse_portfolio(zoho_rows=[_zrow()], true911=t911, tenant="rh")
    # both RH-177 sites fuse into one building (same store#/address) -> duplicate flagged
    dups = [d for t in rep["buildings"] for d in t["duplicate_assets"]]
    assert any("Multiple True911 sites" in d for d in dups)
    assert rep["summary"]["buildings_with_duplicates"] >= 1


# ── outputs: CSV / JSON / MD + executive dashboard ───────────────────
def test_outputs_and_dashboard(tmp_path):
    napco = [SimpleNamespace(vendor="napco", radio_number="9743676", iccid="8901260882237499857",
                             subscriber_name="RH #177", site_hint=None)]
    rep = fz.fuse_portfolio(zoho_rows=[_zrow()], napco_records=napco, true911=_t911(), tenant="rh")
    s = rep["summary"]
    # dashboard shape
    assert s["buildings"] == 1 and set(s["source_coverage"]) == set(fz.ALL_SOURCES)
    assert "by_category" in s and "avg_source_confidence" in s

    cpath, jpath, mpath = tmp_path / "c.csv", tmp_path / "r.json", tmp_path / "r.md"
    fz.write_csv(str(cpath), rep)
    fz.write_json(str(jpath), rep)
    fz.write_markdown_report(str(mpath), rep)

    with open(cpath, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and rows[0]["building_id"] == "BLD-0001" and rows[0]["sources"]

    loaded = json.load(open(jpath, encoding="utf-8"))
    assert loaded["summary"]["buildings"] == 1 and loaded["buildings"][0]["devices"]

    md = mpath.read_text(encoding="utf-8")
    assert "Executive dashboard" in md and "Buildings (Digital Twins)" in md
    assert "Missing assets" in md and "Duplicate assets" in md
    assert "never auto-verified" in md                     # read-only / no-fabrication note


def test_norm_id_and_device_join_normalization():
    assert fz._norm_id(" 89-0126:0882 ") == "8901260882"
    # a hyphenated phone in one source and plain in another still join
    genesis = [{"iccid": None, "msisdn": "(614) 209-8841", "imei": None, "model": "MS130v4",
                "name": None, "street": None, "city": None, "state": None, "zip": None}]
    t911 = _t911(devices=[{"device_id": "D9", "site_id": "RH-177", "model": "MS130v4",
                           "device_type": "cellular", "imei": None, "iccid": None,
                           "msisdn": "6142098841", "starlink_id": None, "serial_number": None,
                           "identifier_type": "cellular"}])
    rep = fz.fuse_portfolio(genesis_rows=genesis, true911=t911, tenant="rh")
    assert rep["summary"]["buildings"] == 1


# ── CLI validation + Genesis API guard ───────────────────────────────
def test_cli_requires_a_source(monkeypatch):
    monkeypatch.setattr("sys.argv", ["rh_portfolio_fusion", "--tenant", "rh"])
    with pytest.raises(SystemExit) as e:
        fz.main()
    assert e.value.code == 2                                # argparse usage error


def test_genesis_api_is_read_only_stub():
    with pytest.raises(RuntimeError):
        fz.load_genesis_api()


# ══════════════════════════════════════════════════════════════════════
# Genesis RH filtering — the raw export is the whole Infatrac book
# ══════════════════════════════════════════════════════════════════════
def _rh_context_true911():
    """A True911 RH footprint that supplies store #s, cities, and one RH phone."""
    return {"tenant": "restoration-hardware",
            "sites": [{"site_id": f"RH-{n}", "name": f"Restoration Hardware #{n}", "street": None,
                       "city": c, "state": st, "zip": None, "e911_status": "validated"}
                      for n, c, st in [("150", "Leawood", "KS"), ("149", "Austin", "TX"),
                                       ("140", "Houston", "TX"), ("187", "Cleveland", "OH"),
                                       ("142", "Boston", "MA"), ("437", "New York", "NY"),
                                       ("506", "Toronto", "ON"), ("146", "West Hollywood", "CA"),
                                       ("161", "San Francisco", "CA")]],
            "devices": [{"device_id": "D1", "site_id": "RH-140", "msisdn": "7135550140",
                         "iccid": "ICRH140", "imei": None, "starlink_id": None,
                         "serial_number": None, "identifier_type": "cellular",
                         "model": "MS130v4", "device_type": "cellular"}],
            "units": [], "lines": []}


def _g(name, msisdn="9005550000", iccid=None, imei=None, status="active"):
    return {"name": name, "label": name, "msisdn": msisdn, "iccid": iccid, "imei": imei,
            "status": status, "street": None, "city": None, "state": None, "zip": None}


def test_genesis_rh_label_rows_included():
    ctx = fz._build_rh_context([], [], _rh_context_true911())
    labels = ["Restoration hardware 140 Houston elevator", "RH 150 Leawood KS",
              "RH 437 West 16th Street NYC - Elevator", "RH Hollywood CA - Elevator",
              "RH San Francisco Pier 70", "RH Toronto Canada -506 Elevator 1"]
    incl, excl = fz.genesis_rh_filter([_g(x) for x in labels], ctx)
    assert len(incl) == len(labels) and excl == 0
    assert all(r["_rh_reason"].startswith(("label:", "context:")) for r in incl)


def test_genesis_known_alias_and_store_context():
    ctx = fz._build_rh_context([], [], _rh_context_true911())
    incl, _ = fz.genesis_rh_filter([_g("RH MDC Distribution"), _g("Restoration Hardware Beverly Modern")], ctx)
    reasons = {r["_rh_reason"] for r in incl}
    assert "label:known_alias" in reasons and any(r.startswith("label:") for r in reasons)
    assert incl[0]["_rh_canonical"] == "RH MDC (Distribution Center)"


def test_genesis_non_rh_and_infatrac_rows_excluded():
    ctx = fz._build_rh_context([], [], _rh_context_true911())
    noise = ["Infatrac Test Device", "Overhead Door Company Dallas", "Fairhaven Apartments",
             "Marsh & McLennan", "Sherwin Williams Store 44", "March Networks Camera",
             "Elevator Co of America", "Northrop Grumman"]
    incl, excl = fz.genesis_rh_filter([_g(x, msisdn=f"20255510{i}") for i, x in enumerate(noise)], ctx)
    assert incl == [] and excl == len(noise)


def test_arbitrary_words_containing_rh_excluded():
    ctx = fz._build_rh_context([], [], _rh_context_true911())
    # "rh" only as a substring (overhead, fairhaven, marsh) — never a standalone token
    incl, excl = fz.genesis_rh_filter(
        [_g("Overhead Door"), _g("Fairhaven Center"), _g("Marsh Supermarket")], ctx)
    assert incl == [] and excl == 3


def test_genesis_rh_phone_context_included_without_label():
    ctx = fz._build_rh_context([], [], _rh_context_true911())
    # a non-RH label, but the MSISDN belongs to an RH True911 device -> kept (stage B)
    incl, excl = fz.genesis_rh_filter([_g("Elevator Line 2", msisdn="713-555-0140")], ctx)
    assert len(incl) == 1 and incl[0]["_rh_reason"] == "context:msisdn"


def test_production_style_sample_matches_about_23_not_thousands():
    true911 = _rh_context_true911()
    rh_labels = ["RH Hollywood CA - Elevator", "Restoration hardware 147 Chicago", "RH 150 Leawood KS",
                 "RH 149 Austin Elevator 2", "Restoration hardware 140 Houston elevator",
                 "RH 187 Cleveland - Elevator", "RH 142 Boston - Elevator",
                 "RH 437 West 16th Street NYC - Elevator", "RH Toronto Canada -506 Elevator 1",
                 "Restoration Hardware - Lindern House", "Restoration Hardware 613 Long Beach - Actual",
                 "RH San Francisco Pier 70", "RH MDC Distribution", "Restoration Hardware Beverly Modern",
                 "RH 161 - Elevator", "RH 146 Melrose", "Restoration Hardware #001 Tracy",
                 "RH 117 Tulsa", "RH 178 Raleigh", "RH 174 Charlotte", "RH 632 Vero Beach",
                 "RH 652 Bloomfield", "RH 145 Atlanta"]
    rows = [_g(l, msisdn=f"90055500{i:02d}") for i, l in enumerate(rh_labels)]
    rows += [_g(f"Infatrac Subscriber {i}", msisdn=f"3035552{i:03d}") for i in range(1600)]  # the book
    rep = fz.fuse_portfolio(genesis_rows=rows, true911=true911, tenant="restoration-hardware")
    s = rep["summary"]
    assert s["genesis_rows_total"] == len(rows)
    assert 20 <= s["genesis_rows_rh_matched"] <= 26          # ~23, not 1618
    assert s["genesis_rows_excluded"] == 1600
    # Genesis coverage no longer explodes buildings
    assert s["source_coverage"]["genesis"] <= 26
    assert s["buildings"] < 60                               # not ~1744


def test_report_has_genesis_section_and_fields(tmp_path):
    true911 = _rh_context_true911()
    rows = [_g("RH 150 Leawood KS"), _g("Infatrac Random", msisdn="3035550001")]
    rep = fz.fuse_portfolio(genesis_rows=rows, true911=true911, tenant="restoration-hardware")
    assert rep["summary"]["genesis_rows_rh_matched"] == 1
    assert rep["summary"]["genesis_rows_excluded"] == 1
    assert rep["genesis_included"][0]["label"] == "RH 150 Leawood KS"
    assert rep["genesis_included"][0]["reason"].startswith("label:")

    mpath = tmp_path / "r.md"
    fz.write_markdown_report(str(mpath), rep)
    md = mpath.read_text(encoding="utf-8")
    assert "Genesis RH rows included" in md and "Match reason" in md
    assert "RH matched" in md


# ══════════════════════════════════════════════════════════════════════
# Napco RH filtering + over-splitting fixes
# ══════════════════════════════════════════════════════════════════════
def _napco(radio, iccid, subscriber):
    return SimpleNamespace(vendor="napco", radio_number=radio, iccid=iccid,
                           subscriber_name=subscriber, site_hint=subscriber)


def _rh_true911():
    return {"tenant": "restoration-hardware",
            "sites": [{"site_id": f"RH-{n}", "name": f"Restoration Hardware #{n}", "street": None,
                       "city": c, "state": st, "zip": None, "e911_status": "validated"}
                      for n, c, st in [("177", "Jacksonville", "FL"), ("149", "Austin", "TX"),
                                       ("140", "Houston", "TX")]],
            "devices": [{"device_id": "D1", "site_id": "RH-177", "msisdn": "9045550177",
                         "iccid": "ICRH177", "imei": None, "starlink_id": "RAD177",
                         "serial_number": "RAD177", "identifier_type": "starlink", "model": "SLE",
                         "device_type": "fire_alarm"}],
            "units": [], "lines": []}


def test_napco_non_rh_rows_excluded():
    napco = [_napco("R1", "IC1", "Lincoln Elementary School"),
             _napco("R2", "IC2", "Maple Grove Apartments"),
             _napco("R3", "IC3", "Aritzia Boston"), _napco("R4", "IC4", "Louis Vuitton NYC"),
             _napco("R5", "IC5", "City of Springfield"), _napco("R6", "IC6", "John Q Homeowner")]
    ctx = fz._build_rh_context([], [], _rh_true911())
    incl, excl = fz.napco_rh_filter(napco, ctx)
    assert incl == [] and excl == 6


def test_napco_rh_rows_included():
    napco = [_napco("R1", "IC1", "Restoration Hardware #177 Jacksonville"),
             _napco("R2", "IC2", "RH 149 Austin - Elevator"),
             _napco("R3", "IC3", "Restoration Hardware - MDC")]
    ctx = fz._build_rh_context([], [], _rh_true911())
    incl, excl = fz.napco_rh_filter(napco, ctx)
    assert len(incl) == 3 and excl == 0
    assert incl[2]["canonical"] == "RH MDC (Distribution Center)"


def test_napco_rh_row_included_by_radio_context():
    # subscriber label is not RH, but the radio is a known RH True911 device
    napco = [_napco("RAD177", None, "Some Alarm Account")]
    ctx = fz._build_rh_context([], [], _rh_true911())
    incl, excl = fz.napco_rh_filter(napco, ctx)
    assert len(incl) == 1 and incl[0]["reason"] == "context:radio"


def test_two_napco_radios_same_location_one_building_two_devices():
    napco = [_napco("R1", "IC1", "Restoration Hardware #177 Jacksonville"),
             _napco("R2", "IC2", "Restoration Hardware #177 Jacksonville")]
    rep = fz.fuse_portfolio(napco_records=napco,
                            true911={"tenant": "rh", "sites": [], "devices": [], "units": [], "lines": []},
                            tenant="rh")
    assert rep["summary"]["buildings"] == 1
    assert len(rep["buildings"][0]["devices"]) == 2


def test_two_napco_radios_same_known_alias_one_building():
    napco = [_napco("R1", "IC1", "Restoration Hardware - MDC"),
             _napco("R2", "IC2", "Restoration Hardware - MDC")]     # no store #, joins on alias
    rep = fz.fuse_portfolio(napco_records=napco,
                            true911={"tenant": "rh", "sites": [], "devices": [], "units": [], "lines": []},
                            tenant="rh")
    assert rep["summary"]["buildings"] == 1 and len(rep["buildings"][0]["devices"]) == 2


def test_two_genesis_lines_same_store_one_building_two_devices():
    genesis = [{"name": "RH 149 Austin Elevator 1", "label": "RH 149 Austin Elevator 1",
                "msisdn": "5125550001", "iccid": "G1", "imei": None, "status": "active",
                "street": None, "city": None, "state": None, "zip": None},
               {"name": "RH 149 Austin Elevator 2", "label": "RH 149 Austin Elevator 2",
                "msisdn": "5125550002", "iccid": "G2", "imei": None, "status": "active",
                "street": None, "city": None, "state": None, "zip": None}]
    rep = fz.fuse_portfolio(genesis_rows=genesis, true911=_rh_true911(), tenant="rh")
    austin = [t for t in rep["buildings"] if t["store_number"] == "149"]
    assert len(austin) == 1 and len(austin[0]["devices"]) == 2       # one building, two modems


def test_four_sources_same_store_one_fully_fused_building():
    zoho = [{"account_name": "Restoration Hardware #177 Jacksonville", "facility_name": None,
             "street": "10300 Southside Blvd", "city": "Jacksonville", "state": "FL", "zip": "32256",
             "connection_type": "Alarm Panel", "imei": None, "sim": "ICRH177", "msisdn": None,
             "starlink_id": "RAD177"}]
    napco = [_napco("RAD177", "ICRH177", "Restoration Hardware #177 Jacksonville")]
    genesis = [{"name": "RH 177 Jacksonville", "label": "RH 177 Jacksonville", "msisdn": "9045550177",
                "iccid": None, "imei": None, "status": "active", "street": None, "city": None,
                "state": None, "zip": None}]
    rep = fz.fuse_portfolio(zoho_rows=zoho, napco_records=napco, genesis_rows=genesis,
                            true911=_rh_true911(), tenant="rh")
    b177 = [t for t in rep["buildings"] if t["store_number"] == "177"]
    assert len(b177) == 1
    assert set(b177[0]["sources"]) == set(fz.ALL_SOURCES)           # fully fused
    assert b177[0]["source_confidence"] == 100


def test_duplicate_true911_sites_are_one_building_with_finding():
    t911 = _rh_true911()
    t911["sites"].append({"site_id": "RH-177b", "name": "Restoration Hardware #177 Jacksonville",
                          "street": None, "city": "Jacksonville", "state": "FL", "zip": None,
                          "e911_status": "validated"})
    rep = fz.fuse_portfolio(true911=t911, zoho_rows=[{"account_name": "Restoration Hardware #177 Jacksonville",
                            "facility_name": None, "street": None, "city": "Jacksonville", "state": "FL",
                            "zip": None, "connection_type": None, "imei": None, "sim": None, "msisdn": None,
                            "starlink_id": None}], tenant="rh")
    b177 = [t for t in rep["buildings"] if t["store_number"] == "177"]
    assert len(b177) == 1                                            # NOT two buildings
    assert any("Multiple True911 sites" in d for d in b177[0]["duplicate_assets"])


def test_generic_restoration_hardware_does_not_overmatch():
    # two bare "Restoration Hardware" radios (no store #, no distinctive token, diff radios)
    napco = [_napco("R1", "IC1", "Restoration Hardware"),
             _napco("R2", "IC2", "Restoration Hardware")]
    rep = fz.fuse_portfolio(napco_records=napco,
                            true911={"tenant": "rh", "sites": [], "devices": [], "units": [], "lines": []},
                            tenant="rh")
    assert rep["summary"]["buildings"] == 2                          # not merged into one


def test_production_style_portfolio_does_not_inflate():
    stores = [("177", "Jacksonville", "FL"), ("149", "Austin", "TX"), ("140", "Houston", "TX"),
              ("142", "Boston", "MA"), ("147", "Chicago", "IL"), ("150", "Leawood", "KS"),
              ("161", "San Francisco", "CA"), ("174", "Charlotte", "NC"), ("178", "Raleigh", "NC"),
              ("187", "Cleveland", "OH")]
    true911 = {"tenant": "restoration-hardware",
               "sites": [{"site_id": f"RH-{n}", "name": f"Restoration Hardware #{n}", "street": None,
                          "city": c, "state": st, "zip": None, "e911_status": "validated"}
                         for n, c, st in stores],
               "devices": [{"device_id": f"D{n}", "site_id": f"RH-{n}", "msisdn": f"90055500{n}",
                            "iccid": f"IC{n}", "imei": None, "starlink_id": f"RAD{n}",
                            "serial_number": f"RAD{n}", "identifier_type": "starlink",
                            "model": "SLE", "device_type": "fire_alarm"} for n, _, _ in stores],
               "units": [], "lines": []}
    zoho = [{"account_name": f"Restoration Hardware #{n} {c}", "facility_name": None, "street": None,
             "city": c, "state": st, "zip": None, "connection_type": "Alarm Panel", "imei": None,
             "sim": f"IC{n}", "msisdn": None, "starlink_id": f"RAD{n}"} for n, c, st in stores]
    napco = []
    for n, c, _ in stores:
        napco.append(_napco(f"RAD{n}", f"IC{n}", f"Restoration Hardware #{n} {c}"))
        napco.append(_napco(f"RAD{n}b", f"IC{n}b", f"Restoration Hardware #{n} {c}"))   # 2nd radio
    for i in range(200):
        napco.append(_napco(f"NX{i}", f"NIC{i}", f"Some Dealer Account {i} School"))
    genesis = [{"name": f"RH {n} {c}", "label": f"RH {n} {c}", "msisdn": f"70055500{n}",
                "iccid": None, "imei": None, "status": "active", "street": None, "city": None,
                "state": None, "zip": None} for n, c, _ in stores]
    genesis += [{"name": f"Infatrac Subscriber {i}", "label": f"Infatrac Subscriber {i}",
                 "msisdn": f"3035552{i:03d}", "iccid": None, "imei": None, "status": "active",
                 "street": None, "city": None, "state": None, "zip": None} for i in range(1600)]

    rep = fz.fuse_portfolio(zoho_rows=zoho, napco_records=napco, genesis_rows=genesis,
                            true911=true911, tenant="restoration-hardware")
    s = rep["summary"]
    assert s["napco_rows_excluded"] == 200 and s["genesis_rows_excluded"] == 1600
    # ~10 stores -> ~10 buildings, NOT 145 (and definitely not thousands)
    assert len(stores) <= s["buildings"] <= len(stores) + 3
    assert s["source_rows"]["napco"] == len(napco)                  # rows != buildings
    assert s["fully_fused_all_sources"] >= len(stores) - 1          # each store fully fused


# ══════════════════════════════════════════════════════════════════════
# Portfolio Registry integration (fusion reconciles against approved registry)
# ══════════════════════════════════════════════════════════════════════
from app.services import portfolio_registry as _reg  # noqa: E402


def _reg_t911():
    return {"tenant": "rh",
            "sites": [{"site_id": "RH-177", "name": "Restoration Hardware #177 Jacksonville",
                       "street": "10300 Southside Blvd", "city": "Jacksonville", "state": "FL",
                       "zip": "32256", "e911_status": "validated"}],
            "devices": [{"device_id": "D1", "site_id": "RH-177", "msisdn": None, "iccid": "ICRH177",
                         "imei": None, "starlink_id": "RAD177", "serial_number": "RAD177",
                         "identifier_type": "starlink", "model": "SLE", "device_type": "fire_alarm"}],
            "units": [], "lines": []}


def test_fusion_empty_registry_flags_new_building():
    rep = fz.fuse_portfolio(true911=_reg_t911(), tenant="rh",
                            registry=_reg.empty_registry("rh"),
                            zoho_rows=[{"account_name": "Restoration Hardware #177 Jacksonville",
                                        "facility_name": None, "street": None, "city": None,
                                        "state": None, "zip": None, "connection_type": None,
                                        "imei": None, "sim": None, "msisdn": None, "starlink_id": None}])
    s = rep["summary"]
    assert s["buildings_new"] == 1 and s["buildings_known"] == 0 and s["pending_review"] == 1
    assert rep["review_items"][0]["review_type"] == "new_building"
    assert rep["buildings"][0]["registry"]["status"] == "new"


def test_fusion_approved_registry_resolves_known_before_heuristics():
    registry = {"tenant": "rh",
                "buildings": [{"id": 1, "canonical_name": "RH #177 Jacksonville",
                               "store_number": "177", "site_type": "store", "status": "active",
                               "address": "10300 Southside Blvd", "city": "Jacksonville",
                               "state": "FL", "zip": "32256", "approved": True}],
                "aliases": [], "review_items": [],
                "device_mappings": [{"building_id": 1, "kind": "napco_radio", "value": "RAD177",
                                     "value_normalized": _reg.norm_id("RAD177"), "source": "napco",
                                     "confidence": 100, "active": True}]}
    rep = fz.fuse_portfolio(true911=_reg_t911(), tenant="rh", registry=registry,
                            zoho_rows=[{"account_name": "Restoration Hardware #177 Jacksonville",
                                        "facility_name": None, "street": "10300 Southside Blvd",
                                        "city": "Jacksonville", "state": "FL", "zip": "32256",
                                        "connection_type": "Alarm Panel", "imei": None,
                                        "sim": "ICRH177", "msisdn": None, "starlink_id": "RAD177"}])
    s = rep["summary"]
    assert s["buildings_known"] == 1 and s["buildings_new"] == 0
    assert s["portfolio_buildings"] == 1 and s["approved_mappings"] == 1
    assert rep["buildings"][0]["registry"]["building_id"] == 1
    assert rep["buildings"][0]["registry"]["method"] == "device"       # approved mapping, not heuristic


def test_fusion_report_has_registry_and_confidence_sections(tmp_path):
    rep = fz.fuse_portfolio(true911=_reg_t911(), tenant="rh", registry=_reg.empty_registry("rh"),
                            zoho_rows=[{"account_name": "Restoration Hardware #177 Jacksonville",
                                        "facility_name": None, "street": None, "city": None,
                                        "state": None, "zip": None, "connection_type": None,
                                        "imei": None, "sim": None, "msisdn": None, "starlink_id": None}])
    assert "confidence_distribution" in rep["summary"]
    assert set(rep["summary"]["coverage_by_source"]) == set(fz.ALL_SOURCES)
    mpath = tmp_path / "r.md"
    fz.write_markdown_report(str(mpath), rep)
    md = mpath.read_text(encoding="utf-8")
    assert "Portfolio Registry" in md and "review queue" in md
    assert "Confidence distribution" in md
