"""Health-normalization thresholds — the ONE place to change a number.

The MVP intentionally inherits the existing AI Health Summary
threshold (5 minutes hard-coded in ``app/services/llm/context.py``)
because AI Health Summary is the only consumer in Phase 1.  When the
normalizer is rolled out to Devices / Command Center / Map / Attention
engine in later phases, this module will become the unification point
for the staleness-threshold drift documented in
``docs/HEALTH_STATUS_AUDIT.md`` §6.

Do NOT change a value here without:
  * Updating the threshold-drift table in
    ``docs/HEALTH_STATUS_AUDIT.md`` if the change is now divergent
    from the legacy services.
  * Adding a test that asserts the new value in
    ``api/tests/test_health_normalizer.py``.
"""

from __future__ import annotations


# ── Liveness ────────────────────────────────────────────────────────

STALE_OBSERVATION_SECONDS: int = 300
"""How long since the last observation (heartbeat OR carrier event OR
call event OR VOLA sync) before the device is OFFLINE.

5 minutes matches the current ``STALE_DEVICE_SECONDS`` in
``app/services/llm/context.py`` so the AI Health Summary behavior
stays consistent when the flag flips on for the FIRST consumer.
Phase N1 may raise this when Devices page is migrated — the
``continuity.py`` page currently uses 2× ``heartbeat_interval``
(default 10 minutes).
"""


# ── Network status values that mean "explicitly disconnected" ──────
# These are the substrings the normalizer reads off Device.network_status
# (case-insensitive).  Anything not in this set is treated as
# "no signal of degradation" — including unknown vendor-specific strings,
# which we deliberately do NOT fail closed on.

DISCONNECTED_NETWORK_STATUSES: frozenset[str] = frozenset({
    "disconnected",
    "offline",
    "down",
    "not_connected",
    "not connected",
    "unreachable",
})


# ── SIP status values that mean "explicitly degraded" ──────────────
# SIP status is not currently a Device column — it lives in
# CommandTelemetry metadata.  The MVP signals_loader leaves
# sip_status=None; this constant is here so the algorithm is
# complete and future commits can pull SIP status from
# CommandTelemetry without re-deriving the rule.

DEGRADED_SIP_STATUSES: frozenset[str] = frozenset({
    "unregistered",
    "failed",
    "timeout",
    "error",
})


# ── Signal-strength dBm thresholds (cellular) ──────────────────────
# Same as those in ``app/services/health_scoring.py``.  Phase 1
# does not actually use these because the MVP loader does not yet
# populate ``signal_dbm`` (it's not a Device column).  Kept here
# so a follow-up commit pulling signal from CommandTelemetry has
# the rule already in place.

SIGNAL_CRITICAL_DBM: float = -110.0
"""At or below this, normalizer returns ATTENTION."""

SIGNAL_WARNING_DBM: float = -100.0
"""At or below this, normalizer returns ATTENTION.
Currently identical-in-effect to CRITICAL because the MVP only
exposes one ATTENTION state, but kept separate for clarity and
future expansion."""


# ── Lifecycle classification ───────────────────────────────────────
# Device.status string values, normalized to lowercase before matching.

TERMINAL_LIFECYCLE: frozenset[str] = frozenset({
    "decommissioned",
    "retired",
})

INACTIVE_LIFECYCLE: frozenset[str] = frozenset({
    "inactive",
})

PROVISIONING_LIFECYCLE: frozenset[str] = frozenset({
    "provisioning",
    "pending",
    "new",
})
