"""Ops Center Phase 1.5 — operational-intelligence foundations.

This package adds the SCAFFOLDING for richer Tier-1 support intelligence:
canonical severity, an escalation queue, support knowledge (articles /
playbooks / learned resolution patterns), a customer-health snapshot, and a
carrier/vendor context.

Phase 1.5 is **foundations only**: models, enums, and read-only / additive
service stubs.  Nothing here is wired to an HTTP route, drives the live
support workflow, or is exposed to a customer/public surface.  Like the rest
of the module it stays behind ``FEATURE_OPS_CENTER`` — and because no router
reads it yet, it is entirely inert at runtime until a later phase opts in
(any such endpoint will 404 when the flag is off, per the existing pattern).
"""

from app.services.ops_center.intelligence.constants import (
    EscalationQueueStatus,
    IncidentSeverity,
    KnowledgeArticleStatus,
    PlaybookStatus,
    ResolutionPatternStatus,
    SEVERITY_RANK,
    priority_for_severity,
    severity_for_issue,
)

__all__ = [
    "IncidentSeverity",
    "EscalationQueueStatus",
    "KnowledgeArticleStatus",
    "PlaybookStatus",
    "ResolutionPatternStatus",
    "SEVERITY_RANK",
    "severity_for_issue",
    "priority_for_severity",
]
