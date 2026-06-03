"""Input/output shapes for the Assurance Engine — pure dataclasses, no I/O.

``AssuranceSignals`` is the single read-only input the engine consumes for one
site (assembled by ``loader.py`` from existing tables).  ``AssuranceResult`` is
the engine's output.  Both are trivially testable and serialisable.

Lifecycle fields are ``Optional`` on purpose: ``sites.lifecycle_status`` may not
exist on a given deployment (it lands with the Zoho lifecycle work). Absent
lifecycle is treated CONSERVATIVELY — never as "active and healthy".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AssuranceLabel(str, Enum):
    """The six approved customer-facing labels (human strings on purpose)."""
    PROTECTED = "Protected"
    ATTENTION = "Attention Needed"
    CRITICAL = "Critical"
    INACTIVE = "Inactive / Deactivated"
    PENDING_INSTALL = "Pending Install"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class DeviceSignal:
    """One device's already-computed operational state + lifecycle.

    ``operational_state`` is a ``CanonicalDeviceState`` value string
    (connected/attention/offline/provisioning/decommissioned/unknown), computed
    upstream by ``services.health.compute_device_state``.  The engine does not
    recompute health — it consumes it.
    """
    device_id: str
    operational_state: str
    device_lifecycle: str = "active"          # Device.status
    model: Optional[str] = None
    device_type: Optional[str] = None
    carrier: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None
    last_observed_at: Optional[datetime] = None


@dataclass(frozen=True)
class ServiceUnitSignal:
    unit_id: str
    unit_name: str
    unit_type: str
    status: str = "active"                     # ServiceUnit.status
    device_id: Optional[str] = None
    has_active_device: bool = False


@dataclass(frozen=True)
class LineSignal:
    line_id: str
    status: str = "active"                     # Line.status
    e911_status: Optional[str] = None


@dataclass(frozen=True)
class TestRecord:
    __test__ = False  # not a pytest test class

    at: datetime
    result: str                               # "pass" | "fail"
    source: str                               # "verification_tasks" | "command_testing"


@dataclass(frozen=True)
class AssuranceSignals:
    tenant_id: str
    site_id: str
    site_name: Optional[str] = None
    customer_name: Optional[str] = None

    # ── Lifecycle (defensive — may be None on a deployment without PR#70) ──
    site_lifecycle_status: Optional[str] = None   # sites.lifecycle_status (Zoho commercial)
    onboarding_status: Optional[str] = None       # sites.onboarding_status (deployment)
    reconciliation_status: Optional[str] = None

    # ── E911 / compliance ───────────────────────────────────────────────
    e911_address_present: bool = False
    e911_status: Optional[str] = None             # sites.e911_status
    e911_confirmation_required: bool = False

    # ── Children ─────────────────────────────────────────────────────────
    devices: tuple[DeviceSignal, ...] = ()
    service_units: tuple[ServiceUnitSignal, ...] = ()
    lines: tuple[LineSignal, ...] = ()

    # ── Most recent life-safety-relevant test (verification first) ───────
    last_test: Optional[TestRecord] = None


@dataclass(frozen=True)
class DeviceAssurance:
    device_id: str
    label: AssuranceLabel
    reason_codes: tuple[str, ...]
    model: Optional[str] = None
    device_type: Optional[str] = None
    operational_state: Optional[str] = None
    last_heartbeat_at: Optional[datetime] = None


@dataclass(frozen=True)
class AssuranceResult:
    label: AssuranceLabel
    reason_codes: tuple[str, ...]
    devices: tuple[DeviceAssurance, ...] = ()
