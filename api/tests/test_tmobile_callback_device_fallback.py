"""Tests for the Device-fallback path in tmobile_callback_processor.

Production finding (2026-05-26)
===============================

After ``FEATURE_TMOBILE_CALLBACK_INGEST=true`` was flipped on, end-to-end
testing confirmed callbacks were arriving and being archived correctly,
but ``Device.last_network_event`` never updated.  Root cause: many
imported cellular devices store ICCID/MSISDN directly on the ``Device``
row, leaving the ``Sim`` table empty for those devices.  The processor
only ever matched against ``Sim``, so those callbacks were silently
archived as ``skipped:no_match``.

The fix: after ``match_sim`` returns no match, try
``match_device_fallback`` — a direct lookup against
``Device.iccid`` / ``Device.msisdn`` with normalised MSISDN variants.
Same safety contract: ambiguous → refuse, zero → archive-only.

What these tests prove
======================

  * The SIM-match path is unchanged (still wins first when populated).
  * No-SIM-match + exact ``Device.msisdn`` match → promotes.
  * No-SIM-match + formatted-MSISDN variant match → promotes.
  * No-SIM-match + ``Device.iccid`` match → promotes.
  * Multiple device matches → skipped:ambiguous_device_match.
  * No match anywhere → skipped:no_match (existing behavior preserved).
  * ``_msisdn_variants`` covers the formats T-Mobile emits.
  * Callback endpoint still returns HTTP 200 across all device-fallback
    branches (router contract preserved).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.routers.tmobile_callback import router as tmobile_router
from app.services.tmobile_callback_processor import (
    DeviceMatchResult,
    ExtractedSignal,
    _msisdn_variants,
    match_device_fallback,
    process_payload,
)


_NOW = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)


# ─── Shared builders ────────────────────────────────────────────────


def _payload(*, body=None, headers=None, created_at=_NOW, payload_id="wh-test"):
    return SimpleNamespace(
        payload_id=payload_id,
        source="tmobile",
        direction="inbound",
        headers=headers or {},
        body=body,
        raw_body=None,
        processed=False,
        created_at=created_at,
    )


def _device(*, device_id="dev-a", tenant_id="tenant-x",
            iccid=None, msisdn=None):
    return SimpleNamespace(
        device_id=device_id,
        tenant_id=tenant_id,
        site_id="site-a",
        carrier="tmobile",
        network_status=None,
        last_network_event=None,
        telemetry_source=None,
        data_usage_mb=None,
        iccid=iccid,
        msisdn=msisdn,
    )


def _sim(*, iccid="89014103211118510720", msisdn="13105551234",
         tenant_id="tenant-x", device_id="dev-a"):
    return SimpleNamespace(
        iccid=iccid, msisdn=msisdn, tenant_id=tenant_id,
        device_id=device_id, carrier="tmobile", id=1, status="active",
    )


def _signal(*, iccid=None, msisdn=None, network_status=None,
            event_type="usage", ts=_NOW):
    return ExtractedSignal(
        iccid=iccid, msisdn=msisdn,
        network_status=network_status,
        event_timestamp=ts, event_type=event_type,
    )


# ═══════════════════════════════════════════════════════════════════
# _msisdn_variants — formatting normalisation
# ═══════════════════════════════════════════════════════════════════


class TestMsisdnVariants:
    """T-Mobile PIT callbacks emit MSISDNs in multiple forms.  The
    operator-imported ``Device.msisdn`` values were sourced from
    spreadsheets / CRM exports that also use multiple forms.  These
    tests pin which variants resolve to the same canonical set."""

    @pytest.mark.parametrize("raw", [
        "8563081391",      # 10-digit US local
        "18563081391",     # 11-digit with country
        "+18563081391",    # E.164
    ])
    def test_us_number_variants_include_all_three_forms(self, raw):
        v = _msisdn_variants(raw)
        assert "8563081391" in v
        assert "18563081391" in v
        assert "+18563081391" in v

    def test_formatted_input_is_normalised_to_digits(self):
        v = _msisdn_variants("(856) 308-1391")
        # The raw string is always preserved (so a literal stored value
        # still matches), plus the digits-only and US-derived variants.
        assert "(856) 308-1391" in v
        assert "8563081391" in v
        assert "18563081391" in v
        assert "+18563081391" in v

    def test_empty_returns_empty(self):
        assert _msisdn_variants(None) == ()
        assert _msisdn_variants("") == ()
        assert _msisdn_variants("   ") == ()

    def test_non_us_falls_through_safely(self):
        """A non-US E.164 or short string should not invent US prefixes."""
        v = _msisdn_variants("+447911123456")  # UK mobile
        assert "+447911123456" in v
        assert "447911123456" in v
        # Must NOT inject a US "+1" wrap.
        assert "+1447911123456" not in v

    def test_short_garbage_does_not_explode(self):
        """Defensive: a 3-digit string shouldn't crash or produce
        unsafe variants like a 'leading-1 + 2 chars' MSISDN."""
        v = _msisdn_variants("123")
        assert "123" in v
        # No US derivation for short input.
        assert "1123" not in v
        assert "+1123" not in v


# ═══════════════════════════════════════════════════════════════════
# match_device_fallback — unit
# ═══════════════════════════════════════════════════════════════════


class TestMatchDeviceFallback:
    """Drive ``match_device_fallback`` through each branch with
    AsyncMock — no real DB.  Same pattern as the SIM-side ``match_sim``
    tests in ``test_tmobile_callback_processor.py``."""

    @pytest.mark.asyncio
    async def test_iccid_single_match_returns_one(self):
        device = _device(iccid="89014103211118510720")
        count_r = MagicMock(); count_r.scalar.return_value = 1
        load_r = MagicMock(); load_r.scalar_one_or_none.return_value = device
        db = MagicMock(); db.execute = AsyncMock(side_effect=[count_r, load_r])

        result = await match_device_fallback(
            db, _signal(iccid="89014103211118510720"),
        )
        assert result.kind == "one"
        assert result.device is device
        assert result.matched_on == "iccid"
        # ICCID hit → MSISDN sub-query NEVER issued.
        assert db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_iccid_ambiguous_refused(self):
        count_r = MagicMock(); count_r.scalar.return_value = 3
        db = MagicMock(); db.execute = AsyncMock(side_effect=[count_r])

        result = await match_device_fallback(
            db, _signal(iccid="89014103211118510720"),
        )
        assert result.kind == "ambiguous"
        assert result.candidate_count == 3
        assert result.matched_on == "iccid"
        # Load query NOT issued — we refuse to guess.
        assert db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_iccid_miss_falls_through_to_msisdn(self):
        device = _device(msisdn="18563081391")
        iccid_count_r = MagicMock(); iccid_count_r.scalar.return_value = 0
        msisdn_count_r = MagicMock(); msisdn_count_r.scalar.return_value = 1
        msisdn_load_r = MagicMock(); msisdn_load_r.scalar_one_or_none.return_value = device
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            iccid_count_r, msisdn_count_r, msisdn_load_r,
        ])

        result = await match_device_fallback(
            db, _signal(iccid="ABSENT", msisdn="8563081391"),
        )
        assert result.kind == "one"
        assert result.device is device
        assert result.matched_on == "msisdn"

    @pytest.mark.asyncio
    async def test_msisdn_only_single_match(self):
        device = _device(msisdn="+18563081391")
        msisdn_count_r = MagicMock(); msisdn_count_r.scalar.return_value = 1
        msisdn_load_r = MagicMock(); msisdn_load_r.scalar_one_or_none.return_value = device
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[msisdn_count_r, msisdn_load_r])

        result = await match_device_fallback(
            db, _signal(msisdn="8563081391"),
        )
        assert result.kind == "one"
        assert result.matched_on == "msisdn"

    @pytest.mark.asyncio
    async def test_msisdn_ambiguous_refused(self):
        msisdn_count_r = MagicMock(); msisdn_count_r.scalar.return_value = 2
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[msisdn_count_r])

        result = await match_device_fallback(
            db, _signal(msisdn="8563081391"),
        )
        assert result.kind == "ambiguous"
        assert result.candidate_count == 2
        assert result.matched_on == "msisdn"

    @pytest.mark.asyncio
    async def test_no_identifiers_short_circuit(self):
        db = MagicMock(); db.execute = AsyncMock()
        result = await match_device_fallback(db, _signal())
        assert result.kind == "none"
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_match_at_all(self):
        iccid_count_r = MagicMock(); iccid_count_r.scalar.return_value = 0
        msisdn_count_r = MagicMock(); msisdn_count_r.scalar.return_value = 0
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[iccid_count_r, msisdn_count_r])

        result = await match_device_fallback(
            db, _signal(iccid="X", msisdn="8563081391"),
        )
        assert result.kind == "none"


# ═══════════════════════════════════════════════════════════════════
# process_payload — sim-vs-device priority + new branches
# ═══════════════════════════════════════════════════════════════════


class TestSimMatchStillWinsFirst:
    """Regression: when the SIM table has the match, the SIM path runs
    and the Device fallback is NEVER consulted.  This preserves the
    pre-fallback ``promoted`` status and ensures the sim-side tenant
    isolation contract still holds."""

    @pytest.mark.asyncio
    async def test_sim_match_promotes_without_touching_device_fallback(self):
        payload = _payload(body={
            "iccid": "89014103211118510720",
            "network_status": "REGISTERED",
            "event_time": _NOW.isoformat(),
        })
        sim = _sim()
        device = _device()

        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        sim_hit = MagicMock(); sim_hit.scalar_one_or_none.return_value = sim
        device_hit = MagicMock(); device_hit.scalar_one_or_none.return_value = device

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[load_hit, sim_hit, device_hit])
        db.commit = AsyncMock()

        ingest_mock = AsyncMock(return_value=[])
        with patch(
            "app.services.tmobile_callback_processor.ingest_carrier_telemetry",
            new=ingest_mock,
        ), patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        # The headline assertion: status is the SIM-path "promoted",
        # NOT "promoted:device_fallback".
        assert result.status == "promoted"
        assert result.matched_sim_iccid == sim.iccid
        # Exactly three execute calls: payload load + sim match + device lookup.
        # No fourth call (device-fallback count) was issued.
        assert db.execute.call_count == 3


class TestNoSimMatchDeviceFallbackPromotes:
    """Production-finding coverage: with the Sim table empty, the
    callback should still promote when an exact Device match exists."""

    @pytest.mark.asyncio
    async def test_no_sim_match_exact_msisdn_device_promotes(self):
        """Stored ``Device.msisdn`` matches the callback MSISDN
        exactly (no formatting variation)."""
        payload = _payload(body={
            "msisdn": "18563081391",
            "network_status": "REGISTERED",
            "event_time": _NOW.isoformat(),
        })
        device = _device(device_id="dev-cellular", tenant_id="tenant-prod",
                         msisdn="18563081391")

        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        # SIM side: msisdn-count=0 (sim table empty for this number).
        sim_count = MagicMock(); sim_count.scalar.return_value = 0
        # Device fallback: msisdn count=1, load returns device.
        # (No ICCID in body, so iccid sub-query is skipped.)
        dev_count = MagicMock(); dev_count.scalar.return_value = 1
        dev_load = MagicMock(); dev_load.scalar_one_or_none.return_value = device

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            load_hit, sim_count, dev_count, dev_load,
        ])
        db.commit = AsyncMock()

        ingest_mock = AsyncMock(return_value=[])
        with patch(
            "app.services.tmobile_callback_processor.ingest_carrier_telemetry",
            new=ingest_mock,
        ), patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "promoted:device_fallback"
        assert result.matched_device_id == device.device_id
        # Sim id is not populated on this path — that's the contract.
        assert result.matched_sim_iccid is None
        # Tenant is taken from the Device, not guessed.
        ingest_mock.assert_awaited_once()
        assert ingest_mock.await_args.args[1] == "tenant-prod"
        telemetry = ingest_mock.await_args.args[2]
        assert telemetry.device_id == "dev-cellular"
        assert telemetry.carrier == "t-mobile"
        assert telemetry.network_status == "REGISTERED"

    @pytest.mark.asyncio
    async def test_no_sim_match_formatted_msisdn_variant_promotes(self):
        """Callback emits ``8563081391``, but operator imported
        ``+18563081391``.  Variant set covers both."""
        payload = _payload(body={
            "msisdn": "8563081391",   # 10-digit US local from T-Mobile
            "event_time": _NOW.isoformat(),
        })
        device = _device(device_id="dev-cellular", tenant_id="tenant-prod",
                         msisdn="+18563081391")  # stored in E.164

        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        sim_count = MagicMock(); sim_count.scalar.return_value = 0
        dev_count = MagicMock(); dev_count.scalar.return_value = 1
        dev_load = MagicMock(); dev_load.scalar_one_or_none.return_value = device

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            load_hit, sim_count, dev_count, dev_load,
        ])
        db.commit = AsyncMock()

        ingest_mock = AsyncMock(return_value=[])
        with patch(
            "app.services.tmobile_callback_processor.ingest_carrier_telemetry",
            new=ingest_mock,
        ), patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "promoted:device_fallback"
        assert result.matched_device_id == device.device_id

    @pytest.mark.asyncio
    async def test_no_sim_match_iccid_on_device_promotes(self):
        """ICCID stored on Device row (no SIM record) → device
        fallback path promotes."""
        payload = _payload(body={
            "iccid": "89014103211118510720",
            "event_time": _NOW.isoformat(),
        })
        device = _device(device_id="dev-cellular", tenant_id="tenant-prod",
                         iccid="89014103211118510720")

        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        # SIM side: ICCID lookup returns None (sim table empty).
        sim_miss = MagicMock(); sim_miss.scalar_one_or_none.return_value = None
        # Device fallback: ICCID count=1, load returns device.
        dev_count = MagicMock(); dev_count.scalar.return_value = 1
        dev_load = MagicMock(); dev_load.scalar_one_or_none.return_value = device

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            load_hit, sim_miss, dev_count, dev_load,
        ])
        db.commit = AsyncMock()

        ingest_mock = AsyncMock(return_value=[])
        with patch(
            "app.services.tmobile_callback_processor.ingest_carrier_telemetry",
            new=ingest_mock,
        ), patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "promoted:device_fallback"
        assert result.matched_device_id == device.device_id


class TestNoSimMatchAmbiguousDeviceFallbackRefuses:
    @pytest.mark.asyncio
    async def test_multiple_devices_match_msisdn_is_skipped(self):
        payload = _payload(body={
            "msisdn": "8563081391",
            "event_time": _NOW.isoformat(),
        })
        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        sim_count = MagicMock(); sim_count.scalar.return_value = 0
        # Two devices match the same MSISDN variants → ambiguous.
        dev_count = MagicMock(); dev_count.scalar.return_value = 2

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            load_hit, sim_count, dev_count,
        ])
        db.commit = AsyncMock()

        ingest_mock = AsyncMock(return_value=[])
        with patch(
            "app.services.tmobile_callback_processor.ingest_carrier_telemetry",
            new=ingest_mock,
        ), patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "skipped:ambiguous_device_match"
        assert "matched_on=msisdn" in (result.reason or "")
        assert "candidates=2" in (result.reason or "")
        # Critically, the load query was NOT issued (we refuse to guess).
        ingest_mock.assert_not_called()


class TestNoSimNoDeviceMatchPreservesArchiveOnly:
    @pytest.mark.asyncio
    async def test_no_sim_no_device_archives_only(self):
        """When neither Sim nor Device matches, the original
        archive-only behavior is preserved (status=skipped:no_match)."""
        payload = _payload(body={
            "iccid": "89014103211118510720",
            "msisdn": "8563081391",
            "event_time": _NOW.isoformat(),
        })
        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        # Sim path: ICCID miss → fall through to MSISDN count (0) → none.
        sim_iccid_miss = MagicMock(); sim_iccid_miss.scalar_one_or_none.return_value = None
        sim_msisdn_count = MagicMock(); sim_msisdn_count.scalar.return_value = 0
        # Device fallback: ICCID count=0 → fall through to MSISDN count=0 → none.
        dev_iccid_count = MagicMock(); dev_iccid_count.scalar.return_value = 0
        dev_msisdn_count = MagicMock(); dev_msisdn_count.scalar.return_value = 0

        db = MagicMock()
        db.execute = AsyncMock(side_effect=[
            load_hit, sim_iccid_miss, sim_msisdn_count,
            dev_iccid_count, dev_msisdn_count,
        ])
        db.commit = AsyncMock()

        ingest_mock = AsyncMock(return_value=[])
        with patch(
            "app.services.tmobile_callback_processor.ingest_carrier_telemetry",
            new=ingest_mock,
        ), patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "skipped:no_match"
        assert payload.processed is True
        ingest_mock.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# Router-side: HTTP 200 contract still holds across new branches
# ═══════════════════════════════════════════════════════════════════


def _capture_db_mock():
    db = MagicMock()
    db.added = []
    db.add = lambda obj: db.added.append(obj)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


def _build_app_with_db(db):
    app = FastAPI()
    app.include_router(tmobile_router, prefix="/tmobile/wholesale")

    async def _stub_get_db():
        yield db

    app.dependency_overrides[get_db] = _stub_get_db
    return app


class TestCallbackStillReturns200:
    """The PIT-validator contract: regardless of what the device
    fallback does at worker-time, the synchronous callback endpoint
    must return HTTP 200.  The new fallback only affects the worker,
    not the router; these tests guard against a refactor accidentally
    plumbing fallback logic into the request path."""

    def test_flag_on_callback_returns_200_when_fallback_will_match(self):
        from types import SimpleNamespace as _NS
        db = _capture_db_mock()
        client = TestClient(_build_app_with_db(db))

        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.routers.tmobile_callback.job_service.create_and_enqueue",
            new=AsyncMock(return_value=_NS(id=1)),
        ):
            r = client.post(
                "/tmobile/wholesale/callback/usage",
                json={"msisdn": "8563081391"},
            )

        assert r.status_code == 200
        # Archive still occurred — the router is unchanged.
        assert len(db.added) == 1

    def test_flag_on_callback_returns_200_when_fallback_will_be_ambiguous(self):
        from types import SimpleNamespace as _NS
        db = _capture_db_mock()
        client = TestClient(_build_app_with_db(db))

        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.routers.tmobile_callback.job_service.create_and_enqueue",
            new=AsyncMock(return_value=_NS(id=1)),
        ):
            r = client.post(
                "/tmobile/wholesale/callback/device-change",
                json={"msisdn": "8563081391"},  # would be ambiguous downstream
            )

        # The router doesn't know; it returns 200 regardless.
        assert r.status_code == 200
