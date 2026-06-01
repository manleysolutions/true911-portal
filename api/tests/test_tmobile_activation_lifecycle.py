"""Tests for the T-Mobile activation lifecycle (states + timestamps) and the
callback's activation-status extraction. Pure — no DB."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import tmobile_activation as act
from app.services.tmobile_callback_processor import extract_signal

AT = "2026-06-01T12:00:00+00:00"


class TestStates:
    def test_new_record_is_pending(self):
        r = act.new_record()
        assert r["state"] == "Pending Activation"
        assert act.state_of(r) == act.ActivationState.PENDING

    def test_submit_sets_requested_at(self):
        r = act.mark_submitted(act.new_record(), at=AT)
        assert r["state"] == "Activation Submitted"
        assert r["requested_at"] == AT

    def test_processing(self):
        r = act.mark_processing(act.new_record(), at=AT, activation_status="processing")
        assert r["state"] == "Activation Processing"
        assert r["callback_at"] == AT

    def test_activated_captures_account_and_msisdn(self):
        r = act.mark_activated(act.new_record(), account_id="ACC-1",
                               msisdn="7542697860", at=AT, activation_status="active")
        assert r["state"] == "Activated"
        assert r["account_id"] == "ACC-1"
        assert r["msisdn"] == "7542697860"
        assert r["callback_at"] == AT

    def test_failed_captures_reason(self):
        r = act.mark_failed(act.new_record(), reason="rejected", at=AT,
                            activation_status="failed")
        assert r["state"] == "Activation Failed"
        assert r["failure_reason"] == "rejected"

    def test_transitions(self):
        S = act.ActivationState
        assert act.can_transition(S.PENDING, S.SUBMITTED)
        assert act.can_transition(S.SUBMITTED, S.ACTIVATED)
        assert not act.can_transition(S.ACTIVATED, S.PENDING)


class TestResolveFromCallback:
    def test_account_id_yields_activated(self):
        r = act.resolve_from_callback(None, account_id="ACC-9", msisdn="7542697860",
                                      activation_status=None, at=AT)
        assert r["state"] == "Activated"
        assert r["account_id"] == "ACC-9"
        assert r["msisdn"] == "7542697860"

    def test_explicit_success_status(self):
        r = act.resolve_from_callback(None, account_id=None, msisdn=None,
                                      activation_status="completed", at=AT)
        assert r["state"] == "Activated"

    def test_failure_status(self):
        r = act.resolve_from_callback(None, account_id=None, msisdn=None,
                                      activation_status="failed", at=AT)
        assert r["state"] == "Activation Failed"

    def test_intermediate_status_is_processing(self):
        r = act.resolve_from_callback(None, account_id=None, msisdn=None,
                                      activation_status="in_progress", at=AT)
        assert r["state"] == "Activation Processing"

    def test_noop_when_nothing_actionable(self):
        r = act.resolve_from_callback(None, account_id=None, msisdn=None,
                                      activation_status=None, at=AT)
        assert r["state"] == "Pending Activation"

    def test_preserves_prior_account_id(self):
        prior = act.mark_activated(act.new_record(), account_id="ACC-1",
                                   msisdn="111", at=AT)
        r = act.resolve_from_callback(prior, account_id=None, msisdn=None,
                                      activation_status="active", at=AT)
        assert r["account_id"] == "ACC-1"  # not lost


class TestCallbackExtractsActivationStatus:
    def _payload(self, body):
        return SimpleNamespace(
            headers={"x-true911-tmobile-event-type": "provisioning"},
            body=body, created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))

    def test_extract_signal_picks_up_activation_status(self):
        sig = extract_signal(self._payload({
            "ICCID": "8901240204219433645", "accountId": "ACC-1",
            "activationStatus": "active", "msisdn": "7542697860"}))
        assert sig.activation_status == "active"
        assert sig.account_id == "ACC-1"

    def test_activation_status_absent(self):
        sig = extract_signal(self._payload({"ICCID": "8901240204219433645"}))
        assert sig.activation_status is None
