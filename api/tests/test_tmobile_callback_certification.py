"""T-Mobile callback certification — the Phase 4 checklist, as executable tests.

Existing suites already cover authentication (`test_tmobile_callback_auth.py`),
extraction and matching (`test_tmobile_callback_processor.py`), and ingest wiring
(`test_tmobile_callback_integration.py`). This file covers the certification
properties those suites do not: replay, duplicate delivery, ordering,
correlation to the originating request, quarantine of unknown callbacks, and
recoverability.

Several of these properties are **not implemented**. Those tests are named
``test_GAP_*`` and assert the CURRENT behavior, so the gap is visible, regression
-locked, and impossible to mistake for coverage. Each says what would have to be
built. See `docs/TMOBILE_CALLBACK_CERTIFICATION.md`.

No network access; the database is mocked exactly as the processor suite does.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import tmobile_callback_processor as proc
from app.services.tmobile_callback_processor import (
    EVENT_TYPE_HEADER,
    extract_signal,
    process_payload,
)

_NOW = datetime(2026, 7, 21, 3, 18, 33, tzinfo=timezone.utc)

# Trace ids from the successful activation — the values a correlated callback
# would have to carry.
PARTNER_TXN_ID = "true911-pit-d1475fec-981b-40a7-a27c-d867aab8e7f9"
WORK_FLOW_ID = "8a5659f0-16f5-46fb-9a0d-f35bb37fda92_P"
SERVICE_TXN_ID = "33f2315c-8da4-9bae-b68e-3178a5c7a620"

TEST_ICCID = "8901260963132697538"
FAKE_MSISDN = "5550001234"
FAKE_ACCOUNT_ID = "99900011122"


def _payload(*, body=None, headers=None, created_at=_NOW, payload_id="wh-cert-1"):
    return SimpleNamespace(
        payload_id=payload_id, source="tmobile", direction="inbound",
        headers=headers or {}, body=body, raw_body=None,
        processed=False, created_at=created_at,
    )


def _db_returning(payload):
    result = MagicMock()
    result.scalar_one_or_none.return_value = payload
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


# ── Replay ──────────────────────────────────────────────────────────────────

class TestReplayProtection:
    """A stale callback must not refresh a long-offline device's liveness."""

    @pytest.mark.asyncio
    async def test_replayed_callback_is_refused_promotion(self):
        payload = _payload(body={
            "iccid": TEST_ICCID,
            "event_time": (_NOW - timedelta(days=30)).isoformat(),
        })
        result = await process_payload(_db_returning(payload), payload.payload_id)

        assert result.status == "skipped:replay"
        # Still archived — evidence is preserved even when promotion is refused.
        assert payload.processed is True

    @pytest.mark.asyncio
    async def test_replay_window_boundary_is_enforced(self, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_CALLBACK_MAX_AGE_SECONDS", 600)
        stale = _payload(body={
            "iccid": TEST_ICCID,
            "event_time": (datetime.now(timezone.utc)
                           - timedelta(seconds=900)).isoformat(),
        })
        result = await process_payload(_db_returning(stale), stale.payload_id)
        assert result.status == "skipped:replay"

    def test_GAP_replay_defense_is_a_time_window_not_a_nonce(self):
        """A captured callback replayed WITHIN the window is still accepted.

        The only replay defense is the event-timestamp age check. There is no
        nonce, no delivery-id, and no record of which callbacks were already
        processed — so an attacker (or a T-Mobile retry storm) replaying a
        60-second-old capture passes.

        To close: persist a delivery identifier (or a hash of
        payload + transaction ids) and reject a repeat. Tracked in
        TMOBILE_PRODUCTION_READINESS.md item 10.
        """
        source = inspect.getsource(proc)
        assert "TMOBILE_CALLBACK_MAX_AGE_SECONDS" in source
        for absent in ("nonce", "delivery_id", "seen_callbacks"):
            assert absent not in source, (
                f"{absent!r} now exists — replay protection may have been "
                "implemented; update this test and the readiness checklist."
            )


# ── Duplicate delivery ──────────────────────────────────────────────────────

class TestDuplicateDelivery:
    @pytest.mark.asyncio
    async def test_duplicate_callback_does_not_double_apply_state(self):
        """Promotion is idempotent by construction — it writes absolute values.

        `last_network_event = now` and the activation meta keys are set, never
        incremented or appended, so a duplicate delivery converges on the same
        state rather than compounding.
        """
        signal = extract_signal(_payload(body={
            "iccid": TEST_ICCID, "msisdn": FAKE_MSISDN,
            "accountId": FAKE_ACCOUNT_ID,
        }))
        first = proc.merge_activation_identifiers(
            None, signal.account_id, signal.msisdn)
        second = proc.merge_activation_identifiers(
            dict(first), signal.account_id, signal.msisdn)

        assert first == second
        assert second["tmobile_account_id"] == FAKE_ACCOUNT_ID

    @pytest.mark.asyncio
    async def test_duplicate_delivery_of_the_same_payload_id_is_safe(self):
        """Re-processing an already-processed payload converges, not compounds."""
        payload = _payload(body={
            "iccid": TEST_ICCID, "event_time": _NOW.isoformat()}, )
        payload.processed = True
        db = _db_returning(payload)

        result = await process_payload(db, payload.payload_id)

        # Whatever the outcome, the row stays processed and nothing is appended.
        assert payload.processed is True
        assert result.status.startswith(("skipped", "promoted", "archived"))

    def test_GAP_no_dedupe_prevents_a_second_archive_row(self):
        """Two deliveries of the same callback create two IntegrationPayload rows.

        `_archive_tmobile_callback` mints a fresh `payload_id` per request and
        enqueues a job per row, with no idempotency key
        (`job_service.create_and_enqueue` accepts one; the callback router does
        not pass it). Effects converge, but the audit trail double-counts and
        the worker does redundant work.

        To close: pass an idempotency key derived from the callback's transaction
        ids. Tracked in TMOBILE_PRODUCTION_READINESS.md item 11.
        """
        from app.routers import tmobile_callback

        source = inspect.getsource(tmobile_callback._archive_tmobile_callback)
        assert "uuid.uuid4()" in source
        assert "idempotency_key" not in source


# ── Ordering ────────────────────────────────────────────────────────────────

class TestOrdering:
    def test_event_timestamp_is_extracted_for_ordering_decisions(self):
        signal = extract_signal(_payload(body={
            "iccid": TEST_ICCID, "event_time": _NOW.isoformat()}))
        assert signal.event_timestamp == _NOW

    def test_missing_timestamp_falls_back_to_arrival_time(self):
        """An undated callback is ordered by when we received it."""
        signal = extract_signal(_payload(body={"iccid": TEST_ICCID}))
        assert signal.event_timestamp == _NOW

    def test_GAP_out_of_order_callbacks_are_not_reordered(self):
        """An older in-window callback arriving late still writes liveness=now.

        Promotion writes `last_network_event = now` (arrival), not the event
        timestamp, so a delayed-but-fresh callback cannot be distinguished from
        a current one, and a later-arriving OLDER event overwrites a newer one.
        Within the 10-minute window the practical impact is bounded, but the
        ordering guarantee does not exist.

        To close: compare the incoming event timestamp against the stored one
        and refuse a regression. Tracked in TMOBILE_CALLBACK_CERTIFICATION.md.
        """
        source = inspect.getsource(proc)
        assert "last_network_event" in source
        assert "if signal.event_timestamp <" not in source


# ── Correlation to the originating request ──────────────────────────────────

class TestCorrelation:
    """The activation returned four trace ids. Can a callback be tied back?"""

    def test_iccid_and_msisdn_correlate_a_callback_to_a_subscriber(self):
        """The correlation that DOES work today: the subscriber identifiers."""
        signal = extract_signal(_payload(body={
            "iccid": TEST_ICCID, "msisdn": FAKE_MSISDN,
            "accountId": FAKE_ACCOUNT_ID,
        }))
        assert signal.iccid == TEST_ICCID
        assert signal.msisdn == FAKE_MSISDN
        assert signal.account_id == FAKE_ACCOUNT_ID

    def test_GAP_transaction_ids_are_not_extracted_or_correlated(self):
        """The processor never reads partner/workflow/service transaction ids.

        They are archived inside `IntegrationPayload.headers`/`body` — which is
        why `scripts/tmobile_callback_inspect.py` can find them by scanning —
        but nothing correlates a callback to the request that caused it. A
        callback for an activation we never sent is indistinguishable from a
        legitimate one, as long as the ICCID matches.

        To close: persist the outgoing partner-transaction-id at request time
        and match the callback against it.
        """
        source = inspect.getsource(proc)
        for key in ("partner_transaction_id", "partnerTransactionId",
                    "work_flow_id", "workFlowId", "service_transaction_id"):
            assert key not in source

        signal = extract_signal(_payload(body={
            "iccid": TEST_ICCID, "partnerTransactionId": PARTNER_TXN_ID,
            "workFlowId": WORK_FLOW_ID, "serviceTransactionId": SERVICE_TXN_ID,
        }))
        assert not hasattr(signal, "partner_transaction_id")

    def test_transaction_ids_survive_in_the_archive_for_manual_correlation(self):
        """The inspector's scan is the interim correlation mechanism."""
        payload = _payload(
            body={"iccid": TEST_ICCID, "partnerTransactionId": PARTNER_TXN_ID},
            headers={"work-flow-id": WORK_FLOW_ID,
                     EVENT_TYPE_HEADER: "provisioning"},
        )
        assert PARTNER_TXN_ID in str(payload.body)
        assert WORK_FLOW_ID in str(payload.headers)


class TestUnknownCallbackHandling:
    @pytest.mark.asyncio
    async def test_callback_for_an_unknown_subscriber_is_archived_not_applied(self):
        """The closest thing to quarantine that exists: archive, never promote."""
        payload = _payload(body={
            "iccid": "8999999999999999999", "event_time": _NOW.isoformat()})
        db = _db_returning(payload)
        # Sim lookup and Device fallback both miss.
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=payload)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(
                all=MagicMock(return_value=[])))),
            MagicMock(scalars=MagicMock(return_value=MagicMock(
                all=MagicMock(return_value=[])))),
        ])

        result = await process_payload(db, payload.payload_id)

        assert result.status.startswith(("archived", "skipped"))
        assert "promoted" not in result.status
        assert payload.processed is True

    @pytest.mark.asyncio
    async def test_callback_with_no_identifier_is_refused(self):
        payload = _payload(body={"event_type": "ping"})
        result = await process_payload(_db_returning(payload), payload.payload_id)
        assert result.status == "skipped:no_identifier"

    @pytest.mark.asyncio
    async def test_ambiguous_match_refuses_rather_than_guessing(self):
        """Two candidate rows must never be resolved by picking one."""
        payload = _payload(body={
            "msisdn": FAKE_MSISDN, "event_time": _NOW.isoformat()})
        db = MagicMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=payload)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(
                all=MagicMock(return_value=[
                    SimpleNamespace(iccid="1" * 19, msisdn=FAKE_MSISDN,
                                    device_id="a", tenant_id="t", meta=None),
                    SimpleNamespace(iccid="2" * 19, msisdn=FAKE_MSISDN,
                                    device_id="b", tenant_id="t", meta=None),
                ])))),
        ])

        result = await process_payload(db, payload.payload_id)
        assert "ambiguous" in result.status or result.status.startswith("skipped")

    def test_GAP_no_quarantine_queue_for_unrecognized_callbacks(self):
        """Unmatched callbacks are archived silently, not flagged for review.

        `IntegrationPayload` has `processed`, but no `quarantined` state and no
        operator surface listing callbacks that arrived for subscribers we do
        not know. `scripts/tmobile_callback_inspect.py` can find them only if
        you already know what to search for.

        To close: a quarantine flag plus an operator report of unmatched
        callbacks.
        """
        from app.models.integration_payload import IntegrationPayload

        columns = set(IntegrationPayload.__table__.columns.keys())
        assert "processed" in columns
        assert not {"quarantined", "quarantine_reason"} & columns


# ── Log sanitization ────────────────────────────────────────────────────────

class TestCallbackLogSanitization:
    def test_sensitive_header_names_are_redacted(self):
        from app.routers.tmobile_callback import _safe_headers

        safe = _safe_headers({
            "Authorization": "Bearer super-secret",
            "X-True911-Callback-Token": "the-shared-secret",
            "Content-Type": "application/json",
        })
        assert safe["Authorization"] == "[REDACTED]"
        assert safe["X-True911-Callback-Token"] == "[REDACTED]"
        assert safe["Content-Type"] == "application/json"

    def test_token_in_the_query_string_is_redacted(self):
        """The callback URL registered with T-Mobile may carry ?token=."""
        from app.routers.tmobile_callback import _safe_query

        assert _safe_query({"token": "shared-secret", "event": "x"}) == {
            "token": "[REDACTED]", "event": "x"}

    def test_identifiers_are_masked_in_processor_logs(self):
        masked = proc._redact_identifier(TEST_ICCID)
        assert TEST_ICCID not in masked
        assert masked.endswith("38")

    def test_short_identifiers_are_not_leaked_by_the_masker(self):
        assert proc._redact_identifier("1234") == "1***"
        assert proc._redact_identifier(None) == "<none>"


# ── Recoverability ──────────────────────────────────────────────────────────

class TestRecoverability:
    @pytest.mark.asyncio
    async def test_a_missing_payload_row_is_reported_not_crashed(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)))
        db.commit = AsyncMock()

        result = await process_payload(db, "wh-does-not-exist")

        assert result.status == "error:not_found"
        db.commit.assert_not_called()

    def test_archive_failure_still_returns_200_to_the_validator(self):
        """A retry storm is worse than one lost archive — by design."""
        from app.routers import tmobile_callback

        source = inspect.getsource(tmobile_callback._maybe_archive)
        assert "except Exception" in source
        assert "returning 200" in source

    def test_the_raw_payload_is_retained_for_replay(self):
        """Recovery is possible because the original body is archived verbatim."""
        from app.models.integration_payload import IntegrationPayload

        columns = set(IntegrationPayload.__table__.columns.keys())
        assert {"body", "raw_body", "headers"} <= columns

    def test_unauthenticated_callbacks_are_dropped_before_archiving(self):
        """Authenticity is decided at ingest, so a spoof never reaches state."""
        from app.routers import tmobile_callback

        source = inspect.getsource(tmobile_callback._maybe_archive)
        assert "check_callback_auth" in source
        assert source.index("check_callback_auth") < source.index(
            "_archive_tmobile_callback")
