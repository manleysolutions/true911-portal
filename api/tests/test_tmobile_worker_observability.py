"""Worker-side observability for T-Mobile callback ingest.

Production finding (2026-05-26 evening)
=======================================

After ``FEATURE_TMOBILE_CALLBACK_INGEST=true`` was set on the API
service via the Render dashboard, end-to-end testing confirmed:

  * callback returned 200,
  * IntegrationPayload archived correctly (``processed=true``),
  * webhook.tmobile jobs completed,

but ``Device.last_network_event`` never updated and
``command_telemetry`` had no new rows.

Root cause: ``FEATURE_TMOBILE_CALLBACK_INGEST`` was set on the
``true911-api`` service only, NOT on the ``true911-worker`` service.
Render Blueprint sync propagates only env vars listed in
``render.yaml`` per service; the dashboard-only var was scoped to
the API.  The worker process therefore read the default ``"false"``
and ``sim_service.handle_webhook`` fell through to the legacy
"mark processed" stub — never invoking the processor or the
Device-fallback match.

Symptom in production was invisible at the ``jobs.result`` level
because the legacy stub returned exactly ``{"processed": True,
"payload_id": "..."}`` with no marker indicating WHY the processor
didn't run.

What these tests pin
====================

  * ``handle_webhook`` always surfaces ``source`` in its result dict.
  * For ``source='tmobile'`` with flag OFF, the result tags
    ``tmobile_status="skipped:flag_off"`` so the symptom is
    diagnosable from a single ``SELECT result FROM jobs`` query.
  * For ``source='tmobile'`` with flag ON, the result contains the
    full ``tmobile_*`` set from the processor (including
    ``tmobile_matched_device_id`` on the device-fallback promotion
    path).
  * The end-to-end device-fallback promotion path actually mutates
    ``Device.last_network_event`` and ``Device.telemetry_source``
    when the worker invokes it.
  * Existing legacy contract for non-T-Mobile sources is preserved
    (no behavioral change, just a ``source`` tag added).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sim_service import handle_webhook


_NOW = datetime(2026, 5, 26, 18, 0, 0, tzinfo=timezone.utc)


# ─── Helpers ────────────────────────────────────────────────────────


def _make_job(*, source: str = "tmobile", payload_id: str = "wh-test"):
    return SimpleNamespace(
        payload={"payload_id": payload_id, "source": source},
    )


# ═══════════════════════════════════════════════════════════════════
# Flag-off observability — the "skipped:flag_off" marker
# ═══════════════════════════════════════════════════════════════════


class TestFlagOffObservability:
    """The new contract: a T-Mobile job that arrives at a worker
    process where the flag is OFF must be immediately diagnosable
    from ``jobs.result``."""

    @pytest.mark.asyncio
    async def test_result_carries_skipped_flag_off_marker(self):
        db = MagicMock()
        ip = SimpleNamespace(payload_id="wh-fo-1", processed=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ip
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ):
            result = await handle_webhook(db, _make_job(payload_id="wh-fo-1"))

        # The diagnosable shape — every field operators need to tell
        # at a glance that the worker env is wrong:
        assert result["source"] == "tmobile"
        assert result["tmobile_status"] == "skipped:flag_off"
        assert result["payload_id"] == "wh-fo-1"
        assert result["processed"] is True
        # The legacy "mark processed" side effect still ran.
        assert ip.processed is True

    @pytest.mark.asyncio
    async def test_processor_is_not_called_on_flag_off(self):
        """The kill-switch contract: even with observability added,
        the processor must NEVER run when the flag is off.  This is
        the tenant-isolation defence-in-depth — see the surface
        containment guard in test_tmobile_callback_integration.py."""
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        process_mock = AsyncMock()
        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ), patch(
            "app.services.tmobile_callback_processor.process_payload",
            new=process_mock,
        ):
            await handle_webhook(db, _make_job())

        process_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_flag_off_emits_warning_log(self, caplog):
        """The WARNING log line gives operators a non-DB signal too —
        a tail of the worker logs immediately surfaces the
        missing-env-var problem."""
        import logging
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ), caplog.at_level(logging.WARNING, logger="true911.sims"):
            await handle_webhook(db, _make_job(payload_id="wh-warn-1"))

        warnings = [
            rec for rec in caplog.records
            if rec.levelno >= logging.WARNING
            and "wh-warn-1" in rec.getMessage()
        ]
        assert warnings, "Expected a WARNING log explaining the flag-off cause"
        msg = warnings[0].getMessage()
        assert "FEATURE_TMOBILE_CALLBACK_INGEST" in msg
        # The log line must point operators at the WORKER service
        # specifically — that's the diagnostic value-add.
        assert "WORKER service" in msg or "worker service" in msg.lower()


# ═══════════════════════════════════════════════════════════════════
# Flag-on result shape — full tmobile_* surface
# ═══════════════════════════════════════════════════════════════════


class TestFlagOnResultIncludesFullProcessorSurface:
    """When the worker IS configured correctly and the processor
    runs, the result must include every field a future debug session
    might need."""

    @pytest.mark.asyncio
    async def test_promoted_via_sim_includes_all_tmobile_fields(self):
        from app.services.tmobile_callback_processor import ProcessResult

        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        process_mock = AsyncMock(return_value=ProcessResult(
            status="promoted",
            reason=None,
            matched_sim_iccid="89014103211118510720",
            matched_device_id="dev-a",
        ))
        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.services.tmobile_callback_processor.process_payload",
            new=process_mock,
        ):
            result = await handle_webhook(db, _make_job(payload_id="wh-on-1"))

        assert result == {
            "payload_id": "wh-on-1",
            "processed": True,
            "source": "tmobile",
            "tmobile_status": "promoted",
            "tmobile_reason": None,
            "tmobile_matched_sim_iccid": "89014103211118510720",
            "tmobile_matched_device_id": "dev-a",
            # Additive observability field — None on the Sim-match path (capture
            # only runs on the device-fallback account-ID path).
            "tmobile_account_capture": None,
        }

    @pytest.mark.asyncio
    async def test_promoted_via_device_fallback_includes_device_id(self):
        """The headline production scenario: SIM table empty, but a
        Device row's MSISDN matches.  Result must carry
        ``tmobile_matched_device_id`` so operators can trace which
        device received the carrier-liveness write."""
        from app.services.tmobile_callback_processor import ProcessResult

        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        process_mock = AsyncMock(return_value=ProcessResult(
            status="promoted:device_fallback",
            reason=None,
            matched_sim_iccid=None,  # no Sim row
            matched_device_id="8563081391",  # device_id == MSISDN digits
        ))
        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.services.tmobile_callback_processor.process_payload",
            new=process_mock,
        ):
            result = await handle_webhook(db, _make_job(payload_id="wh-df-1"))

        assert result["tmobile_status"] == "promoted:device_fallback"
        assert result["tmobile_matched_device_id"] == "8563081391"
        assert result["tmobile_matched_sim_iccid"] is None
        assert result["source"] == "tmobile"

    @pytest.mark.asyncio
    async def test_skipped_paths_surface_reason(self):
        """Every skip path returns a reason string when one applies —
        operators inspecting jobs.result for a non-promoting job
        should see WHY the device wasn't promoted."""
        from app.services.tmobile_callback_processor import ProcessResult

        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        process_mock = AsyncMock(return_value=ProcessResult(
            status="skipped:ambiguous_device_match",
            reason="matched_on=msisdn candidates=3",
        ))
        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.services.tmobile_callback_processor.process_payload",
            new=process_mock,
        ):
            result = await handle_webhook(db, _make_job(payload_id="wh-amb-1"))

        assert result["tmobile_status"] == "skipped:ambiguous_device_match"
        assert result["tmobile_reason"] == "matched_on=msisdn candidates=3"


# ═══════════════════════════════════════════════════════════════════
# Non-T-Mobile sources — backwards-compat with the new source tag
# ═══════════════════════════════════════════════════════════════════


class TestNonTmobileSourcePreservesLegacy:
    """A telnyx/vola/etc. job must NOT pick up any tmobile_* fields,
    must NOT consult the processor, and must still get the
    IntegrationPayload mark.  The only new thing is a ``source``
    field on the result."""

    @pytest.mark.asyncio
    async def test_telnyx_source_returns_no_tmobile_fields(self):
        db = MagicMock()
        ip = SimpleNamespace(processed=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ip
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        process_mock = AsyncMock()
        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",  # even with flag ON, non-tmobile job is untouched
        ), patch(
            "app.services.tmobile_callback_processor.process_payload",
            new=process_mock,
        ):
            result = await handle_webhook(
                db, _make_job(source="telnyx", payload_id="wh-tx-1"),
            )

        process_mock.assert_not_called()
        assert ip.processed is True
        assert result == {
            "payload_id": "wh-tx-1",
            "processed": True,
            "source": "telnyx",
        }
        assert "tmobile_status" not in result

    @pytest.mark.asyncio
    async def test_unknown_source_still_processes_with_source_tag(self):
        db = MagicMock()
        ip = SimpleNamespace(processed=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ip
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        result = await handle_webhook(
            db, _make_job(source="mystery", payload_id="wh-mys-1"),
        )
        assert result["source"] == "mystery"
        assert ip.processed is True

    @pytest.mark.asyncio
    async def test_none_source_still_handled(self):
        """A malformed job with no source field shouldn't crash —
        legacy stub should run, source field is None in the result."""
        db = MagicMock()
        ip = SimpleNamespace(processed=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ip
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        job = SimpleNamespace(payload={"payload_id": "wh-none-1"})
        result = await handle_webhook(db, job)
        assert result["source"] is None
        assert result["processed"] is True


# ═══════════════════════════════════════════════════════════════════
# End-to-end device-fallback promotion — proves the worker actually
# mutates Device.last_network_event when wired correctly
# ═══════════════════════════════════════════════════════════════════


class TestEndToEndDeviceFallbackMutatesDevice:
    """The point of all this work: prove that when the worker is
    configured correctly (flag ON) and a T-Mobile callback arrives
    for a Sim-less device whose MSISDN is on the Device row, the
    end-to-end flow actually writes ``last_network_event`` AND
    ``telemetry_source`` to the Device, plus adds a CommandTelemetry
    row.

    Uses a custom session-like mock that returns the SAME Device
    object from both queries (match_device_fallback's load AND
    carrier_adapter's lookup), simulating SQLAlchemy's identity
    map.  This is the production scenario where the user observed
    NULL ``last_network_event``."""

    @pytest.mark.asyncio
    async def test_real_chain_updates_device_and_writes_command_telemetry(
        self,
    ):
        from datetime import datetime
        # Build the device the way production has it: device_id == MSISDN digits,
        # msisdn in E.164.
        device = SimpleNamespace(
            id=1,
            device_id="8563081391",
            tenant_id="tenant-prod",
            site_id="site-a",
            carrier="T-Mobile",
            network_status=None,
            data_usage_mb=None,
            last_network_event=None,
            telemetry_source=None,
            msisdn="+18563081391",
            iccid=None,
        )

        # Build the IntegrationPayload as the router would have written it.
        payload = SimpleNamespace(
            payload_id="wh-e2e-1",
            source="tmobile",
            direction="inbound",
            headers={"x-true911-tmobile-event-type": "subscriber_status"},
            body={
                "msisdn": "8563081391",  # 10-digit US local from T-Mobile
                "network_status": "REGISTERED",
                "event_time": _NOW.isoformat(),
            },
            raw_body=None,
            processed=False,
            created_at=_NOW,
        )

        # Capture CommandTelemetry rows added.
        added_objects: list = []

        # The session mock returns the right object per query in order.
        # Sequence of db.execute calls for the full chain:
        #   1. _load_payload          → returns payload
        #   2. match_sim ICCID lookup → signal.iccid is None so SKIPPED;
        #                               match_sim MSISDN count → 0
        #   3. match_device_fallback ICCID skipped (no iccid);
        #                               msisdn count → 1
        #   4. match_device_fallback msisdn load → device
        #   5. ingest_carrier_telemetry Device lookup → device (identity map)
        results = [
            MagicMock(scalar_one_or_none=lambda: payload),  # 1. payload load
            MagicMock(scalar=lambda: 0),                    # 2. sim msisdn count
            MagicMock(scalar=lambda: 1),                    # 3. device msisdn count
            MagicMock(scalar_one_or_none=lambda: device),   # 4. device msisdn load
            MagicMock(scalar_one_or_none=lambda: device),   # 5. carrier_adapter device lookup
        ]

        db = MagicMock()
        db.execute = AsyncMock(side_effect=results)
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.add = lambda obj: added_objects.append(obj)

        job = SimpleNamespace(payload={
            "payload_id": "wh-e2e-1",
            "source": "tmobile",
            "event_type": "subscriber_status",
        })

        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.services.tmobile_callback_processor.datetime",
        ) as mock_dt_proc, patch(
            "app.services.carrier_adapter.datetime",
        ) as mock_dt_ca:
            mock_dt_proc.now.return_value = _NOW
            mock_dt_proc.fromisoformat = datetime.fromisoformat
            mock_dt_proc.fromtimestamp = datetime.fromtimestamp
            mock_dt_ca.now.return_value = _NOW

            result = await handle_webhook(db, job)

        # Result-shape contract: worker.result captures everything an
        # operator needs to confirm promotion from psql.
        assert result["tmobile_status"] == "promoted:device_fallback"
        assert result["tmobile_matched_device_id"] == "8563081391"
        assert result["source"] == "tmobile"

        # The HEADLINE assertion: the device's last_network_event was
        # actually updated.  This is the production symptom this PR
        # is making diagnosable.
        assert device.last_network_event == _NOW
        assert device.telemetry_source == "t-mobile_carrier"
        assert device.network_status == "REGISTERED"
        assert device.carrier == "t-mobile"

        # carrier_adapter contract: a CommandTelemetry row was added
        # for the sample.  This is the user-visible row that was
        # missing from production.
        from app.models.command_telemetry import CommandTelemetry
        ct_rows = [o for o in added_objects if isinstance(o, CommandTelemetry)]
        assert len(ct_rows) == 1, (
            "ingest_carrier_telemetry must add exactly one CommandTelemetry "
            "row per promotion — production was reporting zero, which "
            "this test now guards against regressing."
        )
        ct = ct_rows[0]
        assert ct.tenant_id == "tenant-prod"
        assert ct.device_id == "8563081391"
