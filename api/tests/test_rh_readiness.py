"""Tests for the Restoration Hardware readiness audit (pure helpers only)."""

from __future__ import annotations

from app.audit_rh_readiness import (
    device_identifiers,
    device_monitorable,
    diagnose_device,
    e911_readiness,
    infer_unit_type,
    missing_e911_parts,
    service_unit_gap,
    summarize_scorecard,
)


# ── E911 readiness ───────────────────────────────────────────────────────
def _site(**kw):
    base = dict(e911_street="1 Main St", e911_city="Tampa", e911_state="FL",
                e911_zip="33601", e911_status="provided")
    base.update(kw)
    return base


def test_e911_verified():
    assert e911_readiness(_site(e911_status="validated")) == "verified"
    assert e911_readiness(_site(e911_status="CONFIRMED")) == "verified"


def test_e911_complete_needs_validation():
    # RH's situation: full address, status not yet verified.
    assert e911_readiness(_site(e911_status="provided")) == "address_complete_needs_validation"
    assert e911_readiness(_site(e911_status=None)) == "address_complete_needs_validation"


def test_e911_partial():
    assert e911_readiness(_site(e911_zip="", e911_state="")) == "address_partial"
    assert missing_e911_parts(_site(e911_zip=" ")) == ["e911_zip"]


def test_e911_missing():
    blank = {k: "" for k in ("e911_street", "e911_city", "e911_state", "e911_zip")}
    assert e911_readiness(blank) == "address_missing"
    assert len(missing_e911_parts(blank)) == 4


# ── device monitorability / diagnosis ───────────────────────────────────
def test_device_identifiers():
    assert device_identifiers({"imei": "123"}) == ["imei"]
    assert device_identifiers({"serial_number": "", "msisdn": None}) == []


def test_monitorable_requires_adapter_and_identifier():
    d = {"imei": "35", "last_heartbeat": object()}
    assert device_monitorable(d, ("tmobile",)) is True
    assert device_monitorable(d, ()) is False              # no adapter
    assert device_monitorable({"imei": ""}, ("tmobile",)) is False  # no identifier


def test_diagnose_no_adapter_no_id_no_heartbeat():
    # RH's 0/51 case: unmapped device, no identifiers, never reported.
    reasons = diagnose_device({"last_heartbeat": None}, ())
    joined = " ".join(reasons)
    assert "no vendor adapter" in joined
    assert "no vendor identifiers" in joined
    assert "never reported a heartbeat" in joined


def test_diagnose_clean_device_has_no_reasons():
    d = {"imei": "35", "last_heartbeat": object()}
    assert diagnose_device(d, ("tmobile",)) == []


# ── service-unit inference ───────────────────────────────────────────────
def test_infer_unit_type():
    assert infer_unit_type("Elevator Phone", None) == "elevator_phone"
    assert infer_unit_type(None, "fire panel") == "fire_alarm_line"
    assert infer_unit_type("Cisco ATA", "analog") == "emergency_voice_line"
    assert infer_unit_type("CallBox 9000", None) == "emergency_call_station"
    assert infer_unit_type(None, None) == "emergency_voice_line"   # safe default


def test_service_unit_gap_recommends_when_none():
    devices = [{"site_id": "S1", "device_id": "D1", "model": "Elevator Phone"},
               {"site_id": "S2", "device_id": "D2", "model": "Cisco ATA"}]
    gap = service_unit_gap(0, devices)
    assert gap["has_units"] is False and len(gap["suggestions"]) == 2
    assert gap["suggestions"][0]["suggested_unit_type"] == "elevator_phone"


def test_service_unit_gap_quiet_when_units_exist():
    gap = service_unit_gap(5, [{"site_id": "S1", "device_id": "D1", "model": "x"}])
    assert gap["has_units"] is True and gap["suggestions"] == []


# ── scorecard ────────────────────────────────────────────────────────────
def test_summarize_scorecard():
    s = summarize_scorecard(["Critical", "Critical", "Protected", "Pending Install"])
    assert s["Critical"] == 2 and s["Protected"] == 1 and s["Pending Install"] == 1
    assert s["Unknown"] == 0
    # all six keys always present
    assert set(s) >= {"Protected", "Attention Needed", "Critical",
                      "Inactive / Deactivated", "Pending Install", "Unknown"}
