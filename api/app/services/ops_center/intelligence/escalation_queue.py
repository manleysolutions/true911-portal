"""Escalation-queue helper (Phase 1.5 foundation).

A thin, additive helper that turns a support session into a queued escalation
row with a canonical severity + derived priority.  NOT yet wired to the
router/workflow — provided so a later phase can enqueue from `escalate`
without reworking the schema.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ops_center_intelligence import OpsEscalationQueue
from app.services.ops_center.intelligence.constants import (
    IncidentSeverity,
    priority_for_severity,
    severity_for_issue,
)


def build_escalation_entry(session, *, severity: Optional[IncidentSeverity] = None) -> OpsEscalationQueue:
    """Construct (but do not persist) an :class:`OpsEscalationQueue` row from a
    support session.  Severity defaults from the issue category / emergency
    flag; priority is derived from severity."""
    sev = severity or severity_for_issue(
        getattr(session, "issue_category", None),
        bool(getattr(session, "is_emergency", False)),
    )
    return OpsEscalationQueue(
        tenant_id=getattr(session, "matched_tenant_id", None),
        session_id=getattr(session, "id", None),
        session_ref=getattr(session, "session_ref", None),
        issue_category=getattr(session, "issue_category", None),
        severity=sev.value,
        priority=priority_for_severity(sev),
        status="queued",
        is_emergency=bool(getattr(session, "is_emergency", False)),
        summary=getattr(session, "issue_summary", None),
        handoff_number=getattr(session, "handoff_number", None),
        incident_ref=getattr(session, "incident_ref", None),
        site_id=getattr(session, "matched_site_id", None),
        device_id=getattr(session, "matched_device_id", None),
    )


async def enqueue_escalation(
    db: AsyncSession, session, *, severity: Optional[IncidentSeverity] = None
) -> OpsEscalationQueue:
    """Persist an escalation-queue entry for *session*.  Caller commits."""
    entry = build_escalation_entry(session, severity=severity)
    db.add(entry)
    return entry
