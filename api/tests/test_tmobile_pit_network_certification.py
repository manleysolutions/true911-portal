"""query_network PIT certification (2026-09-30) and the lifecycle-evidence rule.

On 2026-09-01 one Network Profile request returned HTTP 500 / GENS-0005 and
certified nothing (``test_tmobile_pit_network_failure.py`` still replays that).
On 2026-09-30, at T-Mobile Engineering's written request, exactly one re-test
returned HTTP 200 / SUCCESS / 100 for the approved PIT subscriber. This suite
pins what that does and does not change:

* ``query_network`` reaches ``PIT_TESTED`` - maturity only;
* it stays ``SINGLE_RUN_ONLY``: one-shot, operation- and subscriber-specific,
  consumed after one request, never generally sendable;
* ``query_usage`` inherits nothing; ``query_transaction_status`` stays blocked;
  no destructive operation gains any authorization;
* the observed response shape parses and unknown fields are preserved;
* lifecycle reconciliation from a read is DECLARED per operation
  (``Operation.lifecycle_evidence``), never inferred from a field being present,
  and stays fail-closed for absent, unrecognised or conflicting statuses.

Offline only: every carrier exchange is mocked with respx. Every identifier is
fabricated - the real PIT selector and trace identifiers stay in the operator's
private evidence store.
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
from app.integrations.tmobile_contracts import (
    NormalizedStatus,
    ResponseKind,
    TMobileResponseEnvelope,
)
from app.integrations.tmobile_lifecycle import CarrierEvidence, LifecycleState
from app.integrations.tmobile_operations import (
    Classification,
    ReadinessState,
    SendAuthorization,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE_URL = "https://wholesaleapi-test.t-mobile.com"
TOKEN_URL = f"{BASE_URL}/oauth2/v1/tokens"
NETWORK_PATH = "/wholesale/v1/subscriber/network-profile"
PROFILE_PATH = "/wholesale/v1/subscriber/profile"
USAGE_PATH = "/wholesale/v1/subscriber/usage"

# Fabricated sentinels - see .gitleaks.toml (TM_TEST_ prefix is allowlisted).
CONSUMER_KEY = "TM_TEST_CK_HG7XQ2"
CONSUMER_SECRET = "TM_TEST_CS_PL3JR9"
ACCESS_TOKEN = "redacted-token-not-real"

# Fabricated stand-ins - never the certified PIT line's identifiers.
ICCID = "8901260963132600001"
OTHER_ICCID = "8901260963132600002"
MSISDN = "5550001234"

#: The SHAPE observed on 2026-09-30, with every identifier fabricated and the
#: network / product / profile detail reduced to representative placeholders.
NETWORK_SUCCESS = {
    "status": "SUCCESS",
    "result": [{"result": "100", "status": "SUCCESS"}],
    "iccid": ICCID,
    "msisdn": MSISDN,
    "iccidStatus": "INUSE",
    "subscriberStatus": "ACTIVE",
    "simNetworkType": "M2M",
    "apn": "iot.example",
    "networkProfile": {"lte": True, "volte": True, "ims": True},
    "networkSpecification": [{"name": "placeholder", "value": "placeholder"}],
}


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cli():
    path = REPO_ROOT / "scripts" / "tmobile_pit.py"
    spec = importlib.util.spec_from_file_location("tmobile_pit_cli_net", path)
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


def _run_read(cli, tmp_path, operation, path, body):
    """Drive exactly one successful read through the operator harness."""
    token = respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600}))
    resource = respx.post(f"{BASE_URL}{path}").mock(
        return_value=httpx.Response(200, json=body))
    args = _read_args(out_dir=str(tmp_path / "evidence"))
    code = asyncio.run(cli.cmd_read_only(args, operation))
    return code, token, resource


def _bundle(tmp_path):
    (path,) = sorted((tmp_path / "evidence").glob("*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def _grant(operation, selector=ICCID, selector_type="iccid"):
    return AUTH.grant_single_run(
        operation=operation, selector_type=selector_type, selector=selector,
        operator="reviewer", confirmed=True)


def _boundary_allows(operation: str) -> bool:
    try:
        OPS.require_live_sendable(operation)
        return True
    except OPS.TMobileOperationBlockedError:
        return False


def _envelope(body, operation="query_network"):
    return TMobileResponseEnvelope.from_payload(
        body, operation=operation, kind=ResponseKind.SYNCHRONOUS, http_status=200)


# ── 1-4. Maturity advanced; authorization did not ───────────────────────────

class TestNetworkProfileMaturity:
    def test_1_query_network_is_pit_tested_with_history_preserved(self):
        op = OPS.get_operation("query_network")
        assert op.readiness is ReadinessState.PIT_TESTED
        assert "2026-09-30" in op.test_status and "SUCCESS" in op.test_status
        # the failure is history, not erased
        assert "2026-09-01" in op.test_status and "GENS-0005" in op.test_status
        assert op.blocking_questions == ()

    def test_2_send_authorization_is_still_single_run_only(self):
        assert (OPS.get_operation("query_network").send_authorization
                is SendAuthorization.SINGLE_RUN_ONLY)

    def test_3_pit_tested_does_not_make_it_generally_sendable(self, pit_env):
        op = OPS.get_operation("query_network")
        assert not op.is_sendable
        assert "query_network" not in [o.name for o in OPS.sendable_operations()]
        with pytest.raises(OPS.TMobileOperationBlockedError):
            OPS.require_live_sendable("query_network")

    def test_4_a_one_shot_grant_is_still_required(self, pit_env):
        assert not _boundary_allows("query_network")
        _grant("query_network")
        assert _boundary_allows("query_network")


# ── 5-7. The one-shot grant is unchanged ────────────────────────────────────

class TestOneShotGrant:
    def test_5_the_grant_is_operation_specific(self, pit_env):
        _grant("query_network")
        assert not _boundary_allows("query_usage")
        assert not _boundary_allows("subscriber_inquiry")
        auth = AUTH.active_authorization()
        with pytest.raises(AUTH.AuthorizationError, match="covers 'query_network'"):
            auth.consume("query_usage")

    def test_6_the_grant_is_subscriber_specific(self, pit_env):
        auth = _grant("query_network")
        assert auth.matches_selector(ICCID)
        assert not auth.matches_selector(OTHER_ICCID)

    @respx.mock
    def test_7_the_grant_is_consumed_after_exactly_one_request(self, cli, pit_env):
        code, _token, resource = _run_read(
            cli, pit_env, "query_network", NETWORK_PATH, NETWORK_SUCCESS)
        assert code == 0
        assert resource.call_count == 1
        assert AUTH.active_authorization() is None
        assert not _boundary_allows("query_network")
        assert _bundle(pit_env)["ok"] is True


# ── 8-10. Nothing else moved ────────────────────────────────────────────────

class TestNothingElseMoved:
    def test_8_query_usage_inherits_nothing(self, pit_env):
        op = OPS.get_operation("query_usage")
        assert op.readiness is ReadinessState.MOCK_CERTIFIED
        assert op.send_authorization is SendAuthorization.SINGLE_RUN_ONLY
        assert op.lifecycle_evidence is False
        assert "Never sent live." in op.test_status
        _grant("query_network")
        assert not _boundary_allows("query_usage")

    def test_9_query_transaction_status_stays_blocked(self, pit_env):
        op = OPS.get_operation("query_transaction_status")
        assert op.readiness is ReadinessState.MOCK_CERTIFIED
        assert op.certification_blockers
        assert not op.is_single_run_certifiable
        with pytest.raises(AUTH.AuthorizationError):
            _grant("query_transaction_status", selector="TXN-FABRICATED-1",
                   selector_type=AUTH.TRANSACTION_SELECTOR)

    def test_10_no_destructive_operation_is_authorized(self):
        for op in OPS.OPERATIONS:
            if op.classification is Classification.DESTRUCTIVE:
                assert op.send_authorization is SendAuthorization.NONE, op.name
                assert not op.is_sendable, op.name
                assert not op.is_single_run_certifiable, op.name
        assert [o.name for o in OPS.sendable_operations()] == ["activate_subscriber"]


# ── 11-12. The observed response shape ──────────────────────────────────────

class TestObservedResponseShape:
    def test_11_the_observed_shape_parses(self):
        env = _envelope(NETWORK_SUCCESS)
        assert env.normalized_status is NormalizedStatus.SUCCESS
        assert env.vendor_code == "100"
        assert env.accepted is True and env.completed is False
        assert env.iccid == ICCID
        assert env.subscriber_status_raw == "ACTIVE"
        assert env.sim_network_type == "M2M"

    def test_12_unknown_fields_are_preserved_not_dropped(self):
        env = _envelope(NETWORK_SUCCESS)
        for key in ("apn", "networkProfile", "networkSpecification"):
            assert key in env.raw_extra_fields
        assert env.raw_extra_fields["networkProfile"] == NETWORK_SUCCESS["networkProfile"]


# ── 13-16. Lifecycle reconciliation is declared, and fail-closed ────────────

class TestLifecycleEvidenceDeclaration:
    def test_13a_exactly_the_documented_reads_are_declared(self):
        assert OPS.lifecycle_evidence_operations() == ("subscriber_inquiry",
                                                       "query_network")
        for op in OPS.OPERATIONS:
            if op.lifecycle_evidence:
                assert op.classification is Classification.READ_ONLY
                assert "subscriber" in op.response_schema.lower() or \
                    "subscriberStatus" in op.response_schema

    def test_13b_the_registry_refuses_a_non_read_declared_as_evidence(self):
        import dataclasses
        bad = dataclasses.replace(OPS.get_operation("activate_subscriber"),
                                  lifecycle_evidence=True)
        original = OPS.OPERATIONS
        try:
            OPS.OPERATIONS = original + (bad,)
            with pytest.raises(AssertionError, match="only an independent READ"):
                OPS._validate_authorization_policy()
        finally:
            OPS.OPERATIONS = original

    @respx.mock
    def test_13c_network_active_settles_an_unknown_ledger(self, cli, pit_env):
        """The exact 2026-09-30 outcome: unknown -> active, carrier_verified."""
        assert cli._load_state(ICCID) is LifecycleState.UNKNOWN
        code, _t, _r = _run_read(cli, pit_env, "query_network", NETWORK_PATH,
                                 NETWORK_SUCCESS)
        doc = cli._load_ledger(ICCID)
        assert code == 0
        assert doc["state"] == LifecycleState.ACTIVE.value
        assert doc["evidence"] == CarrierEvidence.CARRIER_VERIFIED.value
        assert (doc["evidence_ledger"]["carrier_verified_by_operation"]
                == "query_network")
        rec = _bundle(pit_env)["ledger_reconciliation"]
        assert rec["reconciled"] is True and rec["previous_state"] == "unknown"

    @pytest.mark.parametrize("operation", ["query_usage", "query_transaction_status"])
    def test_13d_an_undeclared_read_never_reconciles_even_with_a_status(
        self, cli, pit_env, operation
    ):
        body = {"status": "SUCCESS", "iccid": ICCID, "subscriberStatus": "Active"}
        result = cli._reconcile_ledger_from_read(
            operation, _envelope(body, operation), iccid=ICCID, operator="reviewer")
        assert result["reconciled"] is False
        assert "not declared a lifecycle-evidence operation" in result["reason"]
        assert cli._load_state(ICCID) is LifecycleState.UNKNOWN

    def test_13e_a_replayed_undeclared_bundle_never_reconciles(self, cli, pit_env):
        body = {"status": "SUCCESS", "iccid": ICCID, "subscriberStatus": "Active"}
        bundle = {
            "schema": "true911.tmobile.pit-evidence/1", "operation": "query_usage",
            "ok": True, "selector_type": "iccid",
            "selector_masked": "*" * 15 + ICCID[-4:],
            "exchanges": [{"request": {"method": "POST", "path": USAGE_PATH},
                           "response": {"status_code": 200, "body": json.dumps(body)}}],
        }
        path = pit_env / "usage.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        code = cli.cmd_reconcile(argparse.Namespace(
            command="reconcile", iccid=ICCID, evidence=str(path), operator="reviewer"))
        assert code == 1
        assert cli._load_state(ICCID) is LifecycleState.UNKNOWN

    @respx.mock
    def test_14_an_unrecognised_status_fails_closed(self, cli, pit_env):
        body = dict(NETWORK_SUCCESS, subscriberStatus="SOMETHING_NEW")
        code, _t, _r = _run_read(cli, pit_env, "query_network", NETWORK_PATH, body)
        assert code == 0                         # the carrier request succeeded
        assert cli._load_state(ICCID) is LifecycleState.UNKNOWN
        rec = _bundle(pit_env)["ledger_reconciliation"]
        assert rec["reconciled"] is False
        assert "not in the reconciled vocabulary" in rec["reason"]

    @respx.mock
    def test_15a_a_conflicting_read_never_overwrites_a_settled_state(
        self, cli, pit_env
    ):
        _run_read(cli, pit_env, "query_network", NETWORK_PATH, NETWORK_SUCCESS)
        assert cli._load_state(ICCID) is LifecycleState.ACTIVE
        for f in (pit_env / "evidence").glob("*"):
            f.unlink()

        code, _t, _r = _run_read(cli, pit_env, "query_network", NETWORK_PATH,
                                 dict(NETWORK_SUCCESS, subscriberStatus="Suspended"))
        doc = cli._load_ledger(ICCID)
        assert code == 0
        assert doc["state"] == LifecycleState.ACTIVE.value      # NOT overwritten
        assert doc["evidence"] == CarrierEvidence.CONFLICT.value
        assert doc["evidence_ledger"]["reconciliation_required"] is True

    @respx.mock
    def test_15b_network_cannot_overwrite_a_state_an_inquiry_verified(
        self, cli, pit_env
    ):
        """Stronger prior carrier evidence (an inquiry) is never silently replaced."""
        _run_read(cli, pit_env, "subscriber_inquiry", PROFILE_PATH, {
            "status": "SUCCESS", "iccid": ICCID, "subscriberStatus": "Active",
            "result": [{"result": "100", "status": "SUCCESS"}]})
        assert cli._load_state(ICCID) is LifecycleState.ACTIVE
        for f in (pit_env / "evidence").glob("*"):
            f.unlink()

        _run_read(cli, pit_env, "query_network", NETWORK_PATH,
                  dict(NETWORK_SUCCESS, subscriberStatus="Deactivated"))
        doc = cli._load_ledger(ICCID)
        assert doc["state"] == LifecycleState.ACTIVE.value
        assert doc["evidence_ledger"]["reconciliation_required"] is True

    def test_15c_the_reconciler_itself_is_fail_closed(self):
        r = LC.reconcile_from_carrier_read("Suspended", current=LifecycleState.ACTIVE)
        assert r.conflict and r.observed_state is LifecycleState.ACTIVE

    @respx.mock
    def test_16_an_absent_subscriber_status_fabricates_nothing(self, cli, pit_env):
        body = {k: v for k, v in NETWORK_SUCCESS.items() if k != "subscriberStatus"}
        code, _t, _r = _run_read(cli, pit_env, "query_network", NETWORK_PATH, body)
        assert code == 0
        assert cli._load_state(ICCID) is LifecycleState.UNKNOWN
        assert "ledger_reconciliation" not in _bundle(pit_env)
        with pytest.raises(LC.ReconciliationError, match="no subscriberStatus"):
            LC.reconcile_from_carrier_read(None, current=LifecycleState.UNKNOWN)
