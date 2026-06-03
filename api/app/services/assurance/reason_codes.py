"""Assurance reason codes — the explainable "why" behind every label.

Each code carries a machine value (``ASSURANCE.*``), a severity, a calm
customer-facing message, and an internal recommended action for support/ops.
Customer surfaces render ``customer_message``; internal surfaces may render the
code + ``internal_action``.  Pure data — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    GATE = "gate"          # blocks the best status (e.g. inactive/pending)
    CRITICAL = "critical"  # emergency calling may not work
    WARNING = "warning"    # human should check, likely still working
    INFO = "info"          # all-clear / contextual


@dataclass(frozen=True)
class ReasonCode:
    code: str
    severity: Severity
    customer_message: str
    internal_action: str


# ── Catalog ──────────────────────────────────────────────────────────
# Keyed by the bare code (without the "ASSURANCE." prefix) for ergonomic
# engine references; ``.code`` carries the fully-qualified value.

E911_MISSING = ReasonCode(
    "ASSURANCE.E911_MISSING", Severity.CRITICAL,
    "We don't yet have a verified 911 address on file for this location.",
    "Capture and validate the dispatchable E911 address; run E911 provisioning.",
)
E911_UNVERIFIED = ReasonCode(
    "ASSURANCE.E911_UNVERIFIED", Severity.CRITICAL,
    "We're confirming the 911 address for this location.",
    "E911 address present but not validated (or reconfirmation required). Validate with carrier/PSAP.",
)
DEVICE_OFFLINE = ReasonCode(
    "ASSURANCE.DEVICE_OFFLINE", Severity.CRITICAL,
    "An emergency device at this location isn't currently reachable.",
    "Device has no fresh liveness signal. Check power/connectivity/carrier; dispatch if needed.",
)
DEVICE_UNKNOWN = ReasonCode(
    "ASSURANCE.DEVICE_UNKNOWN", Severity.WARNING,
    "We're confirming the status of an emergency device at this location.",
    "Device expected active but no telemetry observed yet. Confirm registration/reporting.",
)
NO_ACTIVE_DEVICE = ReasonCode(
    "ASSURANCE.NO_ACTIVE_DEVICE", Severity.CRITICAL,
    "An emergency endpoint at this location has no active device.",
    "Active service unit / live site has no active device assigned. Assign/activate a device.",
)
TEST_FAILED = ReasonCode(
    "ASSURANCE.TEST_FAILED", Severity.CRITICAL,
    "The most recent emergency test for this location did not pass.",
    "Most recent test result = fail. Investigate call path; open incident; retest.",
)
TEST_STALE = ReasonCode(
    "ASSURANCE.TEST_STALE", Severity.WARNING,
    "It's been a while since this location's last successful emergency test.",
    "Last successful test is older than the staleness window. Schedule a test call.",
)
TEST_MISSING = ReasonCode(
    "ASSURANCE.TEST_MISSING", Severity.WARNING,
    "We don't have a recorded emergency test for this location yet.",
    "No verification or infrastructure test on record. Schedule and record a test call.",
)
CARRIER_UNAVAILABLE = ReasonCode(
    "ASSURANCE.CARRIER_UNAVAILABLE", Severity.CRITICAL,
    "The voice/carrier path for this location appears unavailable.",
    "Line/voice path reported disconnected or carrier unavailable. Verify carrier + line status.",
)
VENDOR_API_UNAVAILABLE = ReasonCode(
    "ASSURANCE.VENDOR_API_UNAVAILABLE", Severity.WARNING,
    "We're reconciling the latest data for this location.",
    "A vendor data channel was unavailable; using last-known DB state. Re-check when channel restores.",
)
PENDING_INSTALL = ReasonCode(
    "ASSURANCE.PENDING_INSTALL", Severity.GATE,
    "This location is being set up. Protection will be confirmed after installation and testing.",
    "Lifecycle/onboarding indicates not yet live. No alarm; track to completion.",
)
INACTIVE = ReasonCode(
    "ASSURANCE.INACTIVE", Severity.GATE,
    "Service at this location is not currently active.",
    "Lifecycle indicates inactive/suspended/deactivated/cancelled. Alarms suppressed.",
)
OK = ReasonCode(
    "ASSURANCE.OK", Severity.INFO,
    "Emergency calling is active and verified.",
    "All gates green: active, E911 verified, device healthy, recent passing test.",
)

# Lookup by fully-qualified code (for serialization / tests).
ALL: dict[str, ReasonCode] = {
    rc.code: rc
    for rc in (
        E911_MISSING, E911_UNVERIFIED, DEVICE_OFFLINE, DEVICE_UNKNOWN,
        NO_ACTIVE_DEVICE, TEST_FAILED, TEST_STALE, TEST_MISSING,
        CARRIER_UNAVAILABLE, VENDOR_API_UNAVAILABLE, PENDING_INSTALL,
        INACTIVE, OK,
    )
}
