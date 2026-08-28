"""Cover for how the PIT certification ledger learns what the carrier believes.

The 2026-08-28 PIT run exposed a gap rather than a bug in any one function. The
activation returned HTTP 201 / status SUCCESS / result 100 with an MSISDN and an
account id; an independent SubscriberInquiry then returned
``subscriberStatus: Active``; and the operator ledger still read
``activation_requested``. Nothing was wrong with either call — there was simply
no code path by which *any* observation could settle the ledger. The only thing
that ever wrote it was the request itself, which can only ever say "I asked".

These tests pin the model that closes that gap:

* the ledger records **what** we believe and **why** as two separate things;
* a synchronous answer is evidence class B and settles nothing on its own;
* an independent carrier read is class C and settles the line **without**
  needing a callback;
* a callback that agrees strengthens nothing already carrier-attested, and one
  that disagrees is surfaced rather than absorbed;
* a read-only operation is still single-run authorized, one at a time; and
* QueryTransactionStatus is not authorizable at all while T-Mobile has not said
  what ``transactionId`` means.

Every identifier here is fabricated. The live PIT values stay in the operator's
private evidence store.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.integrations.tmobile_lifecycle as LC
import app.integrations.tmobile_pit_authorization as AUTH
import app.integrations.tmobile_taap as taap
from app.integrations.tmobile_lifecycle import CarrierEvidence, LifecycleState

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

BASE_URL = "https://wholesaleapi-test.t-mobile.com"
TOKEN_URL = f"{BASE_URL}/oauth2/v1/tokens"
ACTIVATE_PATH = "/wholesale/v1/subscriber/activation"
PROFILE_PATH = "/wholesale/v1/subscriber/profile"
NETWORK_PATH = "/wholesale/v1/subscriber/network-profile"
CALLBACK = "https://example.invalid/api/tmobile/callback"

# Fabricated sentinels — see .gitleaks.toml (TM_TEST_ prefix is allowlisted).
CONSUMER_KEY = "TM_TEST_CK_HG7XQ2"
CONSUMER_SECRET = "TM_TEST_CS_PL3JR9"
ACCESS_TOKEN = "redacted-token-not-real"

# Fabricated stand-ins. The certified PIT line's real identifiers are never in
# a test, a fixture, or a doc.
ICCID = "8901260963132600001"
MSISDN = "5550001234"
ACCOUNT_ID = "99900011122"

ACTIVATION_SUCCESS = {
    "status": "SUCCESS",
    "msisdn": MSISDN,
    "iccid": ICCID,
    "accountId": ACCOUNT_ID,
    "result": [{"result": "100", "status": "SUCCESS"}],
}


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cli():
    """The operator harness, loaded by path — it is a script, not a package."""
    path = REPO_ROOT / "scripts" / "tmobile_pit.py"
    spec = importlib.util.spec_from_file_location("tmobile_pit_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def signing_key(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    monkeypatch.setattr(taap, "_load_private_key", lambda: pem)
    return pem


@pytest.fixture
def pit_env(monkeypatch, signing_key, tmp_path):
    for name, value in {
        "TMOBILE_ENV": "pit",
        "TMOBILE_BASE_URL": BASE_URL,
        "TMOBILE_TOKEN_URL": TOKEN_URL,
        "TMOBILE_CONSUMER_KEY": CONSUMER_KEY,
        "TMOBILE_CONSUMER_SECRET": CONSUMER_SECRET,
        "TMOBILE_PARTNER_ID": "128",
        "TMOBILE_SENDER_ID": "128",
        "TMOBILE_ACCOUNT_ID": "",
        "TMOBILE_MARKET_ZIP": "30338",
        "TMOBILE_BASE_PRODUCT_ID": "Infatrac Internet Access Plan",
        "TMOBILE_WPS": "00011586",
        "TMOBILE_ACTIVATION_PATH": ACTIVATE_PATH,
        "TMOBILE_CALLBACK_LOCATION": CALLBACK,
        "TMOBILE_PIT_LIVE_CALLS_ENABLED": "true",
        "TMOBILE_PARTNER_FOUNDATION_ID": "",
        "TMOBILE_PARTNER_FOUNDATION_HEADER": "",
        "TMOBILE_PIT_READONLY_ICCID_ALLOWLIST": ICCID,
        "TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST": ICCID,
        "TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST": "",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)
    monkeypatch.setenv("TMOBILE_PIT_STATE_DIR", str(tmp_path / "ledger"))
    AUTH.clear_authorization()
    yield tmp_path
    AUTH.clear_authorization()


def _mock_token():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600}))


def _run_args(**overrides) -> argparse.Namespace:
    base = dict(
        command="run", operation="activate_subscriber", iccid=ICCID,
        msisdn=None, account_id=None, market_zip="30338", operator="reviewer",
        reason=None, confirm_live=True, confirm_destructive=False,
        confirm_protected=False, out_dir=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _read_args(**overrides) -> argparse.Namespace:
    base = dict(
        iccid=ICCID, msisdn=None, imsi=None, preview=False, execute=True,
        confirm_live=True, confirm_subscriber_approved=True,
        operator="reviewer", out_dir=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _activate(cli, tmp_path, body, status=201):
    """Drive one activation through the operator harness."""
    _mock_token()
    respx.post(f"{BASE_URL}{ACTIVATE_PATH}").mock(
        return_value=httpx.Response(status, json=body))
    args = _run_args(out_dir=str(tmp_path / "evidence"))
    code = asyncio.run(cli.cmd_run(args))
    return code, cli._load_ledger(ICCID)


def _inquire(cli, tmp_path, body):
    """Drive one SubscriberInquiry through the operator harness."""
    _mock_token()
    respx.post(f"{BASE_URL}{PROFILE_PATH}").mock(
        return_value=httpx.Response(200, json=body))
    args = _read_args(out_dir=str(tmp_path / "evidence"))
    code = asyncio.run(cli.cmd_read_only(args, "subscriber_inquiry"))
    return code, cli._load_ledger(ICCID)


# ── 1-4. What the synchronous activation answer does, and does not, establish ─

class TestActivationSynchronousAnswer:
    @respx.mock
    def test_201_success_result_100_is_recorded_as_a_carrier_sync_ack(
        self, cli, pit_env
    ):
        code, doc = _activate(cli, pit_env, ACTIVATION_SUCCESS)

        assert code == 0
        assert doc["evidence"] == CarrierEvidence.CARRIER_SYNC_ACK.value
        assert doc["evidence_ledger"]["carrier_sync_ack_at"] is not None
        assert doc["evidence_ledger"]["carrier_sync_vendor_code"] == "100"

    @respx.mock
    def test_it_does_not_by_itself_claim_the_line_is_active(self, cli, pit_env):
        """The distinction the whole model exists for.

        The carrier answered OUR REQUEST. It has not yet described its own
        record, so the line is requested — not active, and not carrier-attested.
        """
        _, doc = _activate(cli, pit_env, ACTIVATION_SUCCESS)

        assert doc["state"] == LifecycleState.ACTIVATION_REQUESTED.value
        assert not LC.is_carrier_attested(CarrierEvidence(doc["evidence"]))

    @respx.mock
    def test_msisdn_and_account_id_are_captured_from_the_synchronous_body(
        self, cli, pit_env
    ):
        """T-Mobile documented these as callback-only; they arrived inline."""
        _mock_token()
        route = respx.post(f"{BASE_URL}{ACTIVATE_PATH}").mock(
            return_value=httpx.Response(201, json=ACTIVATION_SUCCESS))
        asyncio.run(cli.cmd_run(_run_args(out_dir=str(pit_env / "evidence"))))

        body = json.loads(route.calls[0].response.text)
        assert body["msisdn"] == MSISDN
        assert body["accountId"] == ACCOUNT_ID

    @respx.mock
    def test_a_carrier_failure_never_marks_the_line_active(self, cli, pit_env):
        code, doc = _activate(
            cli, pit_env,
            {"code": "GENS-0003", "message": "Invalid partnerID"}, status=400)

        assert code == 1
        assert doc["state"] == LifecycleState.FAILED.value
        assert doc["evidence"] == CarrierEvidence.REQUEST_SUBMITTED.value
        assert doc["evidence_ledger"]["carrier_sync_ack_at"] is None

    @respx.mock
    @pytest.mark.parametrize("body", [
        pytest.param({"result": [{"result": "100"}]}, id="no-status"),
        pytest.param({"status": "FAILURE", "result": [{"result": "999"}]},
                     id="failure-status-in-a-2xx"),
        pytest.param({"status": "WOMBAT"}, id="unrecognised-status-word"),
        pytest.param({}, id="empty-body"),
    ])
    def test_an_apparent_success_we_cannot_read_fails_closed(
        self, cli, pit_env, body
    ):
        """A 2xx is not a success. ``_request`` only raises on HTTP >= 400, so
        these all arrive looking exactly like the 201 that worked."""
        code, doc = _activate(cli, pit_env, body)

        assert code == 1
        assert doc["state"] == LifecycleState.FAILED.value
        assert doc["evidence"] != CarrierEvidence.CARRIER_SYNC_ACK.value

    @respx.mock
    def test_no_callback_claim_is_made_after_a_synchronous_success(
        self, cli, pit_env
    ):
        """Silence is not evidence, in either direction.

        No callback was observed for the live activation. The ledger must say
        exactly that — not "no callback arrived", which we cannot know, and not
        nothing at all, which reads as though the question was never asked.
        """
        _, doc = _activate(cli, pit_env, ACTIVATION_SUCCESS)
        ledger = doc["evidence_ledger"]

        assert ledger["callback_received_at"] is None
        assert ledger["callback_authenticity_verified"] is None
        assert ledger["callback_correlated"] is None
        assert ledger["callback_agrees"] is None


# ── 5. An independent carrier read is what settles the line ─────────────────

class TestIndependentCarrierRead:
    @respx.mock
    def test_subscriber_status_active_settles_the_ledger_without_a_callback(
        self, cli, pit_env
    ):
        """The exact 2026-08-28 sequence, end to end."""
        _activate(cli, pit_env, ACTIVATION_SUCCESS)
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(
            200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600}))

        code, doc = _inquire(cli, pit_env, {
            "status": "SUCCESS", "iccid": ICCID, "msisdn": MSISDN,
            "subscriberStatus": "Active",
            "result": [{"result": "100", "status": "SUCCESS"}],
        })

        assert code == 0
        assert doc["state"] == LifecycleState.ACTIVE.value
        assert doc["evidence"] == CarrierEvidence.CARRIER_VERIFIED.value
        assert doc["evidence_ledger"]["carrier_verified_status_raw"] == "Active"
        assert (doc["evidence_ledger"]["carrier_verified_by_operation"]
                == "subscriber_inquiry")
        # And it got there with no callback of any kind.
        assert doc["evidence_ledger"]["callback_received_at"] is None

    def test_a_read_is_not_a_transition_and_is_not_blocked_by_a_pending_one(self):
        """``next_state`` refuses everything while a request is outstanding.

        That rule is right for mutations and would be circular for reads: a
        query is how you find out the state, so gating it on knowing the state
        makes the pending state unescapable — which is exactly how the ledger
        got stuck.
        """
        with pytest.raises(LC.InvalidTransition):
            LC.next_state("activate_subscriber",
                          LifecycleState.ACTIVATION_REQUESTED)

        result = LC.reconcile_from_carrier_read(
            "Active", current=LifecycleState.ACTIVATION_REQUESTED)
        assert result.observed_state is LifecycleState.ACTIVE
        assert result.conflict is False

    def test_confirming_a_state_we_already_hold_still_strengthens_the_evidence(
        self,
    ):
        result = LC.reconcile_from_carrier_read(
            "Active", current=LifecycleState.ACTIVE)
        assert result.advanced is False
        assert result.evidence is CarrierEvidence.CARRIER_VERIFIED

    @pytest.mark.parametrize("raw", ["", None, "   "])
    def test_an_absent_status_reconciles_nothing(self, raw):
        with pytest.raises(LC.ReconciliationError, match="no subscriberStatus"):
            LC.reconcile_from_carrier_read(raw, current=LifecycleState.UNKNOWN)

    def test_an_unrecognised_status_word_is_never_guessed_into_a_state(self):
        with pytest.raises(LC.ReconciliationError, match="not in the reconciled"):
            LC.reconcile_from_carrier_read(
                "PendingActivation", current=LifecycleState.ACTIVATION_REQUESTED)

    def test_a_carrier_read_contradicting_a_settled_state_is_a_conflict(self):
        result = LC.reconcile_from_carrier_read(
            "Suspended", current=LifecycleState.ACTIVE)
        assert result.conflict is True
        assert result.evidence is CarrierEvidence.CONFLICT
        # Not overwritten — which of the two is wrong is an operator judgement.
        assert result.observed_state is LifecycleState.ACTIVE

    @respx.mock
    def test_a_usage_response_carries_no_status_and_reconciles_nothing(
        self, cli, pit_env
    ):
        _activate(cli, pit_env, ACTIVATION_SUCCESS)
        before = cli._load_ledger(ICCID)

        result = cli._reconcile_ledger_from_read(
            "query_usage",
            _envelope({"status": "SUCCESS"}, "query_usage"),
            iccid=ICCID, operator="reviewer")

        assert result is None
        assert cli._load_ledger(ICCID)["state"] == before["state"]


def _envelope(body: dict, operation: str):
    from app.integrations.tmobile_contracts import (
        ResponseKind, TMobileResponseEnvelope,
    )
    return TMobileResponseEnvelope.from_payload(
        body, operation=operation, kind=ResponseKind.SYNCHRONOUS,
        http_status=200)


# ── 6-8. A callback arriving afterwards ─────────────────────────────────────

class TestLateCallbackAgreement:
    def test_a_callback_agreeing_with_a_verified_state_changes_nothing(self):
        result = LC.classify_callback_agreement(
            LifecycleState.ACTIVE, current=LifecycleState.ACTIVE,
            current_evidence=CarrierEvidence.CARRIER_VERIFIED)

        assert result.conflict is False
        assert result.advanced is False
        # Already carrier-attested; a callback cannot make it more so.
        assert result.evidence is CarrierEvidence.CARRIER_VERIFIED

    def test_a_callback_settles_a_state_that_only_had_our_own_word_for_it(self):
        result = LC.classify_callback_agreement(
            LifecycleState.ACTIVE, current=LifecycleState.ACTIVATION_REQUESTED,
            current_evidence=CarrierEvidence.CARRIER_SYNC_ACK)

        assert result.observed_state is LifecycleState.ACTIVE
        assert result.evidence is CarrierEvidence.CALLBACK_CONFIRMED
        assert result.conflict is False

    def test_a_callback_conflicting_with_a_verified_state_is_surfaced(self):
        result = LC.classify_callback_agreement(
            LifecycleState.DEACTIVATED, current=LifecycleState.ACTIVE,
            current_evidence=CarrierEvidence.CARRIER_VERIFIED)

        assert result.conflict is True
        assert result.evidence is CarrierEvidence.CONFLICT
        # A late callback does not outrank an independent read.
        assert result.observed_state is LifecycleState.ACTIVE

    def test_only_a_read_or_a_callback_counts_as_carrier_attested(self):
        assert LC.is_carrier_attested(CarrierEvidence.CARRIER_VERIFIED)
        assert LC.is_carrier_attested(CarrierEvidence.CALLBACK_CONFIRMED)
        for weaker in (CarrierEvidence.NONE, CarrierEvidence.REQUEST_SUBMITTED,
                       CarrierEvidence.CARRIER_SYNC_ACK,
                       CarrierEvidence.CONFLICT):
            assert not LC.is_carrier_attested(weaker)


# ── 9-12. What a single-run certification grant may and may not cover ───────

class TestReadOnlyCertificationAuthorization:
    @pytest.mark.parametrize("operation", ["query_network", "query_usage"])
    def test_blocked_without_an_explicit_certification_grant(
        self, pit_env, operation
    ):
        from app.integrations.tmobile_operations import (
            TMobileOperationBlockedError, require_live_sendable,
        )
        with pytest.raises(TMobileOperationBlockedError):
            require_live_sendable(operation)

    @pytest.mark.parametrize("operation", ["query_network", "query_usage"])
    def test_a_grant_authorizes_exactly_one_request(self, pit_env, operation):
        from app.integrations.tmobile_operations import (
            TMobileOperationBlockedError, require_live_sendable,
        )
        AUTH.grant_single_run(
            operation=operation, selector_type="iccid", selector=ICCID,
            operator="reviewer", confirmed=True)

        require_live_sendable(operation)          # the one it paid for
        with pytest.raises(TMobileOperationBlockedError):
            require_live_sendable(operation)      # and no more

    @pytest.mark.parametrize("operation", ["query_network", "query_usage"])
    def test_a_grant_does_not_leak_to_the_other_read(self, pit_env, operation):
        from app.integrations.tmobile_operations import (
            TMobileOperationBlockedError, require_live_sendable,
        )
        other = "query_usage" if operation == "query_network" else "query_network"
        AUTH.grant_single_run(
            operation=operation, selector_type="iccid", selector=ICCID,
            operator="reviewer", confirmed=True)

        with pytest.raises(TMobileOperationBlockedError):
            require_live_sendable(other)

    def test_query_transaction_status_is_not_authorizable_at_all(self, pit_env):
        """Read-only is not sufficient. We do not know what to send.

        The activation returned four distinct identifiers and the contract does
        not say which one is ``transactionId``. A wrong id returns "not found",
        and so does a correct id for an expired transaction — so the run could
        not be interpreted whichever way it went.
        """
        with pytest.raises(AUTH.AuthorizationError,
                           match="unanswered carrier question"):
            AUTH.grant_single_run(
                operation="query_transaction_status",
                selector_type=AUTH.TRANSACTION_SELECTOR,
                selector="PIT-TXN-FABRICATED-0001",
                operator="reviewer", confirmed=True)

    def test_the_blocker_names_the_question_t_mobile_must_answer(self):
        from app.integrations.tmobile_operations import certification_blockers
        (question,) = certification_blockers("query_transaction_status")
        assert "transactionId" in question
        assert "partner-transaction-id" in question

    @pytest.mark.parametrize("operation", ["query_network", "query_usage",
                                           "subscriber_inquiry"])
    def test_the_certifiable_reads_carry_no_such_blocker(self, operation):
        from app.integrations.tmobile_operations import certification_blockers
        assert certification_blockers(operation) == ()

    @pytest.mark.parametrize("operation", [
        "activate_subscriber", "suspend_subscriber", "restore_subscriber",
        "change_sim", "deactivate_subscriber",
    ])
    def test_no_mutation_is_reachable_through_the_certification_path(
        self, pit_env, operation
    ):
        with pytest.raises(AUTH.AuthorizationError):
            AUTH.grant_single_run(
                operation=operation, selector_type="iccid", selector=ICCID,
                operator="reviewer", confirmed=True)

    def test_none_of_the_reads_became_generally_sendable(self):
        from app.integrations.tmobile_operations import (
            get_operation, sendable_operations,
        )
        for operation in ("subscriber_inquiry", "query_network", "query_usage",
                          "query_transaction_status"):
            assert not get_operation(operation).is_sendable
        assert [op.name for op in sendable_operations()] == [
            "activate_subscriber"]


# ── 13. The operator instruction the harness prints must actually run ───────

class TestEmittedOperatorCommands:
    """The runbook's working directory is ``api/``. Commands are printed for a
    human to paste, so one that fails there is a defect in the tool."""

    def test_the_callback_inspector_is_emitted_as_a_path_not_a_module(self, cli):
        assert cli._callback_inspect_command() == (
            "../scripts/tmobile_callback_inspect.py")

    def test_the_emitted_path_resolves_from_the_documented_directory(self, cli):
        resolved = (REPO_ROOT / "api" / cli._callback_inspect_command()).resolve()
        assert resolved.is_file()

    def test_the_emitted_command_runs_from_the_documented_directory(self, cli):
        proc = subprocess.run(
            [sys.executable, cli._callback_inspect_command(), "--help"],
            cwd=REPO_ROOT / "api", capture_output=True, text=True, timeout=180,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        assert "--iccid" in proc.stdout

    def test_the_module_form_does_not_work_from_there(self):
        """Why the path form is required, pinned so it cannot drift back.

        ``api/scripts`` is a second, unrelated package. From ``api/`` it wins
        the import, so ``python -m scripts.tmobile_callback_inspect`` resolves
        to a package that does not contain this module.
        """
        assert (REPO_ROOT / "api" / "scripts" / "__init__.py").is_file()
        assert not (REPO_ROOT / "api" / "scripts"
                    / "tmobile_callback_inspect.py").exists()

        proc = subprocess.run(
            [sys.executable, "-m", "scripts.tmobile_callback_inspect", "--help"],
            cwd=REPO_ROOT / "api", capture_output=True, text=True, timeout=180,
        )
        assert proc.returncode != 0
        assert "No module named" in (proc.stderr + proc.stdout)

    def test_the_module_form_survives_only_as_an_explanation(self, cli):
        """It may be named in prose so it does not drift back; never printed."""
        source = (REPO_ROOT / "scripts" / "tmobile_pit.py").read_text(
            encoding="utf-8")
        explanation = cli._callback_inspect_sibling.__doc__ or ""

        assert source.count("-m scripts.") == explanation.count("-m scripts.")
        assert explanation.count("-m scripts.") == 1
