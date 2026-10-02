"""Canonical loader - the Zoho Starlink / radio field is found by its LABEL.

Production regression (2026-10-02 post-#205 dry-run: ``radio_fields=[]``): a
Zoho custom field keeps the API name it was created with, so the field the UI
labels "Starlink ID" can have an API name that says nothing about Starlink.
Discovery matched API names only, never requested the field, and every Zoho
FACP record lost its radio and split into an extra ``FACP:zoho:`` service.

The live loader runs here against a mocked Zoho API (no network).  Every
identifier is SYNTHETIC.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services import zoho_crm
from app.services.canonical import engine, loader
from app.services.canonical import vocab as V
from tests.test_canonical_engine import _facp_device, pin, site, snap

SERIAL = "209901010000027"
IMEI = "860000000000017"

META = [
    {"api_name": "Device_Number_1", "field_label": "Starlink ID"},   # relabelled field
    {"api_name": "Device_ID", "field_label": "Device ID"},           # MS130 serial lives here
    {"api_name": "Serial_Number", "field_label": "Serial Number"},
    {"api_name": "Device_IMEI", "field_label": "Device IMEI"},
    {"api_name": "SIM_Number", "field_label": "SIM Number"},
    {"api_name": "Starlink_Plan", "field_label": "Starlink Plan"},   # attribute, not an id
    {"api_name": "Phone_2", "field_label": "Starlink ID (old)"},     # a phone field: refused
] + [{"api_name": "Facility_Extra_%02d" % i, "field_label": "Facility %d" % i}
     for i in range(60)]                                             # crowds the 50-field cap


def rec(zid, facility, ctype, radio=None, msisdn=None, serial=None, imei=None,
        status="Activated"):
    return {"id": zid, "FacilityName": facility, "Account": None, "Parent_Account": None,
            "MSISDN": msisdn, "Connection_Type": ctype, "Subscription_Type": None,
            "Device_Activation_Status": status, "Modified_Time": "2026-09-01T00:00:00+00:00",
            "Device_Number_1": radio, "Serial_Number": serial, "Device_IMEI": imei,
            "Device_ID": serial}


RECORDS = [
    rec("Z578", "RH Princeton", "Alarm Panel", radio="77187020"),
    rec("Z265", "RH Princeton", "Alarm Panel", radio="7187020"),          # dropped digit
    rec("Z264", "RH Houston #130", "Alarm Panel", radio="7700387"),
    # a telephone line labelled Alarm Panel whose radio field holds the serial
    rec("Z496", "RH Houston #130", "Alarm Panel", radio=SERIAL, msisdn="2025550170",
        serial=SERIAL, imei=IMEI),
]


def _fetch(meta=META, records=RECORDS, monkeypatch=None):
    calls = []

    async def fake_get(path, params=None):
        calls.append((path, dict(params or {})))
        if path == "/settings/fields":
            return {"fields": meta}
        return {"data": records, "info": {"more_records": False}}
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)
    monkeypatch.setattr(zoho_crm, "_zoho_get", fake_get)
    rows, info = asyncio.run(loader.fetch_zoho_rows(lambda *a: True))
    return rows, info, calls


def test_relabelled_starlink_field_is_requested_despite_the_field_cap(monkeypatch):
    _rows, info, calls = _fetch(monkeypatch=monkeypatch)
    requested = next(p["fields"] for path, p in calls if path == "/Subscription_Mgmnt").split(",")
    assert len(requested) == loader.ZOHO_MAX_FIELDS
    assert "Device_Number_1" in requested
    assert info["radio_fields"] == ["Device_Number_1 (Starlink ID)"]
    for not_radio in ("Phone_2", "Starlink_Plan", "Device_ID", "Serial_Number"):
        assert not any(f.startswith(not_radio + " ") for f in info["radio_fields"])


def test_radio_value_survives_normalization_and_identifier_roles_use_labels(monkeypatch):
    rows, _info, _c = _fetch(monkeypatch=monkeypatch)
    by_id = {r["zoho_id"]: r for r in rows}
    assert by_id["Z578"]["starlink"] == "77187020"
    assert by_id["Z264"]["starlink"] == "7700387"
    assert (by_id["Z496"]["imei"], by_id["Z496"]["serial"]) == (IMEI, SERIAL)


def _project(monkeypatch, **kw):
    rows, info, _c = _fetch(monkeypatch=monkeypatch, **kw)
    s = snap(zoho_rows=rows, sites=[site("S-P", "RH Princeton")],
             devices=[_facp_device("FP", "S-P", "77187020")], mappings=pin(4, "7700387"))
    s["sources"]["zoho"] = info
    return engine.project(s)


def _facps(res, bid):
    return {s["service_key"]: s for s in res["services"]
            if s["building_id"] == bid and s["service_type"] == V.FACP}


def test_zoho_record_joins_its_radio_and_creates_no_extra_zoho_service(monkeypatch):
    res = _project(monkeypatch)
    princeton, houston = _facps(res, 7), _facps(res, 4)
    assert not [k for k in list(princeton) + list(houston) if k.startswith("FACP:zoho:")]
    p = princeton["FACP:radio:77187020"]
    assert V.SRC_ZOHO in p["provenance"]["sources"] and V.SRC_TRUE911 in p["provenance"]["sources"]
    assert any("zoho:Z578" in e for e in p["evidence"])
    h = houston["FACP:radio:7700387"]
    assert V.SRC_ZOHO in h["provenance"]["sources"]
    assert list(houston) == ["FACP:radio:7700387"]               # one Houston FACP


def test_a_stale_dropped_digit_radio_is_not_fuzzy_merged(monkeypatch):
    princeton = _facps(_project(monkeypatch), 7)
    assert sorted(princeton) == ["FACP:radio:7187020", "FACP:radio:77187020"]
    assert princeton["FACP:radio:7187020"]["provenance"]["sources"] == [V.SRC_ZOHO]


def test_serial_imei_and_phone_values_are_still_never_radio_identities(monkeypatch):
    res = _project(monkeypatch)
    radios = [a["normalized_value"] for a in res["assets"].values()
              if a["asset_type"] == V.NAPCO_RADIO]
    assert SERIAL not in radios and IMEI not in radios and "2025550170" not in radios
    assert any(f["code"] == "RADIO_ID_REJECTED" and "zoho:Z496" in f["subject"]
               for f in res["findings"])


@pytest.mark.parametrize("api,label,radio", [
    ("Starlink_ID", "Starlink ID", True), ("Device_Number_1", "Starlink ID", True),
    ("RadioNumber", "", True), ("Field_9", "Radio Number", True),
    ("Starlink_Serial", "Radio", False), ("Phone_2", "Starlink ID", False),
    ("Starlink_Status", "Starlink Status", False), ("Device_ID", "Device ID", False),
    ("SIM_Number", "Starlink SIM", False)])
def test_radio_field_rule_reads_api_name_and_label_conservatively(api, label, radio):
    assert loader._is_radio_field(api, label) is radio


def test_a_live_pull_without_a_radio_field_is_a_high_finding(monkeypatch):
    meta = [m for m in META if m["api_name"] != "Device_Number_1"]
    res = _project(monkeypatch, meta=meta)
    f = [x for x in res["findings"] if x["code"] == "ZOHO_RADIO_FIELD_MISSING"]
    assert f and f[0]["severity"] == V.HIGH


def test_discovery_failure_falls_back_to_api_name_rules(monkeypatch):
    async def failing_get(path, params=None):
        if path == "/settings/fields":
            raise RuntimeError("metadata unavailable")
        return {"data": [rec("Z1", "RH Princeton", "Alarm Panel") | {"Starlink_ID": "77187020"}],
                "info": {"more_records": False}}
    monkeypatch.setattr(zoho_crm, "is_configured", lambda: True)
    monkeypatch.setattr(zoho_crm, "_zoho_get", failing_get)
    rows, info = asyncio.run(loader.fetch_zoho_rows(lambda *a: True))
    assert info["field_discovery"].startswith("failed")
    assert rows[0]["starlink"] == "77187020"
