"""Canonical enums + mappings for Ops Center operational intelligence.

These are Python string-enums for type safety in code; persisted columns
remain plain ``String`` (storing the ``.value``) to match the project's
no-native-PG-enum convention — the same approach the rest of the codebase
uses (allowed values enforced in code, not by a DB enum type).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class IncidentSeverity(str, Enum):
    """Canonical severity ladder.  Values align with the existing
    ``incidents.severity`` strings (e.g. the emergency path writes
    ``critical``) so this is a typed view over the same vocabulary, not a
    competing one."""

    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INFO = "info"


# Lower rank = more urgent (1 is the top).  Used to derive a queue priority.
SEVERITY_RANK: dict[str, int] = {
    IncidentSeverity.CRITICAL.value: 1,
    IncidentSeverity.HIGH.value: 2,
    IncidentSeverity.MODERATE.value: 3,
    IncidentSeverity.LOW.value: 4,
    IncidentSeverity.INFO.value: 5,
}


class EscalationQueueStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class KnowledgeArticleStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PlaybookStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class ResolutionPatternStatus(str, Enum):
    CANDIDATE = "candidate"   # observed, not yet trusted
    CONFIRMED = "confirmed"   # validated; safe to recommend
    REJECTED = "rejected"     # found unreliable


# Default severity per Ops Center issue category (see app/schemas/ops_center.py
# ISSUE_CATEGORIES).  Life-safety categories bias high; informational/billing
# bias low.  This is a *default* — an operator/policy can always override.
ISSUE_CATEGORY_SEVERITY: dict[str, IncidentSeverity] = {
    "area_of_refuge_issue": IncidentSeverity.CRITICAL,
    "fire_panel_issue": IncidentSeverity.CRITICAL,
    "no_dial_tone": IncidentSeverity.HIGH,
    "elevator_phone_issue": IncidentSeverity.HIGH,
    "device_offline": IncidentSeverity.HIGH,
    "gate_phone_issue": IncidentSeverity.MODERATE,
    "e911_question": IncidentSeverity.MODERATE,
    "location_update": IncidentSeverity.LOW,
    "billing_question": IncidentSeverity.LOW,
    "general_support": IncidentSeverity.INFO,
}


def severity_for_issue(issue_category: Optional[str], is_emergency: bool = False) -> IncidentSeverity:
    """Resolve a default :class:`IncidentSeverity` for an issue.

    A declared emergency is always ``CRITICAL``.  Otherwise the category map
    applies, defaulting to ``MODERATE`` for an unknown/None category.
    """
    if is_emergency:
        return IncidentSeverity.CRITICAL
    if not issue_category:
        return IncidentSeverity.MODERATE
    return ISSUE_CATEGORY_SEVERITY.get(issue_category, IncidentSeverity.MODERATE)


def priority_for_severity(severity: str | IncidentSeverity) -> int:
    """Map a severity to a numeric queue priority (1 = most urgent)."""
    value = severity.value if isinstance(severity, IncidentSeverity) else str(severity)
    return SEVERITY_RANK.get(value, SEVERITY_RANK[IncidentSeverity.MODERATE.value])
