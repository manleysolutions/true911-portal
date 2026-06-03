"""Tests for device-fallback activation account-ID capture (Gap #2).

Before this fix, an activation/provisioning callback that matched only a Device
(no Sim row) had its generated account ID extracted but never persisted.  Now
``capture_activation_via_device`` find-or-creates a single Sim keyed on the
globally-unique ICCID so the account ID always lands on ``sims.meta``.

Proves:
  * No Sim exists  → exactly ONE Sim is created (no duplicate), with the
    account ID + activation record on meta, linked to the device.
  * A Sim already exists → it is REUSED (meta updated, device linked), never
    duplicated.
  * No usable ICCID  → capture is skipped safely (no Sim written).
  * Ambiguous device match → process_payload refuses, captures nothing.
  * End-to-end process_payload device-fallback path promotes AND captures.

DB is mocked (AsyncMock) — same house pattern as
test_tmobile_callback_device_fallback.py.  No real credentials, no network.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.sim import Sim
from app.services.tmobile_callback_processor import (
    ExtractedSignal,
    capture_activation_via_device,
    process_payload,
)

_NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


# ─── builders ───────────────────────────────────────────────────────


def _device(*, device_id="dev-cellular", tenant_id="tenant-prod",
            iccid=None, msisdn=None):
    return SimpleNamespace(
        device_id=device_id, tenant_id=tenant_id, iccid=iccid, msisdn=msisdn,
    )


def _signal(*, iccid=None, msisdn=None, account_id="ACC-789",
            activation_status="active", event_type="provisioning"):
    return ExtractedSignal(
        iccid=iccid, msisdn=msisdn, network_status="REGISTERED",
        event_timestamp=_NOW, event_type=event_type,
        account_id=account_id, activation_status=activation_status,
    )


def _payload(*, body, payload_id="wh-cap"):
    return SimpleNamespace(
        payload_id=payload_id, source="tmobile", direction="inbound",
        headers={"x-true911-tmobile-event-type": "provisioning"},
        body=body, raw_body=None, processed=False, created_at=_NOW,
    )


def _existing_sim(*, iccid, device_id=None, meta=None, msisdn=None):
    return SimpleNamespace(
        iccid=iccid, tenant_id="tenant-prod", device_id=device_id,
        meta=meta, msisdn=msisdn,
    )


# ═══════════════════════════════════════════════════════════════════
# capture_activation_via_device — unit
# ═══════════════════════════════════════════════════════════════════


class TestCaptureUnit:
    @pytest.mark.asyncio
    async def test_creates_one_sim_when_none_exists(self):
        device = _device(iccid="8901260963132697538")
        signal = _signal(iccid="8901260963132697538", msisdn="7542697860")
        # Sim lookup by ICCID returns nothing → create path.
        none_res = MagicMock(); none_res.scalar_one_or_none.return_value = None
        db = MagicMock(); db.execute = AsyncMock(return_value=none_res)
        db.add = MagicMock()

        status = await capture_activation_via_device(db, device, signal)

        assert status == "created_sim"
        # Exactly one Sim row added — no duplicate.
        db.add.assert_called_once()
        new_sim = db.add.call_args.args[0]
        assert isinstance(new_sim, Sim)
        assert new_sim.iccid == "8901260963132697538"
        assert new_sim.tenant_id == "tenant-prod"
        assert new_sim.device_id == "dev-cellular"
        assert new_sim.carrier == "tmobile"
        assert new_sim.data_source == "device_discovered"
        # Account ID persisted both flat and in the activation record.
        assert new_sim.meta["tmobile_account_id"] == "ACC-789"
        assert new_sim.meta["tmobile_msisdn"] == "7542697860"
        assert new_sim.meta["tmobile_activation"]["account_id"] == "ACC-789"
        assert new_sim.meta["tmobile_activation"]["state"] == "Activated"

    @pytest.mark.asyncio
    async def test_reuses_existing_sim_no_duplicate(self):
        device = _device(iccid="8901260963132697538")
        signal = _signal(iccid="8901260963132697538", msisdn="7542697860")
        existing = _existing_sim(iccid="8901260963132697538",
                                 device_id=None, meta={"volte_enabled": True})
        hit = MagicMock(); hit.scalar_one_or_none.return_value = existing
        db = MagicMock(); db.execute = AsyncMock(return_value=hit)
        db.add = MagicMock()

        status = await capture_activation_via_device(db, device, signal)

        assert status == "updated_sim"
        # The crucial guarantee: NO new Sim row created.
        db.add.assert_not_called()
        # Existing meta preserved + account ID merged in.
        assert existing.meta["volte_enabled"] is True
        assert existing.meta["tmobile_account_id"] == "ACC-789"
        # Device linked since it was previously unlinked.
        assert existing.device_id == "dev-cellular"

    @pytest.mark.asyncio
    async def test_existing_sim_device_link_preserved(self):
        device = _device(device_id="dev-new", iccid="8901260963132697538")
        signal = _signal(iccid="8901260963132697538")
        existing = _existing_sim(iccid="8901260963132697538",
                                 device_id="dev-original", meta=None)
        hit = MagicMock(); hit.scalar_one_or_none.return_value = existing
        db = MagicMock(); db.execute = AsyncMock(return_value=hit)
        db.add = MagicMock()

        await capture_activation_via_device(db, device, signal)

        # Already linked → we do NOT steal the Sim to a different device.
        assert existing.device_id == "dev-original"

    @pytest.mark.asyncio
    async def test_resolved_iccid_prefers_signal_then_device(self):
        # Signal has no ICCID; device.iccid is used to key the Sim.
        device = _device(iccid="8901111111111111111")
        signal = _signal(iccid=None, msisdn="7542697860")
        none_res = MagicMock(); none_res.scalar_one_or_none.return_value = None
        db = MagicMock(); db.execute = AsyncMock(return_value=none_res)
        db.add = MagicMock()

        status = await capture_activation_via_device(db, device, signal)

        assert status == "created_sim"
        assert db.add.call_args.args[0].iccid == "8901111111111111111"

    @pytest.mark.asyncio
    async def test_skips_safely_without_any_iccid(self):
        device = _device(iccid=None)
        signal = _signal(iccid=None, msisdn="7542697860")
        db = MagicMock(); db.execute = AsyncMock()
        db.add = MagicMock()

        status = await capture_activation_via_device(db, device, signal)

        assert status == "skipped:no_iccid"
        # No Sim written and no lookup issued — fail safe.
        db.add.assert_not_called()
        db.execute.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# process_payload — device-fallback path now captures
# ═══════════════════════════════════════════════════════════════════


class TestProcessPayloadCapture:
    @pytest.mark.asyncio
    async def test_device_fallback_with_account_id_creates_sim_and_promotes(self):
        payload = _payload(body={
            "iccid": "8901260963132697538",
            "accountId": "ACC-789",
            "activationStatus": "active",
            "network_status": "REGISTERED",
            "event_time": _NOW.isoformat(),
        })
        device = _device(iccid="8901260963132697538", msisdn="7542697860")

        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        sim_none = MagicMock(); sim_none.scalar_one_or_none.return_value = None
        dev_count = MagicMock(); dev_count.scalar.return_value = 1
        dev_load = MagicMock(); dev_load.scalar_one_or_none.return_value = device
        cap_none = MagicMock(); cap_none.scalar_one_or_none.return_value = None

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            load_hit,    # _load_payload
            sim_none,    # match_sim: iccid lookup (no Sim)
            dev_count,   # match_device_fallback: iccid count = 1
            dev_load,    # match_device_fallback: load device
            cap_none,    # capture: Sim lookup by ICCID (none → create)
        ])
        db.commit = AsyncMock()
        db.add = MagicMock()

        with patch(
            "app.services.tmobile_callback_processor.ingest_carrier_telemetry",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "promoted:device_fallback"
        assert result.account_capture == "created_sim"
        assert result.matched_device_id == "dev-cellular"
        assert result.matched_sim_iccid == "8901260963132697538"
        db.add.assert_called_once()
        new_sim = db.add.call_args.args[0]
        assert new_sim.meta["tmobile_account_id"] == "ACC-789"

    @pytest.mark.asyncio
    async def test_ambiguous_device_match_captures_nothing(self):
        payload = _payload(body={
            "iccid": "8901260963132697538",
            "accountId": "ACC-789",
            "activationStatus": "active",
            "event_time": _NOW.isoformat(),
        })

        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        sim_none = MagicMock(); sim_none.scalar_one_or_none.return_value = None
        dev_count = MagicMock(); dev_count.scalar.return_value = 2  # ambiguous

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[load_hit, sim_none, dev_count])
        db.commit = AsyncMock()
        db.add = MagicMock()

        with patch(
            "app.services.tmobile_callback_processor.ingest_carrier_telemetry",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "skipped:ambiguous_device_match"
        assert result.account_capture is None
        # No Sim created on an ambiguous match — fail safe.
        db.add.assert_not_called()
