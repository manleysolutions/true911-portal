"""Tests for the Webber Zoho↔True911 mapping review report (pure, no DB)."""

from __future__ import annotations

from pathlib import Path

from app.audit_webber_mapping_review import (
    REPORT_FIELDS,
    build_review,
    summarize,
    write_csv,
    write_json,
)


def _z(*, sub="SM-1", account="Webber Infrastructure", facility=None,
       msisdn=None, activation="De-activated"):
    return {"subscription_mgmt_id": sub, "account_name": account,
            "facility_name": facility, "msisdn": msisdn,
            "device_activation_status": activation, "lifecycle_state": None}


def _t911(*, devices=None, lines=None, sites=None):
    return {"customer": {"name": "Webber"}, "tenant": {"is_active": True},
            "devices": devices or [], "lines": lines or [], "sites": sites or []}


def _dev(did, msisdn, *, status="active"):
    return {"device_id": did, "site_id": None, "status": status, "msisdn": msisdn,
            "model": None, "iccid": None, "network_status": None}


def _line(lid, did, *, status="active"):
    return {"line_id": lid, "site_id": None, "status": status, "did": did, "sim_iccid": None}


def _site(sid, name, *, status="active"):
    return {"site_id": sid, "site_name": name, "status": status}


def _one(zoho, t911):
    return build_review(zoho, t911)[0]


# 1 — missing MSISDN
def test_missing_msisdn():
    r = _one([_z(msisdn="3054577324")], _t911(devices=[_dev("D1", "9999999999")]))
    assert r["msisdn_match"] == "missing"
    assert r["classification"] == "missing"
    assert "Locate/provision" in r["recommended_action"]


# 2 — duplicate MSISDN
def test_duplicate_msisdn():
    t = _t911(devices=[_dev("D1", "7869600498"), _dev("D2", "17869600498")])
    r = _one([_z(msisdn="7869600498")], t)
    assert r["msisdn_match"] == "duplicate"
    assert r["classification"] == "duplicate"
    assert "2 entities" in r["matched_true911_entity"]
    assert "Resolve duplicate" in r["recommended_action"]


# 3 — facility fuzzy match
def test_facility_fuzzy_match():
    t = _t911(sites=[_site("S1", "Dodge Island")])
    r = _one([_z(facility="Dodge Island - White Phone", msisdn="3054577324")], t)
    assert r["site_match"] == "fuzzy"
    assert r["matched_site_id"] == "S1"
    # no MSISDN match + a site lead -> overall fuzzy
    assert r["classification"] == "fuzzy"
    assert "Verify by site name" in r["recommended_action"]


def test_facility_exact_match():
    t = _t911(sites=[_site("S1", "Operations Building at Watson Island (White)")])
    r = _one([_z(facility="Operations Building at Watson Island (White)")], t)
    assert r["site_match"] == "exact"


# 4 — deactivated Zoho / active True911
def test_deactivated_zoho_active_true911():
    t = _t911(devices=[_dev("D1", "7542697860", status="active")])
    r = _one([_z(msisdn="7542697860", activation="De-activated")], t)
    assert r["msisdn_match"] == "exact"
    assert r["zoho_lifecycle"] == "deactivated"
    assert r["matched_entity_status"] == "active"
    assert "De-activated but matched True911 entity is ACTIVE" in r["recommended_action"]


def test_exact_match_via_line_did():
    t = _t911(lines=[_line("L1", "+1 (754) 269-7860", status="provisioning")])
    r = _one([_z(msisdn="7542697860", activation="Active")], t)
    assert r["msisdn_match"] == "exact"
    assert r["matched_true911_entity"] == "line:L1"
    assert r["classification"] == "exact"


# summary + exports
def test_summary_and_exports(tmp_path):
    zoho = [
        _z(sub="A", msisdn="7542697860"),                          # exact
        _z(sub="B", msisdn="7869600498"),                          # duplicate
        _z(sub="C", msisdn="3054577324", facility="Dodge Island - Red Phone"),  # fuzzy
        _z(sub="D", msisdn="0000000000"),                          # missing
    ]
    t = _t911(
        devices=[_dev("D1", "7542697860"),
                 _dev("D2", "7869600498"), _dev("D3", "7869600498")],
        sites=[_site("S1", "Dodge Island")])
    rows = build_review(zoho, t)
    s = summarize(rows)
    assert s == {"records": 4, "exact": 1, "duplicate": 1, "fuzzy": 1, "missing": 1}
    j = tmp_path / "r.json"
    write_json(rows, s, str(j))
    import json
    doc = json.loads(j.read_text(encoding="utf-8"))
    assert doc["read_only"] is True and len(doc["records"]) == 4
    c = tmp_path / "r.csv"
    n = write_csv(rows, str(c))
    assert n == 4
    header = c.read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",")[0] == "zoho_subscription_id"
    for f in REPORT_FIELDS:
        assert f in header


# 5 — read-only / no writes
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_webber_mapping_review.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "db.bulk", "add_all"):
        assert forbidden not in lower, f"review must be read-only; found {forbidden!r}"
