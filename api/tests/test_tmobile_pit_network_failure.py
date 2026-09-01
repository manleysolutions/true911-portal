"""What a FAILED live carrier read must — and must not — do.

On 2026-09-01 exactly one live Network Profile request was sent to T-Mobile
Wholesale PIT. OAuth returned HTTP 200; the resource request returned HTTP 500
with carrier code ``GENS-0005`` ("Unexpected Exception"). Record:
``docs/TMOBILE_PIT_CERTIFICATION_20260901.md``.

Nothing about that outcome was wrong, and the harness handled it correctly. The
hazard is what a *later* session might do with it — because a failure is where
the tempting mistakes live: retry it, treat "we reached the gateway" as
certification evidence, let the consumed grant cover the next operation, settle
the ledger from a read that never returned a status, or quietly walk on to
Usage. Each of those would be a live-fire mistake, and none of them was pinned
by a test before this file existed.

So these are failure-path invariants, driven end-to-end through the operator
harness against a mocked carrier that returns the real shape of that 500:

* maturity does not advance — ``query_network`` stays ``MOCK_CERTIFIED``;
* a carrier error never becomes successful PIT evidence;
* the one-shot grant is consumed and cleared even though nothing succeeded;
* exactly one resource request leaves the process — no retry, no polling;
* no next operation runs, and ``query_usage`` inherits nothing;
* the lifecycle ledger is not reconciled from a failed read;
* ``query_transaction_status`` stays blocked by its carrier question, which
  outranks any one-shot grant;
* an explicitly nominated ICCID survives parser -> preview -> execute intact.

Every identifier here is fabricated. The real PIT selector and the carrier trace
identifiers stay in the operator's private evidence store.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.integrations.tmobile_lifecycle as LC
import app.integrations.tmobile_operations as OPS
import app.integrations.tmobile_pit_authorization as AUTH
import app.integrations.tmobile_taap as taap

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

BASE_URL = "https://wholesaleapi-test.t-mobile.com"
TOKEN_URL = f"{BASE_URL}/oauth2/v1/tokens"
NETWORK_PATH = "/wholesale/v1/subscriber/network-profile"
USAGE_PATH = "/wholesale/v1/subscriber/usage"
PROFILE_PATH = "/wholesale/v1/subscriber/profile"
TRANSACTION_PATH = "/wholesale/v1/transaction"

# Fabricated sentinels — see .gitleaks.toml (the TM_TEST_ prefix is allowlisted).
CONSUMER_KEY = "TM_TEST_CK_HG7XQ2"
CONSUMER_SECRET = "TM_TEST_CS_PL3JR9"
ACCESS_TOKEN = "redacted-token-not-real"

# Fabricated stand-in for the designated PIT SIM. Never the real one.
ICCID = "8901260963132600001"
OTHER_ICCID = "8901260963132600002"

#: The shape T-Mobile actually returned, with its own trace identifiers replaced
#: by fabricated ones. The carrier's message text is generic and vendor-supplied,
#: not documentation, so reproducing it here discloses nothing.
GENS_0005_BODY = {
    "code": "GENS-0005",
    "userMessage": "Unexpected Exception: Please notify your system administrator",
}
GENS_0005_HEADERS = {
    "X-Correlation-Id": "00000000-0000-4000-8000-fabricated0001",
    "work-flow-id": "00000000-0000-4000-8000-fabricated0002_P",
    "service-transaction-id": "00000000-0000-4000-8000-fabricated0003",
}


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
    """A fully configured PIT environment with the live switch open.

    Deliberately permissive: every gate that could refuse *before* the request
    is satisfied, so what these tests observe is genuinely the failure path and
    not an early refusal wearing its clothes.
    """
    for name, value in {
        "TMOBILE_ENV": "pit",
        "TMOBILE_BASE_URL": BASE_URL,
        "TMOBILE_TOKEN_URL": TOKEN_URL,
        "TMOBILE_CONSUMER_KEY": CONSUMER_KEY,
        "TMOBILE_CONSUMER_SECRET": CONSUMER_SECRET,
        "TMOBILE_PARTNER_ID": "128",
        "TMOBILE_SENDER_ID": "128",
        "TMOBILE_ACCOUNT_ID": "",
        "TMOBILE_CALLBACK_LOCATION": "https://example.invalid/api/tmobile/callback",
        "TMOBILE_PIT_LIVE_CALLS_ENABLED": "true",
        "TMOBILE_PARTNER_FOUNDATION_ID": "",
        "TMOBILE_PARTNER_FOUNDATION_HEADER": "",
        "TMOBILE_PIT_READONLY_ICCID_ALLOWLIST": ICCID,
        "TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST": "",
        "TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST": "",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)
    monkeypatch.setenv("TMOBILE_PIT_STATE_DIR", str(tmp_path / "ledger"))
    AUTH.clear_authorization()
    yield tmp_path
    AUTH.clear_authorization()


def _read_args(**overrides) -> argparse.Namespace:
    base = dict(
        iccid=ICCID, msisdn=None, imsi=None, transaction_id=None,
        preview=False, execute=True, confirm_live=True,
        confirm_subscriber_approved=True, operator="reviewer", out_dir=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _mock_token():
    return respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600}))


def _carrier_error(path=NETWORK_PATH, status=500, body=None, headers=None):
    return respx.post(f"{BASE_URL}{path}").mock(return_value=httpx.Response(
        status, json=body if body is not None else GENS_0005_BODY,
        headers=headers if headers is not None else GENS_0005_HEADERS))


def _run_failed_network_read(cli, tmp_path, **overrides):
    """Drive exactly one failing query_network through the operator harness."""
    token = _mock_token()
    resource = _carrier_error()
    args = _read_args(out_dir=str(tmp_path / "evidence"), **overrides)
    code = asyncio.run(cli.cmd_read_only(args, "query_network"))
    return code, token, resource


def _bundles(tmp_path):
    return sorted((tmp_path / "evidence").glob("*.json"))


def _blocked(operation: str) -> bool:
    try:
        OPS.require_live_sendable(operation)
        return False
    except OPS.TMobileOperationBlockedError:
        return True


# ── A. Maturity does not advance on a failed attempt ────────────────────────

class TestMaturityDoesNotAdvanceOnFailure:
    """`PIT_TESTED` means *successfully* exercised. A 500 is neither half."""

    @respx.mock
    def test_query_network_stays_mock_certified_after_a_carrier_500(
        self, cli, pit_env
    ):
        code, _, _ = _run_failed_network_read(cli, pit_env)

        assert code == 1
        assert (OPS.get_operation("query_network").readiness
                is OPS.ReadinessState.MOCK_CERTIFIED)

    @respx.mock
    def test_send_authorization_is_untouched_by_a_failed_attempt(
        self, cli, pit_env
    ):
        """Maturity and authorization are separate axes; neither moved."""
        _run_failed_network_read(cli, pit_env)

        op = OPS.get_operation("query_network")
        assert op.send_authorization is OPS.SendAuthorization.SINGLE_RUN_ONLY
        assert not op.is_sendable
        assert op.is_single_run_certifiable

    def test_the_registry_records_the_attempt_without_claiming_certification(self):
        """*Attempted and failed* must stay distinguishable from *not attempted*.

        The existing free-text status fields carry that distinction, which is
        why no new enum member was invented for it.
        """
        network = OPS.get_operation("query_network")
        usage = OPS.get_operation("query_usage")

        assert "2026-09-01" in network.test_status
        assert "GENS-0005" in network.test_status
        assert "NOT certified" in network.test_status
        assert "Never sent live." in usage.test_status
        assert "GENS-0005" not in usage.test_status

    def test_no_read_operation_became_generally_sendable(self):
        assert [o.name for o in OPS.sendable_operations()] == ["activate_subscriber"]


# ── B. A carrier error is never successful evidence ─────────────────────────

class TestFailureIsNotSuccessfulEvidence:
    @respx.mock
    def test_the_bundle_records_the_run_as_failed(self, cli, pit_env):
        _run_failed_network_read(cli, pit_env)

        bundle = json.loads(_bundles(pit_env)[0].read_text(encoding="utf-8"))
        assert bundle["ok"] is False
        assert "error" in bundle
        assert bundle.get("normalized_status") is None
        assert "subscriber_status_raw" not in bundle

    @respx.mock
    def test_evidence_is_written_even_though_nothing_succeeded(self, cli, pit_env):
        """A failure is exactly when the bundle matters most."""
        _run_failed_network_read(cli, pit_env)

        written = _bundles(pit_env)
        assert len(written) == 1
        assert written[0].with_suffix(".txt").exists()

    @respx.mock
    def test_the_bundle_captures_the_exchange_that_failed(self, cli, pit_env):
        _run_failed_network_read(cli, pit_env)

        bundle = json.loads(_bundles(pit_env)[0].read_text(encoding="utf-8"))
        resource = [e for e in bundle["exchanges"]
                    if e["request"]["path"] == NETWORK_PATH]
        assert len(resource) == 1
        assert resource[0]["response"]["status_code"] == 500

    @respx.mock
    def test_the_captured_error_carries_no_access_token(self, cli, pit_env):
        """Sanitization must hold on the failure path too."""
        _run_failed_network_read(cli, pit_env)

        blob = _bundles(pit_env)[0].read_text(encoding="utf-8")
        assert ACCESS_TOKEN not in blob
        assert CONSUMER_SECRET not in blob

    @respx.mock
    def test_the_operator_is_told_to_stop_and_classify(self, cli, pit_env, capsys):
        _run_failed_network_read(cli, pit_env)

        out = capsys.readouterr().out
        assert "STOP" in out
        assert "Do NOT retry" in out
        assert "advance to the next operation" in out

    @respx.mock
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 502, 503])
    def test_any_carrier_error_status_fails_closed(self, cli, pit_env, status):
        """Not a 500 special case — no error status may read as success."""
        _mock_token()
        _carrier_error(status=status)
        args = _read_args(out_dir=str(pit_env / "evidence"))
        code = asyncio.run(cli.cmd_read_only(args, "query_network"))

        assert code == 1
        bundle = json.loads(_bundles(pit_env)[0].read_text(encoding="utf-8"))
        assert bundle["ok"] is False


# ── C. The one-shot grant is spent, not left lying around ───────────────────

class TestGrantIsConsumedOnFailure:
    @respx.mock
    def test_the_grant_is_cleared_after_a_failed_read(self, cli, pit_env):
        _run_failed_network_read(cli, pit_env)

        assert AUTH.active_authorization() is None
        assert _blocked("query_network")

    @respx.mock
    def test_a_second_attempt_finds_no_standing_authorization(self, cli, pit_env):
        """Re-running is a fresh, deliberate grant — never a free retry."""
        _run_failed_network_read(cli, pit_env)

        client = taap.TMobileTAAPClient()
        with pytest.raises(OPS.TMobileOperationBlockedError):
            asyncio.run(client.query_network(iccid=ICCID))
        asyncio.run(client.close())


# ── D/E. One request; nothing else runs by itself ───────────────────────────

class TestExactlyOneRequestAndNoFollowOn:
    @respx.mock
    def test_exactly_one_resource_request_is_sent(self, cli, pit_env):
        _, _, resource = _run_failed_network_read(cli, pit_env)

        assert resource.call_count == 1

    @respx.mock
    def test_no_usage_or_transaction_request_follows_the_failure(
        self, cli, pit_env
    ):
        _mock_token()
        _carrier_error()
        usage = respx.post(f"{BASE_URL}{USAGE_PATH}").mock(
            return_value=httpx.Response(200, json={"status": "SUCCESS"}))
        transaction = respx.post(f"{BASE_URL}{TRANSACTION_PATH}").mock(
            return_value=httpx.Response(200, json={"status": "SUCCESS"}))
        profile = respx.post(f"{BASE_URL}{PROFILE_PATH}").mock(
            return_value=httpx.Response(200, json={"status": "SUCCESS"}))

        asyncio.run(cli.cmd_read_only(
            _read_args(out_dir=str(pit_env / "evidence")), "query_network"))

        assert usage.call_count == 0
        assert transaction.call_count == 0
        assert profile.call_count == 0

    @respx.mock
    def test_only_one_evidence_bundle_is_produced(self, cli, pit_env):
        """A retry or a chained follow-on would show up as a second bundle."""
        _run_failed_network_read(cli, pit_env)

        assert len(_bundles(pit_env)) == 1

    def test_the_harness_has_no_scheduler_retry_or_bulk_mode(self, cli):
        source = (REPO_ROOT / "scripts" / "tmobile_pit.py").read_text(
            encoding="utf-8")
        for banned in ("while True", "for attempt in", "retry(", "tenacity",
                       "backoff", "--all", "asyncio.gather"):
            assert banned not in source, banned


# ── F. A failed read settles nothing about the line ─────────────────────────

class TestFailedReadDoesNotReconcileLifecycleState:
    @respx.mock
    def test_the_ledger_is_not_written_by_a_failed_read(self, cli, pit_env):
        _run_failed_network_read(cli, pit_env)

        ledger = cli._load_ledger(ICCID)
        assert ledger["state"] == LC.LifecycleState.UNKNOWN.value
        assert ledger["evidence_ledger"]["carrier_verified_at"] is None
        assert ledger["evidence_ledger"]["carrier_verified_status_raw"] is None

    @respx.mock
    def test_a_previously_settled_state_is_left_alone(self, cli, pit_env):
        """A failure must not disturb a state that a successful read settled."""
        _mock_token()
        respx.post(f"{BASE_URL}{PROFILE_PATH}").mock(
            return_value=httpx.Response(200, json={
                "status": "SUCCESS", "iccid": ICCID,
                "subscriberStatus": "Active",
                "result": [{"result": "100", "status": "SUCCESS"}]}))
        asyncio.run(cli.cmd_read_only(
            _read_args(out_dir=str(pit_env / "evidence")), "subscriber_inquiry"))
        before = cli._load_ledger(ICCID)
        assert before["state"] == LC.LifecycleState.ACTIVE.value

        _carrier_error()
        asyncio.run(cli.cmd_read_only(
            _read_args(out_dir=str(pit_env / "evidence")), "query_network"))

        after = cli._load_ledger(ICCID)
        assert after["state"] == before["state"]
        assert (after["evidence_ledger"]["carrier_verified_at"]
                == before["evidence_ledger"]["carrier_verified_at"])
        assert (after["evidence_ledger"]["carrier_verified_by_operation"]
                == "subscriber_inquiry")

    @respx.mock
    def test_the_bundle_claims_no_reconciliation(self, cli, pit_env):
        _run_failed_network_read(cli, pit_env)

        bundle = json.loads(_bundles(pit_env)[0].read_text(encoding="utf-8"))
        assert "ledger_reconciliation" not in bundle


# ── G. Usage is gated on its own, always ────────────────────────────────────

class TestUsageInheritsNothing:
    def test_usage_remains_mock_certified_and_unattempted(self):
        op = OPS.get_operation("query_usage")
        assert op.readiness is OPS.ReadinessState.MOCK_CERTIFIED
        assert not op.is_sendable
        assert "Never sent live." in op.test_status

    def test_a_network_grant_does_not_authorize_usage(self, pit_env):
        AUTH.grant_single_run(
            operation="query_network", selector_type="iccid", selector=ICCID,
            operator="reviewer", confirmed=True)

        assert _blocked("query_usage")
        assert _blocked("subscriber_inquiry")
        assert _blocked("query_transaction_status")

    @respx.mock
    def test_usage_is_blocked_at_the_client_after_a_failed_network_read(
        self, cli, pit_env
    ):
        """The consumed grant must not leave a usable opening behind it."""
        _run_failed_network_read(cli, pit_env)
        usage = respx.post(f"{BASE_URL}{USAGE_PATH}").mock(
            return_value=httpx.Response(200, json={"status": "SUCCESS"}))

        client = taap.TMobileTAAPClient()
        with pytest.raises(OPS.TMobileOperationBlockedError):
            asyncio.run(client.query_usage(iccid=ICCID))
        asyncio.run(client.close())
        assert usage.call_count == 0

    def test_a_usage_grant_must_be_issued_for_usage_by_name(self, pit_env):
        auth = AUTH.grant_single_run(
            operation="query_usage", selector_type="iccid", selector=ICCID,
            operator="reviewer", confirmed=True)

        assert auth.is_valid_for("query_usage")
        assert not auth.is_valid_for("query_network")


# ── H. The transaction-status blocker outranks everything ───────────────────

class TestTransactionStatusStaysBlocked:
    def test_the_carrier_question_is_still_recorded_as_a_blocker(self):
        blockers = OPS.certification_blockers("query_transaction_status")
        assert blockers
        assert "transactionId" in blockers[0]

    def test_no_single_run_grant_can_be_issued_for_it(self, pit_env):
        with pytest.raises(AUTH.AuthorizationError):
            AUTH.grant_single_run(
                operation="query_transaction_status",
                selector_type=AUTH.TRANSACTION_SELECTOR,
                selector="PIT-TXN-FABRICATED-0001",
                operator="reviewer", confirmed=True)

    def test_the_blocker_outranks_route_and_maturity(self):
        """Declared SINGLE_RUN_ONLY and still ungrantable — by design."""
        op = OPS.get_operation("query_transaction_status")
        assert op.send_authorization is OPS.SendAuthorization.SINGLE_RUN_ONLY
        assert not op.is_single_run_certifiable
        assert not op.is_sendable

    @respx.mock
    def test_the_failures_trace_identifiers_do_not_unblock_it(self, cli, pit_env):
        """The 500 returned four identifiers. None is a confirmed transactionId.

        This is the specific temptation the blocker exists to refuse: a failed
        call that hands back plausible-looking ids is not T-Mobile answering the
        question of which one the field wants.
        """
        _run_failed_network_read(cli, pit_env)

        assert OPS.certification_blockers("query_transaction_status")
        assert _blocked("query_transaction_status")

    def test_the_certifiable_reads_carry_no_such_blocker(self):
        for operation in ("subscriber_inquiry", "query_network", "query_usage"):
            assert not OPS.certification_blockers(operation), operation


# ── I. The nominated ICCID survives the whole dispatch ──────────────────────

class TestExplicitSelectorSurvivesDispatch:
    """Two live attempts on 2026-09-01 reached the gate with no selector.

    The cause was a shell-local variable that did not survive between copied
    command blocks — no carrier request was sent, and the gate was right. These
    pin that the harness itself never loses an ICCID that WAS supplied, so a
    future recurrence is unambiguously an operator-environment problem.
    """

    def test_the_parser_keeps_the_iccid_on_the_read_subcommands(self, cli):
        for command in ("subscriber-inquiry", "query-network", "query-usage"):
            args = cli.build_parser().parse_args([command, "--iccid", ICCID])
            assert args.iccid == ICCID, command
            assert args.command == command

    def test_the_parsed_iccid_reaches_the_selector_resolver(self, cli):
        args = cli.build_parser().parse_args(["query-network", "--iccid", ICCID])
        assert cli._selector_from(args) == ("iccid", ICCID)

    def test_a_missing_selector_refuses_rather_than_defaulting(self, cli):
        args = cli.build_parser().parse_args(["query-network"])
        with pytest.raises(SystemExit, match="explicitly nominated"):
            cli._selector_from(args)

    def test_two_selectors_refuse_rather_than_choosing(self, cli):
        args = cli.build_parser().parse_args(
            ["query-network", "--iccid", ICCID, "--msisdn", "5550001234"])
        with pytest.raises(SystemExit, match="Exactly one selector"):
            cli._selector_from(args)

    def test_preview_shows_the_nominated_iccid_masked_and_sends_nothing(
        self, cli, pit_env, capsys
    ):
        args = cli.build_parser().parse_args(["query-network", "--iccid", ICCID])
        args.out_dir = str(pit_env / "evidence")
        code = asyncio.run(cli.cmd_read_only(args, "query_network"))

        out = capsys.readouterr().out
        assert code == 0
        assert "PREVIEW ONLY" in out
        assert ICCID[-4:] in out
        assert ICCID not in out          # masked, never printed in full

    @respx.mock
    def test_the_nominated_iccid_is_what_reaches_the_wire(self, cli, pit_env):
        """Parser -> preview -> execute: the same subscriber the whole way."""
        _, _, resource = _run_failed_network_read(cli, pit_env)

        sent = json.loads(resource.calls[0].request.content.decode("utf-8"))
        assert sent == {"iccid": ICCID}

    @respx.mock
    def test_an_iccid_off_the_allowlist_is_refused_before_any_request(
        self, cli, pit_env
    ):
        token = _mock_token()
        resource = _carrier_error()
        args = _read_args(iccid=OTHER_ICCID, out_dir=str(pit_env / "evidence"))

        with pytest.raises(LC.AllowlistError):
            asyncio.run(cli.cmd_read_only(args, "query_network"))

        assert token.call_count == 0
        assert resource.call_count == 0

    @respx.mock
    def test_the_grant_pins_the_subscriber_that_was_nominated(self, cli, pit_env):
        _run_failed_network_read(cli, pit_env)

        bundle = json.loads(_bundles(pit_env)[0].read_text(encoding="utf-8"))
        record = bundle["authorization"]
        assert record["selector_masked"].endswith(ICCID[-4:])
        assert ICCID not in json.dumps(record)


# ── Confidentiality of this file itself ─────────────────────────────────────

def test_this_file_carries_no_live_identifier():
    """Synthetic identifiers only — the real ones stay in the private store."""
    blob = pathlib.Path(__file__).read_text(encoding="utf-8")
    for label, banned in (
        ("live PIT ICCID", "89012609631" + "32697538"),
        ("assigned MSISDN", "410240" + "6851"),
        ("generated account id", "104107" + "63214"),
    ):
        if banned in blob:
            pytest.fail(f"test file contains the {label} (value redacted)")
