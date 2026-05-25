"""Canonical health states — the single vocabulary the platform will
eventually share.

These string enums are intentionally lowercase so they can be used
verbatim as JSON / API values, matching the convention already used
by :class:`app.services.attention_engine.CanonicalStatus`.  The two
overlap by design — Phase N4 will collapse them, but in the MVP
they coexist (the attention engine continues to own Command Center
status; the new enum owns AI Health Summary status).
"""

from __future__ import annotations

from enum import Enum


class CanonicalDeviceState(str, Enum):
    """The single canonical state for one device, computed by
    :func:`app.services.health.compute_device_state`.

    The six values cover every legitimate combination of liveness +
    degradation + lifecycle that the MVP needs to express.  More
    granular states (e.g. ``DEGRADED_SIGNAL`` vs ``DEGRADED_SIP``)
    would belong to a presentation layer, not here.
    """

    CONNECTED = "connected"
    """Fresh liveness signal AND no degradation indicators present."""

    ATTENTION = "attention"
    """Fresh liveness signal but at least one degradation indicator
    (network disconnected, signal critically low, SIP unregistered).
    """

    OFFLINE = "offline"
    """No liveness signal within the stale threshold across any
    source.  Equivalent to 'we haven't heard from this device'.
    """

    PROVISIONING = "provisioning"
    """Device row exists but no liveness signal has EVER been
    observed on any source.  Distinct from OFFLINE because the
    operator action differs ('finish installation' vs
    'troubleshoot connectivity').
    """

    UNKNOWN = "unknown"
    """Reserved for site rollup when the site has no devices at
    all.  At the device level this is unreachable today but kept
    for symmetry.
    """

    DECOMMISSIONED = "decommissioned"
    """Explicit lifecycle terminal — device row is retained for
    audit but operator action is none.  Excluded from rollup
    counts.
    """


class CanonicalSiteState(str, Enum):
    """The single canonical state for one site, computed by
    :func:`app.services.health.compute_site_state`.

    The rollup rules are:

      * No devices → UNKNOWN
      * All devices DECOMMISSIONED → DECOMMISSIONED
      * Every non-decommissioned device CONNECTED → CONNECTED
      * Every non-decommissioned device OFFLINE → OFFLINE
      * Every non-decommissioned device PROVISIONING → PROVISIONING
      * Any other mix → ATTENTION
    """

    CONNECTED = "connected"
    ATTENTION = "attention"
    OFFLINE = "offline"
    PROVISIONING = "provisioning"
    UNKNOWN = "unknown"
    DECOMMISSIONED = "decommissioned"
