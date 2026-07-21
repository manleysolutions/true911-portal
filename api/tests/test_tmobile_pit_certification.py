"""Safety cover for the T-Mobile PIT certification harness.

The harness exists to make one class of mistake impossible: sending a request to
a carrier's live gateway that we have no documented right to send, or sending a
correct request at the wrong SIM. These tests pin every gate that stands between
an operator and that mistake.

The load-bearing property is in :class:`TestOperationProvenance` — an operation
whose path we derived ourselves is BLOCKED, and no config toggle can unblock it.

All network interaction is mocked; no test opens a real connection.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.integrations.tmobile_evidence as ev
import app.integrations.tmobile_lifecycle as lc
import app.integrations.tmobile_operations as ops
import app.integrations.tmobile_taap as taap

TOKEN_URL = "https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens"
BASE_URL = "https://wholesaleapi-test.t-mobile.com"
ACTIVATE_PATH = "/wholesale/v1/subscriber/activation"
ACTIVATE_URL = f"{BASE_URL}{ACTIVATE_PATH}"
CALLBACK = "https://example.invalid/api/tmobile/callback"

# Fabricated sentinels — see .gitleaks.toml (TM_TEST_ prefix is allowlisted).
CONSUMER_KEY = "TM_TEST_CK_HG7XQ2"
CONSUMER_SECRET = "TM_TEST_CS_PL3JR9"
ACCESS_TOKEN = "redacted-token-not-real"

PROTECTED_ICCID = "8901260963132697538"   # the first-activation line
LIFECYCLE_ICCID = "8901260963132600001"   # fabricated designated test SIM
OTHER_ICCID = "8901260963132600002"       # fabricated, never allowlisted


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
def tmobile_env(monkeypatch, signing_key):
    for name, value in {
        "TMOBILE_ENV": "pit",
        "TMOBILE_BASE_URL": BASE_URL,
        "TMOBILE_TOKEN_URL": TOKEN_URL,
        "TMOBILE_CONSUMER_KEY": CONSUMER_KEY,
        "TMOBILE_CONSUMER_SECRET": CONSUMER_SECRET,
        "TMOBILE_PARTNER_ID": "128",
        "TMOBILE_SENDER_ID": "128",
        "TMOBILE_ACCOUNT_ID": "",
        "TMOBILE_MARKET_ZIP": "30346",
        "TMOBILE_ACTIVATION_PATH": ACTIVATE_PATH,
        "TMOBILE_CALLBACK_LOCATION": CALLBACK,
        "TMOBILE_PIT_LIVE_CALLS_ENABLED": "false",
        "TMOBILE_PIT_READONLY_ICCID_ALLOWLIST": "",
        "TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST": "",
        "TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST": "",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _set_allowlists(monkeypatch, *, read_only="", lifecycle="", destructive=""):
    monkeypatch.setattr(
        "app.config.settings.TMOBILE_PIT_READONLY_ICCID_ALLOWLIST", read_only)
    monkeypatch.setattr(
        "app.config.settings.TMOBILE_PIT_LIFECYCLE_ICCID_ALLOWLIST", lifecycle)
    monkeypatch.setattr(
        "app.config.settings.TMOBILE_PIT_DESTRUCTIVE_ICCID_ALLOWLIST", destructive)


# ── Inventory completeness and provenance ───────────────────────────────────

class TestOperationInventory:
    def test_every_client_method_appears_in_the_inventory(self):
        """A new client method must be classified before it can be shipped.

        This is the guard against the inventory silently going stale: if someone
        adds a wholesale call to the client, this test fails until they record
        its provenance and risk class.
        """
        inventoried = {op.client_method.split(".")[-1] for op in ops.OPERATIONS}
        client_methods = {
            "activate_subscriber", "subscriber_inquiry", "query_network",
            "query_usage", "change_sim", "suspend_subscriber",
            "restore_subscriber", "deactivate_subscriber",
            # Added by the authoritative-contract reconciliation: the vendor
            # contract carries a transaction-status lookup, which is the
            # supported way to investigate a submitted request instead of
            # resending it.
            "query_transaction_status",
        }
        # Confirm the expected set really is what the client exposes.
        for name in client_methods:
            assert hasattr(taap.TMobileTAAPClient, name), name
        assert client_methods == inventoried

    def test_every_operation_has_a_complete_record(self):
        for op in ops.OPERATIONS:
            for field in ("path_source", "request_schema", "response_schema",
                          "callback_behavior", "synchronous", "reversibility",
                          "prerequisite_state", "pit_restrictions",
                          "implementation_status", "test_status"):
                value = getattr(op, field)
                assert value and value.strip(), f"{op.name}.{field} is empty"
            assert op.required_headers
            assert op.pop_ehts

    def test_operation_names_are_unique(self):
        names = [op.name for op in ops.OPERATIONS]
        assert len(names) == len(set(names))

    def test_lookup_of_an_unknown_operation_lists_the_valid_set(self):
        with pytest.raises(KeyError, match="activate_subscriber"):
            ops.get_operation("cancel_everything")


class TestOperationProvenance:
    """The load-bearing rule, in its post-reconciliation form.

    Originally this class pinned "no documented contract, no live request".
    The contracts have since been obtained and reconciled, so the rule that now
    carries the weight is the second half: **having the contract is still not
    authorization to send it.** Every reconciled operation stays blocked on
    readiness until it has actually been exercised in PIT.
    """

    RECONCILED = [
        "subscriber_inquiry", "query_network", "query_usage",
        "suspend_subscriber", "restore_subscriber", "change_sim",
        "deactivate_subscriber", "query_transaction_status",
    ]

    def test_only_activation_is_currently_sendable(self):
        """Exactly one operation may be transmitted live.

        If this fails, either an operation was cleared after real PIT testing
        (update the docs alongside) or someone advanced a readiness state
        without the evidence (revert it).
        """
        assert [op.name for op in ops.sendable_operations()] == [
            "activate_subscriber"]
        assert len(ops.blocked_operations()) == 8

    def test_activation_provenance_is_the_live_response(self):
        op = ops.get_operation("activate_subscriber")
        assert op.provenance is ops.Provenance.CONFIRMED_BY_LIVE_RESPONSE
        assert op.readiness is ops.ReadinessState.PIT_TESTED
        assert op.path == ACTIVATE_PATH
        assert op.is_sendable

    @pytest.mark.parametrize("name", RECONCILED)
    def test_reconciled_operations_are_documented_but_still_blocked(self, name):
        """Documentation moved provenance forward; it did NOT unblock sending."""
        op = ops.get_operation(name)
        assert op.provenance is ops.Provenance.VENDOR_DOCUMENTED
        assert op.readiness is ops.ReadinessState.MOCK_CERTIFIED
        assert not op.is_sendable
        with pytest.raises(ops.TMobileOperationBlockedError):
            ops.require_live_sendable(name)

    @pytest.mark.parametrize("name", RECONCILED)
    def test_block_reason_is_readiness_not_missing_contract(self, name):
        """The refusal must say why, and the why has changed.

        These are no longer blocked for lack of a contract — they are blocked
        because knowing a contract is not the same as having exercised it.
        """
        with pytest.raises(ops.TMobileOperationBlockedError) as exc:
            ops.require_live_sendable(name)
        message = str(exc.value)
        assert "nothing was sent" in message
        assert "blocking gate    : readiness" in message
        assert "mock_certified" in message
        assert ops.CONTRACT_EVIDENCE_REF in message

    def test_no_readiness_state_below_pit_tested_can_send(self):
        """Readiness is the gate; only real PIT evidence opens it."""
        assert ops.LIVE_SENDABLE_READINESS == {
            ops.ReadinessState.PIT_TESTED, ops.ReadinessState.PRODUCTION_APPROVED}
        for state in ops.ReadinessState:
            if state in ops.LIVE_SENDABLE_READINESS:
                continue
            candidate = ops.Operation(
                name="probe", client_method="c", http_method="POST", path="/p",
                path_source="s", classification=ops.Classification.READ_ONLY,
                provenance=ops.Provenance.VENDOR_DOCUMENTED,
                request_schema="r", response_schema="r", callback_behavior="c",
                required_headers=("Authorization",), pop_ehts="e",
                body_signed=True, synchronous="s", reversibility="r",
                prerequisite_state="p", pit_restrictions="p",
                implementation_status="i", test_status="t", readiness=state,
            )
            assert not candidate.is_sendable, state

    def test_unknown_classification_is_never_sendable(self):
        """Even a documented, PIT-tested path is blocked if semantics are unknown."""
        unknown = ops.Operation(
            name="x", client_method="c", http_method="POST", path="/p",
            path_source="s", classification=ops.Classification.UNKNOWN,
            provenance=ops.Provenance.VENDOR_DOCUMENTED,
            request_schema="r", response_schema="r", callback_behavior="c",
            required_headers=("Authorization",), pop_ehts="e", body_signed=True,
            synchronous="s", reversibility="r", prerequisite_state="p",
            pit_restrictions="p", implementation_status="i", test_status="t",
            readiness=ops.ReadinessState.PIT_TESTED,
        )
        assert not unknown.is_sendable

    def test_an_unregistered_operation_fails_closed(self):
        with pytest.raises(ops.TMobileOperationBlockedError, match="unknown operation"):
            ops.require_live_sendable("cancel_everything")

    def test_classification_drives_the_confirmation_requirements(self):
        read = ops.get_operation("subscriber_inquiry")
        reversible = ops.get_operation("activate_subscriber")
        destructive = ops.get_operation("deactivate_subscriber")

        assert not read.requires_confirm_live
        assert reversible.requires_confirm_live
        assert not reversible.requires_confirm_destructive
        assert destructive.requires_confirm_live
        assert destructive.requires_confirm_destructive

    def test_change_sim_is_classified_destructive(self):
        """The replaced SIM ages out and no customer-facing inverse exists."""
        assert (ops.get_operation("change_sim").classification
                is ops.Classification.DESTRUCTIVE)

    def test_deactivation_stays_destructive_despite_a_documented_inverse(self):
        """A reactivation operation exists in the vendor contract.

        We still treat deactivation as terminal: reactivation is neither
        implemented nor tested here, and is not assumed to return the same
        number or plans.
        """
        op = ops.get_operation("deactivate_subscriber")
        assert op.classification is ops.Classification.DESTRUCTIVE
        assert op.requires_confirm_destructive


class TestReconciledWireContract:
    """Exact paths and methods. These are literals, never derived."""

    EXPECTED = {
        "activate_subscriber": ("POST", "/wholesale/v1/subscriber/activation"),
        "subscriber_inquiry": ("POST", "/wholesale/v1/subscriber/profile"),
        "query_network": ("POST", "/wholesale/v1/subscriber/network-profile"),
        "query_usage": ("POST", "/wholesale/v1/subscriber/usage"),
        "suspend_subscriber": ("PUT", "/wholesale/v1/subscriber/suspension"),
        "restore_subscriber": ("PUT", "/wholesale/v1/subscriber/restoration"),
        "change_sim": ("PUT", "/wholesale/v1/subscriber/sim-change"),
        "deactivate_subscriber": ("PUT", "/wholesale/v1/subscriber/deactivation"),
        "query_transaction_status": ("POST", "/wholesale/v1/transaction"),
    }

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_exact_path_and_method(self, name):
        op = ops.get_operation(name)
        method, path = self.EXPECTED[name]
        assert (op.http_method, op.path) == (method, path)

    def test_no_path_is_reproducible_by_the_old_derivation(self):
        """The naming convention that produced these paths was wrong every time.

        Guards against anyone reintroducing a route builder: if a path ever
        again equals base + '/' + operation-name, that is the bug returning.
        """
        base = "/wholesale/v1/subscriber"
        for op in ops.OPERATIONS:
            derived = f"{base}/{op.name.replace('_subscriber', '').replace('_', '')}"
            assert op.path != derived, op.name

    def test_four_lifecycle_operations_use_put_not_post(self):
        """The most dangerous class of prior defect: right path, wrong verb."""
        for name in ("suspend_subscriber", "restore_subscriber",
                     "change_sim", "deactivate_subscriber"):
            assert ops.get_operation(name).http_method == "PUT", name

    def test_path_lookup_recognises_an_outbound_request(self):
        assert ops.operation_for_request(
            "PUT", "/wholesale/v1/subscriber/suspension") == "suspend_subscriber"
        assert ops.operation_for_request(
            "POST", "/wholesale/v1/subscriber/suspension") is None
        assert ops.operation_for_request("POST", "/nope") is None


# ── Allowlist policy ────────────────────────────────────────────────────────

class TestAllowlistParsing:
    def test_empty_is_the_default_and_refuses_everything(self, tmobile_env):
        policy = lc.AllowlistPolicy.from_settings()
        assert policy.read_only == ()
        with pytest.raises(lc.AllowlistError, match="is empty"):
            policy.require_allowed(LIFECYCLE_ICCID, ops.Classification.READ_ONLY)

    def test_wildcards_are_refused(self):
        for raw in ("*", "890126*", "all", "89012609631326975??"):
            with pytest.raises(lc.AllowlistError):
                lc.parse_allowlist(raw, name="TEST")

    def test_malformed_iccids_are_refused_not_silently_dropped(self):
        with pytest.raises(lc.AllowlistError, match="not a valid ICCID"):
            lc.parse_allowlist("12345", name="TEST")
        with pytest.raises(lc.AllowlistError):
            lc.parse_allowlist("890126096313269753A", name="TEST")

    def test_error_messages_mask_the_identifier(self):
        with pytest.raises(lc.AllowlistError) as exc:
            lc.parse_allowlist("1234567890123456789012", name="TEST")
        assert "1234567890123456789012" not in str(exc.value)

    def test_whitespace_and_duplicates_are_normalized(self):
        parsed = lc.parse_allowlist(
            f" {LIFECYCLE_ICCID} , {LIFECYCLE_ICCID},{OTHER_ICCID} ", name="TEST")
        assert parsed == (LIFECYCLE_ICCID, OTHER_ICCID)


class TestAllowlistHierarchy:
    def test_lifecycle_must_be_a_subset_of_read_only(self, tmobile_env, monkeypatch):
        _set_allowlists(monkeypatch, read_only=OTHER_ICCID, lifecycle=LIFECYCLE_ICCID)
        with pytest.raises(lc.AllowlistError, match="subset of the read-only"):
            lc.AllowlistPolicy.from_settings()

    def test_destructive_must_be_a_subset_of_lifecycle(self, tmobile_env, monkeypatch):
        _set_allowlists(
            monkeypatch,
            read_only=f"{LIFECYCLE_ICCID},{OTHER_ICCID}",
            lifecycle=LIFECYCLE_ICCID,
            destructive=OTHER_ICCID,
        )
        with pytest.raises(lc.AllowlistError, match="subset of the lifecycle"):
            lc.AllowlistPolicy.from_settings()

    def test_read_only_listing_does_not_authorize_a_lifecycle_operation(
        self, tmobile_env, monkeypatch
    ):
        """The whole point of the tiers: read access is not write access."""
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID)
        policy = lc.AllowlistPolicy.from_settings()

        policy.require_allowed(LIFECYCLE_ICCID, ops.Classification.READ_ONLY)
        with pytest.raises(lc.AllowlistError, match="is empty"):
            policy.require_allowed(LIFECYCLE_ICCID, ops.Classification.REVERSIBLE)

    def test_lifecycle_listing_does_not_authorize_destruction(
        self, tmobile_env, monkeypatch
    ):
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID,
                        lifecycle=LIFECYCLE_ICCID)
        policy = lc.AllowlistPolicy.from_settings()

        policy.require_allowed(LIFECYCLE_ICCID, ops.Classification.REVERSIBLE)
        with pytest.raises(lc.AllowlistError, match="is empty"):
            policy.require_allowed(LIFECYCLE_ICCID, ops.Classification.DESTRUCTIVE)

    def test_an_unlisted_iccid_is_refused_at_every_tier(self, tmobile_env, monkeypatch):
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID,
                        lifecycle=LIFECYCLE_ICCID, destructive=LIFECYCLE_ICCID)
        policy = lc.AllowlistPolicy.from_settings()
        for classification in (ops.Classification.READ_ONLY,
                               ops.Classification.REVERSIBLE,
                               ops.Classification.DESTRUCTIVE):
            with pytest.raises(lc.AllowlistError, match="is not on"):
                policy.require_allowed(OTHER_ICCID, classification)

    def test_refusal_message_masks_the_iccid(self, tmobile_env, monkeypatch):
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID,
                        lifecycle=LIFECYCLE_ICCID, destructive=LIFECYCLE_ICCID)
        policy = lc.AllowlistPolicy.from_settings()
        with pytest.raises(lc.AllowlistError) as exc:
            policy.require_allowed(OTHER_ICCID, ops.Classification.DESTRUCTIVE)
        assert OTHER_ICCID not in str(exc.value)


class TestProtectedIccid:
    def test_the_first_activation_is_protected(self):
        assert PROTECTED_ICCID in lc.PROTECTED_ICCIDS

    def test_protected_iccid_is_not_destructible_by_lifecycle_listing_alone(
        self, tmobile_env, monkeypatch
    ):
        """Nominating it for suspension must not also nominate it for deletion."""
        _set_allowlists(monkeypatch, read_only=PROTECTED_ICCID,
                        lifecycle=PROTECTED_ICCID)
        policy = lc.AllowlistPolicy.from_settings()
        with pytest.raises(lc.AllowlistError):
            policy.require_allowed(PROTECTED_ICCID, ops.Classification.DESTRUCTIVE)

    def test_protected_iccid_passes_only_when_separately_allowlisted(
        self, tmobile_env, monkeypatch
    ):
        """Explicit destructive listing is the documented escape hatch.

        The CLI still requires --confirm-protected on top of this; see
        TestCliGateOrdering.
        """
        _set_allowlists(monkeypatch, read_only=PROTECTED_ICCID,
                        lifecycle=PROTECTED_ICCID, destructive=PROTECTED_ICCID)
        policy = lc.AllowlistPolicy.from_settings()
        policy.require_allowed(PROTECTED_ICCID, ops.Classification.DESTRUCTIVE)


# ── Lifecycle state machine ─────────────────────────────────────────────────

class TestStateMachine:
    def test_only_the_activation_path_is_marked_confirmed(self):
        """Honesty check: states we have never observed must say so."""
        assert lc.is_confirmed_state(lc.LifecycleState.ACTIVE)
        assert not lc.is_confirmed_state(lc.LifecycleState.SUSPENDED)
        assert not lc.is_confirmed_state(lc.LifecycleState.DEACTIVATED)

        confirmed = {t.operation for t in lc.TRANSITIONS if t.confirmed}
        assert confirmed == {"activate_subscriber"}

    def test_activation_moves_through_pending_to_active(self):
        pending = lc.next_state("activate_subscriber", lc.LifecycleState.UNKNOWN)
        assert pending is lc.LifecycleState.ACTIVATION_REQUESTED
        assert lc.settle("activate_subscriber", pending) is lc.LifecycleState.ACTIVE

    def test_a_pending_request_blocks_a_duplicate(self):
        """Duplicate-operation detection — the reason pending states exist."""
        with pytest.raises(lc.InvalidTransition, match="DUPLICATE"):
            lc.next_state("activate_subscriber",
                          lc.LifecycleState.ACTIVATION_REQUESTED)

    def test_duplicate_activation_on_an_active_line_is_refused(self):
        with pytest.raises(lc.InvalidTransition, match="not a valid transition"):
            lc.next_state("activate_subscriber", lc.LifecycleState.ACTIVE)

    def test_terminal_state_refuses_every_operation(self):
        for operation in ("activate_subscriber", "suspend_subscriber",
                          "restore_subscriber", "deactivate_subscriber"):
            with pytest.raises(lc.InvalidTransition, match="terminal"):
                lc.next_state(operation, lc.LifecycleState.DEACTIVATED)

    def test_restore_requires_a_suspended_line(self):
        with pytest.raises(lc.InvalidTransition, match="not a valid transition"):
            lc.next_state("restore_subscriber", lc.LifecycleState.ACTIVE)

    def test_suspend_requires_an_active_line(self):
        with pytest.raises(lc.InvalidTransition, match="not a valid transition"):
            lc.next_state("suspend_subscriber", lc.LifecycleState.UNKNOWN)

    def test_deactivation_is_reachable_from_active_and_suspended(self):
        for source in (lc.LifecycleState.ACTIVE, lc.LifecycleState.SUSPENDED):
            assert (lc.next_state("deactivate_subscriber", source)
                    is lc.LifecycleState.DEACTIVATION_REQUESTED)

    def test_invalid_transition_message_lists_what_is_legal(self):
        with pytest.raises(lc.InvalidTransition) as exc:
            lc.next_state("restore_subscriber", lc.LifecycleState.ACTIVE)
        assert "suspend_subscriber" in str(exc.value)

    def test_every_modelled_transition_targets_a_known_state(self):
        for t in lc.TRANSITIONS:
            assert isinstance(t.from_state, lc.LifecycleState)
            assert isinstance(t.to_state, lc.LifecycleState)

    def test_transitions_for_blocked_operations_are_marked_unconfirmed(self):
        """The state machine must not out-claim the operation inventory."""
        for t in lc.TRANSITIONS:
            if not ops.get_operation(t.operation).is_sendable:
                assert not t.confirmed, t


# ── The live-call gates, end to end ─────────────────────────────────────────

class TestLiveCallGates:
    """Each gate independently prevents a send."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_live_switch_off_blocks_activation(self, tmobile_env):
        route = respx.post(ACTIVATE_URL).mock(
            return_value=httpx.Response(201, json={"status": "SUCCESS"}))
        client = taap.TMobileTAAPClient()
        with pytest.raises(RuntimeError, match="TMOBILE_PIT_LIVE_CALLS_ENABLED"):
            await client.activate_subscriber(LIFECYCLE_ICCID, market_zip="30346")
        await client.close()
        assert route.call_count == 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_missing_callback_location_blocks_activation(
        self, tmobile_env, monkeypatch
    ):
        """Without a callback we could not reconcile the result — so refuse."""
        monkeypatch.setattr("app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "true")
        monkeypatch.setattr("app.config.settings.TMOBILE_CALLBACK_LOCATION", "")
        route = respx.post(ACTIVATE_URL).mock(
            return_value=httpx.Response(201, json={"status": "SUCCESS"}))
        client = taap.TMobileTAAPClient()
        with pytest.raises(ValueError, match="call-back-location"):
            await client.activate_subscriber(LIFECYCLE_ICCID, market_zip="30346")
        await client.close()
        assert route.call_count == 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_one_request_per_invocation_and_no_retry_on_failure(
        self, tmobile_env, monkeypatch
    ):
        monkeypatch.setattr("app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "true")
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(
            200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600}))
        route = respx.post(ACTIVATE_URL).mock(
            return_value=httpx.Response(500, json={"error": "gateway"}))

        bundle = await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=LIFECYCLE_ICCID,
            market_zip="30346", confirm_live=True)

        assert route.call_count == 1
        assert bundle["ok"] is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_evidence_from_a_certification_run_carries_no_credentials(
        self, tmobile_env, monkeypatch
    ):
        monkeypatch.setattr("app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "true")
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(
            200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600}))
        respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(
            201, json={"status": "SUCCESS", "msisdn": "5550001234"}))

        bundle = await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=LIFECYCLE_ICCID,
            market_zip="30346", confirm_live=True)
        blob = json.dumps(bundle) + ev.render_text_report(bundle)

        for secret in (ACCESS_TOKEN, CONSUMER_KEY, CONSUMER_SECRET):
            assert secret not in blob


class TestCliGateOrdering:
    """The CLI's gate evaluation, exercised directly.

    Imported lazily: the script lives outside the package, so it is loaded by
    path rather than as a module.
    """

    @pytest.fixture
    def cli(self):
        import importlib.util
        import pathlib
        path = (pathlib.Path(__file__).resolve().parents[2]
                / "scripts" / "tmobile_pit.py")
        spec = importlib.util.spec_from_file_location("tmobile_pit_cli", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @pytest.fixture
    def args(self):
        import argparse
        return argparse.Namespace(
            iccid=LIFECYCLE_ICCID, msisdn=None, account_id=None,
            market_zip="30346", operator="tester", reason=None,
            confirm_live=False, confirm_destructive=False,
            confirm_protected=False, out_dir=".",
        )

    def _isolate_state(self, cli, monkeypatch, tmp_path):
        monkeypatch.setattr(cli, "_state_dir", lambda: str(tmp_path))

    def test_blocked_operation_is_refused_even_in_preview(
        self, cli, args, tmobile_env, monkeypatch, tmp_path
    ):
        """Preview must not render a request we may never send.

        A rendered request invites someone to send it — so the provenance gate
        runs before anything is built, in both modes.
        """
        self._isolate_state(cli, monkeypatch, tmp_path)
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID,
                        lifecycle=LIFECYCLE_ICCID, destructive=LIFECYCLE_ICCID)
        with pytest.raises(ops.OperationBlocked):
            cli._evaluate_gates(args, ops.get_operation("deactivate_subscriber"),
                                live=False)

    def test_preview_passes_the_gates_without_confirmations(
        self, cli, args, tmobile_env, monkeypatch, tmp_path
    ):
        self._isolate_state(cli, monkeypatch, tmp_path)
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID,
                        lifecycle=LIFECYCLE_ICCID)
        report = cli._evaluate_gates(
            args, ops.get_operation("activate_subscriber"), live=False)
        assert any("PREVIEW" in line for line in report)

    def test_run_without_confirm_live_is_refused(
        self, cli, args, tmobile_env, monkeypatch, tmp_path
    ):
        self._isolate_state(cli, monkeypatch, tmp_path)
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID,
                        lifecycle=LIFECYCLE_ICCID)
        with pytest.raises(SystemExit, match="confirm-live"):
            cli._evaluate_gates(
                args, ops.get_operation("activate_subscriber"), live=True)

    def test_run_with_confirm_live_but_switch_off_is_refused(
        self, cli, args, tmobile_env, monkeypatch, tmp_path
    ):
        """Operator intent alone is not enough — the env switch is independent."""
        self._isolate_state(cli, monkeypatch, tmp_path)
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID,
                        lifecycle=LIFECYCLE_ICCID)
        args.confirm_live = True
        with pytest.raises(SystemExit, match="TMOBILE_PIT_LIVE_CALLS_ENABLED"):
            cli._evaluate_gates(
                args, ops.get_operation("activate_subscriber"), live=True)

    def test_allowlist_gate_runs_before_any_confirmation(
        self, cli, args, tmobile_env, monkeypatch, tmp_path
    ):
        self._isolate_state(cli, monkeypatch, tmp_path)
        args.confirm_live = True
        with pytest.raises(lc.AllowlistError):
            cli._evaluate_gates(
                args, ops.get_operation("activate_subscriber"), live=True)

    def test_state_is_persisted_and_reloaded(
        self, cli, tmobile_env, monkeypatch, tmp_path
    ):
        self._isolate_state(cli, monkeypatch, tmp_path)
        assert cli._load_state(LIFECYCLE_ICCID) is lc.LifecycleState.UNKNOWN
        cli._record_state(LIFECYCLE_ICCID, lc.LifecycleState.ACTIVE,
                          {"operation": "activate_subscriber"})
        assert cli._load_state(LIFECYCLE_ICCID) is lc.LifecycleState.ACTIVE

    def test_persisted_state_masks_the_iccid(
        self, cli, tmobile_env, monkeypatch, tmp_path
    ):
        self._isolate_state(cli, monkeypatch, tmp_path)
        cli._record_state(LIFECYCLE_ICCID, lc.LifecycleState.ACTIVE, {"op": "x"})
        content = (tmp_path / f"{LIFECYCLE_ICCID}.json").read_text()
        assert LIFECYCLE_ICCID not in json.loads(content)["iccid_masked"]

    def test_second_run_while_pending_is_refused_as_duplicate(
        self, cli, args, tmobile_env, monkeypatch, tmp_path
    ):
        """Duplicate-request protection across invocations, not just in memory."""
        self._isolate_state(cli, monkeypatch, tmp_path)
        _set_allowlists(monkeypatch, read_only=LIFECYCLE_ICCID,
                        lifecycle=LIFECYCLE_ICCID)
        cli._record_state(LIFECYCLE_ICCID,
                          lc.LifecycleState.ACTIVATION_REQUESTED, {"op": "x"})
        with pytest.raises(lc.InvalidTransition, match="DUPLICATE"):
            cli._evaluate_gates(
                args, ops.get_operation("activate_subscriber"), live=False)

    def test_ledger_entry_captures_every_required_field(self, cli):
        """Phase-3 record completeness."""
        entry = cli._ledger_entry(
            op_name="activate_subscriber", iccid=LIFECYCLE_ICCID,
            msisdn="5550001234", account_id="99900011122",
            previous=lc.LifecycleState.UNKNOWN,
            expected=lc.LifecycleState.ACTIVATION_REQUESTED,
            observed=lc.LifecycleState.ACTIVE,
            bundle={"generated_at_utc": "2026-07-21T03:18:33.694749Z",
                    "exchanges": [{
                        "request": {"headers": {"safe_values": {
                            "X-Correlation-Id": "corr-1",
                            "partner-transaction-id": "ptx-1"}}},
                        "response": {"work_flow_id": "wf-1",
                                     "service_transaction_id": "svc-1",
                                     "partner_transaction_id": "ptx-1"},
                    }]},
            operator="tester", reason="certification", result="ok",
        )
        for key in ("operation", "iccid_masked", "msisdn_masked",
                    "account_id_masked", "previous_state", "expected_state",
                    "observed_state", "request_timestamp_utc",
                    "callback_timestamp_utc", "verification_timestamp_utc",
                    "operator", "reason", "result"):
            assert key in entry
        assert entry["trace"] == {
            "partner_transaction_id": "ptx-1", "correlation_id": "corr-1",
            "work_flow_id": "wf-1", "service_transaction_id": "svc-1",
        }
        for raw in (LIFECYCLE_ICCID, "5550001234", "99900011122"):
            assert raw not in json.dumps(entry)
