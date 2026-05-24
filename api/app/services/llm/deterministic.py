"""Deterministic summary builder — the always-available fallback.

Given a ``SummaryContext`` (assembled by
:mod:`app.services.llm.context`), produce the same response shape the
LLM-backed path returns, but composed from existing structured fields
using simple rules.

This is the SAFE OUTPUT.  Anything the LLM does is decoration on top of
this — if the LLM is disabled, times out, fails validation, or the
tenant has exhausted its token quota, the result of this function is
returned with ``deterministic_fallback=True`` and the operator sees
something useful either way.

The wording style is borrowed from
``app.services.support.wording`` — short, factual, no marketing
language, never claims certainty the data doesn't support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class SiteSnapshot:
    """A normalized view of a single site that fits one summary line."""

    site_id: str
    site_name: str
    needs_attention: bool = False
    active_incidents: int = 0
    critical_incidents: int = 0
    stale_devices: int = 0
    overdue_tasks: int = 0
    last_heartbeat_seconds_ago: Optional[int] = None
    # Most recent connection_status / sip_status string, e.g. "connected",
    # "degraded", "disconnected".  Sourced from CommandTelemetry metadata
    # without ever including a raw IP or identifier.
    connection_status: Optional[str] = None


@dataclass
class IncidentSnapshot:
    """A normalized view of one open incident — no PII."""

    incident_id: str
    severity: str  # critical | warning | info
    summary: str   # human-readable, must already be PII-safe
    opened_minutes_ago: int
    site_id: Optional[str] = None


@dataclass
class FleetSnapshot:
    """Roll-up counts used for the fleet-scope summary line."""

    total_sites: int = 0
    connected_sites: int = 0
    sites_needing_attention: int = 0
    active_incidents: int = 0
    critical_incidents: int = 0
    stale_devices: int = 0


@dataclass
class SummaryContext:
    """The complete, tenant-scoped data the summarizer can see.

    Built once per request by :class:`app.services.llm.context.LLLMContext`
    so every consumer (deterministic builder, prompt template, validator)
    sees identical inputs.
    """

    scope: str                                # fleet | site | device
    scope_id: Optional[str] = None
    tenant_id: str = ""
    fleet: FleetSnapshot = field(default_factory=FleetSnapshot)
    site: Optional[SiteSnapshot] = None
    incidents: List[IncidentSnapshot] = field(default_factory=list)
    # Structured list of "<table>:<key>" references — populated by the
    # context loader as data is read.  Becomes ``sources_used`` on the
    # audit row and on the response.
    sources_used: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Builders ──────────────────────────────────────────────────────────


def _fleet_status_line(fleet: FleetSnapshot) -> str:
    """Single-sentence summary of fleet health."""
    if fleet.total_sites == 0:
        return "No sites are deployed for this tenant yet."
    pct = round(100 * fleet.connected_sites / fleet.total_sites)
    parts = [
        f"{fleet.connected_sites} of {fleet.total_sites} sites connected ({pct}%)"
    ]
    if fleet.sites_needing_attention:
        parts.append(f"{fleet.sites_needing_attention} need attention")
    return ", ".join(parts) + "."


def _fleet_issue_line(fleet: FleetSnapshot) -> Optional[str]:
    """The 'likely issue' line for the fleet scope — None when healthy."""
    if fleet.critical_incidents:
        s = "s" if fleet.critical_incidents != 1 else ""
        return f"{fleet.critical_incidents} critical incident{s} currently open."
    if fleet.active_incidents:
        s = "s" if fleet.active_incidents != 1 else ""
        return f"{fleet.active_incidents} active incident{s} currently open."
    if fleet.stale_devices:
        s = "s" if fleet.stale_devices != 1 else ""
        return f"{fleet.stale_devices} device{s} with overdue heartbeat reporting."
    if fleet.sites_needing_attention:
        return "One or more sites are flagged for attention."
    return None


def _fleet_recommendation(fleet: FleetSnapshot) -> str:
    """The 'recommended next step' line for the fleet scope."""
    if fleet.critical_incidents:
        return "Triage critical incidents first; assign owners and ack timelines."
    if fleet.active_incidents:
        return "Review open incidents and acknowledge any older than the SLA."
    if fleet.stale_devices:
        return "Check the device list for stale heartbeats; verify carrier connectivity."
    if fleet.sites_needing_attention:
        return "Open the attention list and resolve flagged items in priority order."
    return "Continue monitoring; no immediate action required."


def _site_status_line(site: SiteSnapshot) -> str:
    """Single-sentence status for one site."""
    if site.last_heartbeat_seconds_ago is None:
        return f"{site.site_name} has not reported telemetry yet."
    secs = site.last_heartbeat_seconds_ago
    if secs < 120:
        when = f"{secs}s ago"
    elif secs < 3600:
        when = f"{secs // 60} min ago"
    elif secs < 86400:
        when = f"{secs // 3600}h ago"
    else:
        when = f"{secs // 86400}d ago"
    status = site.connection_status or "reporting"
    return f"{site.site_name} last reported {when} ({status})."


def _site_issue_line(site: SiteSnapshot, incidents: List[IncidentSnapshot]) -> Optional[str]:
    """The 'likely issue' line for a single site — None when healthy."""
    if site.critical_incidents:
        return f"{site.critical_incidents} critical incident(s) currently open at this site."
    if site.active_incidents:
        return f"{site.active_incidents} open incident(s) at this site."
    if site.stale_devices:
        return f"{site.stale_devices} device(s) at this site have overdue heartbeats."
    if site.overdue_tasks:
        return f"{site.overdue_tasks} verification task(s) overdue at this site."
    if incidents:
        # Surface the most-recent incident summary as the issue line.
        first = incidents[0]
        return first.summary
    return None


def _site_recommendation(site: SiteSnapshot, incidents: List[IncidentSnapshot]) -> str:
    """The 'recommended next step' line for a single site."""
    if site.critical_incidents or any(i.severity == "critical" for i in incidents):
        return "Open the site detail page and acknowledge the critical incident."
    if site.stale_devices:
        return "Check device heartbeat status; verify carrier signal and SIM activation."
    if site.overdue_tasks:
        return "Schedule the overdue verification task to maintain compliance."
    if site.active_incidents or incidents:
        return "Review the open incident and follow the standard triage path."
    return "Site looks normal — continue routine monitoring."


def _confidence(ctx: SummaryContext) -> float:
    """Deterministic confidence score.

    The deterministic path is rule-based, so confidence reflects
    *coverage* (how much data we actually had to work with), not
    statistical certainty.  More signal = higher confidence.
    """
    if ctx.scope == "fleet":
        if ctx.fleet.total_sites == 0:
            return 0.40
        if ctx.fleet.total_sites < 3:
            return 0.65
        return 0.80
    if ctx.scope == "site":
        if not ctx.site:
            return 0.30
        if ctx.site.last_heartbeat_seconds_ago is None:
            return 0.45
        if ctx.incidents:
            return 0.85
        return 0.75
    # device scope — Phase 1 keeps device deterministic until we add a
    # per-device summary builder (Phase 2 or later).
    return 0.50


def build_deterministic_summary(ctx: SummaryContext) -> dict:
    """Build the response payload using only structured fields.

    Returns a dict whose keys match :class:`app.schemas.llm.HealthSummaryResponse`
    (less ``summary_id`` and ``source`` — those are filled in by the
    orchestrator).  Caller is expected to set ``deterministic_fallback``
    when wrapping this as the final response.
    """
    if ctx.scope == "fleet":
        current = _fleet_status_line(ctx.fleet)
        issue = _fleet_issue_line(ctx.fleet)
        rec = _fleet_recommendation(ctx.fleet)
    elif ctx.scope == "site":
        if not ctx.site:
            current = "Site not found or no data available."
            issue = None
            rec = "Verify the site_id and that the site has at least one assigned device."
        else:
            current = _site_status_line(ctx.site)
            issue = _site_issue_line(ctx.site, ctx.incidents)
            rec = _site_recommendation(ctx.site, ctx.incidents)
    else:  # device or unknown
        current = "Per-device deterministic summary not implemented in Phase 1."
        issue = None
        rec = "Use the fleet or site scope for Phase 1 reporting."

    return {
        "current_status": current,
        "likely_issue": issue,
        "recommended_next_step": rec,
        "confidence": _confidence(ctx),
        "sources_used": list(ctx.sources_used),
        # Phase 1 does not surface customer-safe summaries; reserved
        # for Phase 3 (customer-visible drafts).
        "customer_safe_summary": None,
        "internal_summary": _compose_internal(current, issue, rec),
        "generated_at": ctx.generated_at,
    }


def _compose_internal(current: str, issue: Optional[str], rec: str) -> str:
    """Compose the internal_summary paragraph from the three rule outputs."""
    parts = [current]
    if issue:
        parts.append(issue)
    parts.append(rec)
    return " ".join(parts)
