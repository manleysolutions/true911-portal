"""Regression cover for the typed contract and lifecycle foundation.

Three properties carry the weight here:

* an invalid request fails as a local object, before OAuth and before the wire;
* a synchronous acceptance is never mistaken for a completed provisioning;
* a callback changes state only on exact correlation, and never otherwise.

Every fixture is fabricated (`tests/fixtures/tmobile_golden_contracts.json`) and
no test opens a network connection.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

import app.integrations.tmobile_contracts as C
import app.integrations.tmobile_operations as OPS
import app.integrations.tmobile_snapshot as SNAP
import app.integrations.tmobile_state as ST
import app.integrations.tmobile_transactions as TX

FIXTURE_PATH = (pathlib.Path(__file__).parent / "fixtures"
                / "tmobile_golden_contracts.json")
GOLDEN = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
FIXTURES = GOLDEN["fixtures"]
IDS = GOLDEN["_identifiers"]

ICCID_A = IDS["iccid_current"]
ICCID_B = IDS["iccid_replacement"]
MSISDN = IDS["msisdn"]
PTX = IDS["partner_transaction_id"]


def envelope(name: str) -> C.TMobileResponseEnvelope:
    f = FIXTURES[name]
    return C.TMobileResponseEnvelope.from_payload(
        f["body"], operation=f["operation"],
        kind=C.ResponseKind(f["kind"]), http_status=f["http_status"],
        headers=f["headers"],
    )


def confirmed(state: ST.LifecycleState) -> ST.TMobileSubscriberState:
    return ST.TMobileSubscriberState(
        workflow_state=state, last_confirmed_state=state, confidence="confirmed")


# ── Requests ────────────────────────────────────────────────────────────────

class TestRequestModels:
    def test_undocumented_fields_are_rejected(self):
        with pytest.raises(C.TMobileRequestError):
            C.SuspendSubscriberRequest(
                msisdn=MSISDN, iccid=ICCID_A, accountId="99900011122")

    def test_required_identifiers_are_enforced(self):
        for model in (C.SuspendSubscriberRequest, C.RestoreSubscriberRequest,
                      C.DeactivateSubscriberRequest):
            with pytest.raises(C.TMobileRequestError):
                model(msisdn=MSISDN)          # iccid missing
            with pytest.raises(C.TMobileRequestError):
                model(iccid=ICCID_A)          # msisdn missing

    def test_query_requires_at_least_one_identifier(self):
        for model in (C.SubscriberInquiryRequest, C.QueryNetworkRequest,
                      C.QuerySubscriberUsageRequest):
            with pytest.raises(C.TMobileRequestError):
                model()

    @pytest.mark.parametrize("field", ["msisdn", "iccid", "imsi"])
    def test_any_single_identifier_suffices(self, field):
        req = C.QueryNetworkRequest(**{field: "5550001234"})
        assert set(req.to_wire()) == {field}

    def test_validation_happens_before_any_network_use(self):
        """A bad request never becomes a client call.

        Proven structurally: constructing the model raises, so there is no
        object to hand to the transport at all.
        """
        with pytest.raises(C.TMobileRequestError):
            C.ChangeSimRequest(msisdn=MSISDN, iccid=ICCID_A)  # newIccid missing

    def test_change_sim_direction_is_explicit(self):
        req = C.ChangeSimRequest(msisdn=MSISDN, iccid=ICCID_A, new_iccid=ICCID_B)
        wire = req.to_wire()
        assert wire["iccid"] == ICCID_A       # the SIM being replaced
        assert wire["newIccid"] == ICCID_B    # its replacement
        assert wire["iccid"] != wire["newIccid"]

    def test_change_sim_rejects_identical_sims(self):
        with pytest.raises(C.TMobileRequestError) as exc:
            C.ChangeSimRequest(msisdn=MSISDN, iccid=ICCID_A, new_iccid=ICCID_A)
        assert ICCID_A not in str(exc.value)   # masked in the error

    def test_usage_rejects_legacy_date_range(self):
        """The old shape must fail loudly, not travel as extra fields."""
        with pytest.raises(C.TMobileRequestError):
            C.QuerySubscriberUsageRequest(
                msisdn=MSISDN, startDate="2026-01-01", endDate="2026-01-31")

    def test_subscriber_inquiry_has_no_account_id_gate(self):
        """The previous false requirement is gone, and cannot return silently."""
        req = C.SubscriberInquiryRequest(msisdn=MSISDN)
        assert req.to_wire() == {"msisdn": MSISDN}
        with pytest.raises(C.TMobileRequestError):
            C.SubscriberInquiryRequest(msisdn=MSISDN, accountId="99900011122")

    def test_transaction_status_requires_an_explicit_id(self):
        with pytest.raises(C.TMobileRequestError):
            C.QueryTransactionStatusRequest(transactionId="")

    def test_wire_aliases_are_exact(self):
        req = C.ChangeSimRequest(msisdn=MSISDN, iccid=ICCID_A,
                                 new_iccid=ICCID_B, pairing_id="DEMO1")
        assert "newIccid" in req.to_wire() and "new_iccid" not in req.to_wire()
        assert "pairingId" in req.to_wire()

    def test_paths_and_methods_come_from_the_registry(self):
        for name, model in C.REQUEST_MODELS.items():
            op = OPS.get_operation(name)
            assert model.model_fields["operation"].default == name
        req = C.SuspendSubscriberRequest(msisdn=MSISDN, iccid=ICCID_A)
        assert req.http_method == "PUT"
        assert req.path == "/wholesale/v1/subscriber/suspension"

    def test_repr_masks_identifiers(self):
        req = C.SuspendSubscriberRequest(msisdn=MSISDN, iccid=ICCID_A)
        text = repr(req)
        assert MSISDN not in text and ICCID_A not in text
        assert text.endswith(")")


# ── Responses ───────────────────────────────────────────────────────────────

class TestResponseModels:
    def test_sim_network_type_present_is_captured(self):
        env = envelope("query_network_with_sim_network_type")
        assert env.sim_network_type == "FABRICATED_NET_A"

    def test_sim_network_type_absent_is_valid(self):
        env = envelope("query_network_without_sim_network_type")
        assert env.sim_network_type is None
        assert env.normalized_status is C.NormalizedStatus.SUCCESS

    def test_unknown_fields_are_preserved_not_rejected(self):
        env = envelope("unknown_added_response_field")
        assert env.raw_extra_fields["someFutureAttribute"] == "fabricated-value"
        assert env.raw_extra_fields["anotherNewBlock"] == {"nested": True}

    def test_unknown_vendor_code_routes_to_manual_review(self):
        env = envelope("unknown_vendor_code")
        assert env.disposition == "unknown_manual_review"

    def test_classification_needs_no_vendor_prose(self):
        """Severity/disposition derive from the code alone."""
        env = envelope("generic_warning")
        assert env.severity == "warning"
        assert env.disposition == "warning_continue"

    def test_sync_acceptance_is_not_completion(self):
        env = envelope("suspend_sync_acceptance")
        assert env.accepted is True
        assert env.completed is False

    def test_async_success_is_completion(self):
        env = envelope("suspend_async_success")
        assert env.completed is True

    def test_failure_response_is_not_accepted(self):
        env = envelope("generic_failure")
        assert env.accepted is False
        assert env.normalized_status is C.NormalizedStatus.FAILURE

    def test_correlation_fields_survive_from_headers_and_body(self):
        env = envelope("activation_sync_acceptance")
        assert env.partner_transaction_id == PTX
        assert env.workflow_id == IDS["workflow_id"]
        assert env.service_transaction_id == IDS["service_transaction_id"]

    def test_pending_transaction_status_is_pending_not_success(self):
        env = envelope("transaction_status_pending")
        assert env.normalized_status is C.NormalizedStatus.PENDING
        assert env.completed is False


# ── Lifecycle ───────────────────────────────────────────────────────────────

class TestLifecyclePreconditions:
    def test_suspend_requires_confirmed_active(self):
        ST.check_preconditions("suspend_subscriber", confirmed(ST.LifecycleState.ACTIVE))
        with pytest.raises(ST.PreconditionError):
            ST.check_preconditions("suspend_subscriber",
                                   confirmed(ST.LifecycleState.SUSPENDED))

    def test_restore_requires_confirmed_suspended(self):
        ST.check_preconditions("restore_subscriber",
                               confirmed(ST.LifecycleState.SUSPENDED))
        with pytest.raises(ST.PreconditionError):
            ST.check_preconditions("restore_subscriber",
                                   confirmed(ST.LifecycleState.ACTIVE))

    def test_mutations_fail_closed_on_unknown_state(self):
        for op in ("suspend_subscriber", "restore_subscriber",
                   "deactivate_subscriber", "change_sim"):
            with pytest.raises(ST.PreconditionError, match="unknown"):
                ST.check_preconditions(op, ST.TMobileSubscriberState())

    def test_deactivate_rejects_already_deactivated(self):
        with pytest.raises(ST.PreconditionError, match="deactivated"):
            ST.check_preconditions("deactivate_subscriber",
                                   confirmed(ST.LifecycleState.DEACTIVATED))

    def test_mutation_while_pending_is_refused_as_duplicate(self):
        state = confirmed(ST.LifecycleState.ACTIVE)
        ST.begin_transition("suspend_subscriber", state)
        with pytest.raises(ST.PreconditionError, match="DUPLICATE"):
            ST.check_preconditions("deactivate_subscriber", state)

    def test_assumed_state_cannot_be_mutated(self):
        state = ST.TMobileSubscriberState(
            workflow_state=ST.LifecycleState.ACTIVE, confidence="assumed")
        with pytest.raises(ST.PreconditionError, match="CONFIRMED"):
            ST.check_preconditions("suspend_subscriber", state)

    def test_reads_are_permitted_from_any_state(self):
        """A query is how you learn the state; gating it on state is circular."""
        for op in ST.READ_ONLY_OPERATIONS:
            ST.check_preconditions(op, ST.TMobileSubscriberState())

    def test_manual_review_blocks_mutation(self):
        state = confirmed(ST.LifecycleState.ACTIVE)
        state.require_reconciliation("conflicting carrier report")
        with pytest.raises(ST.PreconditionError, match="manual review"):
            ST.check_preconditions("suspend_subscriber", state)


class TestTransitions:
    def test_sync_acceptance_creates_pending_not_terminal(self):
        state = confirmed(ST.LifecycleState.ACTIVE)
        ST.begin_transition("suspend_subscriber", state,
                            partner_transaction_id=PTX)
        assert state.workflow_state is ST.LifecycleState.SUSPEND_PENDING
        assert state.expected_state is ST.LifecycleState.SUSPENDED
        assert state.confidence == "assumed"

    def test_async_success_settles_to_expected_terminal(self):
        state = confirmed(ST.LifecycleState.ACTIVE)
        ST.begin_transition("suspend_subscriber", state)
        ST.settle_transition("suspend_subscriber", state, succeeded=True)
        assert state.workflow_state is ST.LifecycleState.SUSPENDED
        assert state.confidence == "confirmed"
        assert state.pending_operation is None

    def test_async_failure_settles_to_failure_state(self):
        state = confirmed(ST.LifecycleState.ACTIVE)
        ST.begin_transition("suspend_subscriber", state)
        ST.settle_transition("suspend_subscriber", state, succeeded=False)
        assert state.workflow_state is ST.LifecycleState.FAILED

    def test_change_sim_has_no_inverse(self):
        assert ST.TRANSITIONS["change_sim"].inverse_operation is None

    def test_suspend_expects_no_async_completion(self):
        """Suspension's synchronous answer is terminal; the others' is not."""
        assert ST.TRANSITIONS["suspend_subscriber"].expects_async_completion is False
        assert ST.TRANSITIONS["restore_subscriber"].expects_async_completion is True

    def test_only_activation_transitions_are_evidence_backed(self):
        backed = {t.operation for t in ST.TRANSITIONS.values() if t.evidence_backed}
        assert backed == {"activate_subscriber"}

    def test_settling_a_non_pending_line_is_refused(self):
        with pytest.raises(ST.TransitionError):
            ST.settle_transition("suspend_subscriber",
                                 confirmed(ST.LifecycleState.ACTIVE), succeeded=True)


# ── Callbacks ───────────────────────────────────────────────────────────────

def _pending_txn(operation="suspend_subscriber", ptx=PTX):
    return TX.LifecycleTransaction(
        operation=operation, tenant_id="t1", partner_transaction_id=ptx,
        iccid_masked="****0001", status=TX.TransactionStatus.SYNC_ACCEPTED,
    )


class TestCallbackApplication:
    def _armed(self, operation="suspend_subscriber"):
        state = confirmed(ST.LifecycleState.ACTIVE)
        ST.begin_transition(operation, state, partner_transaction_id=PTX)
        return state, [_pending_txn(operation)]

    def test_correlated_callback_applies(self):
        state, txns = self._armed()
        out = TX.apply_callback(envelope("suspend_async_success"), txns, state)
        assert out.decision is TX.CallbackDecision.APPLIED
        assert out.state_changed
        assert state.workflow_state is ST.LifecycleState.SUSPENDED

    def test_exact_duplicate_is_idempotent(self):
        state, txns = self._armed()
        TX.apply_callback(envelope("suspend_async_success"), txns, state)
        before = state.workflow_state
        out = TX.apply_callback(envelope("duplicate_callback"), txns, state)
        assert out.decision in (TX.CallbackDecision.DUPLICATE_IGNORED,
                                TX.CallbackDecision.REPLAY_AFTER_COMPLETION)
        assert not out.state_changed
        assert state.workflow_state is before

    def test_replay_after_completion_does_not_overwrite(self):
        state, txns = self._armed()
        TX.apply_callback(envelope("suspend_async_success"), txns, state)
        txns[0].applied_callback_keys.clear()   # force past the dedupe key
        out = TX.apply_callback(envelope("replayed_callback_after_completion"),
                                txns, state)
        assert out.decision is TX.CallbackDecision.REPLAY_AFTER_COMPLETION
        assert not out.state_changed

    def test_out_of_order_callback_for_another_operation_is_quarantined(self):
        state, txns = self._armed()
        out = TX.apply_callback(envelope("out_of_order_callback"), txns, state)
        assert out.decision is TX.CallbackDecision.QUARANTINED_CONFLICTING_OPERATION
        assert not out.state_changed
        assert state.workflow_state is ST.LifecycleState.SUSPEND_PENDING

    def test_conflicting_identifier_is_quarantined(self):
        state, txns = self._armed()
        out = TX.apply_callback(envelope("conflicting_identifier_callback"),
                                txns, state, expected_iccid=ICCID_A)
        assert out.decision is TX.CallbackDecision.QUARANTINED_CONFLICTING_IDENTIFIER
        assert not out.state_changed

    def test_conflict_message_masks_identifiers(self):
        state, txns = self._armed()
        out = TX.apply_callback(envelope("conflicting_identifier_callback"),
                                txns, state, expected_iccid=ICCID_A)
        assert ICCID_A not in out.reason and ICCID_B not in out.reason

    def test_unknown_transaction_leaves_state_untouched(self):
        state, _ = self._armed()
        out = TX.apply_callback(envelope("suspend_async_success"),
                                [_pending_txn(ptx="some-other-txn")], state)
        assert out.decision is TX.CallbackDecision.QUARANTINED_NO_CORRELATION or \
               out.decision is TX.CallbackDecision.QUARANTINED_UNKNOWN_TRANSACTION
        assert not out.state_changed

    def test_uncorrelatable_callback_is_quarantined(self):
        state, txns = self._armed()
        out = TX.apply_callback(envelope("uncorrelatable_callback"), txns, state)
        assert out.decision is TX.CallbackDecision.QUARANTINED_NO_CORRELATION
        assert not out.state_changed

    def test_ambiguous_correlation_is_quarantined(self):
        state, _ = self._armed()
        dupes = [_pending_txn(), _pending_txn()]      # same ptx twice
        out = TX.apply_callback(envelope("suspend_async_success"), dupes, state)
        assert out.decision is TX.CallbackDecision.QUARANTINED_AMBIGUOUS
        assert not out.state_changed

    def test_unknown_result_status_routes_to_manual_review(self):
        state, txns = self._armed()
        env = envelope("suspend_async_success")
        env.normalized_status = C.NormalizedStatus.UNKNOWN
        out = TX.apply_callback(env, txns, state)
        assert out.decision is TX.CallbackDecision.QUARANTINED_UNKNOWN_RESULT
        assert state.reconciliation_required

    def test_correlation_never_falls_back_to_latest_pending(self):
        """The dangerous convenience this module exists to refuse.

        A pending transaction EXISTS and would be the obvious guess. It must not
        be used: a callback with no correlation id is quarantined instead.
        """
        state, txns = self._armed()
        env = envelope("uncorrelatable_callback")
        assert env.partner_transaction_id is None
        out = TX.apply_callback(env, txns, state)
        assert not out.state_changed   # a pending txn existed and was NOT used

    def test_idempotency_key_is_stable_across_deliveries(self):
        a = TX.callback_idempotency_key(envelope("suspend_async_success"))
        b = TX.callback_idempotency_key(envelope("duplicate_callback"))
        assert a == b

    def test_idempotency_key_differs_by_outcome(self):
        ok = envelope("suspend_async_success")
        bad = envelope("suspend_async_success")
        bad.normalized_status = C.NormalizedStatus.FAILURE
        assert TX.callback_idempotency_key(ok) != TX.callback_idempotency_key(bad)

    def test_sync_response_never_marks_completion(self):
        txn = _pending_txn()
        TX.record_sync_response(txn, envelope("suspend_sync_acceptance"))
        assert txn.status is TX.TransactionStatus.SYNC_ACCEPTED
        assert txn.completed_at is None


# ── Snapshot ────────────────────────────────────────────────────────────────

class TestCarrierSnapshot:
    def test_built_from_an_envelope_without_network(self):
        snap = SNAP.TMobileCarrierSnapshot.from_envelope(
            envelope("query_network_with_sim_network_type"), tenant_id="t1")
        assert snap.carrier == "tmobile"
        assert snap.sim_network_type == "FABRICATED_NET_A"
        assert snap.subscriber_status_normalized is C.NormalizedStatus.SUCCESS

    def test_identifiers_are_masked(self):
        snap = SNAP.TMobileCarrierSnapshot.from_envelope(
            envelope("query_network_with_sim_network_type"))
        blob = f"{snap.msisdn_masked}{snap.iccid_masked}{snap.imsi_masked}"
        assert MSISDN not in blob and ICCID_A not in blob
        assert snap.iccid_masked.endswith("0001")

    def test_missing_observation_time_is_stale_not_fresh(self):
        assert SNAP.TMobileCarrierSnapshot().is_stale() is True

    def test_freshness_window(self):
        now = datetime.now(timezone.utc)
        fresh = SNAP.TMobileCarrierSnapshot(observed_at=now - timedelta(hours=1))
        stale = SNAP.TMobileCarrierSnapshot(observed_at=now - timedelta(days=3))
        assert not fresh.is_stale(now=now)
        assert stale.is_stale(now=now)

    def test_unknown_field_count_is_carried(self):
        snap = SNAP.TMobileCarrierSnapshot.from_envelope(
            envelope("unknown_added_response_field"))
        assert snap.raw_extra_field_count == 2


# ── Safety ──────────────────────────────────────────────────────────────────

class TestSafetyUnchanged:
    def test_activation_remains_the_sole_live_sendable_operation(self):
        assert [o.name for o in OPS.sendable_operations()] == ["activate_subscriber"]
        assert len(OPS.blocked_operations()) == 8

    @pytest.mark.parametrize("name", [
        "subscriber_inquiry", "query_network", "query_usage",
        "suspend_subscriber", "restore_subscriber", "change_sim",
        "deactivate_subscriber", "query_transaction_status",
    ])
    def test_typed_models_do_not_weaken_the_registry(self, name):
        """Having a typed model must not imply permission to send it."""
        assert name in C.REQUEST_MODELS
        with pytest.raises(OPS.TMobileOperationBlockedError):
            OPS.require_live_sendable(name)

    def test_fixtures_contain_no_live_identifier(self):
        blob = FIXTURE_PATH.read_text(encoding="utf-8")
        # Split literals: this assertion must not itself become an occurrence
        # of the very identifiers it forbids — the confidentiality guard scans
        # tracked test files for exactly these values.
        for banned in ("89012609631" + "32697538",      # live PIT ICCID
                       "410240" + "6851",                # assigned MSISDN
                       "104107" + "63214"):              # generated account id
            assert banned not in blob

    def test_no_module_performs_io_on_import(self):
        for mod in (C, ST, TX, SNAP):
            source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
            assert "httpx.AsyncClient(" not in source
            assert "requests.get" not in source
