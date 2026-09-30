"""The policy matrix: certification maturity is NOT send authorization.

These two questions had one answer, and that was a live-fire hazard:

* *how far has this operation been certified?* — :class:`ReadinessState`
* *may we transmit it right now?* — :class:`SendAuthorization`

Because ``LIVE_SENDABLE_READINESS`` contained ``PIT_TESTED``, promoting an
operation on the strength of one successful **controlled** PIT run would have
silently converted it from "needs an explicit one-shot key" into "send freely" —
one certified call buying unlimited uncertified ones. Nobody would have had to
decide that; it would simply have happened as a side effect of recording the
truth about a test.

The two axes are now independent, and this file is the proof. The invariant that
matters most is stated in :class:`TestMaturityNeverGrants`: **maturity can veto a
send and can never grant one.** Authorization is always an explicit, reviewed,
per-operation declaration.

Nothing here contacts a carrier. Every identifier is fabricated.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

import app.integrations.tmobile_operations as OPS
import app.integrations.tmobile_pit_authorization as AUTH
from app.integrations.tmobile_operations import (
    Classification,
    Provenance,
    ReadinessState,
    SendAuthorization,
)

# Fabricated. Never a real PIT identifier.
NOMINATED = "8901260963132600001"
OTHER = "8901260963132600002"

#: The canonical maturity ladder. There is exactly one, and these tests must
#: not be read as defining a second.
CANONICAL_LADDER = (
    ReadinessState.MOCK_CERTIFIED,
    ReadinessState.PIT_TESTED,
    ReadinessState.PRODUCTION_APPROVED,
)


@pytest.fixture(autouse=True)
def _clean_grants():
    AUTH.clear_authorization()
    yield
    AUTH.clear_authorization()


@pytest.fixture
def pit_env(monkeypatch):
    monkeypatch.setattr("app.config.settings.TMOBILE_ENV", "pit")


def probe(**overrides) -> OPS.Operation:
    """A synthetic operation for varying exactly one policy term at a time."""
    kwargs = dict(
        name="probe", client_method="c", http_method="POST", path="/probe",
        path_source="s", classification=Classification.READ_ONLY,
        provenance=Provenance.VENDOR_DOCUMENTED,
        request_schema="r", response_schema="r", callback_behavior="c",
        required_headers=("Authorization",), pop_ehts="e", body_signed=True,
        synchronous="s", reversibility="r", prerequisite_state="p",
        pit_restrictions="p", implementation_status="i", test_status="t",
    )
    kwargs.update(overrides)
    return OPS.Operation(**kwargs)


def grant(operation, selector=NOMINATED, selector_type="iccid"):
    return AUTH.grant_single_run(
        operation=operation, selector_type=selector_type, selector=selector,
        operator="reviewer", confirmed=True)


def boundary_allows(operation: str) -> bool:
    """Does the CLIENT boundary let this through — grant or otherwise?"""
    try:
        OPS.require_live_sendable(operation)
        return True
    except OPS.TMobileOperationBlockedError:
        return False


# ── The central invariant ───────────────────────────────────────────────────

class TestMaturityNeverGrants:
    @pytest.mark.parametrize("state", list(ReadinessState))
    def test_no_maturity_makes_an_undeclared_operation_sendable(self, state):
        """Every state on the ladder, with no authorization: still shut."""
        assert not probe(readiness=state).is_sendable

    @pytest.mark.parametrize("state", CANONICAL_LADDER)
    def test_advancing_maturity_cannot_change_authorization(self, state):
        """The exact regression this file exists for.

        A SINGLE_RUN_ONLY operation stays single-run at every maturity — being
        certified never graduates it to sending freely.
        """
        op = probe(readiness=state,
                   send_authorization=SendAuthorization.SINGLE_RUN_ONLY)
        assert not op.is_sendable
        assert op.is_single_run_certifiable

    def test_maturity_can_still_veto(self):
        """Necessary, never sufficient — and it works in the shutting direction."""
        low = probe(readiness=ReadinessState.MOCK_CERTIFIED,
                    send_authorization=SendAuthorization.OPERATOR_HARNESS_ONLY)
        high = probe(readiness=ReadinessState.PIT_TESTED,
                     send_authorization=SendAuthorization.OPERATOR_HARNESS_ONLY)
        assert not low.is_sendable
        assert high.is_sendable


# ── 1-6. The maturity × authorization matrix ────────────────────────────────

class TestPolicyMatrix:
    def test_1_mock_certified_general_send_denied(self):
        assert not probe(readiness=ReadinessState.MOCK_CERTIFIED).is_sendable

    def test_2_mock_certified_with_a_grant_allows_one_request(self, pit_env):
        """query_usage is genuinely MOCK_CERTIFIED and genuinely grantable.
        (query_network held this role until it was PIT certified 2026-09-30.)"""
        op = OPS.get_operation("query_usage")
        assert op.readiness is ReadinessState.MOCK_CERTIFIED
        assert not boundary_allows("query_usage")

        grant("query_usage")
        assert boundary_allows("query_usage")

    def test_3_pit_tested_general_send_denied(self):
        """Being live PIT certified authorizes nothing by itself."""
        op = OPS.get_operation("subscriber_inquiry")
        assert op.readiness is ReadinessState.PIT_TESTED
        assert not op.is_sendable
        assert not boundary_allows("subscriber_inquiry")

    def test_4_pit_tested_with_a_grant_allows_one_controlled_request(self, pit_env):
        """Certification does not end eligibility for further controlled runs."""
        grant("subscriber_inquiry")
        assert boundary_allows("subscriber_inquiry")

    def test_5_production_approved_satisfies_the_readiness_component(self):
        op = probe(readiness=ReadinessState.PRODUCTION_APPROVED,
                   send_authorization=SendAuthorization.PRODUCTION)
        assert op.is_sendable

    @pytest.mark.parametrize("failing_gate,overrides", [
        ("provenance", {"provenance": Provenance.DERIVED_UNCONFIRMED}),
        ("classification", {"classification": Classification.UNKNOWN}),
        ("certification blocker", {"certification_blockers": ("unanswered",)}),
        ("no authorization", {"send_authorization": SendAuthorization.NONE}),
        ("single-run only", {"send_authorization":
                             SendAuthorization.SINGLE_RUN_ONLY}),
    ])
    def test_6_production_approved_is_not_a_master_bypass(
        self, failing_gate, overrides
    ):
        """The top of the ladder overrides nothing. Every other gate still bites."""
        kwargs = dict(readiness=ReadinessState.PRODUCTION_APPROVED,
                      send_authorization=SendAuthorization.PRODUCTION)
        kwargs.update(overrides)
        assert not probe(**kwargs).is_sendable, failing_gate

    def test_production_authorization_below_the_top_is_rejected_at_import(self):
        """The declaration itself is invalid, not merely inert."""
        for state in ReadinessState:
            op = probe(readiness=state,
                       send_authorization=SendAuthorization.PRODUCTION)
            assert op.is_sendable is (state is ReadinessState.PRODUCTION_APPROVED)


# ── 7-8. Blockers outrank everything ────────────────────────────────────────

class TestCertificationBlockersOutrank:
    @pytest.mark.parametrize("state", CANONICAL_LADDER)
    @pytest.mark.parametrize("auth", list(SendAuthorization))
    def test_7_a_blocker_shuts_the_operation_at_any_maturity_or_route(
        self, state, auth
    ):
        assert not probe(readiness=state, send_authorization=auth,
                         certification_blockers=("unanswered",)).is_sendable

    def test_7b_a_blocker_also_denies_the_certification_grant(self, pit_env):
        blocked = [op for op in OPS.OPERATIONS if op.certification_blockers]
        assert blocked, "the policy is untested if nothing carries a blocker"
        for op in blocked:
            with pytest.raises(AUTH.AuthorizationError,
                               match="unanswered carrier question"):
                grant(op.name, selector="PIT-TXN-FABRICATED",
                      selector_type=AUTH.TRANSACTION_SELECTOR
                      if op.name == "query_transaction_status" else "iccid")

    def test_8_query_transaction_status_stays_denied(self, pit_env):
        """transactionId semantics are unresolved; nothing may send it."""
        op = OPS.get_operation("query_transaction_status")
        assert op.certification_blockers
        assert not op.is_sendable
        assert not op.is_single_run_certifiable
        assert not boundary_allows("query_transaction_status")

        with pytest.raises(AUTH.AuthorizationError,
                           match="unanswered carrier question"):
            grant("query_transaction_status", selector="PIT-TXN-FABRICATED",
                  selector_type=AUTH.TRANSACTION_SELECTOR)

    def test_the_blocker_refusal_names_the_blocker_not_the_route(self, pit_env):
        """An operator told the wrong reason fixes the wrong thing."""
        with pytest.raises(OPS.TMobileOperationBlockedError) as exc:
            OPS.require_live_sendable("query_transaction_status")
        assert "blocking gate    : certification blocker" in str(exc.value)


# ── 9-11. The registry's actual state ───────────────────────────────────────

class TestRegistryState:
    def test_9_query_network(self, pit_env):
        """Live PIT certified 2026-09-30. Still not generally sendable. Still
        grantable - and only by a one-shot grant."""
        op = OPS.get_operation("query_network")
        assert op.readiness is ReadinessState.PIT_TESTED
        assert op.send_authorization is SendAuthorization.SINGLE_RUN_ONLY
        assert not op.is_sendable
        assert op.is_single_run_certifiable

    def test_10_query_usage(self, pit_env):
        op = OPS.get_operation("query_usage")
        assert op.readiness is ReadinessState.MOCK_CERTIFIED
        assert not op.is_sendable
        assert op.is_single_run_certifiable

    def test_11_subscriber_inquiry(self, pit_env):
        """Live PIT certified. Still not generally sendable. Still grantable."""
        op = OPS.get_operation("subscriber_inquiry")
        assert op.readiness is ReadinessState.PIT_TESTED
        assert op.send_authorization is SendAuthorization.SINGLE_RUN_ONLY
        assert not op.is_sendable
        assert op.is_single_run_certifiable

    def test_activation_authorization_is_unchanged_and_now_explicit(self):
        """Its policy was preserved, not broadened — and no longer inferred."""
        op = OPS.get_operation("activate_subscriber")
        assert op.readiness is ReadinessState.PIT_TESTED
        assert op.send_authorization is SendAuthorization.OPERATOR_HARNESS_ONLY
        assert op.is_sendable
        # Harness-only is NOT ordinary application-path sendability.
        assert op.send_authorization is not SendAuthorization.PRODUCTION
        # And it is not reachable through the read-only grant path.
        assert not op.is_single_run_certifiable

    def test_activation_is_still_the_only_generally_sendable_operation(self):
        assert [o.name for o in OPS.sendable_operations()] == [
            "activate_subscriber"]

    def test_exactly_the_three_reads_are_grant_eligible(self):
        assert [o.name for o in OPS.single_run_certifiable_operations()] == [
            "subscriber_inquiry", "query_network", "query_usage"]

    @pytest.mark.parametrize("operation", [
        "suspend_subscriber", "restore_subscriber", "change_sim",
        "deactivate_subscriber",
    ])
    def test_no_mutation_declares_any_send_authorization(self, operation):
        op = OPS.get_operation(operation)
        assert op.send_authorization is SendAuthorization.NONE
        assert not op.is_sendable
        assert not op.is_single_run_certifiable

    def test_destructive_operations_may_never_declare_authorization(self):
        for op in OPS.OPERATIONS:
            if op.classification is Classification.DESTRUCTIVE:
                assert op.send_authorization is SendAuthorization.NONE, op.name


# ── 12-14. Grant mechanics survive the split ────────────────────────────────

class TestGrantMechanicsUnchanged:
    @pytest.mark.parametrize("operation", [
        "subscriber_inquiry", "query_network", "query_usage"])
    def test_12_a_grant_is_consumed_after_exactly_one_request(
        self, pit_env, operation
    ):
        grant(operation)
        assert boundary_allows(operation)
        assert not boundary_allows(operation)

    def test_13_an_expired_grant_is_denied(self, pit_env):
        AUTH.grant_single_run(
            operation="query_network", selector_type="iccid",
            selector=NOMINATED, operator="reviewer", confirmed=True,
            ttl=timedelta(seconds=-1))
        assert not boundary_allows("query_network")

    def test_13b_a_reused_grant_is_denied(self, pit_env):
        auth = grant("query_network")
        auth.consume("query_network")
        with pytest.raises(AUTH.AuthorizationError, match="already consumed"):
            auth.consume("query_network")

    def test_14_a_grant_does_not_cover_another_operation(self, pit_env):
        grant("query_network")
        assert not boundary_allows("query_usage")
        assert not boundary_allows("subscriber_inquiry")

    def test_14b_a_grant_pins_the_exact_target(self, pit_env):
        auth = grant("query_network", selector=NOMINATED)
        assert auth.matches_selector(NOMINATED)
        assert not auth.matches_selector(OTHER)

    def test_a_grant_outside_pit_is_refused(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.TMOBILE_ENV", "production")
        with pytest.raises(AUTH.AuthorizationError, match="not PIT"):
            grant("query_network")

    def test_an_unconfirmed_grant_is_refused(self, pit_env):
        with pytest.raises(AUTH.AuthorizationError, match="confirmation"):
            AUTH.grant_single_run(
                operation="query_network", selector_type="iccid",
                selector=NOMINATED, operator="reviewer", confirmed=False)

    def test_the_hard_floor_and_the_registry_must_both_permit_it(self, pit_env):
        """Two independent checks: neither edit alone can widen access."""
        for operation in OPS.single_run_certifiable_operations():
            assert operation.name in AUTH.AUTHORIZABLE_OPERATIONS
        for name in AUTH.AUTHORIZABLE_OPERATIONS:
            assert OPS.get_operation(name).classification is Classification.READ_ONLY


# ── Terminology ─────────────────────────────────────────────────────────────

class TestTerminology:
    def test_the_registry_never_equates_pit_tested_with_production(self):
        for op in OPS.OPERATIONS:
            if op.readiness is ReadinessState.PIT_TESTED:
                assert op.send_authorization is not SendAuthorization.PRODUCTION

    def test_the_refusal_explains_the_separation(self, pit_env):
        with pytest.raises(OPS.TMobileOperationBlockedError) as exc:
            OPS.require_live_sendable("subscriber_inquiry")
        message = str(exc.value)
        assert "one-shot PIT grant" in message
        assert "not generally sendable" in message
        assert "advancing its maturity will not make it so" in message
