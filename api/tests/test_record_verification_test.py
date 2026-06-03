"""Tests for the record-verification-test command (pure parts + assurance chain).

No DB: covers result normalization, the verification_task / E911-log builders,
and that a recorded passing test + validated E911 + a connected device yields
Protected via the real Assurance engine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.record_verification_test import (
    build_e911_validation_log_kwargs,
    build_verification_task_kwargs,
    normalize_result,
)
from app.services.assurance import reason_codes as a_rc
from app.services.assurance.engine import compute_site_assurance
from app.services.assurance.signals import (
    AssuranceLabel,
    AssuranceSignals,
    DeviceSignal,
    ServiceUnitSignal,
    TestRecord,
)

NOW = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)


# ── result normalization (never silently defaults to pass) ───────────
def test_normalize_result():
    assert normalize_result("passed") == "pass"
    assert normalize_result("PASS") == "pass"
    assert normalize_result("failed") == "fail"
    assert normalize_result("Fail") == "fail"
    assert normalize_result("") is None
    assert normalize_result(None) is None
    assert normalize_result("maybe") is None


# ── verification_task builder ────────────────────────────────────────
def test_verification_task_kwargs():
    kw = build_verification_task_kwargs(
        tenant_id="integrity-pm", site_id="IPM-BELLE-TERRE",
        unit_id="IPM-BELLE-TERRE-EL1", test_type="elevator_emergency_call_test",
        result="pass", notes="Verified path.", completed_by="cindy@x.io", now=NOW,
    )
    assert kw["site_id"] == "IPM-BELLE-TERRE"
    assert kw["result"] == "pass"            # read by the assurance loader
    assert kw["completed_at"] == NOW
    assert kw["status"] == "completed"
    assert "IPM-BELLE-TERRE-EL1" in kw["title"]
    assert kw["task_type"] == "elevator_emergency_call_test"


# ── E911 validation log builder (address unchanged) ──────────────────
def test_e911_validation_log_kwargs():
    site = SimpleNamespace(
        site_id="IPM-BELLE-TERRE", e911_street="7800 W Oakland Park Blvd",
        e911_city="Sunrise", e911_state="FL", e911_zip="33351",
    )
    kw = build_e911_validation_log_kwargs(site, tenant_id="integrity-pm",
                                          requested_by="cindy@x.io", now=NOW)
    assert kw["status"] == "validated"
    assert kw["new_street"] == kw["old_street"] == "7800 W Oakland Park Blvd"
    assert kw["applied_at"] == NOW
    assert kw["log_id"].startswith("e911-val-")


# ── Assurance chain: recorded pass + E911 validated + connected → Protected ──
def _belle_terre(*, e911_status, last_test, op_state="connected"):
    return AssuranceSignals(
        tenant_id="integrity-pm", site_id="IPM-BELLE-TERRE",
        site_name="Belle Terre at Sunrise", customer_name="Integrity Property Management",
        site_lifecycle_status="active", onboarding_status="active",
        e911_address_present=True, e911_status=e911_status, e911_confirmation_required=False,
        devices=(DeviceSignal(device_id="VOLA-VOLA00325600226", operational_state=op_state,
                              device_lifecycle="active"),),
        service_units=(ServiceUnitSignal(unit_id="IPM-BELLE-TERRE-EL1", unit_name="Elevator 1",
                                         unit_type="elevator_phone", status="active",
                                         device_id="VOLA-VOLA00325600226", has_active_device=True),),
        last_test=last_test,
    )


def test_protected_after_test_and_e911_validation():
    res = compute_site_assurance(
        _belle_terre(e911_status="validated",
                     last_test=TestRecord(at=NOW, result="pass", source="verification_tasks")),
        now=NOW,
    )
    assert res.label == AssuranceLabel.PROTECTED
    assert a_rc.OK.code in set(res.reason_codes)


def test_still_critical_if_e911_not_validated():
    # Recording the test alone (E911 still 'provided') stays Critical — the
    # command does not, on its own, make Belle Terre Protected.
    res = compute_site_assurance(
        _belle_terre(e911_status="provided",
                     last_test=TestRecord(at=NOW, result="pass", source="verification_tasks")),
        now=NOW,
    )
    assert res.label == AssuranceLabel.CRITICAL
    assert a_rc.E911_UNVERIFIED.code in set(res.reason_codes)
    assert a_rc.TEST_MISSING.code not in set(res.reason_codes)   # test now recorded


def test_attention_if_device_offline_even_with_test_and_e911():
    # Device must also be reachable (PR #72 / Vola sync) — offline → Critical.
    res = compute_site_assurance(
        _belle_terre(e911_status="validated", op_state="offline",
                     last_test=TestRecord(at=NOW, result="pass", source="verification_tasks")),
        now=NOW,
    )
    assert res.label == AssuranceLabel.CRITICAL
    assert a_rc.DEVICE_OFFLINE.code in set(res.reason_codes)
