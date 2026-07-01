"""RH ↔ Zoho reconciliation (read-only) — normalization, matching, flags, output.

Uses MOCKED Zoho responses (no live API).  Verifies every required flag fires and
that the tool is read-only (never writes Zoho/True911).
"""

from __future__ import annotations

import asyncio
import csv
import json

from scripts import rh_zoho_reconciliation as rz


# ── normalization / mapping ──────────────────────────────────────────
def test_norm_phone_and_name_match():
    assert rz.norm_phone("+1 (617) 555-0100") == "6175550100"
    assert rz.norm_phone("555") == "555"
    assert rz.name_match("RH Boston — Back Bay", "rh boston back bay") is True
    assert rz.name_match("RH Boston", "RH Chicago") is False


def test_map_zoho_location_field_fallbacks():
    m = rz.map_zoho_location({"id": "z1", "Account_Name": "RH Yountville",
                              "Billing_Street": "6725 Washington St", "Billing_City": "Yountville",
                              "Billing_State": "CA", "Phone": "707-555-0142"})
    assert m["zoho_id"] == "z1" and m["name"] == "RH Yountville"
    assert m["street"] == "6725 Washington St" and m["phone"] == "707-555-0142"
    # tolerant of alternate field names
    alt = rz.map_zoho_location({"id": "z2", "Store_Name": "RH X", "Shipping_City": "Dallas"})
    assert alt["name"] == "RH X" and alt["city"] == "Dallas"


# ── reconciliation: every required flag fires ────────────────────────
def _fixture():
    return {
        "tenant": "restoration-hardware",
        "sites": [
            {"site_id": "S1", "name": "RH Boston", "street": "1 Main", "city": "Boston", "state": "MA", "zip": "02116", "e911_status": "validated"},
            {"site_id": "S2", "name": "RH Chicago", "street": "", "city": "Chicago", "state": "IL", "zip": "", "e911_status": "pending"},
            {"site_id": "S3a", "name": "RH Dallas", "street": "5 Oak", "city": "Dallas", "state": "TX", "zip": "75201", "e911_status": "validated"},
            {"site_id": "S3b", "name": "RH Dallas", "street": "5 Oak", "city": "Dallas", "state": "TX", "zip": "75201", "e911_status": "validated"},
        ],
        "devices": [{"device_id": "D1", "site_id": "S1", "model": "MS130", "device_type": "fire_alarm", "msisdn": "6175550100"}],
        "units": [
            {"unit_id": "U1", "site_id": "S1", "unit_type": "fire_alarm", "device_id": "D1", "line_id": None},
            {"unit_id": "U3", "site_id": "S3a", "unit_type": "elevator_phone", "device_id": None, "line_id": "L3"},
        ],
        "lines": [{"line_id": "L3", "site_id": "S3a", "did": "617-555-0100"}],   # dup of D1 msisdn
    }


def _zoho():
    return [
        {"zoho_id": "Z1", "name": "RH Boston", "street": "9 Elsewhere", "city": "Boston", "state": "MA", "phone": None},  # addr mismatch
        {"zoho_id": "Z2", "name": "RH Nowhere", "street": "", "city": "", "state": "", "phone": None},                    # missing in T911
    ]


def test_reconcile_flags_every_condition():
    r = rz.reconcile(_fixture(), _zoho())
    kinds = r["summary"]["by_kind"]
    for expect in (rz.KIND_ZOHO_MISSING, rz.KIND_T911_MISSING, rz.KIND_ADDR_MISMATCH,
                   rz.KIND_MISSING_DEVICE, rz.KIND_MISSING_UNIT, rz.KIND_MISSING_CALLBACK,
                   rz.KIND_E911_UNVERIFIED, rz.KIND_DUP_SITES, rz.KIND_DUP_PHONES):
        assert kinds.get(expect, 0) >= 1, f"missing flag: {expect}"
    assert r["summary"]["true911_sites"] == 4 and r["summary"]["zoho_locations"] == 2


def test_reconcile_clean_when_everything_matches():
    t = {"tenant": "rh", "sites": [
        {"site_id": "S1", "name": "RH Boston", "street": "1 Main", "city": "Boston", "state": "MA", "zip": "02116", "e911_status": "verified"}],
        "devices": [{"device_id": "D1", "site_id": "S1", "msisdn": "6175550100", "model": "x", "device_type": "fire_alarm"}],
        "units": [{"unit_id": "U1", "site_id": "S1", "unit_type": "fire_alarm", "device_id": "D1", "line_id": None}],
        "lines": []}
    z = [{"zoho_id": "Z1", "name": "RH Boston", "street": "1 Main", "city": "Boston", "state": "MA", "phone": "6175550100"}]
    r = rz.reconcile(t, z)
    assert r["summary"]["findings_total"] == 0   # fully reconciled -> no findings


# ── read-only Zoho fetch (mocked; never writes) ──────────────────────
def test_fetch_zoho_uses_integration_read_only(monkeypatch):
    from app.services import zoho_crm
    calls = {"n": 0}

    async def _fake_fetch(module="Accounts", **kw):
        calls["n"] += 1
        return [{"id": "z1", "Account_Name": "RH Boston", "Billing_City": "Boston", "Phone": "6175550100"}]
    monkeypatch.setattr(zoho_crm, "fetch_records", _fake_fetch)
    out = asyncio.run(rz.fetch_zoho("Accounts"))
    assert calls["n"] == 1 and out[0]["name"] == "RH Boston" and out[0]["city"] == "Boston"


# ── --fields support (the hotfix) ────────────────────────────────────
def test_resolve_fields_default_and_override():
    # default Accounts field set when --fields omitted
    assert rz.resolve_fields("Accounts", None) == rz.DEFAULT_ACCOUNT_FIELDS
    assert "Billing_Street" in rz.DEFAULT_ACCOUNT_FIELDS and "Phone" in rz.DEFAULT_ACCOUNT_FIELDS
    # explicit --fields overrides
    assert rz.resolve_fields("Accounts", "Account_Name,Phone") == "Account_Name,Phone"
    # non-Accounts module with no --fields -> None (Zoho default)
    assert rz.resolve_fields("Custom_Module", None) is None


def test_fetch_zoho_sends_fields_param(monkeypatch):
    from app.services import zoho_crm
    seen = {}

    async def _fake_fetch(module="Accounts", *, fields=None, **kw):
        seen["module"] = module
        seen["fields"] = fields
        return []
    monkeypatch.setattr(zoho_crm, "fetch_records", _fake_fetch)

    # default: safe Accounts fields are sent
    asyncio.run(rz.fetch_zoho("Accounts"))
    assert seen["fields"] == rz.DEFAULT_ACCOUNT_FIELDS
    # override wins
    asyncio.run(rz.fetch_zoho("Accounts", "Account_Name,Phone"))
    assert seen["fields"] == "Account_Name,Phone"


def test_zoho_crm_fetch_records_passes_fields_to_get(monkeypatch):
    # zoho_crm.fetch_records must place `fields` into the Zoho GET params (read-only)
    from app.services import zoho_crm
    captured = {}

    async def _fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return {"data": [{"id": "1"}], "info": {"more_records": False}}
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)
    monkeypatch.setattr(zoho_crm, "_zoho_get", _fake_get)
    asyncio.run(zoho_crm.fetch_records("Accounts", fields="Account_Name,Phone"))
    assert captured["params"]["fields"] == "Account_Name,Phone"
    assert captured["path"] == "/Accounts"


def test_write_markdown_report(tmp_path):
    r = rz.reconcile(_fixture(), _zoho())
    md = tmp_path / "report.md"
    rz.write_markdown_report(str(md), r)
    text = md.read_text(encoding="utf-8")
    for header in ("## A. Matched locations", "## B. Inconsistencies",
                   "## C. Needs investigation", "## D. True911 sync punch list"):
        assert header in text
    assert "READ-ONLY" in text and "never auto-verified" in text


# ── output artifacts ─────────────────────────────────────────────────
def test_write_csv_and_json(tmp_path):
    r = rz.reconcile(_fixture(), _zoho())
    csv_path = tmp_path / "recon.csv"
    json_path = tmp_path / "recon.json"
    rz.write_csv(str(csv_path), r["findings"])
    rz.write_json(str(json_path), r)

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(rows) == r["summary"]["findings_total"]
    assert set(rows[0].keys()) == {"kind", "severity", "zoho_id", "zoho_name", "site_id", "site_name", "detail"}

    doc = json.loads(json_path.read_text(encoding="utf-8"))
    assert doc["summary"]["findings_total"] == len(r["findings"])
    assert "by_kind" in doc["summary"]
