"""Pure, deterministic Assurance decision engine.

No DB, no I/O, no clock except an injectable ``now``.  Given an
``AssuranceSignals`` it returns an ``AssuranceResult`` (label + reason codes +
per-device breakdown).  It NEVER mutates inputs and never writes anything.

Design rules (life-safety; conservative):
  * Operational, commercial-lifecycle, deployment-lifecycle, and E911 are
    SEPARATE axes — combined here, never overwritten.
  * Commercial-active never implies operationally healthy.
  * A live heartbeat never hides a missing/unverified E911 (E911 is a hard gate).
  * Missing data is never treated as healthy.
  * Deactivated/suspended → no false emergency alarms (Inactive/Deactivated).
  * Pending installs are not failures (Pending Install).

Evaluation is ordered — first matching branch wins.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.services.assurance import reason_codes as rc
from app.services.assurance.signals import (
    AssuranceLabel,
    AssuranceResult,
    AssuranceSignals,
    DeviceAssurance,
    DeviceSignal,
)

# ── Tunable policy constants (global — no per-device-class thresholds in MVP) ──

# A passing test older than this is "stale" → Attention (not Critical).
# Default 90 days is conservative-but-not-noisy for life-safety testing cadence;
# documented in docs/ASSURANCE_ENGINE.md and open for tuning.
TEST_STALE_SECONDS: int = 90 * 24 * 3600

# Operational state strings (CanonicalDeviceState values, consumed verbatim).
_OP_CONNECTED = "connected"
_OP_ATTENTION = "attention"
_OP_OFFLINE = "offline"
_OP_PROVISIONING = "provisioning"
_OP_DECOMMISSIONED = "decommissioned"

# Lifecycle vocabularies (lowercased).
_INACTIVE_LIFECYCLE = frozenset({
    "deactivated", "suspended", "cancelled", "canceled", "inactive", "decommissioned", "retired",
})
_PENDING_LIFECYCLE = frozenset({"pending_install", "pending", "staged", "installed", "testing"})
# onboarding_status values that mean "the site is live".
_LIVE_ONBOARDING = frozenset({"active", "complete", "completed", "operational", "accepted", "done"})
# E911 status values that count as affirmatively verified.
_VERIFIED_E911 = frozenset({"validated", "verified", "confirmed"})
# Service-unit types that are emergency/life-safety endpoints.
_LIFE_SAFETY_UNIT_TYPES = frozenset({"elevator_phone", "fire_alarm", "emergency_call_station"})
# Line statuses that mean the voice path is down.
_VOICE_DOWN = frozenset({"disconnected", "deactivated", "failed"})


def _lc(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _is_inactive_lifecycle(value: Optional[str]) -> bool:
    return _lc(value) in _INACTIVE_LIFECYCLE


def _is_pending_lifecycle(value: Optional[str]) -> bool:
    return _lc(value) in _PENDING_LIFECYCLE


def _onboarding_incomplete(value: Optional[str]) -> bool:
    """True only when onboarding has a value AND it is not a 'live' value.

    None/empty is NOT treated as incomplete (we don't know) — that avoids
    forcing legacy rows (no onboarding data) into Pending Install.
    """
    v = _lc(value)
    return bool(v) and v not in _LIVE_ONBOARDING


def _device_is_inactive(d: DeviceSignal) -> bool:
    return _lc(d.device_lifecycle) in _INACTIVE_LIFECYCLE or d.operational_state == _OP_DECOMMISSIONED


def _device_is_pending(d: DeviceSignal) -> bool:
    return _lc(d.device_lifecycle) in _PENDING_LIFECYCLE


# ── Per-device assurance ─────────────────────────────────────────────

def compute_device_assurance(
    device: DeviceSignal, *, now: Optional[datetime] = None
) -> DeviceAssurance:
    """One device's contribution label (operational + device lifecycle only).

    E911 and test signals are site-scoped and applied in
    ``compute_site_assurance`` — a device on its own cannot be called Protected
    in the customer sense, but this expresses its operational contribution.
    """
    codes: list[str]
    if _device_is_inactive(device):
        label, codes = AssuranceLabel.INACTIVE, [rc.INACTIVE.code]
    elif _device_is_pending(device) or (
        device.operational_state == _OP_PROVISIONING and _lc(device.device_lifecycle) in _PENDING_LIFECYCLE
    ):
        label, codes = AssuranceLabel.PENDING_INSTALL, [rc.PENDING_INSTALL.code]
    elif device.operational_state == _OP_OFFLINE:
        label, codes = AssuranceLabel.CRITICAL, [rc.DEVICE_OFFLINE.code]
    elif device.operational_state == _OP_PROVISIONING:
        # Expected active (lifecycle not pending) but never observed → telemetry missing.
        label, codes = AssuranceLabel.ATTENTION, [rc.DEVICE_UNKNOWN.code]
    elif device.operational_state == _OP_ATTENTION:
        label, codes = AssuranceLabel.ATTENTION, [rc.CARRIER_UNAVAILABLE.code]
    elif device.operational_state == _OP_CONNECTED:
        label, codes = AssuranceLabel.PROTECTED, [rc.OK.code]
    else:
        label, codes = AssuranceLabel.UNKNOWN, [rc.DEVICE_UNKNOWN.code]

    return DeviceAssurance(
        device_id=device.device_id,
        label=label,
        reason_codes=tuple(codes),
        model=device.model,
        device_type=device.device_type,
        operational_state=device.operational_state,
        last_heartbeat_at=device.last_heartbeat_at,
    )


def _e911_verified(s: AssuranceSignals) -> bool:
    """Affirmatively verified dispatchable location.

    Verified only when the site status is an affirmative value AND reconfirmation
    is not required.  As a fallback, if the site has no E911 status but every
    non-inactive line is validated, treat as verified.  Anything else is NOT
    verified (conservative).
    """
    if s.e911_confirmation_required:
        return False
    if _lc(s.e911_status) in _VERIFIED_E911:
        return True
    if not _lc(s.e911_status) and s.lines:
        active_lines = [ln for ln in s.lines if _lc(ln.status) not in _INACTIVE_LIFECYCLE]
        if active_lines and all(_lc(ln.e911_status) in _VERIFIED_E911 for ln in active_lines):
            return True
    return False


def _test_is_stale(test, now: datetime) -> bool:
    at = test.at if test.at.tzinfo else test.at.replace(tzinfo=timezone.utc)
    return (now - at).total_seconds() > TEST_STALE_SECONDS


def _site_is_expected_live(s: AssuranceSignals) -> bool:
    """Positive evidence the site should be in service (drives NO_ACTIVE_DEVICE).

    True if commercial lifecycle is affirmatively active, OR onboarding is a live
    value, OR there is an active life-safety service unit. Absent all evidence we
    do NOT assert it should be live (→ Unknown rather than false Critical).
    """
    if _lc(s.site_lifecycle_status) == "active":
        return True
    if _lc(s.onboarding_status) in _LIVE_ONBOARDING:
        return True
    if any(_lc(u.status) == "active" for u in s.service_units):
        return True
    return False


# ── Site assurance ───────────────────────────────────────────────────

def compute_site_assurance(
    signals: AssuranceSignals, *, now: Optional[datetime] = None
) -> AssuranceResult:
    now = now if now is not None else datetime.now(timezone.utc)
    devices = list(signals.devices)
    device_results = tuple(compute_device_assurance(d, now=now) for d in devices)

    def result(label: AssuranceLabel, codes: list[str]) -> AssuranceResult:
        # de-dup, preserve order
        seen: list[str] = []
        for c in codes:
            if c not in seen:
                seen.append(c)
        return AssuranceResult(label=label, reason_codes=tuple(seen), devices=device_results)

    # 1. Inactive / Deactivated — commercial lifecycle, or every device inactive.
    if _is_inactive_lifecycle(signals.site_lifecycle_status):
        return result(AssuranceLabel.INACTIVE, [rc.INACTIVE.code])
    if devices and all(_device_is_inactive(d) for d in devices):
        return result(AssuranceLabel.INACTIVE, [rc.INACTIVE.code])

    # 2. Pending Install — pending lifecycle/onboarding, or all devices pending,
    #    or no devices yet and onboarding explicitly incomplete.
    if (
        _is_pending_lifecycle(signals.site_lifecycle_status)
        or _onboarding_incomplete(signals.onboarding_status)
        or (devices and all(_device_is_pending(d) for d in devices))
        or (not devices and _onboarding_incomplete(signals.onboarding_status))
    ):
        return result(AssuranceLabel.PENDING_INSTALL, [rc.PENDING_INSTALL.code])

    # ── Site is active / expected-live: gather Critical + Attention reasons ──
    critical: list[str] = []
    attention: list[str] = []

    # E911 hard gate (a live heartbeat must never hide this).
    if not signals.e911_address_present:
        critical.append(rc.E911_MISSING.code)
    elif not _e911_verified(signals):
        critical.append(rc.E911_UNVERIFIED.code)

    # Offline emergency device.
    if any(d.operational_state == _OP_OFFLINE and not _device_is_inactive(d) for d in devices):
        critical.append(rc.DEVICE_OFFLINE.code)

    # Required service unit with no active device, or an expected-live site with
    # zero non-inactive devices.
    active_units_without_device = [
        u for u in signals.service_units
        if _lc(u.status) == "active" and not u.has_active_device
    ]
    non_inactive_devices = [d for d in devices if not _device_is_inactive(d)]
    if active_units_without_device or (_site_is_expected_live(signals) and not non_inactive_devices):
        critical.append(rc.NO_ACTIVE_DEVICE.code)

    # Voice/carrier path down.
    if any(_lc(ln.status) in _VOICE_DOWN for ln in signals.lines):
        critical.append(rc.CARRIER_UNAVAILABLE.code)

    # Test signal.
    if signals.last_test is not None:
        if _lc(signals.last_test.result) == "fail":
            critical.append(rc.TEST_FAILED.code)
        elif _test_is_stale(signals.last_test, now):
            attention.append(rc.TEST_STALE.code)
    else:
        attention.append(rc.TEST_MISSING.code)

    # Telemetry-missing / degraded (warnings).
    if any(
        d.operational_state == _OP_PROVISIONING and not _device_is_pending(d) and not _device_is_inactive(d)
        for d in devices
    ):
        attention.append(rc.DEVICE_UNKNOWN.code)
    if any(d.operational_state == _OP_ATTENTION for d in devices):
        attention.append(rc.CARRIER_UNAVAILABLE.code)

    if critical:
        return result(AssuranceLabel.CRITICAL, critical + attention)
    if attention:
        return result(AssuranceLabel.ATTENTION, attention)

    # Protected — all gates green: E911 verified, at least one connected device,
    # and a recent passing test (test absence/staleness already routed to
    # Attention above, so reaching here means a fresh pass exists).
    if any(d.operational_state == _OP_CONNECTED for d in devices):
        return result(AssuranceLabel.PROTECTED, [rc.OK.code])

    # Otherwise we cannot safely assert anything.
    return result(AssuranceLabel.UNKNOWN, [rc.DEVICE_UNKNOWN.code])
