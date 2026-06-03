"""PR #72 — Vola telemetry reliability.

Covers the hardened lastUpdateTime parser (string layouts + epoch + alternate
keys + safe fallback), that an online Vola device writes last_heartbeat and
network_status=online, that a fresh heartbeat clears DEVICE_OFFLINE through the
normalizer + assurance engine, and that no raw vendor payload reaches a customer
view.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.assurance.engine import compute_site_assurance
from app.services.assurance import reason_codes as a_rc
from app.services.assurance.signals import AssuranceSignals, DeviceSignal
from app.services.device_health.adapters.vola import (
    VolaCloudAdapter,
    _parse_vola_timestamp,
    _select_heartbeat_value,
    heartbeat_debug_fields,
)
from app.services.device_health.models import DeviceHealth, VendorStatus
from app.services.device_health.status import NormalizedStatus
from app.services.health import HealthSignals, compute_device_state
from app.sync_device_health import compute_device_updates
from app.config import settings

NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


class _FakeVola:
    def __init__(self, devices):
        self._devices = devices

    async def get_device_list(self, usage_status="inUse"):
        return {"deviceList": self._devices}


# ── Parser: string layouts ───────────────────────────────────────────
@pytest.mark.parametrize("raw,expect_year,expect_hour", [
    ("Jun 01 2026 09:00", 2026, 9),
    ("Jun 01 2026 09:00:00", 2026, 9),
    ("2026-06-01 09:00:00", 2026, 9),
    ("2026-06-01 09:00", 2026, 9),
    ("2026/06/01 09:00:00", 2026, 9),
    ("06/01/2026 09:00:00", 2026, 9),
    ("Jun 01, 2026 09:00:00", 2026, 9),
    ("01 Jun 2026 09:00:00", 2026, 9),
    ("2026-06-01T09:00:00Z", 2026, 9),
    ("2026-06-01T09:00:00+00:00", 2026, 9),
])
def test_parser_string_layouts(raw, expect_year, expect_hour):
    ts = _parse_vola_timestamp(raw)
    assert ts is not None and ts.tzinfo is not None
    assert ts.year == expect_year and ts.hour == expect_hour


# ── Parser: epoch seconds / milliseconds ─────────────────────────────
def test_parser_epoch_seconds_and_millis():
    epoch_s = int(NOW.timestamp())
    epoch_ms = epoch_s * 1000
    assert _parse_vola_timestamp(epoch_s) == NOW
    assert _parse_vola_timestamp(str(epoch_s)) == NOW
    assert _parse_vola_timestamp(epoch_ms) == NOW
    assert _parse_vola_timestamp(str(epoch_ms)) == NOW


# ── Parser: safe fallback (never fabricates) ─────────────────────────
@pytest.mark.parametrize("raw", [None, "", "   ", "not a date", "Online", {}, [], 0])
def test_parser_fallback_none(raw):
    # 0 epoch (1970) is outside the trusted 2000–2100 window → None.
    assert _parse_vola_timestamp(raw) is None


# ── Alternate heartbeat keys ─────────────────────────────────────────
def test_alternate_heartbeat_keys():
    assert _select_heartbeat_value({"lastUpdateTime": "x"})[0] == "lastUpdateTime"
    # falls back to an alternate when lastUpdateTime absent
    key, val = _select_heartbeat_value({"updateTime": "2026-06-01 09:00:00"})
    assert key == "updateTime" and val == "2026-06-01 09:00:00"
    assert _select_heartbeat_value({"nothing": 1})[0] is None


@pytest.mark.asyncio
async def test_adapter_uses_alternate_key(monkeypatch):
    monkeypatch.setattr(settings, "VOLA_EMAIL", "x@example.com")
    monkeypatch.setattr(settings, "VOLA_PASSWORD", "pw")
    # No lastUpdateTime; only an epoch-ms 'updateTime'.
    epoch_ms = int(NOW.timestamp()) * 1000
    client = _FakeVola([{"deviceSN": "VOLA00325600227", "status": "Online",
                         "updateTime": epoch_ms}])
    vs = await VolaCloudAdapter(client=client).probe(serial="VOLA00325600227")
    assert vs.normalized_status == NormalizedStatus.ONLINE
    assert vs.last_seen == NOW


# ── Online device writes last_heartbeat + network_status=online ──────
def test_online_writes_heartbeat_and_network_status():
    vs = VendorStatus(vendor="vola", available=True,
                      normalized_status=NormalizedStatus.ONLINE,
                      firmware="1.0.9", static_ip="10.0.0.5", last_seen=NOW)
    ch = compute_device_updates([vs], now=NOW)["device"]
    assert ch["last_heartbeat"] == NOW       # primary liveness signal
    assert ch["network_status"] == "online"
    assert ch["vola_last_sync"] == NOW
    assert ch["firmware_version"] == "1.0.9"
    assert ch["wan_ip"] == "10.0.0.5"


def test_online_without_parseable_heartbeat_still_marks_sync():
    # last_seen unparsed → no last_heartbeat, but vola_last_sync proxy is set.
    vs = VendorStatus(vendor="vola", available=True,
                      normalized_status=NormalizedStatus.ONLINE, last_seen=None)
    ch = compute_device_updates([vs], now=NOW)["device"]
    assert "last_heartbeat" not in ch
    assert ch["vola_last_sync"] == NOW
    assert ch["network_status"] == "online"


# ── Fresh heartbeat clears DEVICE_OFFLINE (normalizer + assurance) ───
def test_fresh_heartbeat_makes_device_connected():
    signals = HealthSignals(last_heartbeat_at=NOW, device_lifecycle="active")
    assert compute_device_state(signals, now=NOW).value == "connected"


def test_assurance_no_device_offline_when_heartbeat_fresh():
    # Operational state derived from a fresh heartbeat = connected.
    op = compute_device_state(
        HealthSignals(last_heartbeat_at=NOW, device_lifecycle="active"), now=NOW
    ).value
    sig = AssuranceSignals(
        tenant_id="integrity-pm", site_id="IPM-BELLE-TERRE",
        site_lifecycle_status="active", onboarding_status="active",
        e911_address_present=True, e911_status="provided",   # still unverified
        devices=(DeviceSignal(device_id="VOLA00325600226", operational_state=op,
                              device_lifecycle="active"),),
        last_test=None,
    )
    res = compute_site_assurance(sig, now=NOW)
    codes = set(res.reason_codes)
    assert a_rc.DEVICE_OFFLINE.code not in codes          # offline is gone
    # E911 still unverified + no test → still Critical/Attention (unchanged rules)
    assert a_rc.E911_UNVERIFIED.code in codes
    assert a_rc.TEST_MISSING.code in codes


def test_stale_heartbeat_still_offline():
    # A heartbeat older than the staleness window remains OFFLINE — the fix does
    # not weaken the engine or fabricate freshness.
    old = NOW - timedelta(minutes=30)
    assert compute_device_state(
        HealthSignals(last_heartbeat_at=old, device_lifecycle="active"), now=NOW
    ).value == "offline"


# ── Debug helper is safe (named fields only, no payload leak) ────────
def test_debug_fields_named_only():
    raw = {"deviceSN": "VOLA00325600230", "status": "Online",
           "lastUpdateTime": "2026-06-03 12:00:00", "softwareVersion": "1.0.9",
           "ip": "10.0.0.6", "rssi": "-70", "secretSession": "should-not-appear"}
    out = heartbeat_debug_fields(raw)
    assert out["deviceSN"] == "VOLA00325600230"
    assert out["_heartbeat_key_used"] == "lastUpdateTime"
    assert out["_parsed_last_seen"].startswith("2026-06-03T12:00")
    assert "secretSession" not in out      # only named fields are surfaced


def test_customer_view_has_no_raw_payload():
    dh = DeviceHealth(
        tenant_id="integrity-pm", device_id="VOLA00325600226",
        model="LM150", status=NormalizedStatus.ONLINE, last_heartbeat=NOW,
        last_check_in=NOW, recommended_action="No action needed.")
    v = dh.to_customer_view()
    assert "raw_payload" not in v and "vendors" not in v and "vola_org_id" not in v
