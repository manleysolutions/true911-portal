"""RH Portfolio Certification Wizard — normalization, matching, classification, output.

Pure-function tests (no DB, no Zoho): RH alias/store-number/site-type detection,
canonical grouping + confidence, the A–L matching engine, the PASS/CONDITIONAL/
BLOCKED verdict, and the CSV/JSON/MD artifacts.  Verifies the tool is read-only
(never marks E911 verified, never fabricates data).
"""

from __future__ import annotations

import asyncio
import csv
import json

import pytest

from app.services import zoho_crm
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
    # a genuinely-unrecognized special label (NOT in the known registry) still
    # requires manual review
    canon = cert.build_canonical_locations([_row(account_name="Restoration Hardware - Soda Grocery",
                                                 street=None, city=None, state=None, zip=None)])
    c = canon[0]
    assert c["store_number"] is None and c["site_type"] == "special"
    assert c["known_alias"] is False
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


# ══════════════════════════════════════════════════════════════════════
# Live Zoho mode (reuses the existing authenticated client; read-only)
# ══════════════════════════════════════════════════════════════════════
def test_map_zoho_api_record_field_variants():
    """Live Zoho records map to the SAME normalized shape as the CSV rows,
    tolerant of Zoho API field names (Accounts billing / subscription device)."""
    acct = cert.map_zoho_api_record({
        "id": "z1", "Account_Name": "Restoration Hardware #642 Gilbert",
        "Billing_Street": "3787 S Gilbert Rd", "Billing_City": "Gilbert",
        "Billing_State": "az", "Billing_Code": "85297", "Phone": "480-555-0100"})
    assert acct["account_name"] == "Restoration Hardware #642 Gilbert"
    assert acct["street"] == "3787 S Gilbert Rd" and acct["state"] == "AZ"
    assert acct["msisdn"] == "4805550100"
    # a subscription-style record with device fields
    sub = cert.map_zoho_api_record({
        "Account_Name": "RH #169 Columbus", "Facility_Address": "3964 Townsfair Way",
        "Facility_State": "OH", "Device_IMEI": "868105041862416", "SIM_Number": "8901260882237499857",
        "Emergency_Line": "true", "Connection_Type": "Alarm Panel"})
    assert sub["imei"] == "868105041862416" and sub["sim"] == "8901260882237499857"
    assert sub["emergency_line"] is True and sub["connection_type"] == "Alarm Panel"
    # ignores nested Zoho lookup objects (never crashes)
    assert cert.map_zoho_api_record({"Account_Name": {"name": "x"}})["account_name"] is None


def test_resolve_fields_default_and_override():
    assert cert.resolve_fields("Accounts", None) == cert.DEFAULT_ACCOUNT_FIELDS
    assert cert.resolve_fields("Accounts", "Account_Name,Phone") == "Account_Name,Phone"
    assert cert.resolve_fields("Subscriptions", None) is None      # non-Accounts -> Zoho default


def test_load_zoho_live_filters_rh_and_reuses_client(monkeypatch):
    """Live mode must call the EXISTING zoho_crm.fetch_records (no new OAuth) and
    keep only RH rows."""
    captured = {}

    async def _fake_fetch(module="Accounts", *, fields=None, **kw):
        captured["module"] = module
        captured["fields"] = fields
        return [
            {"Account_Name": "Restoration Hardware #177 Jacksonville", "Billing_State": "FL"},
            {"Account_Name": "R&R Realty Group", "Billing_State": "IA"},        # not RH
            {"Account_Name": "RH #506 Toronto", "Billing_State": "ON"},
        ]
    monkeypatch.setattr(zoho_crm, "fetch_records", _fake_fetch)
    rows, total = asyncio.run(cert.load_zoho_live("Accounts", None))
    assert total == 3 and len(rows) == 2                    # non-RH filtered out
    assert captured["module"] == "Accounts"
    assert captured["fields"] == cert.DEFAULT_ACCOUNT_FIELDS  # resolved default passed through


def test_load_zoho_live_passes_custom_fields(monkeypatch):
    captured = {}

    async def _fake_fetch(module="Accounts", *, fields=None, **kw):
        captured["fields"] = fields
        return []
    monkeypatch.setattr(zoho_crm, "fetch_records", _fake_fetch)
    asyncio.run(cert.load_zoho_live("Accounts", "Account_Name,Phone"))
    assert captured["fields"] == "Account_Name,Phone"


def test_fetch_records_pagination_is_reused(monkeypatch):
    """The pagination we depend on lives in the existing client — verify it walks
    all pages and stops when more_records is false (read-only)."""
    pages = {
        1: {"data": [{"Account_Name": "RH #1"}], "info": {"more_records": True}},
        2: {"data": [{"Account_Name": "RH #2"}], "info": {"more_records": False}},
    }

    async def _fake_get(path, params=None):
        return pages[params["page"]]
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)
    monkeypatch.setattr(zoho_crm, "_zoho_get", _fake_get)
    out = asyncio.run(zoho_crm.fetch_records("Accounts", fields="Account_Name"))
    assert [r["Account_Name"] for r in out] == ["RH #1", "RH #2"]   # both pages aggregated


def test_live_mode_produces_same_pipeline_outputs(monkeypatch):
    """A live fetch feeds the identical canonical → certify → report pipeline."""
    async def _fake_fetch(module="Accounts", *, fields=None, **kw):
        return [{"Account_Name": "Restoration Hardware #177 Jacksonville",
                 "Billing_Street": "10300 Southside Blvd", "Billing_City": "Jacksonville",
                 "Billing_State": "FL", "Billing_Code": "32256", "Phone": "904-555-0100"}]
    monkeypatch.setattr(zoho_crm, "fetch_records", _fake_fetch)
    rows, total = asyncio.run(cert.load_zoho_live("Accounts", None))
    canon = cert.build_canonical_locations(rows)
    assert len(canon) == 1 and canon[0]["store_number"] == "177"
    rep = cert.certify(_t911(units=[]), canon)              # matched, but no unit -> BLOCKED
    assert rep["summary"]["matched"] == 1 and rep["summary"]["verdict"] == "BLOCKED"


# ── CLI source validation ────────────────────────────────────────────
def test_cli_requires_a_source(monkeypatch):
    monkeypatch.setattr("sys.argv", ["rh_portfolio_certification"])
    with pytest.raises(SystemExit) as e:
        cert.main()
    assert e.value.code == 2                                # argparse usage error


def test_cli_rejects_both_sources(monkeypatch):
    monkeypatch.setattr("sys.argv",
                        ["rh_portfolio_certification", "--zoho-live", "--zoho-csv", "x.csv"])
    with pytest.raises(SystemExit) as e:
        cert.main()
    assert e.value.code == 2


def test_cli_csv_mode_still_supported(monkeypatch, tmp_path):
    """Backward compatibility: --zoho-csv alone runs (offline) with no --zoho-live."""
    src = tmp_path / "z.csv"
    with open(src, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Account Name", "FacilityAddress", "FacilityCity", "FacilityState", "FacilityZipCode"])
        w.writerow(["Restoration Hardware #177 Jacksonville", "10300 Southside Blvd",
                    "Jacksonville", "FL", "32256"])

    async def _fake_run(tenant, *, zoho_csv, zoho_live, module, fields):
        assert zoho_csv == str(src) and zoho_live is False   # CSV branch selected
        return {"summary": {"tenant": tenant, "verdict": "PASS", "by_class": {},
                            **{k: 0 for k in _SUMMARY_KEYS}},
                "findings": [], "results": []}
    monkeypatch.setattr(cert, "_run", lambda *a, **k: _fake_run(*a, **k))
    monkeypatch.setattr("sys.argv",
                        ["rh_portfolio_certification", "--zoho-csv", str(src),
                         "--csv", str(tmp_path / "c.csv"), "--json", str(tmp_path / "j.json"),
                         "--report", str(tmp_path / "r.md")])
    with pytest.raises(SystemExit) as e:
        cert.main()
    assert e.value.code == 0                                # PASS -> exit 0


_SUMMARY_KEYS = ("zoho_rows", "canonical_locations", "true911_sites", "true911_devices",
                 "true911_service_units", "matched", "possible", "missing_in_true911",
                 "missing_in_zoho", "duplicate_zoho", "duplicate_true911", "address_mismatch",
                 "phone_mismatch", "device_mismatch", "missing_service_units", "e911_unverified",
                 "weird_labels", "manual_review", "findings_total")


# ══════════════════════════════════════════════════════════════════════
# v2 — known RH special-location registry (operator-confirmed 2026-07-01)
# ══════════════════════════════════════════════════════════════════════
_KNOWN_CASES = [
    ("Restoration Hardware - Greenwich 265", "special", "RH Greenwich (265)"),
    ("Restoration Hardware #RHNYC", "gallery", "RH NYC Gallery"),
    ("Restoration Hardware Beverly Modern", "special", "RH Beverly Modern"),
    ("Restoration Hardware - Patterson Warehouse", "warehouse", "RH Patterson Warehouse"),
    ("Restoration Hardware - MDC", "distribution_center", "RH MDC (Distribution Center)"),
    ("Restoration Hardware Linden House", "special", "RH Linden House"),
]


@pytest.mark.parametrize("label,site_type,canonical", _KNOWN_CASES)
def test_known_alias_recognized_typed_and_not_weird(label, site_type, canonical):
    assert cert.is_rh_label(label)                          # included in the portfolio
    assert cert.match_known_location(label) is not None
    c = cert.build_canonical_locations([_row(account_name=label, street=None, city=None,
                                             state=None, zip=None)])[0]
    assert c["known_alias"] is True and c["known_alias_label"]
    assert c["site_type"] == site_type                      # classified per registry
    assert c["canonical_location_name"] == canonical
    assert c["manual_review_required"] is False             # NOT flagged weird


def test_patterson_warehouse_is_warehouse():
    c = cert.build_canonical_locations([_row(account_name="Restoration Hardware - Patterson Warehouse")])[0]
    assert c["site_type"] == "warehouse" and c["known_alias"] is True


def test_mdc_is_distribution_center():
    c = cert.build_canonical_locations([_row(account_name="Restoration Hardware - MDC")])[0]
    assert c["site_type"] == "distribution_center" and c["known_alias"] is True


def test_linden_house_is_special():
    c = cert.build_canonical_locations([_row(account_name="Restoration Hardware Linden House")])[0]
    assert c["site_type"] in ("special", "hospitality") and c["known_alias"] is True


def test_known_aliases_counted_and_not_flagged_weird_but_still_need_match():
    canon = cert.build_canonical_locations(
        [_row(account_name=lbl, street=None, city=None, state=None, zip=None)
         for lbl, _, _ in _KNOWN_CASES])
    rep = cert.certify(_t911(sites=[], devices=[], units=[], lines=[]), canon)
    s = rep["summary"]
    assert s["known_special_locations"] == 6                # all counted as legitimate
    assert s["weird_labels"] == 0                           # none flagged L
    assert s["missing_in_true911"] == 6                     # still must exist in True911
    # every one is reported in the Known special section rows
    assert sum(1 for r in rep["results"] if r["known_alias"]) == 6


def test_known_alias_matched_when_site_bears_alias():
    canon = cert.build_canonical_locations([_row(account_name="Restoration Hardware - MDC",
                                                 street=None, city=None, state=None, zip=None)])
    site = {"site_id": "RH-MDC", "name": "RH MDC", "street": None, "city": None, "state": None,
            "zip": None, "e911_status": "validated"}
    t = _t911(sites=[site], devices=[],
              units=[{"unit_id": "U", "site_id": "RH-MDC", "unit_type": "x",
                      "device_id": None, "line_id": None}])
    rep = cert.certify(t, canon)
    r = rep["results"][0]
    assert cert.CLASS_MATCHED in r["classes"]               # known signal -> strong match
    assert cert.CLASS_WEIRD_LABEL not in r["classes"]
    assert "known" in r["match_signals"]


def test_rhnyc_does_not_overmatch_generic_nyc():
    rhnyc = cert.build_canonical_locations([_row(account_name="Restoration Hardware #RHNYC",
                                                 street=None, city=None, state=None, zip=None)])[0]
    guesthouse = {"site_id": "RH-GH", "name": "Restoration Hardware # NYC Guesthouse",
                  "street": "55 Gansevoort St", "city": "New York", "state": "NY", "zip": "10014",
                  "e911_status": "validated"}
    # no store/address/name/known signal links RHNYC to the generic NYC guesthouse
    assert cert.match_site(rhnyc, [guesthouse], {}, {}) == []


def test_rhnyc_matches_site_bearing_the_code():
    rhnyc = cert.build_canonical_locations([_row(account_name="Restoration Hardware #RHNYC",
                                                 street=None, city=None, state=None, zip=None)])[0]
    site = {"site_id": "RH-RHNYC", "name": "RH RHNYC Gallery", "street": None, "city": "New York",
            "state": "NY", "zip": None, "e911_status": "validated"}
    matches = cert.match_site(rhnyc, [site], {}, {})
    assert matches and matches[0]["signals"]["known"] is True


def test_name_match_ignores_generic_restoration_hardware():
    # two different stores must NOT match on the generic brand tokens alone
    assert cert._name_match("Restoration Hardware #140 Houston",
                            "Restoration Hardware #642 Gilbert") is False
    # a distinctive shared token does match
    assert cert._name_match("Restoration Hardware #177 Jacksonville",
                            "RH #177 Jacksonville") is True
