"""Unit tests for app.services.health.normalizer — pure logic, no DB.

These tests are the executable spec for the algorithm.  Every
``compute_device_state`` branch is exercised; the site rollup rules
in ``compute_site_state`` get a full truth table.

If a test here changes meaning, ``docs/HEALTH_NORMALIZER_MVP.md`` and
``docs/AI_OPERATIONAL_SAFETY.md`` (the platform's safety contract for
read-only AI surfaces) must change too.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.health import (
    CanonicalDeviceState,
    CanonicalSiteState,
    HealthSignals,
    compute_device_state,
    compute_site_state,
)
from app.services.health import thresholds


_NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)


def _fresh(seconds_ago: int) -> datetime:
    """Return a timestamp that is ``seconds_ago`` before the pinned NOW."""
    return _NOW - timedelta(seconds=seconds_ago)


# ═══════════════════════════════════════════════════════════════════
# compute_device_state
# ═══════════════════════════════════════════════════════════════════


class TestDeviceLifecycleTerminals:
    """Lifecycle terminals beat every other rule."""

    def test_decommissioned_lifecycle_always_decommissioned(self):
        # Even with a totally fresh heartbeat, decommissioned wins.
        s = HealthSignals(
            last_heartbeat_at=_NOW,
            device_lifecycle="decommissioned",
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.DECOMMISSIONED

    def test_retired_lifecycle_treated_as_decommissioned(self):
        s = HealthSignals(
            last_heartbeat_at=_NOW,
            device_lifecycle="Retired",  # case-insensitive
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.DECOMMISSIONED

    def test_inactive_lifecycle_returns_offline(self):
        s = HealthSignals(
            last_heartbeat_at=_NOW,
            device_lifecycle="inactive",
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.OFFLINE


class TestDeviceProvisioning:
    """No liveness signal at all → PROVISIONING (operator action: install)."""

    def test_no_signals_at_all_returns_provisioning(self):
        s = HealthSignals(device_lifecycle="active")
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.PROVISIONING

    def test_provisioning_lifecycle_with_no_signals_returns_provisioning(self):
        s = HealthSignals(device_lifecycle="provisioning")
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.PROVISIONING

    def test_pending_lifecycle_with_no_signals_returns_provisioning(self):
        s = HealthSignals(device_lifecycle="pending")
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.PROVISIONING


class TestSingleChannelLiveness:
    """Each liveness channel independently proves freshness."""

    def test_heartbeat_only_fresh_returns_connected(self):
        s = HealthSignals(last_heartbeat_at=_fresh(60))
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED

    def test_telnyx_call_only_fresh_returns_connected(self):
        # No heartbeat ever — Telnyx CDR within the last minute is
        # sufficient to consider this device 'connected' for the AI
        # Health Summary.  This is the headline bug-fix scenario from
        # HEALTH_STATUS_AUDIT.md §5 Scenario B.
        s = HealthSignals(last_call_event_at=_fresh(60))
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED

    def test_carrier_event_only_fresh_returns_connected(self):
        # Verizon poll wrote last_network_event recently — that alone
        # is sufficient (Scenario A in the audit doc).
        s = HealthSignals(last_carrier_event_at=_fresh(60))
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED

    def test_vola_sync_only_fresh_returns_connected(self):
        s = HealthSignals(last_vola_sync_at=_fresh(60))
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED


class TestStaleness:
    """Past STALE_OBSERVATION_SECONDS on every channel → OFFLINE."""

    def test_heartbeat_just_past_threshold_returns_offline(self):
        s = HealthSignals(
            last_heartbeat_at=_fresh(thresholds.STALE_OBSERVATION_SECONDS + 1),
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.OFFLINE

    def test_heartbeat_exactly_at_threshold_is_fresh(self):
        # The threshold is exclusive: elapsed > threshold means stale.
        s = HealthSignals(
            last_heartbeat_at=_fresh(thresholds.STALE_OBSERVATION_SECONDS),
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED

    def test_max_across_channels_determines_freshness(self):
        # Heartbeat is ancient, Telnyx CDR landed 30s ago → CONNECTED.
        s = HealthSignals(
            last_heartbeat_at=_fresh(86400),         # 1 day stale
            last_call_event_at=_fresh(30),            # 30s ago
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED

    def test_all_channels_stale_returns_offline(self):
        stale = thresholds.STALE_OBSERVATION_SECONDS + 60
        s = HealthSignals(
            last_heartbeat_at=_fresh(stale),
            last_carrier_event_at=_fresh(stale),
            last_call_event_at=_fresh(stale),
            last_vola_sync_at=_fresh(stale),
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.OFFLINE


class TestDegradation:
    """Fresh liveness + a degradation indicator → ATTENTION."""

    def test_disconnected_network_status_returns_attention(self):
        s = HealthSignals(
            last_heartbeat_at=_fresh(60),
            network_status="disconnected",
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.ATTENTION

    def test_offline_network_status_returns_attention(self):
        s = HealthSignals(
            last_heartbeat_at=_fresh(60),
            network_status="OFFLINE",  # case-insensitive
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.ATTENTION

    def test_unknown_network_status_does_not_degrade(self):
        # Fail open: a vendor-specific string we haven't enumerated
        # must NOT be treated as degraded.  Otherwise rolling out a
        # new carrier would break health reporting until thresholds.py
        # gets patched.
        s = HealthSignals(
            last_heartbeat_at=_fresh(60),
            network_status="some-vendor-state-we-dont-know",
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED

    def test_signal_at_critical_threshold_returns_attention(self):
        s = HealthSignals(
            last_heartbeat_at=_fresh(60),
            signal_dbm=thresholds.SIGNAL_CRITICAL_DBM,
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.ATTENTION

    def test_signal_above_critical_does_not_degrade(self):
        s = HealthSignals(
            last_heartbeat_at=_fresh(60),
            signal_dbm=thresholds.SIGNAL_CRITICAL_DBM + 5,  # less negative = stronger
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED

    def test_unregistered_sip_returns_attention(self):
        s = HealthSignals(
            last_heartbeat_at=_fresh(60),
            sip_status="unregistered",
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.ATTENTION

    def test_failed_sip_returns_attention(self):
        s = HealthSignals(
            last_heartbeat_at=_fresh(60),
            sip_status="failed",
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.ATTENTION

    def test_registered_sip_does_not_degrade(self):
        s = HealthSignals(
            last_heartbeat_at=_fresh(60),
            sip_status="registered",
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED

    def test_stale_liveness_overrides_degradation(self):
        # Even if the (stale) provider says 'connected', no fresh
        # signal at all means OFFLINE.  Order matters in the algorithm.
        s = HealthSignals(
            last_heartbeat_at=_fresh(thresholds.STALE_OBSERVATION_SECONDS + 60),
            network_status="connected",
        )
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.OFFLINE


class TestNaiveTimestamps:
    """Naive datetimes (no tzinfo) are coerced to UTC.

    Some ORM cold-path queries lose tzinfo even on TIMESTAMPTZ columns;
    the normalizer must not raise a TypeError on subtraction.
    """

    def test_naive_heartbeat_treated_as_utc(self):
        naive = (_NOW - timedelta(seconds=60)).replace(tzinfo=None)
        s = HealthSignals(last_heartbeat_at=naive)
        # Should compute without raising.
        assert compute_device_state(s, now=_NOW) == CanonicalDeviceState.CONNECTED


# ═══════════════════════════════════════════════════════════════════
# compute_site_state
# ═══════════════════════════════════════════════════════════════════


class TestSiteRollup:
    def test_no_devices_returns_unknown(self):
        assert compute_site_state([]) == CanonicalSiteState.UNKNOWN

    def test_all_connected_returns_connected(self):
        assert compute_site_state(
            [CanonicalDeviceState.CONNECTED] * 3
        ) == CanonicalSiteState.CONNECTED

    def test_all_offline_returns_offline(self):
        assert compute_site_state(
            [CanonicalDeviceState.OFFLINE, CanonicalDeviceState.OFFLINE]
        ) == CanonicalSiteState.OFFLINE

    def test_all_provisioning_returns_provisioning(self):
        assert compute_site_state(
            [CanonicalDeviceState.PROVISIONING, CanonicalDeviceState.PROVISIONING]
        ) == CanonicalSiteState.PROVISIONING

    def test_all_decommissioned_returns_decommissioned(self):
        assert compute_site_state(
            [CanonicalDeviceState.DECOMMISSIONED, CanonicalDeviceState.DECOMMISSIONED]
        ) == CanonicalSiteState.DECOMMISSIONED

    def test_decommissioned_excluded_from_rollup(self):
        # One device decommissioned, one connected → CONNECTED (the
        # decommissioned device is not part of operational status).
        assert compute_site_state([
            CanonicalDeviceState.DECOMMISSIONED,
            CanonicalDeviceState.CONNECTED,
        ]) == CanonicalSiteState.CONNECTED

    @pytest.mark.parametrize("mix", [
        [CanonicalDeviceState.CONNECTED, CanonicalDeviceState.OFFLINE],
        [CanonicalDeviceState.CONNECTED, CanonicalDeviceState.ATTENTION],
        [CanonicalDeviceState.CONNECTED, CanonicalDeviceState.PROVISIONING],
        [CanonicalDeviceState.OFFLINE, CanonicalDeviceState.PROVISIONING],
        [CanonicalDeviceState.ATTENTION] * 3,
    ])
    def test_any_mixed_state_returns_attention(self, mix):
        # ATTENTION alone is the conservative aggregate — even three
        # ATTENTION devices roll up as ATTENTION rather than CONNECTED.
        assert compute_site_state(mix) == CanonicalSiteState.ATTENTION
