"""Tests for app.services.health.signals_loader.

The loader is a thin read layer — it should:
  * scope every query by tenant_id (the structural isolation guarantee)
  * never write
  * compose HealthSignals from the right column on the right row
  * survive missing optional columns (defensive getattr)
  * issue O(1) round-trips regardless of fleet size

We exercise this with AsyncMock for the AsyncSession so the tests
stay hermetic — same pattern as the existing
``tests/test_health_system.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.health import HealthSignals
from app.services.health.signals_loader import (
    load_signals_for_site,
    load_signals_for_tenant,
)


_NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)


def _device(
    device_id: str,
    *,
    site_id: str = "site-1",
    last_heartbeat=None,
    network_status=None,
    last_network_event=None,
    vola_last_sync=None,
    heartbeat_interval=300,
    status="active",
):
    """Build a Device-shaped SimpleNamespace the loader will accept."""
    return SimpleNamespace(
        device_id=device_id,
        site_id=site_id,
        last_heartbeat=last_heartbeat,
        network_status=network_status,
        last_network_event=last_network_event,
        vola_last_sync=vola_last_sync,
        heartbeat_interval=heartbeat_interval,
        status=status,
    )


def _mock_db(devices, last_call_rows=None):
    """Return an AsyncMock AsyncSession that yields the canned rows.

    AsyncSession.execute is async and returns a Result.  Result.scalars()
    returns a ScalarResult with .all().  We mock just enough of that
    chain to drive the loader without bringing in a real engine.
    """
    last_call_rows = last_call_rows or []

    devices_result = MagicMock()
    devices_scalars = MagicMock()
    devices_scalars.all.return_value = devices
    devices_result.scalars.return_value = devices_scalars

    calls_result = MagicMock()
    calls_result.all.return_value = last_call_rows

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[devices_result, calls_result])
    return db


# ─── load_signals_for_tenant ───────────────────────────────────────


class TestLoadSignalsForTenant:
    @pytest.mark.asyncio
    async def test_empty_tenant_returns_empty_dict(self):
        db = MagicMock()
        empty_result = MagicMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result.scalars.return_value = empty_scalars
        db.execute = AsyncMock(return_value=empty_result)

        result = await load_signals_for_tenant(db, "tenant-empty")
        assert result == {}
        # Verified: with no devices, the loader skips the call-records
        # query entirely (only one DB round-trip).
        assert db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_one_healthsignals_per_device(self):
        devices = [
            _device("dev-a", last_heartbeat=_NOW - timedelta(seconds=30)),
            _device("dev-b", last_heartbeat=None),
        ]
        db = _mock_db(devices)
        result = await load_signals_for_tenant(db, "tenant-x")

        assert set(result.keys()) == {"dev-a", "dev-b"}
        assert isinstance(result["dev-a"], HealthSignals)
        assert isinstance(result["dev-b"], HealthSignals)

    @pytest.mark.asyncio
    async def test_heartbeat_field_propagates(self):
        ts = _NOW - timedelta(seconds=120)
        devices = [_device("dev-a", last_heartbeat=ts)]
        db = _mock_db(devices)
        result = await load_signals_for_tenant(db, "tenant-x")
        assert result["dev-a"].last_heartbeat_at == ts

    @pytest.mark.asyncio
    async def test_carrier_event_propagates_from_last_network_event(self):
        ts = _NOW - timedelta(seconds=45)
        devices = [_device("dev-a", last_network_event=ts)]
        db = _mock_db(devices)
        result = await load_signals_for_tenant(db, "tenant-x")
        assert result["dev-a"].last_carrier_event_at == ts

    @pytest.mark.asyncio
    async def test_vola_sync_propagates(self):
        ts = _NOW - timedelta(hours=1)
        devices = [_device("dev-a", vola_last_sync=ts)]
        db = _mock_db(devices)
        result = await load_signals_for_tenant(db, "tenant-x")
        assert result["dev-a"].last_vola_sync_at == ts

    @pytest.mark.asyncio
    async def test_telnyx_last_call_attached_per_device(self):
        ts_a = _NOW - timedelta(seconds=60)
        ts_b = _NOW - timedelta(seconds=600)
        devices = [_device("dev-a"), _device("dev-b"), _device("dev-c")]
        last_call_rows = [
            SimpleNamespace(device_id="dev-a", last_call=ts_a),
            SimpleNamespace(device_id="dev-b", last_call=ts_b),
            # dev-c has no call records — should remain None
        ]
        db = _mock_db(devices, last_call_rows=last_call_rows)
        result = await load_signals_for_tenant(db, "tenant-x")

        assert result["dev-a"].last_call_event_at == ts_a
        assert result["dev-b"].last_call_event_at == ts_b
        assert result["dev-c"].last_call_event_at is None

    @pytest.mark.asyncio
    async def test_defensive_getattr_when_optional_columns_missing(self):
        # Simulate an older ORM row without last_network_event /
        # vola_last_sync attributes — the loader should not crash.
        bare = SimpleNamespace(
            device_id="dev-bare",
            site_id="site-1",
            last_heartbeat=None,
            network_status=None,
            heartbeat_interval=300,
            status="active",
        )
        db = _mock_db([bare])
        result = await load_signals_for_tenant(db, "tenant-x")
        assert result["dev-bare"].last_carrier_event_at is None
        assert result["dev-bare"].last_vola_sync_at is None

    @pytest.mark.asyncio
    async def test_lifecycle_string_falls_back_to_active_when_null(self):
        d = _device("dev-a", status=None)
        db = _mock_db([d])
        result = await load_signals_for_tenant(db, "tenant-x")
        assert result["dev-a"].device_lifecycle == "active"

    @pytest.mark.asyncio
    async def test_signal_dbm_and_sip_status_are_none_in_mvp(self):
        # Documenting the MVP gap: signal_dbm and sip_status live in
        # CommandTelemetry, not Device.  The loader leaves them None
        # until a follow-up commit pulls them.
        devices = [_device("dev-a", last_heartbeat=_NOW)]
        db = _mock_db(devices)
        result = await load_signals_for_tenant(db, "tenant-x")
        assert result["dev-a"].signal_dbm is None
        assert result["dev-a"].sip_status is None

    @pytest.mark.asyncio
    async def test_total_round_trips_is_two_with_devices(self):
        # The 'bulk queries, not per-device' guarantee — fleet of
        # 50 devices is still 2 DB round-trips.
        devices = [_device(f"dev-{i}") for i in range(50)]
        db = _mock_db(devices)
        await load_signals_for_tenant(db, "tenant-x")
        assert db.execute.call_count == 2


# ─── load_signals_for_site ─────────────────────────────────────────


class TestLoadSignalsForSite:
    @pytest.mark.asyncio
    async def test_site_with_no_devices_returns_empty_dict(self):
        db = MagicMock()
        empty_result = MagicMock()
        empty_scalars = MagicMock()
        empty_scalars.all.return_value = []
        empty_result.scalars.return_value = empty_scalars
        db.execute = AsyncMock(return_value=empty_result)
        result = await load_signals_for_site(db, "tenant-x", "site-empty")
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_one_healthsignals_per_device_at_site(self):
        devices = [
            _device("dev-a", site_id="site-1"),
            _device("dev-b", site_id="site-1"),
        ]
        db = _mock_db(devices)
        result = await load_signals_for_site(db, "tenant-x", "site-1")
        assert set(result.keys()) == {"dev-a", "dev-b"}
