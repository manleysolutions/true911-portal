"""Tests for the R&R site inventory diagnostic (pure, no DB)."""

from __future__ import annotations

from pathlib import Path

from app.audit_rr_site_inventory import (
    build_inventory,
    classify_site,
    write_csv,
    write_json,
)


def _site(sid, name, *, street=None, city=None, state=None, zip=None, customer_id=7):
    return {"site_id": sid, "site_name": name, "customer_id": customer_id,
            "e911_street": street, "e911_city": city, "e911_state": state, "e911_zip": zip}


def _dev(did, site, msisdn="3055551234"):
    return {"device_id": did, "site_id": site, "msisdn": msisdn}


def _line(lid, site, did="3055551234"):
    return {"line_id": lid, "site_id": site, "did": did}


# ── classify_site ────────────────────────────────────────────────────────
def test_empty_site():
    assert classify_site(_site("S1", "A"), dev_count=0, line_count=0, same_name_siblings=[]) == "empty_site"


def test_placeholder_site():
    # device-only, no address, many devices
    assert classify_site(_site("S1", "(imported)"), dev_count=54, line_count=0,
                         same_name_siblings=[]) == "placeholder_site"


def test_duplicate_same_address():
    a = _site("S1", "Main Office", street="1 Main", city="WDM", state="IA", zip="50266")
    b = _site("S2", "Main Office", street="1 Main", city="WDM", state="IA", zip="50266")
    assert classify_site(a, dev_count=1, line_count=1, same_name_siblings=[b]) == "duplicate_site_name_same_address"


def test_duplicate_same_name_missing_address_treated_as_dup():
    a = _site("S1", "Main Office")
    b = _site("S2", "Main Office")
    assert classify_site(a, dev_count=0, line_count=1, same_name_siblings=[b]) == "duplicate_site_name_same_address"


def test_duplicate_unique_address():
    a = _site("S1", "Main Office", street="1 Main", city="WDM", state="IA", zip="50266")
    b = _site("S2", "Main Office", street="99 Oak", city="Ames", state="IA", zip="50010")
    assert classify_site(a, dev_count=1, line_count=1, same_name_siblings=[b]) == "duplicate_site_name_unique_address"


def test_line_only_and_device_only():
    assert classify_site(_site("S1", "Uniq"), dev_count=0, line_count=2, same_name_siblings=[]) == "line_only_site"
    assert classify_site(_site("S1", "Uniq2"), dev_count=2, line_count=0, same_name_siblings=[]) == "device_only_site"


def test_valid_distinct_site():
    assert classify_site(_site("S1", "Unique HQ", street="1 Main"),
                         dev_count=1, line_count=1, same_name_siblings=[]) == "valid_distinct_site"


# ── build_inventory + recommendation ─────────────────────────────────────
def test_inventory_flags_duplicate_records_unsafe():
    NAME = "R&R REALTY GROUP - West Des Moines, IA - Main Office"
    # placeholder holds all 6 devices (>= PLACEHOLDER_DEVICE_MIN); 6 line-sites
    # share the SAME name AND no address -> duplicate records.
    sites = [_site("SITE-BULK", "(imported placeholder)")] + \
            [_site(f"DST{i}", NAME) for i in range(6)]
    devices = [_dev(f"D{i}", "SITE-BULK", f"30555000{i}") for i in range(6)]
    lines = [_line(f"L{i}", f"DST{i}", f"30555000{i}") for i in range(6)]
    rep = build_inventory(sites, devices, lines)
    assert rep["summary"]["placeholder_site"] == 1
    assert rep["summary"]["duplicate_site_name_same_address"] == 6
    assert "NOT SAFE" in rep["recommendation"]
    g = rep["duplicate_name_groups"][0]
    assert g["site_count"] == 6 and g["site_name"] == NAME


def test_inventory_distinct_addresses_likely_safe():
    NAME = "R&R Main Office"
    sites = [_site("D1", NAME, street="1 Main", city="WDM"),
             _site("D2", NAME, street="99 Oak", city="Ames")]
    devices = [_dev("dev1", "D1", "3050000001"), _dev("dev2", "D2", "3050000002")]
    lines = [_line("l1", "D1", "3050000001"), _line("l2", "D2", "3050000002")]
    rep = build_inventory(sites, devices, lines)
    assert rep["summary"]["duplicate_site_name_unique_address"] == 2
    assert rep["summary"]["duplicate_site_name_same_address"] == 0
    assert "LIKELY SAFE" in rep["recommendation"]


def test_inventory_counts_and_occupancy():
    sites = [_site("S1", "A", street="1 Main"), _site("S2", "B")]
    devices = [_dev("d1", "S1")]
    lines = [_line("l1", "S1"), _line("l2", "S1")]
    rep = build_inventory(sites, devices, lines)
    s1 = next(r for r in rep["rows"] if r["site_id"] == "S1")
    assert s1["device_count"] == 1 and s1["line_count"] == 2 and s1["occupancy"] == "both"
    s2 = next(r for r in rep["rows"] if r["site_id"] == "S2")
    assert s2["occupancy"] == "empty" and s2["classification"] == "empty_site"


# ── exports ──────────────────────────────────────────────────────────────
def test_exports(tmp_path):
    rep = build_inventory([_site("S1", "A", street="1 Main")], [_dev("d1", "S1")], [])
    j = tmp_path / "r.json"
    write_json(rep, str(j))
    import json
    assert json.loads(j.read_text(encoding="utf-8"))["read_only"] is True
    c = tmp_path / "r.csv"
    assert write_csv(rep["rows"], str(c)) == 1
    assert "site_name" in c.read_text(encoding="utf-8").splitlines()[0]


# ── read-only ────────────────────────────────────────────────────────────
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_rr_site_inventory.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "add_all", "insert into", "delete from"):
        assert forbidden not in lower, f"diagnostic must be read-only; found {forbidden!r}"
