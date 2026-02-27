"""Compute device and site liveness from heartbeat timestamps.

These functions are pure read-time derivations — they never persist
the computed status back to the database.
"""

from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_HEARTBEAT_INTERVAL = 300  # seconds (5 min)
GRACE_MULTIPLIER = 2  # allow 2x interval before marking offline


def compute_device_computed_status(
    last_heartbeat: datetime | None,
    heartbeat_interval: int | None,
) -> str:
    """Return one of: ``Provisioning``, ``Online``, ``Offline``.

    * No heartbeat ever received → Provisioning
    * now − last_heartbeat ≤ interval × 2 → Online
    * Otherwise → Offline
    """
    if last_heartbeat is None:
        return "Provisioning"

    interval = heartbeat_interval or DEFAULT_HEARTBEAT_INTERVAL
    threshold = interval * GRACE_MULTIPLIER
    elapsed = (datetime.now(timezone.utc) - last_heartbeat).total_seconds()
    return "Online" if elapsed <= threshold else "Offline"


def compute_site_computed_status(device_computed_statuses: list[str]) -> str:
    """Derive a site-level computed status from its devices.

    * No devices → Unknown
    * All Online → Connected
    * All Offline/Provisioning (none Online) → Not Connected
    * Mixed → Attention Needed
    """
    if not device_computed_statuses:
        return "Unknown"

    has_online = "Online" in device_computed_statuses
    all_online = all(s == "Online" for s in device_computed_statuses)

    if all_online:
        return "Connected"
    if not has_online:
        return "Not Connected"
    return "Attention Needed"
