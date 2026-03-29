"""
True911 — Automation Policy Configuration.

Code-based policy rules that determine how the automation layer responds
to attention engine output.  Structured so DB-backed tenant overrides
can be added later without changing the evaluation logic.

Each policy entry maps a (reason_code, severity) combination to an
automation response: what type of action, who to notify, how long to
suppress duplicates, and what execution mode to use.
"""

from __future__ import annotations
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════
# POLICY DATACLASS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AutomationPolicy:
    """A single automation policy entry."""
    automation_type: str        # notify | suggest_ping | suggest_reboot | escalate | follow_up | report_flag
    execution_mode: str         # manual | assisted | automatic
    recipient_scopes: list[str] # superadmin | admin | manager | user | support
    suppress_minutes: int       # Dedupe window — suppress repeat for this many minutes
    recommendation_title: str   # Human-readable action title template
    recommendation_detail: str  # Detail template (supports {site_name}, {reason_text}, etc.)
    min_severity: str = "low"   # Minimum attention severity to trigger this policy
    enabled: bool = True


# ═══════════════════════════════════════════════════════════════════
# DEFAULT POLICY TABLE
# ═══════════════════════════════════════════════════════════════════
# Keys: (primary_reason_code, severity) -> AutomationPolicy
# Severity "any" matches all severity levels for that reason.
#
# When multiple policies match, the most specific (reason+severity)
# wins over (reason+"any").

POLICIES: dict[tuple[str, str], AutomationPolicy] = {
    # ── Critical site offline ──────────────────────────────────────
    ("site_all_offline", "critical"): AutomationPolicy(
        automation_type="escalate",
        execution_mode="assisted",
        recipient_scopes=["superadmin", "admin"],
        suppress_minutes=15,
        recommendation_title="Escalate: Site offline — {site_name}",
        recommendation_detail="All devices at {site_name} are offline. Check power, connectivity, and carrier status.",
    ),

    # ── Device offline (heartbeat past hard threshold) ─────────────
    ("device_offline", "critical"): AutomationPolicy(
        automation_type="suggest_ping",
        execution_mode="assisted",
        recipient_scopes=["admin", "manager"],
        suppress_minutes=30,
        recommendation_title="Ping device at {site_name}",
        recommendation_detail="Device heartbeat exceeded offline threshold. Suggest ping to verify connectivity.",
    ),

    # ── Stale heartbeat (warning threshold) ────────────────────────
    ("stale_heartbeat", "high"): AutomationPolicy(
        automation_type="suggest_ping",
        execution_mode="manual",
        recipient_scopes=["admin", "manager"],
        suppress_minutes=60,
        recommendation_title="Investigate heartbeat at {site_name}",
        recommendation_detail="Device heartbeat is overdue. {reason_text}",
    ),

    # ── Partial reporting ──────────────────────────────────────────
    ("partial_reporting", "high"): AutomationPolicy(
        automation_type="follow_up",
        execution_mode="manual",
        recipient_scopes=["admin", "manager"],
        suppress_minutes=240,  # 4 hours
        recommendation_title="Check non-reporting devices at {site_name}",
        recommendation_detail="Some devices at {site_name} are not reporting. {reason_text}",
    ),

    # ── Critical incident ──────────────────────────────────────────
    ("incident_critical", "critical"): AutomationPolicy(
        automation_type="escalate",
        execution_mode="automatic",
        recipient_scopes=["superadmin", "admin"],
        suppress_minutes=15,
        recommendation_title="Critical incident at {site_name}",
        recommendation_detail="Active critical incident requires immediate response. {reason_text}",
    ),

    # ── Open incident (non-critical) ──────────────────────────────
    ("incident_open", "medium"): AutomationPolicy(
        automation_type="notify",
        execution_mode="manual",
        recipient_scopes=["admin", "manager"],
        suppress_minutes=120,  # 2 hours
        recommendation_title="Review open incident at {site_name}",
        recommendation_detail="Open incident at {site_name} needs review. {reason_text}",
    ),

    # ── E911 incomplete ────────────────────────────────────────────
    ("e911_incomplete", "low"): AutomationPolicy(
        automation_type="report_flag",
        execution_mode="manual",
        recipient_scopes=["admin"],
        suppress_minutes=1440,  # 24 hours
        recommendation_title="Complete E911 address for {site_name}",
        recommendation_detail="E911 address fields are missing. This is a compliance requirement.",
    ),

    # ── Verification overdue ───────────────────────────────────────
    ("verification_overdue", "low"): AutomationPolicy(
        automation_type="follow_up",
        execution_mode="manual",
        recipient_scopes=["admin", "manager"],
        suppress_minutes=1440,  # 24 hours
        recommendation_title="Schedule verification at {site_name}",
        recommendation_detail="{reason_text}. Overdue verification tasks require scheduling.",
    ),

    # ── Signal degraded ────────────────────────────────────────────
    ("signal_degraded", "medium"): AutomationPolicy(
        automation_type="follow_up",
        execution_mode="manual",
        recipient_scopes=["admin"],
        suppress_minutes=240,  # 4 hours
        recommendation_title="Check signal at {site_name}",
        recommendation_detail="Device signal degraded. {reason_text}",
    ),

    # ── Signal critical ────────────────────────────────────────────
    ("signal_critical", "critical"): AutomationPolicy(
        automation_type="suggest_ping",
        execution_mode="assisted",
        recipient_scopes=["admin", "manager"],
        suppress_minutes=60,
        recommendation_title="Signal critical at {site_name}",
        recommendation_detail="Device signal at critical level. Check antenna and SIM. {reason_text}",
    ),

    # ── Network disconnected ──────────────────────────────────────
    ("network_disconnected", "critical"): AutomationPolicy(
        automation_type="escalate",
        execution_mode="assisted",
        recipient_scopes=["superadmin", "admin"],
        suppress_minutes=15,
        recommendation_title="Network disconnected at {site_name}",
        recommendation_detail="Device network connectivity lost. {reason_text}",
    ),

    # ── SIP unregistered ──────────────────────────────────────────
    ("sip_unregistered", "medium"): AutomationPolicy(
        automation_type="follow_up",
        execution_mode="manual",
        recipient_scopes=["admin"],
        suppress_minutes=240,
        recommendation_title="SIP registration issue at {site_name}",
        recommendation_detail="Voice service registration failed. {reason_text}",
    ),

    # ── Stale telemetry ────────────────────────────────────────────
    ("stale_telemetry", "low"): AutomationPolicy(
        automation_type="follow_up",
        execution_mode="manual",
        recipient_scopes=["admin"],
        suppress_minutes=480,  # 8 hours
        recommendation_title="Stale telemetry at {site_name}",
        recommendation_detail="Device telemetry data is outdated. {reason_text}",
    ),

    # ── No data / provisioning ─────────────────────────────────────
    ("no_data", "low"): AutomationPolicy(
        automation_type="follow_up",
        execution_mode="manual",
        recipient_scopes=["admin"],
        suppress_minutes=1440,  # 24 hours — grace period
        recommendation_title="Verify setup at {site_name}",
        recommendation_detail="Device has no telemetry data yet. Verify provisioning.",
    ),

    ("provisioning", "info"): AutomationPolicy(
        automation_type="follow_up",
        execution_mode="manual",
        recipient_scopes=["admin"],
        suppress_minutes=1440,
        recommendation_title="Complete provisioning at {site_name}",
        recommendation_detail="Device awaiting first heartbeat.",
        enabled=True,
    ),

    # ── Site with no devices ──────────────────────────────────────
    ("site_no_devices", "low"): AutomationPolicy(
        automation_type="report_flag",
        execution_mode="manual",
        recipient_scopes=["admin"],
        suppress_minutes=1440,
        recommendation_title="Assign devices to {site_name}",
        recommendation_detail="Site has no devices assigned. Status cannot be determined.",
    ),
}


def get_policy(reason_code: str, severity: str) -> AutomationPolicy | None:
    """Look up the automation policy for a given reason and severity.

    Checks exact (reason, severity) first, then falls back to (reason, "any").
    Returns None if no matching policy exists.
    """
    policy = POLICIES.get((reason_code, severity))
    if policy and policy.enabled:
        return policy
    policy = POLICIES.get((reason_code, "any"))
    if policy and policy.enabled:
        return policy
    return None
