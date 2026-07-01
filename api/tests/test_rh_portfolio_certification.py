"""RH Portfolio Certification Wizard — normalization, matching, classification, output.

Pure-function tests (no DB, no Zoho): RH alias/store-number/site-type detection,
canonical grouping + confidence, the A–L matching engine, the PASS/CONDITIONAL/
BLOCKED verdict, and the CSV/JSON/MD artifacts.  Verifies the tool is read-only
(never marks E911 verified, never fabricates data).
"""

from __future__ import annotations

import csv
import json

from scripts import rh_portfolio_certification as cert


# ── RH alias / store-number / site-type normalization ────────────────
def test_is_rh_label_aliases():
    assert cert.is_rh_label("Restoration Hardware #177 Jacksonville")
    assert cert.is_rh_label(None, "Restoration Hdwr #506")
    assert cert.is_rh_label("RH #642 Gilbert")
    assert cert.is_rh_label("Restoration Hardware - MDC")
    assert not cert.is_rh_label("R&R Realty Group")
    assert not cert.is_rh_label("University of South Carolina")


def test_extract_store_number_variants():
    assert cert.extract_store_number("Restoration Hardware #177 Jacksonville") == "177"
    assert cert.extract_store_number("Restoration Hardware # 656 San Rafael") == "656"
    assert cert.extract_store_number("Restoration Hardware #001 Tracy") == "1"      # leading zeros dropped
    assert cert.extract_store_number("Restoration hardware - 150 Leawood") == "150"
    assert cert.extract_store_number("Restoration Hardware Toronto #506") == "506"
    assert cert.extract_store_number("Restoration Hardware #RHNYC") == "RHNYC"      # alpha code
    # ambiguous / address-like / none -> None (manual review)
    assert cert.extract_store_number("Restoration Hardware - MDC") is None
    assert cert.extract_store_number("Restoration Hardware 3265 Brunswick Pike") is None
    assert cert.extract_store_number("Restoration Hardware Beverly Modern") is None


def test_detect_site_type():
    assert cert.detect_site_type("RH # NYC Guesthouse") == "guest_house"
    assert cert.detect_site_type("RH # Richmond Warehouse") == "warehouse"
    assert cert.detect_site_type("RH #644 Princeton Outlet") == "outlet"
    assert cert.detect_site_type("RH #147 Chicago Gallery") == "gallery"
    assert cert.detect_site_type("RH - MDC") == "distribution_center"
    assert cert.detect_site_type("RH (main account)") == "corporate"
    assert cert.detect_site_type("RH Linden House") == "special"
    assert cert.detect_site_type("RH #642 Gilbert") == "store"


def test_map_zoho_row_shape():
    row = {"Account Name": "Restoration Hardware #169 Columbus", "FacilityName": "RH #169",
           "FacilityAddress": "3964 Townsfair Way", "FacilityCity": "Columbus",
           "FacilityState": "oh", "FacilityZipCode": "43219", "Emergency Line": "true",
           "Mobile Number - MSISDN": "(614) 209-8841", "Device IMEI": "868105041862416",
           "SIM Number": "8901260882237499857", "Connection Type": "Alarm Panel"}
    m = cert.map_zoho_row(row)
    assert m["account_name"] == "Restoration Hardware #169 Columbus"
    assert m["state"] == "OH" and m["msisdn"] == "6142098841" and m["emergency_line"] is True
    assert m["imei"] == "868105041862416" and m["connection_type"] == "Alarm Panel"


# ── canonical grouping + confidence + manual review ──────────────────
def _row(**kw):
    base = dict(account_name="Restoration Hardware #177 Jacksonville", facility_name=None,
                street="10300 Southside Blvd", city="Jacksonville", state="FL", zip="32256",
                facility_type="Commercial", activation_status="Activated", msisdn="9045550100",
                emergency_line=True, connection_type="Alarm Panel", imei="111", sim="222",
                starlink_id=None)
    base.update(kw)
    return base


def test_canonical_grouping_merges_device_rows():
    rows = [_row(imei="111", connection_type="Alarm Panel"),
            _row(imei="333", connection_type="Elevator", msisdn=None)]
    canon = cert.build_canonical_locations(rows)
    assert len(canon) == 1
    c = canon[0]
    assert c["store_number"] == "177" and c["device_count"] == 2
    assert set(c["connection_types"]) == {"Alarm Panel", "Elevator"}
    assert "111" in c["device_ids"] and "333" in c["device_ids"]
    assert c["manual_review_required"] is False        # numeric store + full address + phone + device
    assert c["confidence"] == 100


def test_canonical_manual_review_for_weird_label():
    canon = cert.build_canonical_locations([_row(account_name="Restoration Hardware - MDC",
                                                 street=None, city=None, state=None, zip=None)])
    c = canon[0]
    assert c["store_number"] is None and c["site_type"] == "distribution_center"
    assert c["manual_review_required"] is True
    assert c["confidence"] < 100


def test_canonical_manual_review_for_non_us():
    canon = cert.build_canonical_locations([_row(account_name="Restoration Hardware Toronto #506",
                                                 city="Toronto", state="ON", zip="M6A 2T9")])
    assert canon[0]["non_us"] is True and canon[0]["manual_review_required"] is True


# ── matching + A–L classification ────────────────────────────────────
def _t911(**kw):
    base = {
        "tenant": "restoration-hardware",
        "sites": [{"site_id": "RH-177", "name": "Restoration Hardware #177 Jacksonville",
                   "street": "10300 Southside Blvd", "city": "Jacksonville", "state": "FL",
                   "zip": "32256", "e911_status": "validated"}],
        "devices": [{"device_id": "D1", "site_id": "RH-177", "msisdn": "9045550100",
                     "imei": "111", "iccid": "222", "starlink_id": None, "serial_number": None,
                     "model": "x", "device_type": "y"}],
        "units": [{"unit_id": "U1", "site_id": "RH-177", "unit_type": "fire_alarm",
                   "device_id": None, "line_id": None}],
        "lines": [], "_zoho_rows": 1,
    }
    base.update(kw)
    return base


def test_certify_clean_match_is_pass():
    canon = cert.build_canonical_locations([_row()])
    rep = cert.certify(_t911(), canon)
    s = rep["summary"]
    assert s["matched"] == 1 and s["verdict"] == "PASS"
    assert s["by_class"].get(cert.CLASS_MISSING_T911, 0) == 0
    r = rep["results"][0]
    assert cert.CLASS_MATCHED in r["classes"] and r["match_site_id"] == "RH-177"


def test_certify_missing_in_true911_blocks():
    canon = cert.build_canonical_locations([_row()])
    rep = cert.certify(_t911(sites=[], devices=[], units=[], lines=[]), canon)
    assert rep["summary"]["missing_in_true911"] == 1
    assert rep["summary"]["verdict"] == "BLOCKED"


def test_certify_missing_service_unit_blocks():
    canon = cert.build_canonical_locations([_row()])
    rep = cert.certify(_t911(units=[]), canon)
    assert rep["summary"]["missing_service_units"] == 1
    assert rep["summary"]["verdict"] == "BLOCKED"


def test_certify_e911_unverified_blocks():
    canon = cert.build_canonical_locations([_row()])
    t = _t911()
    t["sites"][0]["e911_status"] = "pending"
    rep = cert.certify(t, canon)
    assert rep["summary"]["e911_unverified"] == 1 and rep["summary"]["verdict"] == "BLOCKED"


def test_certify_device_mismatch_blocks():
    canon = cert.build_canonical_locations([_row(imei="999", sim="888")])   # ids not on the site
    rep = cert.certify(_t911(), canon)
    assert rep["summary"]["device_mismatch"] == 1 and rep["summary"]["verdict"] == "BLOCKED"


def test_certify_address_mismatch_is_conditional():
    canon = cert.build_canonical_locations([_row(street="999 Wrong St")])
    rep = cert.certify(_t911(), canon)
    assert rep["summary"]["address_mismatch"] == 1
    # address mismatch alone (with device/phone still matching by other signals) is soft
    assert rep["summary"]["verdict"] in ("CONDITIONAL", "BLOCKED")


def test_certify_missing_in_zoho_flags_extra_site():
    canon = cert.build_canonical_locations([_row()])
    t = _t911()
    t["sites"].append({"site_id": "RH-999", "name": "RH Phantom", "street": "1 Nowhere",
                       "city": "Ghost", "state": "TX", "zip": "00000", "e911_status": "validated"})
    rep = cert.certify(t, canon)
    assert rep["summary"]["missing_in_zoho"] == 1


def test_certify_duplicate_true911_sites():
    canon = cert.build_canonical_locations([_row()])
    t = _t911()
    t["sites"].append({"site_id": "RH-177b", "name": "Restoration Hardware #177 Jacksonville",
                       "street": "10300 Southside Blvd", "city": "Jacksonville", "state": "FL",
                       "zip": "32256", "e911_status": "validated"})
    rep = cert.certify(t, canon)
    assert rep["summary"]["duplicate_true911"] >= 1 and rep["summary"]["verdict"] == "BLOCKED"


def test_certify_duplicate_zoho_records():
    # two canonicals (different store keys) sharing the same physical address
    rows = [_row(account_name="Restoration Hardware #177 Jacksonville"),
            _row(account_name="Restoration Hardware Jacksonville Gallery")]
    canon = cert.build_canonical_locations(rows)
    assert len(canon) == 2
    rep = cert.certify(_t911(sites=[], devices=[], units=[], lines=[]), canon)
    assert rep["summary"]["duplicate_zoho"] >= 1


def test_certify_weird_label_flagged_L():
    canon = cert.build_canonical_locations([_row(account_name="Restoration Hardware - Soda Grocery",
                                                 street=None, city=None, state=None, zip=None)])
    rep = cert.certify(_t911(sites=[], devices=[], units=[], lines=[]), canon)
    assert rep["summary"]["weird_labels"] == 1


def test_possible_match_single_weak_signal():
    # only a name signal (no store#, no addr, no phone/device overlap) -> B possible
    canon = cert.build_canonical_locations([_row(account_name="Restoration Hardware Uptown",
                                                 street="5 Elsewhere Ave", city="Nowhere",
                                                 state="FL", zip="00000", msisdn=None,
                                                 imei=None, sim=None)])
    t = _t911(devices=[], units=[{"unit_id": "U1", "site_id": "RH-177", "unit_type": "x",
                                  "device_id": None, "line_id": None}])
    t["sites"][0]["name"] = "Restoration Hardware Uptown Gallery"
    rep = cert.certify(t, canon)
    r = rep["results"][0]
    assert cert.CLASS_POSSIBLE in r["classes"]


# ── output artifacts ─────────────────────────────────────────────────
def test_outputs_csv_json_md(tmp_path):
    canon = cert.build_canonical_locations([_row()])
    rep = cert.certify(_t911(units=[]), canon)   # -> BLOCKED w/ findings
    cpath, jpath, mpath = tmp_path / "c.csv", tmp_path / "r.json", tmp_path / "r.md"
    cert.write_csv(str(cpath), rep["findings"])
    cert.write_json(str(jpath), rep)
    cert.write_markdown_report(str(mpath), rep)

    with open(cpath, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and set(rows[0]) == {"class", "canonical", "store_number", "site_id", "site_name", "detail"}

    loaded = json.load(open(jpath, encoding="utf-8"))
    assert loaded["summary"]["verdict"] == "BLOCKED"

    md = mpath.read_text(encoding="utf-8")
    assert "Go-live recommendation" in md and "BLOCKED" in md
    assert "Operator punch list" in md and "Top 25 issues" in md
    # never claims E911 is verified / never fabricates
    assert "never auto-verified" in md
