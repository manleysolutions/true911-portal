"""Tests for the RH telemetry ingestion (pure readiness + staleness guard)."""

from __future__ import annotations

import datetime as _dt

from app.sync_rh_device_telemetry import (
    ALLOWED_DEVICE_FIELDS,
    MANUAL_REQUIRED,
    READY,
    TELEMETRY_PENDING,
    UNMAPPED,
    classify_telemetry_readiness,
    compute_and_guard,
    guard_stale_updates,
    has_required_identifier,
    safe_device_report,
)

UTC = _dt.timezone.utc


def _dev(**kw):
    base = dict(device_id="RH-1", serial_number=None, imei=None, iccid=None, msisdn=None)
    base.update(kw)
    return base


# ── readiness classification ─────────────────────────────────────────────
def test_ready_when_vola_configured_and_identifier_present():
    r = classify_telemetry_readiness(_dev(serial_number="SN1"), ["vola"], {"vola": True})
    assert r["telemetry_class"] == READY and r["can_produce_heartbeat"] is True
    assert r["live_source_exists"] is True


def test_pending_when_vola_unconfigured_missing_credentials():
    r = classify_telemetry_readiness(_dev(serial_number="SN1"), ["vola"], {"vola": False})
    assert r["telemetry_class"] == TELEMETRY_PENDING
    assert "not configured" in r["reason"]
    assert r["live_source_exists"] is False


def test_pending_when_vola_configured_but_no_identifier():
    r = classify_telemetry_readiness(_dev(), ["vola"], {"vola": True})
    assert r["telemetry_class"] == TELEMETRY_PENDING
    assert "missing" in r["reason"] and r["can_produce_heartbeat"] is False


def test_pending_when_telnyx_stub():
    r = classify_telemetry_readiness(_dev(), ["telnyx"], {"telnyx": False})
    assert r["telemetry_class"] == TELEMETRY_PENDING
    assert "not implemented" in r["reason"]


def test_manual_required_when_no_live_or_pending_adapter():
    r = classify_telemetry_readiness(_dev(), ["future"], {"future": False})
    assert r["telemetry_class"] == MANUAL_REQUIRED
    assert "record a manual verification test" in r["reason"]


def test_unmapped_when_no_probe_vendors():
    r = classify_telemetry_readiness(_dev(), [], {})
    assert r["telemetry_class"] == UNMAPPED
    assert "backfill" in r["reason"]


def test_tmobile_identifier_rules():
    assert has_required_identifier("tmobile", _dev(msisdn="8135550100")) is True
    assert has_required_identifier("tmobile", _dev(iccid="8901" + "0" * 15)) is True
    assert has_required_identifier("tmobile", _dev()) is False
    assert has_required_identifier("vola", _dev(imei="35")) is True


# ── staleness guard (never overwrite fresher with staler) ────────────────
def test_guard_drops_stale_heartbeat():
    fresh = _dt.datetime(2026, 6, 1, tzinfo=UTC)
    stale = _dt.datetime(2026, 5, 1, tzinfo=UTC)
    kept, notes = guard_stale_updates({"last_heartbeat": stale}, {"last_heartbeat": fresh})
    assert "last_heartbeat" not in kept
    assert any("skipped stale last_heartbeat" in n for n in notes)


def test_guard_keeps_fresher_heartbeat():
    older = _dt.datetime(2026, 5, 1, tzinfo=UTC)
    newer = _dt.datetime(2026, 6, 1, tzinfo=UTC)
    kept, _ = guard_stale_updates({"last_heartbeat": newer}, {"last_heartbeat": older})
    assert kept["last_heartbeat"] == newer


def test_guard_applies_when_no_current_value():
    newer = _dt.datetime(2026, 6, 1, tzinfo=UTC)
    kept, _ = guard_stale_updates({"last_heartbeat": newer}, {"last_heartbeat": None})
    assert kept["last_heartbeat"] == newer


def test_guard_passes_through_non_timestamp_fields():
    kept, _ = guard_stale_updates({"network_status": "online", "firmware_version": "1.2"}, {})
    assert kept == {"network_status": "online", "firmware_version": "1.2"}


def test_guard_ignores_non_whitelisted_fields():
    kept, notes = guard_stale_updates({"e911_status": "validated", "status": "active"}, {})
    assert kept == {}
    assert any("ignored non-telemetry field" in n for n in notes)


def test_e911_and_lifecycle_not_writable():
    assert "e911_status" not in ALLOWED_DEVICE_FIELDS
    assert "status" not in ALLOWED_DEVICE_FIELDS


# ── compute + guard integration (stale vendor vs fresh DB) ───────────────
def _vola_status(*, last_seen, online=True):
    from app.services.device_health.models import VendorStatus
    from app.services.device_health.status import NormalizedStatus
    return VendorStatus(vendor="vola",
                        normalized_status=NormalizedStatus.ONLINE if online else NormalizedStatus.OFFLINE,
                        last_seen=last_seen, firmware="2.0")


def test_stale_vendor_does_not_overwrite_fresh_db_heartbeat():
    now = _dt.datetime(2026, 6, 2, tzinfo=UTC)
    fresh_db = _dt.datetime(2026, 6, 1, tzinfo=UTC)
    stale_vendor = _dt.datetime(2026, 1, 1, tzinfo=UTC)
    kept, notes = compute_and_guard(
        [_vola_status(last_seen=stale_vendor)],
        current={"last_heartbeat": fresh_db, "last_network_event": None, "vola_last_sync": None},
        now=now)
    # heartbeat NOT moved backwards, but online liveness/firmware still recorded
    assert "last_heartbeat" not in kept["device"]
    assert kept["device"].get("vola_last_sync") == now
    assert kept["device"].get("firmware_version") == "2.0"
    assert any("skipped stale" in n for n in notes)


def test_fresh_vendor_updates_heartbeat():
    now = _dt.datetime(2026, 6, 2, tzinfo=UTC)
    old_db = _dt.datetime(2026, 1, 1, tzinfo=UTC)
    new_vendor = _dt.datetime(2026, 6, 1, tzinfo=UTC)
    kept, _ = compute_and_guard(
        [_vola_status(last_seen=new_vendor)],
        current={"last_heartbeat": old_db, "last_network_event": None, "vola_last_sync": None},
        now=now)
    assert kept["device"]["last_heartbeat"] == new_vendor


# ── no raw payload exposed ───────────────────────────────────────────────
def test_safe_report_excludes_raw_payload():
    report = safe_device_report(
        "RH-1",
        {"telemetry_class": READY, "reason": "ok"},
        [{"vendor": "vola", "available": True, "status": "online", "reasons": [], "error": None}],
        {"last_heartbeat": _dt.datetime(2026, 6, 1, tzinfo=UTC)})
    flat = repr(report)
    assert "raw_payload" not in flat and "raw_status" not in flat
    assert report["vendors"][0]["vendor"] == "vola"
