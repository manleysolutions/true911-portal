"""Cover for the four read-only certification operations.

The certification sprint runs SubscriberInquiry, QueryNetwork,
QuerySubscriberUsage and QueryTransactionStatus once each. What matters here is
that each is independently gated: a grant for one must never be spendable on
another, and a grant for one subscriber must never be spendable on another.

**No live request has been made.** All four remain blocked and mock-certified.
"""

from __future__ import annotations

import importlib.util
import pathlib

import httpx
import pytest
import respx

import app.integrations.tmobile_contracts as C
import app.integrations.tmobile_operations as OPS
import app.integrations.tmobile_pit_authorization as AUTH
import app.integrations.tmobile_taap as taap

READ_ONLY = ("subscriber_inquiry", "query_network",
             "query_usage", "query_transaction_status")
SUBSCRIBER_OPS = READ_ONLY[:3]

NOMINATED = "8901260963132600001"      # fabricated
OTHER = "8901260963132600002"          # fabricated, never nominated
TXN = "PIT-TXN-FABRICATED-0001"        # fabricated
OTHER_TXN = "PIT-TXN-FABRICATED-0002"  # fabricated


@pytest.fixture(autouse=True)
def _clean_grants():
    AUTH.clear_authorization()
    yield
    AUTH.clear_authorization()


@pytest.fixture
def pit_env(monkeypatch):
    monkeypatch.setattr("app.config.settings.TMOBILE_ENV", "pit")


@pytest.fixture(scope="module")
def cli():
    path = (pathlib.Path(__file__).resolve().parents[2]
            / "scripts" / "tmobile_pit.py")
    spec = importlib.util.spec_from_file_location("tmobile_pit_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _blocked(operation: str) -> bool:
    try:
        OPS.require_live_sendable(operation)
        return False
    except OPS.TMobileOperationBlockedError:
        return True


def _grant(operation, selector, selector_type="iccid"):
    return AUTH.grant_single_run(
        operation=operation, selector_type=selector_type, selector=selector,
        operator="reviewer", confirmed=True)


class TestPerOperationIsolation:
    @pytest.mark.parametrize("operation", READ_ONLY)
    def test_each_is_blocked_without_its_own_grant(self, pit_env, operation):
        assert _blocked(operation)

    @pytest.mark.parametrize("granted", SUBSCRIBER_OPS)
    def test_a_grant_authorizes_only_its_own_operation(self, pit_env, granted):
        """The core isolation property: one grant, one operation."""
        _grant(granted, NOMINATED)
        for other in READ_ONLY:
            if other == granted:
                continue
            assert _blocked(other), f"{granted} grant leaked to {other}"

    def test_inquiry_grant_does_not_authorize_query_network(self, pit_env):
        _grant("subscriber_inquiry", NOMINATED)
        assert _blocked("query_network")

    def test_network_grant_does_not_authorize_usage(self, pit_env):
        _grant("query_network", NOMINATED)
        assert _blocked("query_usage")

    @pytest.mark.parametrize("operation", SUBSCRIBER_OPS)
    def test_each_grant_is_single_use(self, pit_env, operation):
        _grant(operation, NOMINATED)
        assert not _blocked(operation)
        assert _blocked(operation)

    @pytest.mark.parametrize("operation", SUBSCRIBER_OPS)
    def test_grant_pins_the_exact_subscriber(self, pit_env, operation):
        auth = _grant(operation, NOMINATED)
        assert auth.matches_selector(NOMINATED)
        assert not auth.matches_selector(OTHER)


class TestTransactionStatusBinding:
    def test_binds_to_an_exact_transaction_id(self, pit_env):
        auth = _grant("query_transaction_status", TXN,
                      selector_type=AUTH.TRANSACTION_SELECTOR)
        assert auth.matches_selector(TXN)
        assert not auth.matches_selector(OTHER_TXN)

    def test_refuses_a_subscriber_selector(self, pit_env):
        """There is no 'latest transaction', and no subscriber-scoped lookup."""
        with pytest.raises(AUTH.AuthorizationError, match="exact transaction id"):
            _grant("query_transaction_status", NOMINATED, selector_type="iccid")

    def test_a_transaction_grant_covers_nothing_else(self, pit_env):
        with pytest.raises(AUTH.AuthorizationError):
            _grant("subscriber_inquiry", TXN,
                   selector_type=AUTH.TRANSACTION_SELECTOR)

    def test_request_model_requires_an_explicit_id(self):
        with pytest.raises(C.TMobileRequestError):
            C.QueryTransactionStatusRequest(transactionId="   ")


class TestMutationsRemainUnreachable:
    @pytest.mark.parametrize("operation", [
        "suspend_subscriber", "restore_subscriber",
        "change_sim", "deactivate_subscriber",
    ])
    def test_never_authorizable(self, pit_env, operation):
        assert operation not in AUTH.AUTHORIZABLE_OPERATIONS
        with pytest.raises(AUTH.AuthorizationError, match="read-only"):
            _grant(operation, NOMINATED)

    @pytest.mark.parametrize("operation", [
        "suspend_subscriber", "restore_subscriber",
        "change_sim", "deactivate_subscriber",
    ])
    def test_stay_blocked_while_a_read_grant_is_active(self, pit_env, operation):
        _grant("subscriber_inquiry", NOMINATED)
        assert _blocked(operation)


class TestPreviewMakesNoNetworkCall:
    @respx.mock
    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation,kwargs", [
        ("subscriber_inquiry", {"iccid": NOMINATED}),
        ("query_network", {"iccid": NOMINATED}),
        ("query_usage", {"iccid": NOMINATED}),
        ("query_transaction_status", {"transaction_id": TXN}),
    ])
    async def test_blocked_operation_reaches_neither_oauth_nor_the_wire(
        self, pit_env, monkeypatch, operation, kwargs
    ):
        route = respx.route().mock(return_value=httpx.Response(200, json={}))

        async def boom(self):
            raise AssertionError("OAuth reached for a blocked operation")

        monkeypatch.setattr(taap.TMobileTAAPClient, "get_access_token", boom)
        client = taap.TMobileTAAPClient()
        with pytest.raises(OPS.TMobileOperationBlockedError):
            await getattr(client, operation)(**kwargs)
        assert route.call_count == 0

    @pytest.mark.parametrize("operation", READ_ONLY)
    def test_request_construction_opens_no_connection(self, operation):
        spec = {"subscriber_inquiry": C.SubscriberInquiryRequest,
                "query_network": C.QueryNetworkRequest,
                "query_usage": C.QuerySubscriberUsageRequest,
                "query_transaction_status": C.QueryTransactionStatusRequest}[operation]
        kwargs = ({"transaction_id": TXN} if operation == "query_transaction_status"
                  else {"iccid": NOMINATED})
        request = spec(**kwargs)
        assert request.path == OPS.get_operation(operation).path
        assert request.http_method == OPS.get_operation(operation).http_method


class TestCliWiring:
    def test_all_four_operations_are_registered(self, cli):
        assert set(cli.READ_ONLY_OPERATIONS) == set(READ_ONLY)

    def test_certification_order_is_the_documented_one(self, cli):
        assert cli.CERTIFICATION_ORDER == READ_ONLY

    def test_each_operation_has_its_own_request_model_and_method(self, cli):
        """A command for one operation cannot construct or send another."""
        seen_models, seen_methods = set(), set()
        for name, spec in cli.READ_ONLY_OPERATIONS.items():
            assert spec["request_model"] not in seen_models
            assert spec["client_method"] not in seen_methods
            seen_models.add(spec["request_model"])
            seen_methods.add(spec["client_method"])
            assert spec["client_method"] == name

    def test_no_scheduler_or_bulk_mode_exists(self, cli):
        source = pathlib.Path(cli.__file__).read_text(encoding="utf-8")
        for banned in ("while True", "asyncio.sleep", "for _ in range",
                       "--all", "--bulk"):
            assert banned not in source


class TestReadinessUnchanged:
    @pytest.mark.parametrize("operation", READ_ONLY)
    def test_none_has_been_certified(self, operation):
        """No live run has happened, so nothing may claim otherwise."""
        op = OPS.get_operation(operation)
        assert op.readiness is OPS.ReadinessState.MOCK_CERTIFIED
        assert not op.is_sendable

    def test_activation_remains_the_sole_generally_sendable_operation(self):
        assert [o.name for o in OPS.sendable_operations()] == ["activate_subscriber"]

    def test_callback_shadow_remains_off_by_default(self):
        from app.services.tmobile_callback_shadow import shadow_enabled
        assert shadow_enabled() is False
