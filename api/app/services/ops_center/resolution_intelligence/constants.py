"""Enums for Resolution Intelligence.

Python string-enums for type safety; persisted columns stay plain ``String``
(storing ``.value``) per the project's no-native-PG-enum convention.  Severity
reuses the canonical :class:`IncidentSeverity` from Phase 1.5 (single source of
truth — ``CONSTITUTION.md`` P1).
"""

from __future__ import annotations

from enum import Enum

# Re-export so callers in this package have one import site for severity.
from app.services.ops_center.intelligence.constants import IncidentSeverity  # noqa: F401


class OutcomeType(str, Enum):
    """How a support engagement actually ended."""

    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    ESCALATED = "escalated"
    VENDOR_ISSUE = "vendor_issue"
    CARRIER_ISSUE = "carrier_issue"
    CUSTOMER_ISSUE = "customer_issue"
    HARDWARE_FAILURE = "hardware_failure"


class EscalationQueue(str, Enum):
    """Where an unresolved issue is routed.  Internal operational queues — not a
    customer-facing concept."""

    NOC = "NOC"                       # network operations / device offline
    CARRIER = "Carrier"              # carrier provisioning / activation
    VENDOR = "Vendor"                # hardware vendor (NAPCO, FlyingVoice, …)
    TIER2_VOICE = "Tier2Voice"       # SIP / ATA / call-path voice engineering
    E911 = "E911"                    # PSAP routing / ALI / E911 records
    INSTALLER = "Installer"          # on-site field work required
    CUSTOMER_SUPPORT = "CustomerSupport"  # billing / account / customer action


# Allowed string values, for router/validation use without importing the enums.
OUTCOME_TYPES = [o.value for o in OutcomeType]
ESCALATION_QUEUES = [q.value for q in EscalationQueue]
