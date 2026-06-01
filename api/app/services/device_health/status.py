"""The customer-facing 4-value health status, and its mapping from the
internal canonical device state.

The canonical state machine (``app.services.health.states.CanonicalDeviceState``)
is the source of truth for liveness/degradation.  This module collapses its
six engineering states into the four values the spec mandates for operators
and customers:

    Online | Offline | Attention Needed | Unknown
"""

from __future__ import annotations

from enum import Enum

from app.services.health.states import CanonicalDeviceState


class NormalizedStatus(str, Enum):
    """The single 4-value status shown in every health surface.

    Values are the human-facing strings on purpose — they render directly in
    the customer portal and API without a translation table.
    """

    ONLINE = "Online"
    OFFLINE = "Offline"
    ATTENTION = "Attention Needed"
    UNKNOWN = "Unknown"


# CanonicalDeviceState (6 states) -> NormalizedStatus (4 values).
#   CONNECTED       -> Online
#   ATTENTION       -> Attention Needed
#   OFFLINE         -> Offline
#   PROVISIONING    -> Unknown   (never observed; not yet a connectivity fault)
#   UNKNOWN         -> Unknown   (site rollup only)
#   DECOMMISSIONED  -> Unknown   (intentionally retired; not an alarm)
_MAP: dict[CanonicalDeviceState, NormalizedStatus] = {
    CanonicalDeviceState.CONNECTED: NormalizedStatus.ONLINE,
    CanonicalDeviceState.ATTENTION: NormalizedStatus.ATTENTION,
    CanonicalDeviceState.OFFLINE: NormalizedStatus.OFFLINE,
    CanonicalDeviceState.PROVISIONING: NormalizedStatus.UNKNOWN,
    CanonicalDeviceState.UNKNOWN: NormalizedStatus.UNKNOWN,
    CanonicalDeviceState.DECOMMISSIONED: NormalizedStatus.UNKNOWN,
}


def from_canonical(state: CanonicalDeviceState) -> NormalizedStatus:
    """Collapse a canonical device state into the 4-value status."""
    return _MAP.get(state, NormalizedStatus.UNKNOWN)
