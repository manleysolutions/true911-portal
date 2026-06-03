"""Table-driven tests for the pure Assurance decision engine.

Covers every label and the key reason codes, plus the life-safety guardrails:
fresh heartbeat + missing/unverified E911 = Critical; commercial-active never
implies healthy; missing data is never Protected; deactivated/pending suppress
alarms; failed test = Critical, missing/stale test = Attention.

Pure functions only — no DB, no flag, no network. Clock is injected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.assurance import reason_codes as rc
from app.services.assurance.engine import compute_site_assurance
from app.services.assurance.signals import (
    AssuranceLabel,
    AssuranceSignals,
    DeviceSignal,
    LineSignal,
    ServiceUnitSignal,
    TestRecord,
)

NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


def _device(state="connected", lifecycle="active", device_id="DEV-1"):
    return DeviceSignal(device_id=device_id, operational_state=state, device_lifecycle=lifecycle)


def _passing_test(days_ago=1):
    return TestRecord(at=NOW - timedelta(days=days_ago), result="pass", source="verification_tasks")


def _signals(**kw):
    base = dict(
        tenant_id="integrity", site_id="IPM-BELLE-TERRE",
        site_name="Belle Terre at Sunrise", customer_name="Integrity Property Management",
        site_lifecycle_status="active", onboarding_status="active",
        e911_address_present=True, e911_status="validated", e911_confirmation_required=False,
        devices=(_device(),), service_units=(), lines=(),
        last_test=_passing_test(),
    )
    base.update(kw)
    return AssuranceSignals(**base)


def _run(**kw):
    return compute_site_assurance(_signals(**kw), now=NOW)


def _codes(res):
    return set(res.reason_codes)


# ── Protected happy path ─────────────────────────────────────────────
def test_protected_happy_path():
    res = _run()
    assert res.label == AssuranceLabel.PROTECTED
    assert rc.OK.code in _codes(res)


# ── E911 gates (Critical even with a fresh/connected device) ─────────
def test_missing_e911_is_critical():
    res = _run(e911_address_present=False, e911_status=None)
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.E911_MISSING.code in _codes(res)


def test_unverified_e911_is_critical():
    res = _run(e911_status="pending")
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.E911_UNVERIFIED.code in _codes(res)


def test_e911_confirmation_required_is_critical():
    res = _run(e911_status="validated", e911_confirmation_required=True)
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.E911_UNVERIFIED.code in _codes(res)


def test_fresh_heartbeat_does_not_hide_missing_e911():
    # Device is connected (fresh) but E911 missing → still Critical.
    res = _run(devices=(_device(state="connected"),), e911_address_present=False)
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.E911_MISSING.code in _codes(res)


# ── Operational gates ────────────────────────────────────────────────
def test_offline_required_device_is_critical():
    res = _run(devices=(_device(state="offline"),))
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.DEVICE_OFFLINE.code in _codes(res)


def test_active_site_no_device_is_critical():
    res = _run(devices=())
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.NO_ACTIVE_DEVICE.code in _codes(res)


def test_active_service_unit_without_device_is_critical():
    unit = ServiceUnitSignal(unit_id="U1", unit_name="Elevator 1", unit_type="elevator_phone",
                             status="active", device_id=None, has_active_device=False)
    res = _run(service_units=(unit,))
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.NO_ACTIVE_DEVICE.code in _codes(res)


def test_voice_path_down_is_critical():
    res = _run(lines=(LineSignal(line_id="L1", status="disconnected", e911_status="validated"),))
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.CARRIER_UNAVAILABLE.code in _codes(res)


# ── Test signal ──────────────────────────────────────────────────────
def test_failed_test_is_critical():
    res = _run(last_test=TestRecord(at=NOW - timedelta(days=1), result="fail", source="verification_tasks"))
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.TEST_FAILED.code in _codes(res)


def test_stale_test_is_attention():
    res = _run(last_test=_passing_test(days_ago=200))
    assert res.label == AssuranceLabel.ATTENTION
    assert rc.TEST_STALE.code in _codes(res)


def test_missing_test_is_attention():
    res = _run(last_test=None)
    assert res.label == AssuranceLabel.ATTENTION
    assert rc.TEST_MISSING.code in _codes(res)


# ── Telemetry missing / degraded → Attention ─────────────────────────
def test_expected_active_no_telemetry_is_attention():
    # provisioning operational state but lifecycle active = telemetry missing.
    res = _run(devices=(_device(state="provisioning", lifecycle="active"),))
    assert res.label == AssuranceLabel.ATTENTION
    assert rc.DEVICE_UNKNOWN.code in _codes(res)


def test_degraded_device_is_attention():
    res = _run(devices=(_device(state="attention"),))
    assert res.label == AssuranceLabel.ATTENTION
    assert rc.CARRIER_UNAVAILABLE.code in _codes(res)


# ── Pending Install ──────────────────────────────────────────────────
def test_pending_install_lifecycle():
    res = _run(site_lifecycle_status="pending_install")
    assert res.label == AssuranceLabel.PENDING_INSTALL
    assert rc.PENDING_INSTALL.code in _codes(res)


def test_onboarding_incomplete_is_pending():
    res = _run(site_lifecycle_status=None, onboarding_status="staging", devices=())
    assert res.label == AssuranceLabel.PENDING_INSTALL


def test_all_devices_pending_is_pending():
    res = _run(site_lifecycle_status=None, onboarding_status="active",
               devices=(_device(state="provisioning", lifecycle="pending_install"),))
    assert res.label == AssuranceLabel.PENDING_INSTALL


# ── Inactive / Deactivated ───────────────────────────────────────────
@pytest.mark.parametrize("lc", ["deactivated", "suspended", "cancelled", "inactive"])
def test_inactive_lifecycle(lc):
    # Even with an offline device, deactivated must NOT raise a Critical alarm.
    res = _run(site_lifecycle_status=lc, devices=(_device(state="offline"),))
    assert res.label == AssuranceLabel.INACTIVE
    assert rc.INACTIVE.code in _codes(res)
    assert rc.DEVICE_OFFLINE.code not in _codes(res)


def test_all_devices_inactive_is_inactive():
    res = _run(site_lifecycle_status=None,
               devices=(_device(state="offline", lifecycle="inactive"),))
    assert res.label == AssuranceLabel.INACTIVE


# ── Unknown ──────────────────────────────────────────────────────────
def test_no_trusted_data_is_unknown():
    # No devices, no lifecycle/onboarding evidence, no service units → cannot
    # assert active (so not Critical), not pending, not inactive → Unknown.
    res = _run(site_lifecycle_status=None, onboarding_status=None, devices=(),
               service_units=(), e911_address_present=True, e911_status="validated")
    assert res.label == AssuranceLabel.UNKNOWN


# ── Commercial-active never implies healthy ──────────────────────────
def test_commercial_active_but_offline_is_critical():
    res = _run(site_lifecycle_status="active", devices=(_device(state="offline"),))
    assert res.label == AssuranceLabel.CRITICAL
    assert rc.DEVICE_OFFLINE.code in _codes(res)


# ── Defensive: lifecycle absent (pre-PR#70) does not crash, not healthy-by-default ──
def test_absent_lifecycle_defensive():
    res = _run(site_lifecycle_status=None, onboarding_status="active",
               last_test=None)  # no test → Attention, not Protected
    assert res.label == AssuranceLabel.ATTENTION
    assert rc.TEST_MISSING.code in _codes(res)


# ── Engine purity: inputs not mutated ────────────────────────────────
def test_engine_does_not_mutate_inputs():
    s = _signals()
    before = (s.devices, s.reason_codes if hasattr(s, "reason_codes") else None, s.site_lifecycle_status)
    compute_site_assurance(s, now=NOW)
    assert s.site_lifecycle_status == before[2]
    assert s.devices == before[0]
