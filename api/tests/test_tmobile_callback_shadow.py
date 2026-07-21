"""Cover for shadow-mode evaluation of the typed callback rules.

Two things must hold, and the second matters more than the first.

1. With the flag **off**, the deployed path is byte-identical — not even an
   extra read happens.
2. With the flag **on**, the typed rules can still not change anything. That is
   structural, not a promise: they are handed a throwaway state object and no
   session, so there is nothing real for them to mutate.

The shadow currently resolves almost everything to
``quarantined_no_correlation``, and that is the expected, documented state —
nothing creates lifecycle transactions yet, so there is nothing to correlate
against. These tests pin that this stays observation-only until that changes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.tmobile_callback_shadow as SH
from app.services.tmobile_callback_processor import (
    EVENT_TYPE_HEADER,
    ProcessResult,
    process_payload,
)

ICCID = "8901260963132600001"     # fabricated
MSISDN = "5550001234"             # fabricated
_NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def shadow_on(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.FEATURE_TMOBILE_CALLBACK_TYPED_SHADOW", "true")


@pytest.fixture
def shadow_off(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.FEATURE_TMOBILE_CALLBACK_TYPED_SHADOW", "false")


def _payload(body=None, headers=None, payload_id="wh-shadow-1"):
    return SimpleNamespace(
        payload_id=payload_id, source="tmobile", direction="inbound",
        headers=headers or {EVENT_TYPE_HEADER: "provisioning"},
        body=body if body is not None else {"iccid": ICCID, "status": "SUCCESS"},
        raw_body=None, processed=False, created_at=_NOW,
    )


class TestFlagGating:
    def test_disabled_by_default(self):
        assert SH.shadow_enabled() is False

    def test_whitespace_tolerant(self, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.FEATURE_TMOBILE_CALLBACK_TYPED_SHADOW", "  TRUE  ")
        assert SH.shadow_enabled() is True

    def test_evaluate_returns_none_when_disabled(self, shadow_off):
        assert SH.evaluate(body={"iccid": ICCID}, headers={},
                           operation="provisioning", payload_id="wh-1",
                           live_status="promoted") is None

    @pytest.mark.asyncio
    async def test_flag_off_costs_not_even_an_extra_read(self, shadow_off, monkeypatch):
        """The wrapper must short-circuit before touching the database."""
        calls = {"n": 0}

        async def counting_core(db, payload_id):
            calls["n"] += 1
            return ProcessResult(status="promoted")

        load = AsyncMock()
        monkeypatch.setattr(
            "app.services.tmobile_callback_processor._process_payload_core",
            counting_core)
        monkeypatch.setattr(
            "app.services.tmobile_callback_processor._load_payload", load)

        result = await process_payload(MagicMock(), "wh-1")

        assert result.status == "promoted"
        assert result.shadow is None
        assert calls["n"] == 1
        load.assert_not_awaited()          # no extra read at all


class TestShadowCannotMutate:
    def test_evaluation_takes_no_session_and_returns_a_value_object(self, shadow_on):
        obs = SH.evaluate(body={"iccid": ICCID, "status": "SUCCESS"}, headers={},
                          operation="provisioning", payload_id="wh-1",
                          live_status="promoted")
        assert obs is not None
        assert obs.would_change_state is False
        assert isinstance(obs.as_dict(), dict)

    def test_no_candidate_transactions_exist_yet(self):
        """Pins the documented reason the shadow cannot yet be authoritative."""
        assert SH._candidate_transactions() == []

    def test_everything_quarantines_for_want_of_correlation(self, shadow_on):
        obs = SH.evaluate(body={"iccid": ICCID, "status": "SUCCESS"}, headers={},
                          operation="provisioning", payload_id="wh-1",
                          live_status="promoted")
        assert obs.decision == "quarantined_no_correlation"
        assert obs.correlated is False
        assert obs.would_change_state is False

    def test_disagreement_with_the_live_path_is_recorded_not_acted_on(self, shadow_on):
        """The live path promoted; the typed rules would not. That is the point.

        Recording the disagreement is the whole value of shadow mode — it is
        evidence, not a fault, and it must not alter the outcome.
        """
        obs = SH.evaluate(body={"iccid": ICCID, "status": "SUCCESS"}, headers={},
                          operation="provisioning", payload_id="wh-1",
                          live_status="promoted")
        assert obs.live_changed_state is True
        assert obs.would_change_state is False
        assert obs.agrees is False

    def test_agreement_recorded_when_live_path_also_skipped(self, shadow_on):
        obs = SH.evaluate(body={"iccid": ICCID}, headers={},
                          operation="provisioning", payload_id="wh-1",
                          live_status="skipped:no_match")
        assert obs.live_changed_state is False
        assert obs.agrees is True


class TestShadowNeverBreaksIngest:
    def test_malformed_body_is_absorbed(self, shadow_on):
        obs = SH.evaluate(body=None, headers=None, operation="unknown",
                          payload_id="wh-1", live_status="skipped:no_identifier")
        assert obs is not None
        assert obs.would_change_state is False

    def test_internal_failure_is_reported_not_raised(self, shadow_on, monkeypatch):
        def explode(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(SH, "build_envelope", explode)
        obs = SH.evaluate(body={"iccid": ICCID}, headers={},
                          operation="provisioning", payload_id="wh-1",
                          live_status="promoted")
        assert obs.decision == "shadow:error"
        assert obs.would_change_state is False

    @pytest.mark.asyncio
    async def test_shadow_failure_does_not_change_the_live_result(
        self, shadow_on, monkeypatch
    ):
        async def core(db, payload_id):
            return ProcessResult(status="promoted", matched_device_id="dev-a")

        monkeypatch.setattr(
            "app.services.tmobile_callback_processor._process_payload_core", core)
        monkeypatch.setattr(
            "app.services.tmobile_callback_processor._load_payload",
            AsyncMock(return_value=_payload()))
        # Patch the name the processor actually bound at import time.
        def explode(**kwargs):
            raise RuntimeError("shadow layer is broken")

        monkeypatch.setattr(
            "app.services.tmobile_callback_processor.shadow_evaluate", explode)

        result = await process_payload(MagicMock(), "wh-1")

        # Ingest is unaffected: the live result survives intact, minus only the
        # observation it could not produce.
        assert result.status == "promoted"
        assert result.matched_device_id == "dev-a"
        assert result.shadow is None


class TestWrapperAttachesObservation:
    @pytest.mark.asyncio
    async def test_observation_is_attached_without_altering_status(
        self, shadow_on, monkeypatch
    ):
        async def core(db, payload_id):
            return ProcessResult(status="promoted", matched_device_id="dev-a",
                                 matched_sim_iccid=ICCID)

        monkeypatch.setattr(
            "app.services.tmobile_callback_processor._process_payload_core", core)
        monkeypatch.setattr(
            "app.services.tmobile_callback_processor._load_payload",
            AsyncMock(return_value=_payload()))

        result = await process_payload(MagicMock(), "wh-1")

        assert result.status == "promoted"              # unchanged
        assert result.matched_device_id == "dev-a"      # unchanged
        assert result.shadow is not None
        assert result.shadow["decision"] == "quarantined_no_correlation"
        assert result.shadow["live_changed_state"] is True

    @pytest.mark.asyncio
    async def test_missing_payload_row_is_tolerated(self, shadow_on, monkeypatch):
        async def core(db, payload_id):
            return ProcessResult(status="error:not_found")

        monkeypatch.setattr(
            "app.services.tmobile_callback_processor._process_payload_core", core)
        monkeypatch.setattr(
            "app.services.tmobile_callback_processor._load_payload",
            AsyncMock(return_value=None))

        result = await process_payload(MagicMock(), "wh-missing")
        assert result.status == "error:not_found"
        assert result.shadow is not None


class TestObservationIsSafeToRecord:
    def test_no_raw_identifier_in_the_observation(self, shadow_on):
        obs = SH.evaluate(body={"iccid": ICCID, "msisdn": MSISDN,
                                "status": "SUCCESS"},
                          headers={}, operation="provisioning",
                          payload_id="wh-1", live_status="promoted")
        blob = str(obs.as_dict())
        assert ICCID not in blob
        assert MSISDN not in blob

    def test_idempotency_key_is_stable_for_the_same_callback(self, shadow_on):
        args = dict(body={"iccid": ICCID, "status": "SUCCESS"}, headers={},
                    operation="provisioning", payload_id="wh-1",
                    live_status="promoted")
        assert SH.evaluate(**args).idempotency_key == SH.evaluate(**args).idempotency_key

    def test_logs_mask_identifiers(self, shadow_on, caplog):
        import logging

        with caplog.at_level(logging.INFO, logger="true911.tmobile_callback_shadow"):
            SH.evaluate(body={"iccid": ICCID, "status": "SUCCESS"}, headers={},
                        operation="provisioning", payload_id="wh-1",
                        live_status="promoted")
        assert caplog.text
        assert ICCID not in caplog.text
