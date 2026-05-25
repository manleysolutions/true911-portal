"""Pure-logic normalizer — the single function every consumer eventually calls.

Composition order is fixed and order-dependent.  Read the algorithm
in :func:`compute_device_state` as the spec — the implementation is
deliberately literal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from app.services.health.signals import HealthSignals
from app.services.health.states import CanonicalDeviceState, CanonicalSiteState
from app.services.health.thresholds import (
    DEGRADED_SIP_STATUSES,
    DISCONNECTED_NETWORK_STATUSES,
    INACTIVE_LIFECYCLE,
    PROVISIONING_LIFECYCLE,
    SIGNAL_CRITICAL_DBM,
    STALE_OBSERVATION_SECONDS,
    TERMINAL_LIFECYCLE,
)


def _as_utc(ts: datetime) -> datetime:
    """Normalize a naive timestamp to UTC.

    Some ORM reads return naive datetimes when the underlying column
    is timezone-aware but the driver loses tz on cold-path queries.
    Callers should not have to think about this — assume UTC.
    """
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def compute_device_state(
    signals: HealthSignals,
    *,
    now: Optional[datetime] = None,
) -> CanonicalDeviceState:
    """Reduce one device's :class:`HealthSignals` to one canonical state.

    Algorithm (first match wins):

      1. Lifecycle ``decommissioned`` / ``retired`` → DECOMMISSIONED
      2. Lifecycle ``inactive`` → OFFLINE
      3. No liveness signal on any channel:
           - lifecycle ``provisioning`` / ``pending`` / ``new``    → PROVISIONING
           - anything else                                         → PROVISIONING
         (We deliberately don't surface UNKNOWN at the device level;
          UNKNOWN is reserved for site rollup when a site has zero
          devices.)
      4. Any liveness signal but the most recent is older than
         ``STALE_OBSERVATION_SECONDS`` → OFFLINE
      5. Fresh liveness AND a degradation indicator is present
         (disconnected network_status, signal at/below
         SIGNAL_CRITICAL_DBM, or degraded sip_status) → ATTENTION
      6. Otherwise → CONNECTED

    ``now`` is injectable so tests can pin the clock without monkeypatching.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    lifecycle = (signals.device_lifecycle or "").lower().strip()

    # 1. Terminal lifecycle
    if lifecycle in TERMINAL_LIFECYCLE:
        return CanonicalDeviceState.DECOMMISSIONED

    # 2. Inactive (but not terminal)
    if lifecycle in INACTIVE_LIFECYCLE:
        return CanonicalDeviceState.OFFLINE

    # 3. No liveness signal at all
    last_observed = signals.last_observed_at()
    if last_observed is None:
        # Whether the lifecycle is 'provisioning' explicitly or not,
        # 'we have never heard from this device' is the same operator
        # action.  Both map to PROVISIONING.
        return CanonicalDeviceState.PROVISIONING

    # 4. Stale liveness
    elapsed = (now - _as_utc(last_observed)).total_seconds()
    if elapsed > STALE_OBSERVATION_SECONDS:
        return CanonicalDeviceState.OFFLINE

    # 5. Fresh but degraded
    if _is_network_degraded(signals.network_status):
        return CanonicalDeviceState.ATTENTION

    if signals.signal_dbm is not None and signals.signal_dbm <= SIGNAL_CRITICAL_DBM:
        return CanonicalDeviceState.ATTENTION

    if _is_sip_degraded(signals.sip_status):
        return CanonicalDeviceState.ATTENTION

    # 6. Fresh and clean
    return CanonicalDeviceState.CONNECTED


def compute_site_state(
    device_states: Iterable[CanonicalDeviceState],
) -> CanonicalSiteState:
    """Roll up a site's state from its per-device states.

    Rules:

      * No devices at all                                  → UNKNOWN
      * Every device DECOMMISSIONED                        → DECOMMISSIONED
      * (After excluding DECOMMISSIONED from the rollup)
        - every device CONNECTED                            → CONNECTED
        - every device OFFLINE                              → OFFLINE
        - every device PROVISIONING                         → PROVISIONING
        - anything else (any mix)                           → ATTENTION

    UNKNOWN at the site level is reserved for the "site has no
    devices assigned" case — operationally that's a configuration
    problem, not a health problem, and the operator action differs.
    """
    states = list(device_states)
    if not states:
        return CanonicalSiteState.UNKNOWN

    if all(s == CanonicalDeviceState.DECOMMISSIONED for s in states):
        return CanonicalSiteState.DECOMMISSIONED

    # Exclude decommissioned from the rollup — they don't affect
    # operational status.
    active = [s for s in states if s != CanonicalDeviceState.DECOMMISSIONED]
    if not active:
        return CanonicalSiteState.DECOMMISSIONED

    if all(s == CanonicalDeviceState.CONNECTED for s in active):
        return CanonicalSiteState.CONNECTED
    if all(s == CanonicalDeviceState.OFFLINE for s in active):
        return CanonicalSiteState.OFFLINE
    if all(s == CanonicalDeviceState.PROVISIONING for s in active):
        return CanonicalSiteState.PROVISIONING

    return CanonicalSiteState.ATTENTION


# ─── Helpers ────────────────────────────────────────────────────────


def _is_network_degraded(network_status: Optional[str]) -> bool:
    if not network_status:
        return False
    return network_status.lower().strip() in DISCONNECTED_NETWORK_STATUSES


def _is_sip_degraded(sip_status: Optional[str]) -> bool:
    if not sip_status:
        return False
    return sip_status.lower().strip() in DEGRADED_SIP_STATUSES
