"""Cover for the single-run PIT authorization and the SubscriberInquiry path.

The authorization here is the only way past the operation registry's block, so
its narrowness is the whole safety argument. These tests pin that it covers one
read-only operation, one nominated subscriber, one request, in PIT, and that it
destroys itself on use — and that every failure mode falls through to the normal
refusal rather than widening access.

**No live request has been made.** SubscriberInquiry remains blocked and
mock-certified; nothing here advances a readiness state.
"""

from __future__ import annotations

import json
import pathlib
from datetime import timedelta

import httpx
import pytest
import respx

import app.integrations.tmobile_contracts as C
import app.integrations.tmobile_operations as OPS
import app.integrations.tmobile_pit_authorization as AUTH
import app.integrations.tmobile_snapshot as SNAP
import app.integrations.tmobile_taap as taap

FIXTURE = json.loads(
    (pathlib.Path(__file__).parent / "fixtures"
     / "tmobile_subscriber_inquiry_shapes.json").read_text(encoding="utf-8"))

NOMINATED = "8901260963132600001"      # fabricated designated test SIM
OTHER = "8901260963132600002"          # fabricated, never nominated


@pytest.fixture(autouse=True)
def _no_leftover_grant():
    """A grant must never leak between tests — or between operator commands."""
    AUTH.clear_authorization()
    yield
    AUTH.clear_authorization()


@pytest.fixture
def pit_env(monkeypatch):
    monkeypatch.setattr("app.config.settings.TMOBILE_ENV", "pit")


def _grant(**over):
    kwargs = dict(operation="subscriber_inquiry", selector_type="iccid",
                  selector=NOMINATED, operator="reviewer", confirmed=True)
    kwargs.update(over)
    return AUTH.grant_single_run(**kwargs)


def _blocked(operation: str) -> bool:
    try:
        OPS.require_live_sendable(operation)
        return False
    except OPS.TMobileOperationBlockedError:
        return True


class TestAuthorizationNarrowness:
    def test_inquiry_is_blocked_without_a_grant(self, pit_env):
        assert _blocked("subscriber_inquiry")

    def test_a_grant_permits_exactly_one_request(self, pit_env):
        _grant()
        assert not _blocked("subscriber_inquiry")   # first: allowed
        assert _blocked("subscriber_inquiry")       # second: consumed

    def test_a_grant_covers_only_its_own_operation(self, pit_env):
        _grant()
        assert _blocked("query_network")
        assert _blocked("query_usage")
        assert _blocked("query_transaction_status")

    @pytest.mark.parametrize("operation", [
        "suspend_subscriber", "restore_subscriber",
        "change_sim", "deactivate_subscriber",
    ])
    def test_no_lifecycle_mutation_can_ever_be_granted(self, pit_env, operation):
        """The escape hatch must not reach a mutation, by construction."""
        assert operation not in AUTH.AUTHORIZABLE_OPERATIONS
        with pytest.raises(AUTH.AuthorizationError, match="read-only"):
            _grant(operation=operation)

    def test_mutations_stay_blocked_while_a_grant_is_active(self, pit_env):
        _grant()
        for operation in ("suspend_subscriber", "restore_subscriber",
                          "change_sim", "deactivate_subscriber"):
            assert _blocked(operation), operation

    def test_grant_refused_outside_pit(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.TMOBILE_ENV", "prod")
        with pytest.raises(AUTH.AuthorizationError, match="not PIT"):
            _grant()

    def test_an_active_grant_is_inert_outside_pit(self, pit_env, monkeypatch):
        """Environment is re-checked at use, not only at grant time."""
        _grant()
        monkeypatch.setattr("app.config.settings.TMOBILE_ENV", "prod")
        assert _blocked("subscriber_inquiry")

    def test_expired_grant_does_not_authorize(self, pit_env):
        _grant(ttl=timedelta(seconds=-1))
        assert _blocked("subscriber_inquiry")

    def test_subscriber_must_be_explicitly_nominated(self, pit_env):
        with pytest.raises(AUTH.AuthorizationError, match="explicitly nominated"):
            _grant(selector="")

    def test_operator_identity_and_confirmation_are_required(self, pit_env):
        with pytest.raises(AUTH.AuthorizationError):
            _grant(operator="")
        with pytest.raises(AUTH.AuthorizationError):
            _grant(confirmed=False)

    def test_grant_pins_the_exact_subscriber(self, pit_env):
        auth = _grant()
        assert auth.matches_selector(NOMINATED)
        assert not auth.matches_selector(OTHER)

    def test_audit_record_carries_no_reversible_identifier(self, pit_env):
        record = _grant().audit_record()
        blob = json.dumps(record)
        assert NOMINATED not in blob
        assert record["selector_masked"].endswith("0001")
        assert record["operator"] == "reviewer"
        assert record["environment"] == "pit"

    def test_double_consume_raises(self, pit_env):
        auth = _grant()
        auth.consume("subscriber_inquiry")
        with pytest.raises(AUTH.AuthorizationError, match="already consumed"):
            auth.consume("subscriber_inquiry")

    def test_clearing_removes_the_grant(self, pit_env):
        _grant()
        AUTH.clear_authorization()
        assert _blocked("subscriber_inquiry")


class TestPreflightMakesNoNetworkCall:
    """Preview and every refusal path must cost zero requests."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_blocked_inquiry_never_reaches_oauth_or_the_wire(
        self, pit_env, monkeypatch
    ):
        route = respx.route().mock(return_value=httpx.Response(200, json={}))

        async def boom(self):
            raise AssertionError("OAuth was reached for a blocked operation")

        monkeypatch.setattr(taap.TMobileTAAPClient, "get_access_token", boom)
        client = taap.TMobileTAAPClient()
        with pytest.raises(OPS.TMobileOperationBlockedError):
            await client.subscriber_inquiry(iccid=NOMINATED)
        assert route.call_count == 0

    def test_building_the_request_opens_no_connection(self, pit_env):
        request = C.SubscriberInquiryRequest(iccid=NOMINATED)
        assert request.to_wire() == {"iccid": NOMINATED}
        assert request.path == "/wholesale/v1/subscriber/profile"
        assert request.http_method == "POST"

    def test_invalid_request_fails_before_any_authorization_is_spent(self, pit_env):
        _grant()
        with pytest.raises(C.TMobileRequestError):
            C.SubscriberInquiryRequest()          # no identifier
        # The grant is untouched: validation happens first.
        assert not _blocked("subscriber_inquiry")


class TestResponseShapes:
    """Parsing cover for the shapes SubscriberInquiry is expected to return.

    Fabricated from the typed contract — **not** from an observed live response,
    because no live inquiry has been run. When the first real response arrives,
    reconcile it against these and correct here if the wire disagrees.
    """

    def _env(self, name):
        f = FIXTURE["fixtures"][name]
        return C.TMobileResponseEnvelope.from_payload(
            f["body"], operation="subscriber_inquiry",
            kind=C.ResponseKind.SYNCHRONOUS, http_status=f["http_status"],
            headers=f.get("headers", {}))

    def test_active_subscriber_parses(self):
        env = self._env("active_subscriber")
        assert env.normalized_status is C.NormalizedStatus.SUCCESS
        assert env.subscriber_status_raw == "ACTIVE"
        assert env.accepted is True

    def test_suspended_subscriber_parses(self):
        env = self._env("suspended_subscriber")
        assert env.subscriber_status_raw == "SUSPENDED"

    def test_sim_network_type_present(self):
        assert self._env("with_sim_network_type").sim_network_type == "FABRICATED_NET_A"

    def test_sim_network_type_absent_is_valid(self):
        assert self._env("active_subscriber").sim_network_type is None

    def test_unknown_fields_are_preserved(self):
        env = self._env("with_unknown_field")
        assert "someFutureAttribute" in env.raw_extra_fields

    def test_failure_shape_classifies_without_vendor_prose(self):
        env = self._env("validation_failure")
        assert env.normalized_status is C.NormalizedStatus.FAILURE
        assert env.accepted is False
        assert env.disposition in ("correct_request_then_resubmit",
                                   "unknown_manual_review")

    def test_inquiry_builds_a_carrier_snapshot(self):
        snap = SNAP.TMobileCarrierSnapshot.from_envelope(
            self._env("with_sim_network_type"), tenant_id="t1")
        assert snap.carrier == "tmobile"
        assert snap.source_operation == "subscriber_inquiry"
        assert snap.iccid_masked and NOMINATED not in str(snap.iccid_masked)

    def test_inquiry_does_not_mutate_lifecycle_state(self):
        """A read must never move the line, whatever it reports."""
        import app.integrations.tmobile_state as ST

        state = ST.TMobileSubscriberState(
            workflow_state=ST.LifecycleState.ACTIVE, confidence="confirmed")
        before = (state.workflow_state, state.confidence, state.pending_operation)
        SNAP.TMobileCarrierSnapshot.from_envelope(self._env("suspended_subscriber"))
        assert (state.workflow_state, state.confidence,
                state.pending_operation) == before

    def test_fixture_contains_no_live_identifier(self):
        blob = json.dumps(FIXTURE)
        for label, banned in (("live PIT ICCID", "89012609631" + "32697538"),
                              ("assigned MSISDN", "410240" + "6851"),
                              ("generated account id", "104107" + "63214")):
            if banned in blob:
                pytest.fail(f"fixture contains the {label} (value redacted)")


class TestReadinessUnchanged:
    def test_subscriber_inquiry_has_not_been_certified(self):
        """No live run has happened, so nothing may claim otherwise."""
        op = OPS.get_operation("subscriber_inquiry")
        assert op.readiness is OPS.ReadinessState.MOCK_CERTIFIED
        assert not op.is_sendable

    def test_activation_remains_the_sole_generally_sendable_operation(self):
        assert [o.name for o in OPS.sendable_operations()] == ["activate_subscriber"]
        assert len(OPS.blocked_operations()) == 8
