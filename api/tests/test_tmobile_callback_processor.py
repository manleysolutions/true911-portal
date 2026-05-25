"""Unit tests for app.services.tmobile_callback_processor.

The processor decides whether a T-Mobile PIT callback becomes carrier-
liveness evidence (Device.last_network_event update via the existing
carrier_adapter path) or is archived-only.  Every decision branch is
exercised here with AsyncMock so we don't need a real database.

The "no real DB" choice keeps these tests fast (<1s) and identical in
shape to ``tests/test_health_signals_loader.py`` — the loader test
already proven to work for similar shapes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tmobile_callback_processor import (
    EVENT_TYPE_HEADER,
    ExtractedSignal,
    ProcessResult,
    SimMatchResult,
    _redact_identifier,
    extract_signal,
    find_linked_device,
    match_sim,
    process_payload,
)


_NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)


def _payload(
    *,
    body=None,
    headers=None,
    created_at=_NOW,
    payload_id="wh-test-1",
):
    """Build an IntegrationPayload-shaped SimpleNamespace."""
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


def _sim(*, iccid="89014103211118510720", msisdn="13105551234",
         tenant_id="tenant-x", device_id="dev-a"):
    return SimpleNamespace(
        iccid=iccid,
        msisdn=msisdn,
        tenant_id=tenant_id,
        device_id=device_id,
        carrier="tmobile",
        id=1,
        status="active",
    )


def _device(*, device_id="dev-a", tenant_id="tenant-x"):
    return SimpleNamespace(
        device_id=device_id,
        tenant_id=tenant_id,
        site_id="site-a",
        carrier="tmobile",
        network_status=None,
        last_network_event=None,
        telemetry_source=None,
        data_usage_mb=None,
    )


# ═══════════════════════════════════════════════════════════════════
# extract_signal
# ═══════════════════════════════════════════════════════════════════


class TestExtractSignal:
    def test_extracts_iccid_msisdn_status_from_canonical_keys(self):
        p = _payload(
            body={
                "iccid": "89014103211118510720",
                "msisdn": "13105551234",
                "network_status": "registered",
                "event_time": "2026-05-25T11:59:30Z",
            },
            headers={EVENT_TYPE_HEADER: "subscriber_status"},
        )
        sig = extract_signal(p)
        assert sig.iccid == "89014103211118510720"
        assert sig.msisdn == "13105551234"
        assert sig.network_status == "registered"
        assert sig.event_timestamp == datetime(2026, 5, 25, 11, 59, 30, tzinfo=timezone.utc)
        assert sig.event_type == "subscriber_status"

    def test_extracts_iccid_msisdn_from_alternate_camel_keys(self):
        p = _payload(body={
            "ICCID": "89014103211118510720",
            "MSISDN": "13105551234",
            "registrationStatus": "DEREGISTERED",
        })
        sig = extract_signal(p)
        assert sig.iccid == "89014103211118510720"
        assert sig.msisdn == "13105551234"
        assert sig.network_status == "DEREGISTERED"

    def test_strips_whitespace_in_identifiers(self):
        p = _payload(body={"iccid": "  89014103211118510720  "})
        sig = extract_signal(p)
        assert sig.iccid == "89014103211118510720"

    def test_falls_back_to_created_at_when_no_event_timestamp(self):
        created = datetime(2026, 5, 25, 9, 30, 0, tzinfo=timezone.utc)
        p = _payload(body={"iccid": "X"}, created_at=created)
        sig = extract_signal(p)
        assert sig.event_timestamp == created

    def test_parses_epoch_seconds_timestamp(self):
        p = _payload(body={"iccid": "X", "timestamp": 1779710400})
        sig = extract_signal(p)
        # 1779710400 == 2026-05-25 00:00:00 UTC
        assert sig.event_timestamp.tzinfo == timezone.utc
        assert sig.event_timestamp.year == 2026
        assert sig.event_timestamp.month == 5

    def test_malformed_timestamp_falls_back_to_created_at(self):
        created = datetime(2026, 5, 25, 9, 30, 0, tzinfo=timezone.utc)
        p = _payload(body={"iccid": "X", "event_time": "not-a-date"}, created_at=created)
        sig = extract_signal(p)
        assert sig.event_timestamp == created

    def test_empty_body_returns_all_none_identifiers(self):
        p = _payload(body={})
        sig = extract_signal(p)
        assert sig.iccid is None
        assert sig.msisdn is None
        assert sig.network_status is None
        assert sig.event_type == "unknown"

    def test_non_dict_body_treated_as_empty(self):
        # IntegrationPayload.body is JSONB → could in theory be a list
        # or a string if a future migration stored differently.  Defensive.
        p = _payload(body=["not", "a", "dict"])
        sig = extract_signal(p)
        assert sig.iccid is None and sig.msisdn is None

    def test_event_type_defaults_to_unknown(self):
        p = _payload(body={"iccid": "X"}, headers={})
        sig = extract_signal(p)
        assert sig.event_type == "unknown"


# ═══════════════════════════════════════════════════════════════════
# match_sim
# ═══════════════════════════════════════════════════════════════════


def _async_session_for_match(*, scalar_one_or_none_values=None, scalar_values=None):
    """Build an AsyncMock session whose .execute() returns the supplied
    sequence of result objects.  Used to drive match_sim through its
    branches without a real database."""
    results = []
    for v in (scalar_one_or_none_values or []):
        r = MagicMock()
        r.scalar_one_or_none.return_value = v
        results.append(r)
    for v in (scalar_values or []):
        r = MagicMock()
        r.scalar.return_value = v
        results.append(r)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=results)
    return db


class TestMatchSim:
    @pytest.mark.asyncio
    async def test_iccid_single_match_returns_one(self):
        sim = _sim()
        db = _async_session_for_match(scalar_one_or_none_values=[sim])
        signal = ExtractedSignal(iccid="89014103211118510720", msisdn=None,
                                  network_status=None, event_timestamp=_NOW, event_type="x")
        result = await match_sim(db, signal)
        assert result.kind == "one"
        assert result.sim is sim
        # ICCID is unique → only one query needed.
        assert db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_iccid_no_match_with_no_msisdn_returns_none(self):
        db = _async_session_for_match(scalar_one_or_none_values=[None])
        signal = ExtractedSignal(iccid="89014103211118510720", msisdn=None,
                                  network_status=None, event_timestamp=_NOW, event_type="x")
        result = await match_sim(db, signal)
        assert result.kind == "none"

    @pytest.mark.asyncio
    async def test_iccid_no_match_falls_back_to_msisdn(self):
        sim = _sim()
        db = MagicMock()
        # 3 calls expected: ICCID lookup (None), MSISDN count (1), MSISDN load (sim)
        iccid_miss = MagicMock(); iccid_miss.scalar_one_or_none.return_value = None
        msisdn_count = MagicMock(); msisdn_count.scalar.return_value = 1
        msisdn_load = MagicMock(); msisdn_load.scalar_one_or_none.return_value = sim
        db.execute = AsyncMock(side_effect=[iccid_miss, msisdn_count, msisdn_load])

        signal = ExtractedSignal(iccid="ABSENT", msisdn="13105551234",
                                  network_status=None, event_timestamp=_NOW, event_type="x")
        result = await match_sim(db, signal)
        assert result.kind == "one"
        assert result.sim is sim

    @pytest.mark.asyncio
    async def test_msisdn_only_ambiguous_match_refused(self):
        # No ICCID → straight to MSISDN.  Count returns 2 → ambiguous, refuse.
        msisdn_count = MagicMock(); msisdn_count.scalar.return_value = 2
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[msisdn_count])

        signal = ExtractedSignal(iccid=None, msisdn="13105551234",
                                  network_status=None, event_timestamp=_NOW, event_type="x")
        result = await match_sim(db, signal)
        assert result.kind == "ambiguous"
        assert result.candidate_count == 2
        assert result.sim is None
        # Crucially, the load query was NOT issued — we refuse to guess.
        assert db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_msisdn_only_no_match_returns_none(self):
        msisdn_count = MagicMock(); msisdn_count.scalar.return_value = 0
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[msisdn_count])
        signal = ExtractedSignal(iccid=None, msisdn="13105551234",
                                  network_status=None, event_timestamp=_NOW, event_type="x")
        result = await match_sim(db, signal)
        assert result.kind == "none"

    @pytest.mark.asyncio
    async def test_no_identifiers_returns_none(self):
        db = MagicMock()
        db.execute = AsyncMock()
        signal = ExtractedSignal(iccid=None, msisdn=None,
                                  network_status=None, event_timestamp=_NOW, event_type="x")
        result = await match_sim(db, signal)
        assert result.kind == "none"
        assert db.execute.call_count == 0


# ═══════════════════════════════════════════════════════════════════
# find_linked_device
# ═══════════════════════════════════════════════════════════════════


class TestFindLinkedDevice:
    @pytest.mark.asyncio
    async def test_returns_device_when_sim_device_id_resolves(self):
        device = _device()
        result_mock = MagicMock(); result_mock.scalar_one_or_none.return_value = device
        db = MagicMock(); db.execute = AsyncMock(return_value=result_mock)

        result = await find_linked_device(db, _sim(device_id="dev-a"))
        assert result is device

    @pytest.mark.asyncio
    async def test_returns_none_when_sim_has_no_device_id(self):
        db = MagicMock(); db.execute = AsyncMock()
        result = await find_linked_device(db, _sim(device_id=None))
        assert result is None
        db.execute.assert_not_called()  # no query attempted

    @pytest.mark.asyncio
    async def test_returns_none_when_linked_device_does_not_exist(self):
        result_mock = MagicMock(); result_mock.scalar_one_or_none.return_value = None
        db = MagicMock(); db.execute = AsyncMock(return_value=result_mock)
        result = await find_linked_device(db, _sim(device_id="dev-ghost"))
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# process_payload (orchestrator)
# ═══════════════════════════════════════════════════════════════════


class TestProcessPayload:
    @pytest.mark.asyncio
    async def test_returns_error_not_found_when_payload_missing(self):
        load_miss = MagicMock(); load_miss.scalar_one_or_none.return_value = None
        db = MagicMock(); db.execute = AsyncMock(return_value=load_miss)
        db.commit = AsyncMock()

        result = await process_payload(db, "wh-missing")
        assert result.status == "error:not_found"
        db.commit.assert_not_called()  # nothing to commit on not-found

    @pytest.mark.asyncio
    async def test_no_identifier_archives_only(self):
        payload = _payload(body={"event_type": "ping"})
        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        db = MagicMock(); db.execute = AsyncMock(return_value=load_hit)
        db.commit = AsyncMock()

        result = await process_payload(db, payload.payload_id)
        assert result.status == "skipped:no_identifier"
        assert payload.processed is True
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_replay_event_archives_only(self):
        payload = _payload(body={
            "iccid": "X",
            "event_time": "2020-01-01T00:00:00Z",  # ancient
        })
        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        db = MagicMock(); db.execute = AsyncMock(return_value=load_hit)
        db.commit = AsyncMock()

        result = await process_payload(db, payload.payload_id)
        assert result.status == "skipped:replay"
        assert "age=" in result.reason
        assert payload.processed is True

    @pytest.mark.asyncio
    async def test_no_sim_match_archives_only(self):
        payload = _payload(body={
            "iccid": "89014103211118510720",
            "event_time": _NOW.isoformat(),
        })
        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        iccid_miss = MagicMock(); iccid_miss.scalar_one_or_none.return_value = None
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[load_hit, iccid_miss])
        db.commit = AsyncMock()

        with patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "skipped:no_match"
        assert payload.processed is True

    @pytest.mark.asyncio
    async def test_ambiguous_msisdn_match_archives_only(self):
        payload = _payload(body={
            "msisdn": "13105551234",
            "event_time": _NOW.isoformat(),
        })
        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        msisdn_count = MagicMock(); msisdn_count.scalar.return_value = 3
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[load_hit, msisdn_count])
        db.commit = AsyncMock()

        with patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "skipped:ambiguous_match"
        assert "candidates=3" in result.reason
        assert payload.processed is True

    @pytest.mark.asyncio
    async def test_matched_sim_with_no_device_archives_only(self):
        payload = _payload(body={
            "iccid": "89014103211118510720",
            "event_time": _NOW.isoformat(),
        })
        sim = _sim(device_id=None)
        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        iccid_hit = MagicMock(); iccid_hit.scalar_one_or_none.return_value = sim
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[load_hit, iccid_hit])
        db.commit = AsyncMock()

        with patch(
            "app.services.tmobile_callback_processor.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = _NOW
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = await process_payload(db, payload.payload_id)

        assert result.status == "skipped:no_device"
        assert result.matched_sim_iccid == sim.iccid

    @pytest.mark.asyncio
    async def test_happy_path_promotes_to_carrier_liveness(self):
        """Exact one match + linked device → ingest_carrier_telemetry called."""
        payload = _payload(body={
            "iccid": "89014103211118510720",
            "network_status": "REGISTERED",
            "event_time": _NOW.isoformat(),
        })
        sim = _sim()
        device = _device()
        load_hit = MagicMock(); load_hit.scalar_one_or_none.return_value = payload
        iccid_hit = MagicMock(); iccid_hit.scalar_one_or_none.return_value = sim
        device_hit = MagicMock(); device_hit.scalar_one_or_none.return_value = device
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[load_hit, iccid_hit, device_hit])
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

        assert result.status == "promoted"
        assert result.matched_sim_iccid == sim.iccid
        assert result.matched_device_id == device.device_id

        ingest_mock.assert_awaited_once()
        call_args = ingest_mock.await_args
        assert call_args.args[1] == sim.tenant_id, "must scope by SIM's tenant_id"
        telemetry = call_args.args[2]
        assert telemetry.device_id == device.device_id
        assert telemetry.carrier == "t-mobile"
        assert telemetry.network_status == "REGISTERED"

        assert payload.processed is True
        db.commit.assert_awaited()


# ═══════════════════════════════════════════════════════════════════
# _redact_identifier
# ═══════════════════════════════════════════════════════════════════


class TestRedactIdentifier:
    @pytest.mark.parametrize("input_value,expected_pattern", [
        (None, "<none>"),
        ("", "<none>"),
        ("8901410", "8***"),  # short → masked
        ("89014103211118510720", "890141...20"),  # 20-char ICCID → keep prefix + last 2
        ("13105551234", "131055...34"),
    ])
    def test_redacts_correctly(self, input_value, expected_pattern):
        assert _redact_identifier(input_value) == expected_pattern
