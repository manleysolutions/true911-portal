"""
True911 — Centralized Attention Engine.

Single source of truth for site/device status, severity, and attention
items across all roles.  Every dashboard, table, map, and card should
consume this engine's output rather than deriving status independently.

Design:
  1. Evaluate each device → DeviceAttention
  2. Aggregate devices per site → SiteAttention
  3. Collect all attention items → AttentionFeed
  4. Format for role-specific presentation

The engine operates on pre-loaded collections (no DB calls internally)
so callers can batch-load data once and evaluate cheaply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ═══════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════

class CanonicalStatus(str, Enum):
    """Canonical status values — the backend truth."""
    CONNECTED = "connected"
    ATTENTION = "attention"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Severity levels, ordered from most to least urgent."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Reason(str, Enum):
    """Machine-readable reason codes for status derivation."""
    HEARTBEAT_MISSING = "missing_heartbeat"
    HEARTBEAT_STALE = "stale_heartbeat"
    DEVICE_OFFLINE = "device_offline"
    DEVICE_INACTIVE = "device_inactive"
    DEVICE_DECOMMISSIONED = "device_decommissioned"
    SITE_NO_DEVICES = "site_no_devices"
    SITE_ALL_OFFLINE = "site_all_offline"
    SITE_PARTIAL_REPORTING = "partial_reporting"
    SIGNAL_DEGRADED = "signal_degraded"
    SIGNAL_CRITICAL = "signal_critical"
    NETWORK_DISCONNECTED = "network_disconnected"
    SIP_UNREGISTERED = "sip_unregistered"
    TELEMETRY_STALE = "stale_telemetry"
    E911_INCOMPLETE = "e911_incomplete"
    INCIDENT_OPEN = "incident_open"
    INCIDENT_CRITICAL = "incident_critical"
    VERIFICATION_OVERDUE = "verification_overdue"
    NO_DATA = "no_data"
    PROVISIONING = "provisioning"


# ═══════════════════════════════════════════════════════════════════
# THRESHOLDS (documented, easy to tune)
# ═══════════════════════════════════════════════════════════════════

DEFAULT_HEARTBEAT_INTERVAL_SEC = 300   # 5 minutes
HEARTBEAT_GRACE_MULTIPLIER = 2        # 2x interval before "stale"
HEARTBEAT_OFFLINE_MULTIPLIER = 6      # 6x interval before "offline"
SIGNAL_WARNING_DBM = -100
SIGNAL_CRITICAL_DBM = -110
TELEMETRY_STALE_MINUTES = 120         # 2 hours

CONNECTED_NETWORK = {"connected", "registered", "attached", "active"}
DISCONNECTED_NETWORK = {"disconnected", "not_registered", "denied", "detached", "suspended"}
SIP_WARNING = {"unregistered", "failed", "expired", "rejected"}


# ═══════════════════════════════════════════════════════════════════
# ROLE PRESENTATION
# ═══════════════════════════════════════════════════════════════════

# Friendly labels by role tier
STATUS_LABELS = {
    "user": {
        CanonicalStatus.CONNECTED: "Working",
        CanonicalStatus.ATTENTION: "Needs Attention",
        CanonicalStatus.OFFLINE: "Offline",
        CanonicalStatus.UNKNOWN: "Unknown",
    },
    "manager": {
        CanonicalStatus.CONNECTED: "Connected",
        CanonicalStatus.ATTENTION: "Attention Needed",
        CanonicalStatus.OFFLINE: "Not Connected",
        CanonicalStatus.UNKNOWN: "Unknown",
    },
    "admin": {
        CanonicalStatus.CONNECTED: "Connected",
        CanonicalStatus.ATTENTION: "Attention Needed",
        CanonicalStatus.OFFLINE: "Not Connected",
        CanonicalStatus.UNKNOWN: "Unknown",
    },
    "superadmin": {
        CanonicalStatus.CONNECTED: "Connected",
        CanonicalStatus.ATTENTION: "Attention Needed",
        CanonicalStatus.OFFLINE: "Not Connected",
        CanonicalStatus.UNKNOWN: "Unknown",
    },
}

# Friendly reason descriptions by role tier
REASON_FRIENDLY = {
    Reason.HEARTBEAT_MISSING: {
        "user": "Device has not reported in",
        "default": "No heartbeat received — device may be offline or not yet provisioned",
    },
    Reason.HEARTBEAT_STALE: {
        "user": "Device report is overdue",
        "default": "Heartbeat overdue — last seen {minutes_ago}m ago (threshold: {threshold}m)",
    },
    Reason.DEVICE_OFFLINE: {
        "user": "Device is offline",
        "default": "Device offline — heartbeat exceeded {multiplier}x interval",
    },
    Reason.SITE_ALL_OFFLINE: {
        "user": "Site is offline",
        "default": "All devices at site are offline or not reporting",
    },
    Reason.SITE_PARTIAL_REPORTING: {
        "user": "Some devices are not reporting",
        "default": "{online} of {total} devices reporting; {offline} offline",
    },
    Reason.SITE_NO_DEVICES: {
        "user": "No devices at this site",
        "default": "Site has no assigned devices — status cannot be determined",
    },
    Reason.SIGNAL_DEGRADED: {
        "user": "Weak signal detected",
        "default": "Signal degraded at {dbm} dBm (warning threshold: {threshold} dBm)",
    },
    Reason.SIGNAL_CRITICAL: {
        "user": "Very weak signal",
        "default": "Signal critical at {dbm} dBm (critical threshold: {threshold} dBm)",
    },
    Reason.NETWORK_DISCONNECTED: {
        "user": "Network connection lost",
        "default": "Network status: {status}",
    },
    Reason.SIP_UNREGISTERED: {
        "user": "Voice service issue",
        "default": "SIP registration: {status}",
    },
    Reason.TELEMETRY_STALE: {
        "user": "Data is outdated",
        "default": "Telemetry stale — last update {minutes_ago}m ago",
    },
    Reason.E911_INCOMPLETE: {
        "user": "Emergency address incomplete",
        "default": "E911 address fields missing — compliance risk",
    },
    Reason.INCIDENT_OPEN: {
        "user": "There is an open issue",
        "default": "{count} active incident(s) at site",
    },
    Reason.INCIDENT_CRITICAL: {
        "user": "There is a critical issue",
        "default": "{count} critical incident(s) — immediate attention required",
    },
    Reason.VERIFICATION_OVERDUE: {
        "user": "Maintenance is overdue",
        "default": "{count} verification task(s) overdue",
    },
    Reason.NO_DATA: {
        "user": "No information available yet",
        "default": "Insufficient data to determine status",
    },
    Reason.PROVISIONING: {
        "user": "Being set up",
        "default": "Device in provisioning state — awaiting first heartbeat",
    },
}


def format_reason(reason: Reason, role: str = "default", **kwargs) -> str:
    """Get a human-readable reason string for a given role."""
    templates = REASON_FRIENDLY.get(reason, {})
    tier = "user" if role.lower() == "user" else "default"
    template = templates.get(tier, templates.get("default", str(reason.value)))
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


# ═══════════════════════════════════════════════════════════════════
# OUTPUT DATACLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ReasonDetail:
    """A single reason contributing to status."""
    reason: Reason
    severity: Severity
    params: dict = field(default_factory=dict)

    def technical_text(self) -> str:
        return format_reason(self.reason, "default", **self.params)

    def friendly_text(self) -> str:
        return format_reason(self.reason, "user", **self.params)


@dataclass
class DeviceAttention:
    """Attention evaluation result for a single device."""
    device_id: str
    tenant_id: str
    site_id: str | None
    canonical_status: CanonicalStatus
    severity: Severity
    reasons: list[ReasonDetail]
    last_evaluated_at: datetime

    @property
    def primary_reason(self) -> Reason | None:
        return self.reasons[0].reason if self.reasons else None

    def technical_summary(self) -> str:
        if not self.reasons:
            return "All checks passed"
        return "; ".join(r.technical_text() for r in self.reasons[:3])

    def friendly_summary(self) -> str:
        if not self.reasons:
            return "Working normally"
        return self.reasons[0].friendly_text()


@dataclass
class SiteAttention:
    """Attention evaluation result for a site."""
    site_id: str
    site_name: str
    tenant_id: str
    canonical_status: CanonicalStatus
    severity: Severity
    reasons: list[ReasonDetail]
    device_results: list[DeviceAttention]
    last_evaluated_at: datetime
    # Contextual data
    total_devices: int = 0
    online_devices: int = 0
    offline_devices: int = 0
    active_incidents: int = 0
    critical_incidents: int = 0
    overdue_tasks: int = 0
    stale_devices: int = 0

    @property
    def primary_reason(self) -> Reason | None:
        return self.reasons[0].reason if self.reasons else None

    @property
    def needs_attention(self) -> bool:
        return self.canonical_status != CanonicalStatus.CONNECTED

    def technical_summary(self) -> str:
        if not self.reasons:
            return "All systems operational"
        return "; ".join(r.technical_text() for r in self.reasons[:3])

    def friendly_summary(self) -> str:
        if not self.reasons:
            return "Everything is working normally"
        if len(self.reasons) == 1:
            return self.reasons[0].friendly_text()
        return f"{self.reasons[0].friendly_text()}, and {len(self.reasons) - 1} other issue{'s' if len(self.reasons) > 2 else ''}"


@dataclass
class AttentionItem:
    """Normalized attention feed item for dashboard consumption."""
    id: str
    object_type: str  # "site" | "device"
    object_id: str
    tenant_id: str
    site_id: str | None
    site_name: str | None
    canonical_status: str
    severity: str
    primary_reason: str
    reasons: list[str]  # reason codes
    technical_summary: str
    friendly_summary: str
    last_seen_at: str | None
    last_evaluated_at: str
    recommended_action: str | None
    route_hint: str | None


# ═══════════════════════════════════════════════════════════════════
# DEVICE EVALUATOR
# ═══════════════════════════════════════════════════════════════════

def evaluate_device(
    *,
    device_id: str,
    tenant_id: str,
    site_id: str | None,
    status: str | None,
    last_heartbeat: datetime | None,
    heartbeat_interval: int | None,
    network_status: str | None = None,
    signal_dbm: float | None = None,
    last_network_event: datetime | None = None,
    sip_status: str | None = None,
    now: datetime | None = None,
) -> DeviceAttention:
    """Evaluate a single device and return its attention state.

    Rule priority (evaluated in order, all applicable reasons collected):
      1. Decommissioned/inactive → offline (info severity, expected state)
      2. No heartbeat AND no network data → unknown
      3. Heartbeat offline (>6x interval) → offline/critical
      4. Heartbeat stale (>2x interval) → attention/high
      5. Network disconnected → offline/critical
      6. Signal critical → attention/critical
      7. Signal warning → attention/medium
      8. SIP unregistered → attention/medium
      9. Telemetry stale → attention/low
     10. Provisioning (status field) → unknown/info
     11. All clear → connected/info
    """
    now = now or datetime.now(timezone.utc)
    reasons: list[ReasonDetail] = []

    db_status = (status or "").lower()
    interval_sec = heartbeat_interval or DEFAULT_HEARTBEAT_INTERVAL_SEC

    # 1. Decommissioned / inactive
    if db_status in ("decommissioned", "inactive"):
        reason = Reason.DEVICE_DECOMMISSIONED if db_status == "decommissioned" else Reason.DEVICE_INACTIVE
        reasons.append(ReasonDetail(reason, Severity.INFO))
        return DeviceAttention(
            device_id=device_id, tenant_id=tenant_id, site_id=site_id,
            canonical_status=CanonicalStatus.OFFLINE, severity=Severity.INFO,
            reasons=reasons, last_evaluated_at=now,
        )

    # 2. No data at all
    has_heartbeat = last_heartbeat is not None
    has_network = network_status is not None
    if not has_heartbeat and not has_network:
        if db_status == "provisioning":
            reasons.append(ReasonDetail(Reason.PROVISIONING, Severity.INFO))
            return DeviceAttention(
                device_id=device_id, tenant_id=tenant_id, site_id=site_id,
                canonical_status=CanonicalStatus.UNKNOWN, severity=Severity.INFO,
                reasons=reasons, last_evaluated_at=now,
            )
        reasons.append(ReasonDetail(Reason.NO_DATA, Severity.LOW))
        return DeviceAttention(
            device_id=device_id, tenant_id=tenant_id, site_id=site_id,
            canonical_status=CanonicalStatus.UNKNOWN, severity=Severity.LOW,
            reasons=reasons, last_evaluated_at=now,
        )

    # 3-4. Heartbeat evaluation
    if has_heartbeat:
        elapsed_sec = (now - last_heartbeat).total_seconds()
        offline_threshold = interval_sec * HEARTBEAT_OFFLINE_MULTIPLIER
        stale_threshold = interval_sec * HEARTBEAT_GRACE_MULTIPLIER
        minutes_ago = int(elapsed_sec / 60)
        threshold_min = int(stale_threshold / 60)

        if elapsed_sec > offline_threshold:
            reasons.append(ReasonDetail(
                Reason.DEVICE_OFFLINE, Severity.CRITICAL,
                {"multiplier": HEARTBEAT_OFFLINE_MULTIPLIER},
            ))
        elif elapsed_sec > stale_threshold:
            reasons.append(ReasonDetail(
                Reason.HEARTBEAT_STALE, Severity.HIGH,
                {"minutes_ago": minutes_ago, "threshold": threshold_min},
            ))

    # 5. Network disconnected
    if has_network and network_status.lower() in DISCONNECTED_NETWORK:
        reasons.append(ReasonDetail(
            Reason.NETWORK_DISCONNECTED, Severity.CRITICAL,
            {"status": network_status},
        ))

    # 6-7. Signal strength
    if signal_dbm is not None:
        if signal_dbm <= SIGNAL_CRITICAL_DBM:
            reasons.append(ReasonDetail(
                Reason.SIGNAL_CRITICAL, Severity.CRITICAL,
                {"dbm": signal_dbm, "threshold": SIGNAL_CRITICAL_DBM},
            ))
        elif signal_dbm <= SIGNAL_WARNING_DBM:
            reasons.append(ReasonDetail(
                Reason.SIGNAL_DEGRADED, Severity.MEDIUM,
                {"dbm": signal_dbm, "threshold": SIGNAL_WARNING_DBM},
            ))

    # 8. SIP registration
    if sip_status and sip_status.lower() in SIP_WARNING:
        reasons.append(ReasonDetail(
            Reason.SIP_UNREGISTERED, Severity.MEDIUM,
            {"status": sip_status},
        ))

    # 9. Telemetry staleness
    if last_network_event is not None:
        stale_sec = (now - last_network_event).total_seconds()
        if stale_sec > TELEMETRY_STALE_MINUTES * 60:
            reasons.append(ReasonDetail(
                Reason.TELEMETRY_STALE, Severity.LOW,
                {"minutes_ago": int(stale_sec / 60)},
            ))

    # Determine canonical status and worst severity
    if not reasons:
        return DeviceAttention(
            device_id=device_id, tenant_id=tenant_id, site_id=site_id,
            canonical_status=CanonicalStatus.CONNECTED, severity=Severity.INFO,
            reasons=[], last_evaluated_at=now,
        )

    worst_sev = min(reasons, key=lambda r: list(Severity).index(r.severity)).severity
    has_offline_reason = any(r.reason in (Reason.DEVICE_OFFLINE, Reason.NETWORK_DISCONNECTED) for r in reasons)
    canon = CanonicalStatus.OFFLINE if has_offline_reason else CanonicalStatus.ATTENTION

    return DeviceAttention(
        device_id=device_id, tenant_id=tenant_id, site_id=site_id,
        canonical_status=canon, severity=worst_sev,
        reasons=reasons, last_evaluated_at=now,
    )


# ═══════════════════════════════════════════════════════════════════
# SITE EVALUATOR
# ═══════════════════════════════════════════════════════════════════

def evaluate_site(
    *,
    site_id: str,
    site_name: str,
    tenant_id: str,
    site_status: str | None,
    e911_street: str | None,
    e911_city: str | None,
    e911_state: str | None,
    device_results: list[DeviceAttention],
    active_incident_count: int = 0,
    critical_incident_count: int = 0,
    overdue_task_count: int = 0,
    now: datetime | None = None,
) -> SiteAttention:
    """Evaluate a site from its device results and contextual data.

    Rules:
      1. No devices → unknown
      2. All devices offline → offline/critical
      3. Some devices offline → attention/high
      4. Critical incidents → severity boost
      5. Open incidents → attention/medium if not already worse
      6. Overdue verification → attention/low
      7. E911 incomplete → attention/low
      8. All clear → connected/info
    """
    now = now or datetime.now(timezone.utc)
    reasons: list[ReasonDetail] = []

    total = len(device_results)
    online = sum(1 for d in device_results if d.canonical_status == CanonicalStatus.CONNECTED)
    offline = sum(1 for d in device_results if d.canonical_status == CanonicalStatus.OFFLINE)
    stale = sum(1 for d in device_results if d.canonical_status == CanonicalStatus.ATTENTION)

    # 1. No devices
    if total == 0:
        reasons.append(ReasonDetail(Reason.SITE_NO_DEVICES, Severity.LOW))
        return SiteAttention(
            site_id=site_id, site_name=site_name, tenant_id=tenant_id,
            canonical_status=CanonicalStatus.UNKNOWN, severity=Severity.LOW,
            reasons=reasons, device_results=device_results,
            last_evaluated_at=now, total_devices=0,
        )

    # 2. All devices offline
    if online == 0:
        reasons.append(ReasonDetail(
            Reason.SITE_ALL_OFFLINE, Severity.CRITICAL,
        ))

    # 3. Partial reporting
    elif offline > 0 or stale > 0:
        reasons.append(ReasonDetail(
            Reason.SITE_PARTIAL_REPORTING, Severity.HIGH,
            {"online": online, "total": total, "offline": offline + stale},
        ))

    # 4-5. Incidents
    if critical_incident_count > 0:
        reasons.append(ReasonDetail(
            Reason.INCIDENT_CRITICAL, Severity.CRITICAL,
            {"count": critical_incident_count},
        ))
    elif active_incident_count > 0:
        reasons.append(ReasonDetail(
            Reason.INCIDENT_OPEN, Severity.MEDIUM,
            {"count": active_incident_count},
        ))

    # 6. Overdue tasks
    if overdue_task_count > 0:
        reasons.append(ReasonDetail(
            Reason.VERIFICATION_OVERDUE, Severity.LOW,
            {"count": overdue_task_count},
        ))

    # 7. E911 incomplete
    if not e911_street or not e911_city or not e911_state:
        reasons.append(ReasonDetail(Reason.E911_INCOMPLETE, Severity.LOW))

    # Determine canonical status
    if not reasons:
        return SiteAttention(
            site_id=site_id, site_name=site_name, tenant_id=tenant_id,
            canonical_status=CanonicalStatus.CONNECTED, severity=Severity.INFO,
            reasons=[], device_results=device_results,
            last_evaluated_at=now, total_devices=total,
            online_devices=online, offline_devices=offline,
        )

    worst_sev = min(reasons, key=lambda r: list(Severity).index(r.severity)).severity
    has_offline = any(r.reason == Reason.SITE_ALL_OFFLINE for r in reasons)
    canon = CanonicalStatus.OFFLINE if has_offline else CanonicalStatus.ATTENTION if reasons else CanonicalStatus.CONNECTED

    return SiteAttention(
        site_id=site_id, site_name=site_name, tenant_id=tenant_id,
        canonical_status=canon, severity=worst_sev,
        reasons=reasons, device_results=device_results,
        last_evaluated_at=now, total_devices=total,
        online_devices=online, offline_devices=offline,
        active_incidents=active_incident_count,
        critical_incidents=critical_incident_count,
        overdue_tasks=overdue_task_count,
        stale_devices=stale,
    )


# ═══════════════════════════════════════════════════════════════════
# ATTENTION FEED BUILDER
# ═══════════════════════════════════════════════════════════════════

def build_attention_feed(site_results: list[SiteAttention]) -> list[AttentionItem]:
    """Build a sorted attention feed from evaluated sites.

    Only includes sites/devices that need attention (not connected).
    Sorted by severity (critical first), then by site name.
    """
    items: list[AttentionItem] = []
    sev_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFO: 4}

    for site in site_results:
        if site.canonical_status == CanonicalStatus.CONNECTED:
            continue

        # Site-level attention item
        items.append(AttentionItem(
            id=f"site:{site.site_id}",
            object_type="site",
            object_id=site.site_id,
            tenant_id=site.tenant_id,
            site_id=site.site_id,
            site_name=site.site_name,
            canonical_status=site.canonical_status.value,
            severity=site.severity.value,
            primary_reason=site.primary_reason.value if site.primary_reason else "unknown",
            reasons=[r.reason.value for r in site.reasons],
            technical_summary=site.technical_summary(),
            friendly_summary=site.friendly_summary(),
            last_seen_at=None,
            last_evaluated_at=site.last_evaluated_at.isoformat(),
            recommended_action=_recommend_action(site),
            route_hint=f"/SiteDetail?site={site.site_id}",
        ))

    items.sort(key=lambda i: (sev_order.get(Severity(i.severity), 99), i.site_name or ""))
    return items


def _recommend_action(site: SiteAttention) -> str:
    """Generate a recommended action string for a site."""
    if not site.reasons:
        return "No action needed"
    primary = site.reasons[0].reason
    name = site.site_name
    if primary == Reason.SITE_ALL_OFFLINE:
        return f"Check power and connectivity at {name}"
    if primary == Reason.SITE_PARTIAL_REPORTING:
        return f"Investigate non-reporting devices at {name}"
    if primary == Reason.INCIDENT_CRITICAL:
        return f"Respond to critical incident at {name}"
    if primary == Reason.INCIDENT_OPEN:
        return f"Review open incident at {name}"
    if primary == Reason.VERIFICATION_OVERDUE:
        return f"Schedule verification at {name}"
    if primary == Reason.E911_INCOMPLETE:
        return f"Complete E911 address for {name}"
    return f"Review status at {name}"


# ═══════════════════════════════════════════════════════════════════
# BATCH EVALUATOR (main entry point)
# ═══════════════════════════════════════════════════════════════════

def evaluate_tenant(
    *,
    sites: list,
    devices: list,
    incidents_by_site: dict[str, list] | None = None,
    overdue_tasks_by_site: dict[str, int] | None = None,
    now: datetime | None = None,
) -> dict:
    """Evaluate all sites and devices for a tenant in one pass.

    Args:
        sites: list of Site model instances
        devices: list of Device model instances
        incidents_by_site: {site_id: [incident, ...]} — active incidents only
        overdue_tasks_by_site: {site_id: count}
        now: evaluation timestamp (for testability)

    Returns dict with:
        site_results: list[SiteAttention]
        device_results: list[DeviceAttention]
        attention_feed: list[AttentionItem]
        summary: {total_sites, connected, attention, offline, unknown,
                  total_devices, devices_online, devices_offline, ...}
    """
    now = now or datetime.now(timezone.utc)
    incidents_by_site = incidents_by_site or {}
    overdue_tasks_by_site = overdue_tasks_by_site or {}

    # Group devices by site
    devices_by_site: dict[str, list] = {}
    for d in devices:
        if d.site_id:
            devices_by_site.setdefault(d.site_id, []).append(d)

    # Evaluate all devices
    all_device_results: list[DeviceAttention] = []
    device_results_by_site: dict[str, list[DeviceAttention]] = {}

    for d in devices:
        dr = evaluate_device(
            device_id=d.device_id,
            tenant_id=d.tenant_id,
            site_id=d.site_id,
            status=d.status,
            last_heartbeat=d.last_heartbeat,
            heartbeat_interval=d.heartbeat_interval,
            network_status=d.network_status,
            signal_dbm=getattr(d, "signal_dbm", None),
            last_network_event=d.last_network_event,
            sip_status=getattr(d, "sip_status", None),
            now=now,
        )
        all_device_results.append(dr)
        if d.site_id:
            device_results_by_site.setdefault(d.site_id, []).append(dr)

    # Evaluate all sites
    site_results: list[SiteAttention] = []
    for s in sites:
        site_devs = device_results_by_site.get(s.site_id, [])
        site_incs = incidents_by_site.get(s.site_id, [])
        active_inc = [i for i in site_incs if getattr(i, "status", i.get("status", "")) in ("new", "open", "acknowledged", "in_progress")] if site_incs else []
        critical_inc = [i for i in active_inc if getattr(i, "severity", i.get("severity", "")) == "critical"]

        sr = evaluate_site(
            site_id=s.site_id,
            site_name=s.site_name,
            tenant_id=s.tenant_id,
            site_status=s.status,
            e911_street=s.e911_street,
            e911_city=s.e911_city,
            e911_state=s.e911_state,
            device_results=site_devs,
            active_incident_count=len(active_inc),
            critical_incident_count=len(critical_inc),
            overdue_task_count=overdue_tasks_by_site.get(s.site_id, 0),
            now=now,
        )
        site_results.append(sr)

    # Build attention feed
    attention_feed = build_attention_feed(site_results)

    # Compute summary counts
    connected_count = sum(1 for s in site_results if s.canonical_status == CanonicalStatus.CONNECTED)
    attention_count = sum(1 for s in site_results if s.canonical_status == CanonicalStatus.ATTENTION)
    offline_count = sum(1 for s in site_results if s.canonical_status == CanonicalStatus.OFFLINE)
    unknown_count = sum(1 for s in site_results if s.canonical_status == CanonicalStatus.UNKNOWN)
    devices_online = sum(1 for d in all_device_results if d.canonical_status == CanonicalStatus.CONNECTED)
    devices_offline = sum(1 for d in all_device_results if d.canonical_status == CanonicalStatus.OFFLINE)
    devices_attention = sum(1 for d in all_device_results if d.canonical_status == CanonicalStatus.ATTENTION)

    return {
        "site_results": site_results,
        "device_results": all_device_results,
        "attention_feed": attention_feed,
        "summary": {
            "total_sites": len(sites),
            "connected": connected_count,
            "attention": attention_count,
            "offline": offline_count,
            "unknown": unknown_count,
            "total_devices": len(devices),
            "devices_online": devices_online,
            "devices_offline": devices_offline,
            "devices_attention": devices_attention,
        },
    }


# ═══════════════════════════════════════════════════════════════════
# SERIALIZATION (for API responses)
# ═══════════════════════════════════════════════════════════════════

def serialize_site_attention(sa: SiteAttention) -> dict:
    """Convert a SiteAttention to a JSON-safe dict for API responses."""
    return {
        "site_id": sa.site_id,
        "site_name": sa.site_name,
        "canonical_status": sa.canonical_status.value,
        "severity": sa.severity.value,
        "needs_attention": sa.needs_attention,
        "primary_reason": sa.primary_reason.value if sa.primary_reason else None,
        "reasons": [r.reason.value for r in sa.reasons],
        "technical_summary": sa.technical_summary(),
        "friendly_summary": sa.friendly_summary(),
        "total_devices": sa.total_devices,
        "online_devices": sa.online_devices,
        "offline_devices": sa.offline_devices,
        "stale_devices": sa.stale_devices,
        "active_incidents": sa.active_incidents,
        "critical_incidents": sa.critical_incidents,
        "overdue_tasks": sa.overdue_tasks,
        "last_evaluated_at": sa.last_evaluated_at.isoformat(),
    }


def serialize_attention_item(item: AttentionItem) -> dict:
    """Convert an AttentionItem to a JSON-safe dict."""
    return {
        "id": item.id,
        "object_type": item.object_type,
        "object_id": item.object_id,
        "site_id": item.site_id,
        "site_name": item.site_name,
        "canonical_status": item.canonical_status,
        "severity": item.severity,
        "primary_reason": item.primary_reason,
        "reasons": item.reasons,
        "technical_summary": item.technical_summary,
        "friendly_summary": item.friendly_summary,
        "recommended_action": item.recommended_action,
        "route_hint": item.route_hint,
        "last_evaluated_at": item.last_evaluated_at,
    }


def serialize_summary(summary: dict) -> dict:
    """Return the summary counts as-is (already JSON-safe)."""
    return summary
