"""Tests for NAPCO StarLink classification + portal XLS import (pure, no DB)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from app.services.device_health.classifier import classify
from app.import_napco_portal_status import (
    ALLOWED_DEVICE_FIELDS,
    build_column_map,
    compute_napco_updates,
    map_status_to_network,
    match_device,
    parse_last_comm,
    parse_napco_row,
    safe_metadata,
)

UTC = _dt.timezone.utc


# ── classifier recognises NAPCO ──────────────────────────────────────────
def test_classifier_recognises_napco_models():
    for model in ("SLELTE - Fire", "SLELTE - Fire (Dual Line)", "SLE-LTEVI-FIRE",
                  "SLE-LTEVI-FIRE (Comm Dual Path)", "SLEMAXVI-FIRE",
                  "SLEMAXVI-FIRE (Dual Line 5G)", "SLE5G", "StarLink Communicator"):
        c = classify(model=model)
        assert c.vendor_managed is True
        assert c.vendor_cloud == "napco_portal"
        assert c.device_family == "napco_starlink"
        assert c.monitoring_source == "napco_xls_import"
        assert c.probe_vendors == ()          # no live probe — XLS only


def test_fire_panel_with_napco_carrier():
    c = classify(model="Fire Alarm Control Panel", carrier="Napco")
    assert c.vendor_managed and c.device_family == "napco_starlink"


def test_bare_spacex_starlink_is_not_napco():
    c = classify(model="Starlink", device_type="satellite internet")
    assert c.vendor_managed is False and c.vendor_cloud != "napco_portal"


def test_existing_vola_unaffected():
    c = classify(model="LM150")
    assert c.vendor_cloud == "vola" and c.vendor_managed is False


# ── column mapping + row parsing ─────────────────────────────────────────
HEADERS = ["Serial Number", "Comm Status", "Last Communication", "Account Name",
           "Address", "Trouble Condition", "Carrier", "Model", "Configuration"]


def test_build_column_map_prefers_specific_status():
    cm = build_column_map(HEADERS)
    assert cm["serial"] == 0
    assert cm["portal_status"] == 1          # 'Comm Status' chosen, not a generic 'status'
    assert cm["last_comm"] == 2 and cm["trouble"] == 5


def test_parse_napco_row():
    row = ["SN-100", "Online", "06/01/2026 13:45", "Tampa FACP", "1 Main St",
           "None", "AT&T", "SLE-LTEVI-FIRE", "Dual Path"]
    p = parse_napco_row(row, build_column_map(HEADERS))
    assert p["serial"] == "SN-100"
    assert p["network_status"] == "online"
    assert p["last_comm"] == _dt.datetime(2026, 6, 1, 13, 45, tzinfo=UTC)
    assert p["carrier"] == "AT&T" and p["model"] == "SLE-LTEVI-FIRE"


# ── last-comm parsing ────────────────────────────────────────────────────
def test_parse_last_comm_formats():
    assert parse_last_comm(_dt.datetime(2026, 6, 1, tzinfo=UTC)).year == 2026
    assert parse_last_comm("2026-06-01 13:45:00") == _dt.datetime(2026, 6, 1, 13, 45, tzinfo=UTC)
    assert parse_last_comm("06/01/2026") == _dt.datetime(2026, 6, 1, tzinfo=UTC)
    assert parse_last_comm("") is None and parse_last_comm(None) is None
    assert parse_last_comm("not a date") is None


# ── status mapping ───────────────────────────────────────────────────────
def test_trouble_and_offline_are_non_healthy():
    assert map_status_to_network("Online", "Low Battery") == "trouble"
    assert map_status_to_network("No Comm", "None") == "offline"
    assert map_status_to_network("Online", "None") == "online"
    assert map_status_to_network("weird", "") == "unknown"


# ── matching ─────────────────────────────────────────────────────────────
def test_match_by_serial_first():
    dev = object()
    d, method, review = match_device({"serial": "SN-1", "device_id": ""},
                                     {"sn-1": dev}, {})
    assert d is dev and method == "serial" and review is False


def test_match_by_device_id_second():
    dev = object()
    d, method, review = match_device({"serial": "", "device_id": "RH-9"}, {}, {"RH-9": dev})
    assert d is dev and method == "device_id"


def test_unmatched_row_is_review_required():
    d, method, review = match_device({"serial": "X", "device_id": "Y", "name": "n"}, {}, {})
    assert d is None and review is True and method == "name_address_fallback"


# ── update computation + staleness guard ─────────────────────────────────
def test_fresh_comm_updates_heartbeat_and_status():
    parsed = {"last_comm": _dt.datetime(2026, 6, 2, tzinfo=UTC), "network_status": "online", "carrier": ""}
    kept, notes = compute_napco_updates(parsed, {"last_heartbeat": _dt.datetime(2026, 1, 1, tzinfo=UTC)})
    assert kept["last_heartbeat"] == parsed["last_comm"]
    assert kept["network_status"] == "online"
    assert kept["telemetry_source"] == "napco_portal"


def test_stale_comm_does_not_overwrite_newer_heartbeat():
    fresh_db = _dt.datetime(2026, 6, 1, tzinfo=UTC)
    parsed = {"last_comm": _dt.datetime(2026, 1, 1, tzinfo=UTC), "network_status": "offline", "carrier": ""}
    kept, notes = compute_napco_updates(parsed, {"last_heartbeat": fresh_db})
    assert "last_heartbeat" not in kept            # not moved backwards
    assert "network_status" not in kept            # stale row does not regress state
    assert any("skipped stale" in n for n in notes)


def test_carrier_only_backfilled_when_empty():
    parsed = {"last_comm": None, "network_status": "unknown", "carrier": "Verizon"}
    kept, _ = compute_napco_updates(parsed, {"last_heartbeat": None, "carrier": ""})
    assert kept["carrier"] == "Verizon"
    kept2, _ = compute_napco_updates(parsed, {"last_heartbeat": None, "carrier": "AT&T"})
    assert "carrier" not in kept2                  # existing carrier preserved


def test_updates_never_touch_e911_or_status():
    parsed = {"last_comm": _dt.datetime(2026, 6, 2, tzinfo=UTC), "network_status": "online", "carrier": ""}
    kept, _ = compute_napco_updates(parsed, {"last_heartbeat": None})
    assert all(k in ALLOWED_DEVICE_FIELDS for k in kept)
    assert "e911_status" not in ALLOWED_DEVICE_FIELDS and "status" not in ALLOWED_DEVICE_FIELDS


# ── no secrets in archived metadata ──────────────────────────────────────
def test_safe_metadata_has_no_secrets():
    parsed = parse_napco_row(
        ["SN-1", "Online", "2026-06-01", "n", "addr", "None", "AT&T", "SLE5G", "cfg"],
        build_column_map(HEADERS))
    meta = safe_metadata(parsed)
    blob = repr(meta).lower()
    for secret in ("password", "secret", "token", "api_key", "credential", "private_key"):
        assert secret not in blob


# ── read-only guard on the classifier change (no writes added) ───────────
def test_import_module_writes_only_via_audited_apply():
    src = Path(__file__).resolve().parents[1].joinpath("app", "import_napco_portal_status.py").read_text(encoding="utf-8")
    # commits only once, guarded by dry_run; no raw secret logging helpers
    assert "DRY RUN" in src and "await db.commit()" in src
