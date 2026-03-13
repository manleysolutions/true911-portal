"""Device and site health scoring — Phase 2.

Derives a simple health status from available telemetry signals:

    healthy  — online, registered, signal acceptable, SIP registered (if relevant)
    warning  — low signal, stale telemetry, SIM suspended, SIP unregistered
    critical — offline, not registered, or SIM terminated
    unknown  — no telemetry or heartbeat data yet

Telemetry sources (device heartbeat or carrier API) both feed the same
scoring pipeline.  See telemetry_poller.py for the precedence rule.

Thresholds are intentionally simple and documented here for easy adjustment.
"""

from __future__ import annotations

from datetime import datetime, timezone

# ── Thresholds (easy to adjust) ───────────────────────────────────────

SIGNAL_WARNING_DBM = -100     # dBm at or below → warning
SIGNAL_CRITICAL_DBM = -110    # dBm at or below → critical

# If the last network telemetry is older than this many minutes, consider stale
TELEMETRY_STALE_MINUTES = 120  # 2 hours

# Connected network statuses (case-insensitive)
CONNECTED_STATUSES = {"connected", "registered", "attached", "active"}
DISCONNECTED_STATUSES = {"disconnected", "not_registered", "denied", "detached", "suspended"}

# SIP registration states that indicate a problem
SIP_WARNING_STATUSES = {"unregistered", "failed", "expired", "rejected"}

DEFAULT_HEARTBEAT_INTERVAL = 300  # seconds
HEARTBEAT_GRACE_MULTIPLIER = 2


def compute_device_health(
    *,
    last_heartbeat: datetime | None = None,
    heartbeat_interval: int | None = None,
    network_status: str | None = None,
    signal_dbm: float | None = None,
    last_network_event: datetime | None = None,
    device_status: str | None = None,
    sip_status: str | None = None,
) -> str:
    """Compute a health status for a single device.

    Returns one of: 'healthy', 'warning', 'critical', 'unknown'.

    Priority order (first match wins):
        1. Device decommissioned/inactive → critical
        2. No heartbeat AND no network status → unknown
        3. Heartbeat offline → critical
        4. Network disconnected → critical
        5. Signal critical → critical
        6. Signal warning → warning
        7. SIP unregistered → warning
        8. Telemetry stale → warning
        9. Otherwise → healthy
    """
    # 1. DB status check
    if device_status and device_status.lower() in ("decommissioned", "inactive"):
        return "critical"

    # 2. No data at all
    has_heartbeat = last_heartbeat is not None
    has_network = network_status is not None
    if not has_heartbeat and not has_network:
        return "unknown"

    # 3. Heartbeat offline
    if has_heartbeat:
        interval = heartbeat_interval or DEFAULT_HEARTBEAT_INTERVAL
        threshold = interval * HEARTBEAT_GRACE_MULTIPLIER
        elapsed = (datetime.now(timezone.utc) - last_heartbeat).total_seconds()
        if elapsed > threshold:
            return "critical"

    # 4. Network disconnected
    if has_network and network_status.lower() in DISCONNECTED_STATUSES:
        return "critical"

    # 5-6. Signal strength
    if signal_dbm is not None:
        if signal_dbm <= SIGNAL_CRITICAL_DBM:
            return "critical"
        if signal_dbm <= SIGNAL_WARNING_DBM:
            return "warning"

    # 7. SIP registration (relevant for PR12 and other voice devices)
    if sip_status and sip_status.lower() in SIP_WARNING_STATUSES:
        return "warning"

    # 8. Telemetry staleness
    if last_network_event is not None:
        stale_seconds = (
            datetime.now(timezone.utc) - last_network_event
        ).total_seconds()
        if stale_seconds > TELEMETRY_STALE_MINUTES * 60:
            return "warning"

    # 9. All checks passed
    return "healthy"


def compute_site_health(device_healths: list[str]) -> str:
    """Derive site health from its devices.

    * No devices → unknown
    * Any critical → critical
    * Any warning → warning
    * All healthy → healthy
    """
    if not device_healths:
        return "unknown"

    if "critical" in device_healths:
        return "critical"
    if "warning" in device_healths:
        return "warning"
    return "healthy"
