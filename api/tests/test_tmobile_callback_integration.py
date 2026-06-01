"""Integration tests for FEATURE_TMOBILE_CALLBACK_INGEST.

What we prove end-to-end:

  * FEATURE_TMOBILE_CALLBACK_INGEST=false → POST handlers behave
    byte-identically to before the MVP: 200 ack + structured log
    line, no IntegrationPayload write, no job enqueue.

  * FEATURE_TMOBILE_CALLBACK_INGEST=true  → same handlers
    additionally write IntegrationPayload(source='tmobile') with the
    synthetic 'x-true911-tmobile-event-type' header, and enqueue a
    webhook.tmobile job.  HTTP response is unchanged (still 200 ack)
    so the T-Mobile PIT validator never sees a difference.

  * Flag-on archive failure: even when the DB raises, the HTTP 200
    contract holds.  T-Mobile retry-storm is the failure mode we
    must avoid; losing one archived payload is recoverable.

  * Worker handler delegation: handle_webhook routes 'tmobile' work
    through tmobile_callback_processor.process_payload ONLY when
    the flag is on; off-path returns the legacy 'marked processed'
    stub result.

  * Surface containment: the new flag and the new package are NOT
    referenced from any router/service outside the documented
    allowlist.  Catches scope widening at PR time, same pattern as
    the Health Normalizer MVP.

  * Health Normalizer composition: after process_payload promotes a
    T-Mobile callback, the device's last_network_event is what the
    Health Normalizer signals_loader reads as last_carrier_event_at —
    structurally verified.

Same mocking pattern as tests/test_health_system.py and
tests/test_health_normalizer_integration.py — minimal FastAPI app,
dependency overrides, AsyncMock for DB.  No real database.
"""

from __future__ import annotations

import pathlib
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.routers.tmobile_callback import router as tmobile_router


# ─── Test app + db override ────────────────────────────────────────


def _build_app_with_db(db):
    """Build a minimal FastAPI app mounting the callback router with
    the supplied AsyncMock db driving get_db."""
    app = FastAPI()
    app.include_router(tmobile_router, prefix="/tmobile/wholesale")

    async def _stub_get_db():
        yield db

    app.dependency_overrides[get_db] = _stub_get_db
    return app


def _capture_db_mock():
    """Build a db mock that captures the IntegrationPayload row passed
    to db.add() so the test can assert on its fields."""
    db = MagicMock()
    db.added = []  # convenience capture
    db.add = lambda obj: db.added.append(obj)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


# ═══════════════════════════════════════════════════════════════════
# Flag-off: archive helper must NOT fire
# ═══════════════════════════════════════════════════════════════════


class TestFlagOffPreservesCurrentBehavior:
    """The headline no-op guarantee.  Validators reaching the same URLs
    today should see no observable change."""

    def test_flag_off_post_returns_200_and_does_not_archive(self):
        db = _capture_db_mock()
        client = TestClient(_build_app_with_db(db))

        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ):
            r = client.post(
                "/tmobile/wholesale/callback/provisioning",
                json={"iccid": "89014103211118510720"},
            )

        assert r.status_code == 200
        assert r.json()["event"] == "provisioning"
        # The bedrock assertion: no IntegrationPayload was added.
        assert db.added == []
        db.commit.assert_not_called()

    def test_flag_off_does_not_enqueue_job(self):
        db = _capture_db_mock()
        client = TestClient(_build_app_with_db(db))

        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "false",
        ), patch(
            "app.routers.tmobile_callback.job_service.create_and_enqueue",
            new=AsyncMock(),
        ) as enqueue:
            client.post(
                "/tmobile/wholesale/callback/usage",
                json={"msisdn": "13105551234"},
            )

        enqueue.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# Flag-on: archive writes IntegrationPayload + enqueues job
# ═══════════════════════════════════════════════════════════════════


class TestFlagOnArchivesPayload:
    def test_flag_on_post_writes_integration_payload(self):
        db = _capture_db_mock()
        client = TestClient(_build_app_with_db(db))

        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.routers.tmobile_callback.job_service.create_and_enqueue",
            new=AsyncMock(return_value=SimpleNamespace(id=42)),
        ):
            r = client.post(
                "/tmobile/wholesale/callback/subscriber-status",
                json={"iccid": "89014103211118510720", "status": "active"},
            )

        # HTTP 200 still preserved.
        assert r.status_code == 200
        assert r.json()["event"] == "subscriber_status"

        # Exactly one IntegrationPayload row was added.
        assert len(db.added) == 1
        ip = db.added[0]
        assert ip.source == "tmobile"
        assert ip.direction == "inbound"
        assert ip.processed is False
        # Synthetic header carries the URL-path event type forward.
        assert ip.headers["x-true911-tmobile-event-type"] == "subscriber_status"
        # Body parsed as dict (had valid JSON).
        assert ip.body == {"iccid": "89014103211118510720", "status": "active"}
        # raw_body NOT used when body parsed cleanly.
        assert ip.raw_body is None

        db.flush.assert_awaited()
        db.commit.assert_awaited()

    def test_flag_on_malformed_body_archives_as_raw(self):
        db = _capture_db_mock()
        client = TestClient(_build_app_with_db(db))

        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.routers.tmobile_callback.job_service.create_and_enqueue",
            new=AsyncMock(return_value=SimpleNamespace(id=42)),
        ):
            r = client.post(
                "/tmobile/wholesale/callback/cim",
                content=b"this is not json {{{",
                headers={"content-type": "text/plain"},
            )

        # Still 200 — the validator must never see a failure.
        assert r.status_code == 200
        assert len(db.added) == 1
        ip = db.added[0]
        assert ip.body is None  # JSON parse failed
        assert "this is not json" in ip.raw_body

    def test_flag_on_archive_failure_still_returns_200(self):
        """The CRITICAL safety property: even if the DB write fails,
        T-Mobile must still get HTTP 200 so it doesn't retry-storm."""
        db = MagicMock()
        db.add = MagicMock(side_effect=RuntimeError("simulated db meltdown"))
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        client = TestClient(_build_app_with_db(db))

        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.routers.tmobile_callback.job_service.create_and_enqueue",
            new=AsyncMock(),
        ):
            r = client.post(
                "/tmobile/wholesale/callback/device-change",
                json={"iccid": "X"},
            )

        assert r.status_code == 200, (
            "PIT validator must never see a 5xx from a database failure"
        )
        assert r.json()["event"] == "device_change"

    def test_flag_on_enqueues_webhook_tmobile_job(self):
        db = _capture_db_mock()
        client = TestClient(_build_app_with_db(db))
        enqueue_mock = AsyncMock(return_value=SimpleNamespace(id=99))

        with patch(
            "app.routers.tmobile_callback.settings.FEATURE_TMOBILE_CALLBACK_INGEST",
            "true",
        ), patch(
            "app.routers.tmobile_callback.job_service.create_and_enqueue",
            new=enqueue_mock,
        ):
            client.post(
                "/tmobile/wholesale/callback/usage",
                json={"msisdn": "13105551234"},
            )

        enqueue_mock.assert_awaited_once()
        kwargs = enqueue_mock.await_args.kwargs
        assert kwargs["job_type"] == "webhook.tmobile"
        assert kwargs["payload"]["source"] == "tmobile"
        assert kwargs["payload"]["event_type"] == "usage"
        # payload_id is generated; just confirm shape.
        assert kwargs["payload"]["payload_id"].startswith("wh-")


# ═══════════════════════════════════════════════════════════════════
# Worker handler delegation
# ═══════════════════════════════════════════════════════════════════


class TestWorkerHandlerDelegation:
    @pytest.mark.asyncio
    async def test_flag_off_uses_legacy_stub_with_visible_flag_off_marker(self):
        """source='tmobile' with flag off → process_payload NOT called,
        legacy 'mark processed' path runs, AND the result carries
        ``tmobile_status='skipped:flag_off'`` so operators inspecting
        jobs.result can immediately diagnose the missing-worker-env-var
        symptom (Blueprint sync only propagates vars listed in
        render.yaml per service)."""
        from app.services.sim_service import handle_webhook

        db = MagicMock()
        ip = SimpleNamespace(processed=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ip
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        job = SimpleNamespace(payload={"payload_id": "wh-xyz", "source": "tmobile"})

        process_mock = AsyncMock()
        with patch(
            "app.services.sim_service.select"
        ), patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST", "false"
        ), patch(
            "app.services.tmobile_callback_processor.process_payload",
            new=process_mock,
        ):
            result = await handle_webhook(db, job)

        # Processor is still not called — the kill-switch contract holds.
        process_mock.assert_not_called()
        # Legacy IntegrationPayload mark still happens.
        assert ip.processed is True
        # New observability fields are present and visible from a
        # `SELECT result FROM jobs` query.
        assert result == {
            "payload_id": "wh-xyz",
            "processed": True,
            "source": "tmobile",
            "tmobile_status": "skipped:flag_off",
        }

    @pytest.mark.asyncio
    async def test_flag_on_delegates_to_processor(self):
        from app.services.sim_service import handle_webhook
        from app.services.tmobile_callback_processor import ProcessResult

        db = MagicMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        job = SimpleNamespace(payload={"payload_id": "wh-xyz", "source": "tmobile"})
        process_mock = AsyncMock(return_value=ProcessResult(
            status="promoted",
            matched_sim_iccid="89014103211118510720",
            matched_device_id="dev-a",
        ))

        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST", "true"
        ), patch(
            "app.services.tmobile_callback_processor.process_payload",
            new=process_mock,
        ):
            result = await handle_webhook(db, job)

        process_mock.assert_awaited_once_with(db, "wh-xyz")
        assert result["tmobile_status"] == "promoted"
        assert result["tmobile_matched_sim_iccid"] == "89014103211118510720"
        assert result["tmobile_matched_device_id"] == "dev-a"

    @pytest.mark.asyncio
    async def test_flag_on_but_non_tmobile_source_uses_legacy_stub(self):
        """Defense: even with the flag on, a job for source='telnyx' or
        'vola' must not be hijacked by the T-Mobile processor."""
        from app.services.sim_service import handle_webhook

        db = MagicMock()
        ip = SimpleNamespace(processed=False)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = ip
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        job = SimpleNamespace(payload={"payload_id": "wh-xyz", "source": "telnyx"})

        process_mock = AsyncMock()
        with patch(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_INGEST", "true"
        ), patch(
            "app.services.tmobile_callback_processor.process_payload",
            new=process_mock,
        ):
            result = await handle_webhook(db, job)

        process_mock.assert_not_called()
        assert "tmobile_status" not in result


# ═══════════════════════════════════════════════════════════════════
# Surface containment
# ═══════════════════════════════════════════════════════════════════


class TestSurfaceContainment:
    """The MVP scope guarantee — same pattern as the Health Normalizer
    MVP's containment tests.  Any future PR that quietly widens the
    consumer list will fail one of these at PR time."""

    def test_only_callback_router_and_processor_read_the_flag(self):
        """FEATURE_TMOBILE_CALLBACK_INGEST may only appear in:
          * app/config.py                            (declares it)
          * app/routers/tmobile_callback.py          (gates archive)
          * app/services/sim_service.py              (gates delegation)
          * app/services/tmobile_callback_processor.py  (docstring)
          * app/verify_integrity.py                  (read-only readiness
                                                      report — reports the
                                                      flag value, does NOT
                                                      gate behavior on it)
        """
        api_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        allowlist = {
            pathlib.Path("config.py"),
            pathlib.Path("routers/tmobile_callback.py"),
            pathlib.Path("services/sim_service.py"),
            pathlib.Path("services/tmobile_callback_processor.py"),
            pathlib.Path("verify_integrity.py"),
        }
        offending = []
        for p in api_root.rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if "FEATURE_TMOBILE_CALLBACK_INGEST" not in text:
                continue
            rel = p.relative_to(api_root)
            if rel not in allowlist:
                offending.append(str(rel))
        assert not offending, (
            f"FEATURE_TMOBILE_CALLBACK_INGEST referenced outside the allowlist: "
            f"{offending}.  MVP scope is callback ingest only.  Widening "
            f"the consumer list requires updating "
            f"docs/TMOBILE_CALLBACK_INGEST_MVP.md and this test."
        )

    def test_only_sim_service_imports_the_processor_module(self):
        """tmobile_callback_processor may only be imported by:
          * app/services/sim_service.py               (the worker handler)
          * other modules within app/services/        (none yet, but
                                                       reserved)
          * test files (excluded — different root)

        Routers must NOT import the processor directly — the router's
        job is only to archive; promotion is the worker's job.  Catches
        a scope drift where someone wires the processor synchronously
        into the request path.
        """
        api_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        # Match exact module imports, not substring (defense against a
        # future module like tmobile_callback_processor_v2).
        import_re = re.compile(
            r"^\s*(?:from|import)\s+app\.services\.tmobile_callback_processor\b",
            re.MULTILINE,
        )
        offending = []
        for p in api_root.rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if not import_re.search(text):
                continue
            rel = p.relative_to(api_root)
            if rel != pathlib.Path("services/sim_service.py"):
                offending.append(str(rel))
        assert not offending, (
            f"tmobile_callback_processor imported outside the allowlist: "
            f"{offending}.  Only sim_service.handle_webhook may invoke it."
        )

    def test_no_e911_or_provisioning_or_customer_imports_in_processor(self):
        """The processor must not import anything from E911,
        provisioning, customer-record, or call-routing modules.

        Static guard against scope creep into the prohibited surfaces
        listed in the MVP plan.
        """
        api_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        processor = api_root / "services" / "tmobile_callback_processor.py"
        text = processor.read_text(encoding="utf-8")
        # We allow imports of: config, models.{device,integration_payload,sim},
        # services.carrier_adapter (the existing Verizon path we reuse).
        forbidden_substrings = [
            "app.routers.e911",
            "app.services.e911",
            "app.models.e911",
            "app.routers.provisioning",
            "app.services.provision",
            "app.services.line_service",  # provisioning writes
            "app.routers.calls",
            "app.routers.customers",
            "app.models.customer",
        ]
        leaks = [s for s in forbidden_substrings if s in text]
        assert not leaks, (
            f"tmobile_callback_processor imports forbidden modules: {leaks}.  "
            f"The MVP must not touch E911 / provisioning / call routing / "
            f"customer records."
        )


# ═══════════════════════════════════════════════════════════════════
# Health Normalizer composition (structural)
# ═══════════════════════════════════════════════════════════════════


class TestHealthNormalizerComposition:
    """Structural proof: the field the processor writes is the same
    field the Health Normalizer reads as last_carrier_event_at."""

    def test_processor_writes_field_that_signals_loader_reads(self):
        """signals_loader.py reads Device.last_network_event into
        HealthSignals.last_carrier_event_at; carrier_adapter
        (which the processor reuses) writes Device.last_network_event.
        Asserting the field name appears in both files proves the
        wire is intact without spinning up a real DB.
        """
        api_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        carrier_adapter = (api_root / "services" / "carrier_adapter.py").read_text(
            encoding="utf-8"
        )
        signals_loader = (
            api_root / "services" / "health" / "signals_loader.py"
        ).read_text(encoding="utf-8")

        # The bridge field — must appear as a write in carrier_adapter
        # and a read in signals_loader.  If either reference disappears
        # the composition is broken.
        assert "device.last_network_event" in carrier_adapter, (
            "carrier_adapter no longer writes Device.last_network_event — "
            "the T-Mobile callback ingest path can no longer feed the "
            "Health Normalizer."
        )
        assert "last_network_event" in signals_loader, (
            "signals_loader no longer reads Device.last_network_event — "
            "the Health Normalizer can no longer see carrier liveness."
        )
