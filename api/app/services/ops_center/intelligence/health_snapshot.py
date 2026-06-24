"""CustomerHealthSnapshot — read-only customer-health summary (Phase 1.5 stub).

A lightweight, tenant-scoped, READ-ONLY rollup an operator can glance at when a
caller comes in.  It degrades gracefully: with no device data it returns an
``unknown`` snapshot rather than failing.  It writes nothing and is not wired
to any route yet.

This deliberately stays a thin stub — the authoritative customer assurance
label is owned by the Assurance Engine (docs/ASSURANCE_ENGINE.md); this is an
operator convenience that can later delegate to it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device

# A device with no check-in within this many hours counts as "stale".
_STALE_HOURS = 24.0


@dataclass
class CustomerHealthSnapshot:
    tenant_id: str
    label: str = "unknown"           # protected | attention | critical | unknown
    total_devices: int = 0
    active_devices: int = 0
    stale_devices: int = 0
    inactive_devices: int = 0
    generated_at: Optional[datetime] = None
    degraded: bool = False           # True when computed from incomplete data
    notes: list[str] = field(default_factory=list)


def _hours_since(ts: Optional[datetime], now: datetime) -> Optional[float]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 3600.0


async def build_customer_health_snapshot(
    db: AsyncSession, tenant_id: str, *, now: Optional[datetime] = None
) -> CustomerHealthSnapshot:
    """Compute a read-only health snapshot for *tenant_id*.

    *now* is injectable for deterministic tests.
    """
    now = now or datetime.now(timezone.utc)
    snap = CustomerHealthSnapshot(tenant_id=tenant_id, generated_at=now)

    devices = (
        await db.execute(select(Device).where(Device.tenant_id == tenant_id))
    ).scalars().all()

    snap.total_devices = len(devices)
    if not devices:
        snap.label = "unknown"
        snap.degraded = True
        snap.notes.append("No devices on record for this customer.")
        return snap

    for d in devices:
        status = (getattr(d, "status", "") or "").lower()
        if status in ("inactive", "decommissioned"):
            snap.inactive_devices += 1
            continue
        hrs = _hours_since(getattr(d, "last_heartbeat", None), now)
        if hrs is None or hrs > _STALE_HOURS:
            snap.stale_devices += 1
        else:
            snap.active_devices += 1

    # Label heuristic (operator convenience, not an SoT):
    monitored = snap.total_devices - snap.inactive_devices
    if monitored <= 0:
        snap.label = "unknown"
    elif snap.stale_devices == 0:
        snap.label = "protected"
    elif snap.stale_devices >= max(1, monitored // 2):
        snap.label = "critical"
    else:
        snap.label = "attention"

    # No live carrier / SIP / telemetry fusion here yet → flag as degraded so a
    # consumer knows this is a heartbeat-only approximation.
    snap.degraded = True
    snap.notes.append("Heartbeat-only approximation; carrier/SIP fusion not wired in Phase 1.5.")
    return snap
