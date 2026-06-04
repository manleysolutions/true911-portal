"""Tests for the asset liveness audit (pure disposition logic, no DB)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from app.audit_asset_liveness import (
    classify_disposition,
    msisdn_variants,
    _most_recent,
    to_report,
)

UTC = _dt.timezone.utc
NOW = _dt.datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def _asset(**kw):
    base = {"msisdn": "7869600498", "device_id": "D1", "line_id": "L1",
            "site_id": "S1", "customer_id": 5, "device_status": "active",
            "line_status": "active", "last_heartbeat": None,
            "last_network_event": None, "last_call_at": None, "last_telemetry_at": None}
    base.update(kw)
    return base


# ── msisdn variants ──────────────────────────────────────────────────────
def test_msisdn_variants():
    v = msisdn_variants("7869600498")
    assert "7869600498" in v and "17869600498" in v and "+17869600498" in v
    assert msisdn_variants(None) == [] and msisdn_variants("") == []
    assert "7869600498" in msisdn_variants("+1 (786) 960-0498")


def test_most_recent_handles_naive_and_none():
    a = _dt.datetime(2026, 1, 1)            # naive
    b = _dt.datetime(2026, 5, 1, tzinfo=UTC)
    assert _most_recent(None, a, b) == b
    assert _most_recent(None, None) is None


# ── disposition ──────────────────────────────────────────────────────────
def test_active_recent_and_status_active():
    a = _asset(last_heartbeat=NOW - _dt.timedelta(days=2), device_status="active")
    assert classify_disposition(a, now=NOW) == "active"


def test_inactive_when_stale():
    a = _asset(last_heartbeat=NOW - _dt.timedelta(days=120), device_status="active")
    assert classify_disposition(a, now=NOW) == "inactive"


def test_inactive_when_no_signals():
    a = _asset(last_heartbeat=None, last_network_event=None,
               last_call_at=None, last_telemetry_at=None)
    assert classify_disposition(a, now=NOW) == "inactive"


def test_inactive_when_recent_but_status_not_active():
    a = _asset(last_heartbeat=NOW - _dt.timedelta(days=1),
               device_status="decommissioned", line_status="disconnected")
    assert classify_disposition(a, now=NOW) == "inactive"


def test_active_via_call_activity():
    a = _asset(last_heartbeat=None, last_call_at=NOW - _dt.timedelta(days=3),
               device_status="active")
    assert classify_disposition(a, now=NOW) == "active"


def test_orphaned_when_no_customer():
    a = _asset(customer_id=None)
    assert classify_disposition(a, now=NOW) == "orphaned"


def test_unknown_when_no_device_or_line():
    a = _asset(device_id=None, line_id=None)
    assert classify_disposition(a, now=NOW) == "unknown"


# ── report assembly ──────────────────────────────────────────────────────
def test_to_report_summary_and_flags():
    rows = [
        _asset(msisdn="A", last_heartbeat=NOW - _dt.timedelta(days=1)),   # active
        _asset(msisdn="B", last_heartbeat=NOW - _dt.timedelta(days=99)),  # inactive
        _asset(msisdn="C", customer_id=None),                             # orphaned
        _asset(msisdn="D", device_id=None, line_id=None),                 # unknown
    ]
    rep = to_report(rows, NOW)
    assert rep["read_only"] is True
    assert rep["summary"] == {"active": 1, "inactive": 1, "orphaned": 1, "unknown": 1}
    assert all("disposition" in a and "disposition_reason" in a for a in rep["assets"])


# ── read-only / no writes ────────────────────────────────────────────────
def test_read_only_no_db_writes():
    src = Path(__file__).resolve().parents[1].joinpath(
        "app", "audit_asset_liveness.py").read_text(encoding="utf-8")
    lower = src.lower()
    for forbidden in ("commit", "flush(", "setattr(", "db.add", "session.add",
                      "db.delete", "db.merge", "db.bulk", "add_all",
                      "insert into", "update ", "delete from"):
        assert forbidden not in lower, f"audit must be read-only; found {forbidden!r}"
    assert "select(" in src
