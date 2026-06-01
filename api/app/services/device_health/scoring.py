"""Pure scoring — turn HealthSignals + light context into a canonical state,
a 4-value status, and reason codes.  No DB, no I/O, fully unit-testable.

Reuses the canonical normalizer for the liveness/degradation state machine,
then layers SIM / VoLTE / vendor reasons on top.  Vendor-neutral throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.services.device_health.reason_codes import ReasonCode
from app.services.device_health.status import NormalizedStatus, from_canonical
from app.services.health.normalizer import (
    _is_network_degraded,
    _is_sip_degraded,
    compute_device_state,
)
from app.services.health.signals import HealthSignals
from app.services.health.states import CanonicalDeviceState
from app.services.health.thresholds import SIGNAL_CRITICAL_DBM

# SIM lifecycle values that mean "not carrying service".
INACTIVE_SIM_STATUSES = frozenset({"suspended", "deactivated", "inactive", "error"})

# Voice paths for which "no call ever" is worth surfacing (informational).
VOICE_PATHS = frozenset({"volte", "sip", "analog", "sip_over_lte"})


@dataclass
class DeviceContext:
    """Light, non-liveness context the scorer needs beyond HealthSignals."""

    voice_type: str = "unknown"
    sim_status: Optional[str] = None          # Sim.status
    volte_enabled: Optional[bool] = None      # Sim.meta.volte_enabled (None = unknown)
    has_call_history: bool = False            # any CallRecord ever for this device
    extra_reasons: list[ReasonCode] = field(default_factory=list)  # from vendor adapters / sync


@dataclass
class ScoreResult:
    canonical: CanonicalDeviceState
    status: NormalizedStatus
    reasons: list[ReasonCode]


def score(
    signals: HealthSignals,
    ctx: Optional[DeviceContext] = None,
    *,
    now: Optional[datetime] = None,
) -> ScoreResult:
    """Compute (canonical_state, normalized_status, reason_codes)."""
    ctx = ctx or DeviceContext()
    canonical = compute_device_state(signals, now=now)
    status = from_canonical(canonical)
    reasons: list[ReasonCode] = []

    # ── Liveness-driven reasons ─────────────────────────────────────
    if canonical == CanonicalDeviceState.OFFLINE:
        if signals.last_observed_at() is None:
            reasons.append(ReasonCode.NO_RECENT_HEARTBEAT)
        else:
            reasons.append(ReasonCode.DEVICE_OFFLINE)
    elif canonical == CanonicalDeviceState.PROVISIONING:
        reasons.append(ReasonCode.NO_RECENT_HEARTBEAT)
    elif canonical == CanonicalDeviceState.ATTENTION:
        if _is_network_degraded(signals.network_status):
            reasons.append(ReasonCode.DEVICE_OFFLINE)
        if _is_sip_degraded(signals.sip_status):
            reasons.append(ReasonCode.SIP_UNREGISTERED)
        # A critically low signal is treated as a connectivity risk for action
        # purposes — the recommended action (check power / cellular) fits, and
        # signal_dbm is still surfaced separately for detail.
        if (signals.signal_dbm is not None
                and signals.signal_dbm <= SIGNAL_CRITICAL_DBM
                and ReasonCode.DEVICE_OFFLINE not in reasons):
            reasons.append(ReasonCode.DEVICE_OFFLINE)

    # ── SIM lifecycle (independent of heartbeat liveness) ───────────
    if ctx.sim_status and ctx.sim_status.lower().strip() in INACTIVE_SIM_STATUSES:
        if ReasonCode.SIM_INACTIVE not in reasons:
            reasons.append(ReasonCode.SIM_INACTIVE)
        if status == NormalizedStatus.ONLINE:
            status = NormalizedStatus.ATTENTION

    # ── VoLTE readiness for VoLTE voice paths ───────────────────────
    if ctx.voice_type == "volte" and ctx.volte_enabled is False:
        reasons.append(ReasonCode.VOLTE_NOT_READY)
        if status == NormalizedStatus.ONLINE:
            status = NormalizedStatus.ATTENTION

    # ── Vendor-adapter reasons (MISSING_CREDENTIALS / DEVICE_NOT_FOUND
    #    / VENDOR_API_UNAVAILABLE / CONFIG_MISMATCH).  Informational —
    #    they never downgrade a device that is otherwise reporting fine. ─
    for r in ctx.extra_reasons:
        if r not in reasons and r != ReasonCode.OK:
            reasons.append(r)

    # ── No recent call activity (voice devices only, informational) ─
    if (ctx.voice_type in VOICE_PATHS
            and not ctx.has_call_history
            and status == NormalizedStatus.ONLINE):
        reasons.append(ReasonCode.NO_RECENT_CALL_ACTIVITY)

    # ── Clean ───────────────────────────────────────────────────────
    if status == NormalizedStatus.ONLINE and not reasons:
        reasons = [ReasonCode.OK]

    return ScoreResult(canonical=canonical, status=status, reasons=reasons)
