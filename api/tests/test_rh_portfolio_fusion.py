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
