"""
True911 — Deterministic Command Center Intelligence Engine.

Transforms raw platform data into structured operational intelligence:
  - operational_summary (headline, subheadline, highlights)
  - executive_metrics (enriched KPIs)
  - incident_priority_stack (scored and ranked issues)
  - readiness_score (weighted breakdown)
  - recommended_actions (imperative, actionable)
  - activity_timeline (human-readable)

All logic is deterministic — no LLM, no randomness.
Designed for life-safety infrastructure monitoring.
"""

from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

# Service-type importance weights (life-safety priority)
# Higher = more critical.  Used in priority scoring.
SERVICE_IMPORTANCE = {
    "elevator_phone":   100,  # Life-safety — trapped persons
    "fire_alarm":        95,  # Life-safety — fire detection
    "call_station":      85,  # Emergency communications
    "das_radio":         75,  # First responder communications
    "backup_power":      60,  # Infrastructure resilience
    "emergency_device":  70,  # General emergency device
}

SEVERITY_WEIGHT = {
    "critical": 40,
    "warning":  20,
    "info":     5,
}

STATUS_WEIGHT = {
    "new":          10,  # Unacked = extra urgency
    "open":         10,
    "acknowledged":  5,
    "in_progress":   2,
}

# Readable category labels for summaries
CATEGORY_LABELS = {
    "elevator_phone":   "elevator emergency line",
    "fire_alarm":       "fire alarm communicator",
    "call_station":     "emergency call station",
    "das_radio":        "responder radio / DAS",
    "backup_power":     "backup power system",
    "emergency_device": "emergency device",
}


# ═══════════════════════════════════════════════════════════════════
# INCIDENT PRIORITY SCORING
# ═══════════════════════════════════════════════════════════════════

def score_incident(inc: dict, site_data: dict, now: datetime) -> dict:
    """Compute a priority score for a single incident.

    Scoring factors (all additive, max ~200):
      - Service type importance:     0–100
      - Severity weight:             5–40
      - Status urgency:              2–10
      - Duration penalty:            0–25  (longer open = higher)
      - Escalation bonus:            0–15
      - Site-wide impact bonus:      0–10

    Returns enriched incident dict with priority_score, why_it_matters,
    recommended_action, and route.
    """
    # Base score from service type
    category = _classify_incident_category(inc, site_data)
    base = SERVICE_IMPORTANCE.get(category, 50)

    # Severity
    sev_score = SEVERITY_WEIGHT.get(inc.get("severity", "info"), 5)

    # Status urgency
    status_score = STATUS_WEIGHT.get(inc.get("status", "open"), 5)

    # Duration penalty — longer open = more urgent
    opened_at = inc.get("opened_at")
    duration_minutes = 0
    if opened_at:
        try:
            if isinstance(opened_at, str):
                opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
            duration_minutes = max(0, int((now - opened_at).total_seconds() / 60))
        except (ValueError, TypeError):
            pass

    # Duration penalty: 1 point per 5 min, capped at 25
    duration_penalty = min(duration_minutes // 5, 25)

    # Escalation bonus
    escalation_level = inc.get("escalation_level", 0) or 0
    escalation_bonus = min(escalation_level * 5, 15)

    # Site-wide impact: if site has multiple active incidents or stale devices
    site_impact_bonus = 0
    if site_data.get("active_incidents", 0) > 1:
        site_impact_bonus += 5
    if site_data.get("stale_devices", 0) > 0:
        site_impact_bonus += 5

    priority_score = min(base + sev_score + status_score + duration_penalty + escalation_bonus + site_impact_bonus, 200)

    # Generate why_it_matters
    cat_label = CATEGORY_LABELS.get(category, "emergency service")
    severity = inc.get("severity", "info")

    if severity == "critical":
        why = f"Critical {cat_label} unavailable — life-safety risk"
    elif severity == "warning":
        why = f"{cat_label.title()} degraded — may affect emergency response"
    else:
        why = f"{cat_label.title()} requires attention"

    if duration_minutes > 60:
        why += f" (open {duration_minutes // 60}h {duration_minutes % 60}m)"
    elif duration_minutes > 0:
        why += f" (open {duration_minutes}m)"

    # Generate recommended_action
    action = _recommend_action_for_incident(inc, category, severity, duration_minutes)

    return {
        "id": inc.get("incident_id") or inc.get("id"),
        "title": inc.get("summary", "Unknown incident"),
        "site_name": inc.get("site_name") or inc.get("site_id", "Unknown"),
        "site_id": inc.get("site_id"),
        "category": category,
        "severity": severity,
        "status": inc.get("status", "open"),
        "duration_minutes": duration_minutes,
        "priority_score": priority_score,
        "why_it_matters": why,
        "recommended_action": action,
        "escalation_level": escalation_level,
        "route": f"/CommandSite?site={inc.get('site_id', '')}",
    }


def _classify_incident_category(inc: dict, site_data: dict) -> str:
    """Determine the service category of an incident."""
    # Check incident_type first
    inc_type = (inc.get("incident_type") or "").lower()
    if "elevator" in inc_type or "elev" in inc_type:
        return "elevator_phone"
    if "fire" in inc_type or "facp" in inc_type:
        return "fire_alarm"
    if "call" in inc_type or "station" in inc_type:
        return "call_station"
    if "das" in inc_type or "radio" in inc_type:
        return "das_radio"

    # Check summary text
    summary = (inc.get("summary") or "").lower()
    if "elevator" in summary:
        return "elevator_phone"
    if "fire" in summary or "facp" in summary:
        return "fire_alarm"
    if "call station" in summary:
        return "call_station"

    # Fall back to site kit_type
    kit = (site_data.get("kit_type") or "").lower()
    if "elevator" in kit or "elev" in kit:
        return "elevator_phone"
    if "fire" in kit or "facp" in kit:
        return "fire_alarm"

    return "emergency_device"


def _recommend_action_for_incident(inc: dict, category: str, severity: str, duration_minutes: int) -> str:
    """Generate a concise recommended action string."""
    site_name = inc.get("site_name") or inc.get("site_id", "site")

    if severity == "critical" and duration_minutes > 30:
        return f"Escalate and dispatch technician to {site_name}"
    if severity == "critical" and category in ("elevator_phone", "fire_alarm"):
        return f"Reboot CSA and verify carrier link at {site_name}"
    if severity == "critical":
        return f"Investigate outage at {site_name} immediately"
    if "heartbeat" in (inc.get("summary") or "").lower() or "stale" in (inc.get("summary") or "").lower():
        return f"Check connectivity and power at {site_name}"
    if "signal" in (inc.get("summary") or "").lower():
        return f"Check SIM signal and antenna at {site_name}"
    if severity == "warning":
        return f"Monitor and investigate degraded service at {site_name}"
    return f"Review and assess at {site_name}"


# ═══════════════════════════════════════════════════════════════════
# READINESS SCORE (enhanced breakdown)
# ═══════════════════════════════════════════════════════════════════

def compute_readiness_breakdown(
    readiness_data: dict,
    portfolio: dict,
    system_health: list,
) -> dict:
    """Enhance the existing readiness score with a structured breakdown.

    Returns the target readiness_score shape with breakdown sub-scores
    and a summary sentence explaining what is pulling score down.
    """
    score = readiness_data.get("score", 0)
    risk_label = readiness_data.get("risk_label", "Operational")
    factors = readiness_data.get("factors", [])

    # Compute sub-category scores from available data
    total_devices = portfolio.get("total_devices", 0)
    active_devices = portfolio.get("active_devices", 0)
    device_health = round((active_devices / max(total_devices, 1)) * 100)

    total_sites = portfolio.get("total_sites", 0)
    connected = portfolio.get("connected_sites", 0)
    connectivity = round((connected / max(total_sites, 1)) * 100)

    # Power: if we have system health data for backup_power, use it; else assume 100
    power_score = 100
    for sh in system_health:
        if sh.get("key") == "backup_power":
            power_score = sh.get("health_pct", 100)
            break

    # Reporting compliance: based on stale devices and overdue tasks
    stale = portfolio.get("stale_devices", 0)
    overdue = portfolio.get("overdue_tasks", 0)
    compliance_penalty = min((stale * 5) + (overdue * 8), 50)
    reporting_compliance = max(0, 100 - compliance_penalty)

    # Map risk label to status
    status_map = {
        "Operational": "Good",
        "Attention Needed": "Fair",
        "At Risk": "Poor",
    }

    # Summary sentence
    if not factors:
        summary = "All readiness factors within normal parameters."
    else:
        # Pick the top 2 factors by impact magnitude
        sorted_factors = sorted(factors, key=lambda f: f.get("impact", 0))
        top = sorted_factors[:2]
        parts = [f["detail"] for f in top if f.get("detail")]
        if parts:
            summary = " and ".join(parts).capitalize() + " are reducing readiness."
        else:
            summary = "Multiple factors are impacting readiness score."

    return {
        "score": score,
        "status": status_map.get(risk_label, "Unknown"),
        "risk_label": risk_label,
        "factors": factors,
        "breakdown": {
            "device_health": device_health,
            "connectivity": connectivity,
            "power": power_score,
            "reporting_compliance": reporting_compliance,
        },
        "summary": summary,
    }


# ═══════════════════════════════════════════════════════════════════
# OPERATIONAL SUMMARY
# ═══════════════════════════════════════════════════════════════════

def compute_operational_summary(
    portfolio: dict,
    active_incidents: list,
    site_summaries: list,
    incident_stack: list,
) -> dict:
    """Generate headline, subheadline, and highlights for the intelligence banner."""
    attention_count = sum(1 for s in site_summaries if s.get("needs_attention"))
    critical_count = len([i for i in active_incidents if i.get("severity") == "critical" and i.get("status") not in ("resolved", "dismissed", "closed")])
    total_sites = portfolio.get("total_sites", 0)
    connected = portfolio.get("connected_sites", 0)
    healthy_pct = round((connected / max(total_sites, 1)) * 100)

    # Headline
    if critical_count > 0:
        headline = f"{critical_count} critical incident{'s' if critical_count > 1 else ''} requiring immediate attention"
    elif attention_count > 0:
        headline = f"{attention_count} site{'s' if attention_count > 1 else ''} need{'s' if attention_count == 1 else ''} attention"
    else:
        headline = "All systems operational"

    # Subheadline
    if total_sites > 0:
        subheadline = f"System stable across {healthy_pct}% of monitored infrastructure"
    else:
        subheadline = "No sites currently deployed"

    # Highlights — top 3 specific issues in plain language
    highlights = []
    for item in incident_stack[:5]:
        if len(highlights) >= 3:
            break
        cat_label = CATEGORY_LABELS.get(item["category"], "device")
        site = item["site_name"]
        dur = item["duration_minutes"]

        if item["severity"] == "critical":
            if dur > 0:
                highlights.append(f"1 {cat_label} offline at {site} for {_format_duration(dur)}")
            else:
                highlights.append(f"1 {cat_label} offline at {site}")
        elif item["severity"] == "warning":
            highlights.append(f"1 {cat_label} degraded at {site}")

    # Fill remaining with stale/overdue info
    stale_total = portfolio.get("stale_devices", 0)
    if stale_total > 0 and len(highlights) < 3:
        highlights.append(f"{stale_total} device{'s' if stale_total > 1 else ''} with overdue heartbeat reporting")

    overdue = portfolio.get("overdue_tasks", 0)
    if overdue > 0 and len(highlights) < 3:
        highlights.append(f"{overdue} verification task{'s' if overdue > 1 else ''} overdue — compliance risk")

    if not highlights:
        highlights.append(f"{connected} of {total_sites} sites reporting normally")

    return {
        "headline": headline,
        "subheadline": subheadline,
        "highlights": highlights,
    }


def _format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h = minutes // 60
    m = minutes % 60
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


# ═══════════════════════════════════════════════════════════════════
# RECOMMENDED ACTIONS
# ═══════════════════════════════════════════════════════════════════

def compute_recommended_actions(
    incident_stack: list,
    site_summaries: list,
    portfolio: dict,
    readiness: dict,
) -> list:
    """Generate top recommended actions from scored priority data.

    Returns a list of actionable recommendations, capped at 5.
    """
    actions = []

    # From top incidents
    for item in incident_stack[:3]:
        if item["severity"] in ("critical", "warning"):
            actions.append({
                "title": item["recommended_action"],
                "reason": item["why_it_matters"],
                "priority": "high" if item["severity"] == "critical" else "medium",
                "category": item["category"],
                "site_id": item.get("site_id"),
                "route": item["route"],
            })

    # Stale device sites not already covered
    covered_sites = {a.get("site_id") for a in actions}
    for s in site_summaries:
        if len(actions) >= 5:
            break
        if s.get("stale_devices", 0) > 0 and s["site_id"] not in covered_sites:
            actions.append({
                "title": f"Check connectivity at {s['site_name']}",
                "reason": f"{s['stale_devices']} device{'s' if s['stale_devices'] > 1 else ''} with overdue heartbeat",
                "priority": "medium",
                "category": "connectivity",
                "site_id": s["site_id"],
                "route": f"/CommandSite?site={s['site_id']}",
            })
            covered_sites.add(s["site_id"])

    # Overdue verification tasks
    for s in site_summaries:
        if len(actions) >= 5:
            break
        if s.get("overdue_tasks", 0) > 0 and s["site_id"] not in covered_sites:
            actions.append({
                "title": f"Schedule verification at {s['site_name']}",
                "reason": f"{s['overdue_tasks']} overdue task{'s' if s['overdue_tasks'] > 1 else ''} — compliance risk",
                "priority": "medium",
                "category": "compliance",
                "site_id": s["site_id"],
                "route": f"/CommandSite?site={s['site_id']}",
            })
            covered_sites.add(s["site_id"])

    # Low readiness warning
    if readiness.get("score", 100) < 70 and len(actions) < 5:
        actions.append({
            "title": "Review readiness score",
            "reason": f"Score at {readiness['score']}/100 — {readiness.get('risk_label', 'At Risk')}",
            "priority": "medium",
            "category": "readiness",
            "site_id": None,
            "route": None,
        })

    # Default positive
    if not actions:
        actions.append({
            "title": "No recommended actions",
            "reason": "All systems operational — continue monitoring",
            "priority": "low",
            "category": "status",
            "site_id": None,
            "route": None,
        })

    return actions


# ═══════════════════════════════════════════════════════════════════
# EXECUTIVE METRICS
# ═══════════════════════════════════════════════════════════════════

def compute_executive_metrics(portfolio: dict, active_incident_count: int, critical_count: int) -> dict:
    """Compute the executive metrics strip."""
    total_sites = portfolio.get("total_sites", 0)
    connected = portfolio.get("connected_sites", 0)
    healthy_pct = round((connected / max(total_sites, 1)) * 100)
    stale = portfolio.get("stale_devices", 0)
    missing = portfolio.get("devices_missing_telemetry", 0)

    return {
        "total_sites": total_sites,
        "healthy_sites_pct": healthy_pct,
        "active_incidents": active_incident_count,
        "critical_incidents": critical_count,
        "devices_at_risk": stale + missing,
        "stale_devices": stale,
        "silent_devices": missing,
        "total_devices": portfolio.get("total_devices", 0),
        "devices_reporting": portfolio.get("devices_with_telemetry", 0),
        "monitored_sites": portfolio.get("monitored_sites", 0),
    }


# ═══════════════════════════════════════════════════════════════════
# ACTIVITY TIMELINE (enriched)
# ═══════════════════════════════════════════════════════════════════

def enrich_activity_timeline(activities: list) -> list:
    """Enrich raw activity timeline items with severity and display type.

    Input: list of serialized CommandActivity dicts.
    Output: same list with added `severity` and `type` fields.
    """
    TYPE_MAP = {
        "incident_created": ("incident", "critical"),
        "incident_acknowledged": ("action", "warning"),
        "incident_in_progress": ("action", "info"),
        "incident_resolved": ("resolution", "info"),
        "incident_dismissed": ("action", "info"),
        "incident_assigned": ("action", "info"),
        "incident_escalated": ("escalation", "warning"),
        "readiness_recalculated": ("system", "info"),
        "verification_scheduled": ("task", "info"),
        "site_import": ("import", "info"),
        "subscriber_import": ("import", "info"),
        "bulk_import": ("import", "info"),
        "telemetry_anomaly": ("alert", "warning"),
    }

    enriched = []
    for act in activities:
        at = act.get("activity_type", "")
        act_type, act_sev = TYPE_MAP.get(at, ("event", "info"))
        enriched.append({
            **act,
            "type": act_type,
            "severity": act_sev,
            "route": f"/CommandSite?site={act['site_id']}" if act.get("site_id") else None,
        })

    return enriched


# ═══════════════════════════════════════════════════════════════════
# MAIN ASSEMBLY
# ═══════════════════════════════════════════════════════════════════

def compute_intelligence(
    *,
    portfolio: dict,
    readiness: dict,
    system_health: list,
    incident_feed: list,
    active_incidents_count: int,
    critical_incidents_count: int,
    escalated_count: int,
    site_summaries: list,
    activity_timeline: list,
) -> dict:
    """Assemble the full command center intelligence payload.

    Called with the raw data already computed by the existing
    /command/summary endpoint.  This function layers intelligence
    on top without duplicating DB queries.
    """
    now = datetime.now(timezone.utc)

    # Build site lookup for incident scoring
    site_lookup = {s["site_id"]: s for s in site_summaries}

    # 1. Score and rank incidents
    active = [i for i in incident_feed if i.get("status") not in ("resolved", "dismissed", "closed")]
    scored = [
        score_incident(inc, site_lookup.get(inc.get("site_id"), {}), now)
        for inc in active
    ]
    scored.sort(key=lambda x: -x["priority_score"])

    # 2. Readiness breakdown
    readiness_enhanced = compute_readiness_breakdown(readiness, portfolio, system_health)

    # 3. Operational summary
    operational_summary = compute_operational_summary(portfolio, active, site_summaries, scored)

    # 4. Recommended actions
    recommended_actions = compute_recommended_actions(scored, site_summaries, portfolio, readiness)

    # 5. Executive metrics
    executive_metrics = compute_executive_metrics(portfolio, active_incidents_count, critical_incidents_count)

    # 6. Enriched timeline
    timeline = enrich_activity_timeline(activity_timeline)

    return {
        "operational_summary": operational_summary,
        "executive_metrics": executive_metrics,
        "incident_priority_stack": scored[:15],
        "readiness_score": readiness_enhanced,
        "recommended_actions": recommended_actions,
        "activity_timeline": timeline,
    }
