"""HealthSignals — the single input dataclass for the normalizer.

Every field is optional.  ``None`` means "no data on this channel"
and is treated AS data — it's not an error.  The normalizer's job
is to compose a coherent state out of whatever signals are present.

The MVP loader only populates a subset of these (the ones whose
source already exists as a Device column or in call_records).
Signal-strength and SIP status are intentionally left ``None`` in
Phase 1 — they live in :class:`CommandTelemetry` metadata and a
follow-up commit will read them once the MVP soak validates the
core algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class HealthSignals:
    """All inputs the normalizer needs to compute one device's state.

    Frozen + slots-friendly so an accidental mutation is loud.  Every
    field is keyword-only-ish at the dataclass level; tests construct
    these directly without much ceremony.
    """

    # ── Liveness signals (any one of these proves "we heard from
    # this device on this channel at this time") ───────────────────

    last_heartbeat_at: Optional[datetime] = None
    """Most recent CSAS edge heartbeat (Device.last_heartbeat)."""

    last_carrier_event_at: Optional[datetime] = None
    """Most recent carrier-side event — Verizon ThingSpace polling
    writes to Device.last_network_event today."""

    last_call_event_at: Optional[datetime] = None
    """Most recent Telnyx CDR for this device — derived as
    MAX(call_records.started_at) WHERE device_id=...."""

    last_vola_sync_at: Optional[datetime] = None
    """Most recent VOLA / TR-069 sync — Device.vola_last_sync,
    written by the Inseego provisioning workflow."""

    # ── Provider-reported state ────────────────────────────────────

    network_status: Optional[str] = None
    """Free-form vendor string — case-insensitive matched against
    thresholds.DISCONNECTED_NETWORK_STATUSES.  Unknown strings are
    NOT treated as degraded (the normalizer fails open)."""

    sip_status: Optional[str] = None
    """SIP registration state.  NOT populated by the MVP loader —
    reserved for a follow-up commit that reads CommandTelemetry."""

    # ── Quality ─────────────────────────────────────────────────────

    signal_dbm: Optional[float] = None
    """Cellular signal strength in dBm.  NOT populated by the MVP
    loader — also lives in CommandTelemetry."""

    heartbeat_interval_seconds: Optional[int] = None
    """Per-device cadence.  Phase 1 normalizer does not vary the
    staleness threshold per-device — it uses the platform-wide
    thresholds.STALE_OBSERVATION_SECONDS regardless.  Phase N1 may
    use this when continuity.py migrates."""

    # ── Lifecycle ───────────────────────────────────────────────────

    device_lifecycle: str = "active"
    """The Device.status column value — provisioning / active /
    inactive / decommissioned (or anything else that happens to be
    there).  Case-insensitive."""

    def has_any_liveness_signal(self) -> bool:
        """True when at least one liveness channel has a timestamp."""
        return any(
            ts is not None
            for ts in (
                self.last_heartbeat_at,
                self.last_carrier_event_at,
                self.last_call_event_at,
                self.last_vola_sync_at,
            )
        )

    def last_observed_at(self) -> Optional[datetime]:
        """Most recent timestamp across every liveness channel.

        Returns ``None`` when no channel has reported.
        """
        candidates = [
            ts
            for ts in (
                self.last_heartbeat_at,
                self.last_carrier_event_at,
                self.last_call_event_at,
                self.last_vola_sync_at,
            )
            if ts is not None
        ]
        if not candidates:
            return None
        return max(candidates)
