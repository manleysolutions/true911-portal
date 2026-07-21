"""Regression cover for the successful 2026-07-21 T-Mobile PIT activation.

The activation that finally succeeded returned **HTTP 201** with a body of
``{"status": "SUCCESS", ..., "result": [{"result": "100", ...}]}``. Every prior
attempt on the same deployed client contract returned ``400 GENS-0003``, so the
success path had never actually executed against the real response shape. These
tests pin it.

They also pin the properties that must not silently regress now that the
integration works: no Partner Foundation header, no credentials in the evidence
bundle, all trace identifiers preserved, and exactly one activation per operator
invocation.

No real credentials — the RSA key is generated per test and HTTP is mocked.
"""

from __future__ import annotations

import json
import os
import re

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.integrations.tmobile_evidence as ev
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
ID_TOKEN = "redacted-id-token-not-real"

TEST_ICCID = "8901260963132697538"  # operator-approved PIT test identifier
# Fabricated stand-ins for the assigned line. The real values live only in the
# restricted operator record — never in a test, a fixture, or a doc.
FAKE_MSISDN = "5550001234"
FAKE_ACCOUNT_ID = "99900011122"
FOUNDATION_ID = "FOUNDATION_VALUE_UNCONFIRMED"

# The trace ids T-Mobile returned on the successful activation. Not secrets —
# they are exactly what T-Mobile asks for when correlating to their logs.
PARTNER_TXN_ID = "true911-pit-d1475fec-981b-40a7-a27c-d867aab8e7f9"
CORRELATION_ID = "ee790876-7b0a-472e-823e-4b30fbefa88d"
WORK_FLOW_ID = "8a5659f0-16f5-46fb-9a0d-f35bb37fda92_P"
SERVICE_TXN_ID = "33f2315c-8da4-9bae-b68e-3178a5c7a620"
# Named IDP_ rather than OAUTH_ deliberately: gitleaks' generic-api-key rule
# fires on a high-entropy value within 20 characters of the keyword "auth", and
# "OAUTH_SERVICE_TXN_ID" lands inside that window. This is a T-Mobile
# service-transaction-id from the OAuth token exchange — a correlation id, not a
# credential — so the value stays and the name avoids the false positive.
IDP_SERVICE_TXN_ID = "62f5fd11-7756-953b-b032-e71a14ac118d"

FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures",
    "tmobile_pit_success_20260721T031833Z.json",
)

SUCCESS_BODY = {
    "status": "SUCCESS",
    "msisdn": FAKE_MSISDN,
    "iccid": TEST_ICCID,
    "accountId": FAKE_ACCOUNT_ID,
    "result": [{"result": "100", "status": "SUCCESS"}],
}

SUCCESS_RESPONSE_HEADERS = {
    "work-flow-id": WORK_FLOW_ID,
    "service-transaction-id": SERVICE_TXN_ID,
    "partner-transaction-id": PARTNER_TXN_ID,
}


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
        "TMOBILE_BASE_PRODUCT_ID": "Infatrac Internet Access Plan",
        "TMOBILE_WPS": "00011586",
        "TMOBILE_ACTIVATION_PATH": ACTIVATE_PATH,
        "TMOBILE_CALLBACK_LOCATION": CALLBACK,
        "TMOBILE_PIT_LIVE_CALLS_ENABLED": "true",
        "TMOBILE_PARTNER_FOUNDATION_ID": "",
        "TMOBILE_PARTNER_FOUNDATION_HEADER": "",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _mock_token(**extra):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600, **extra}))


def _mock_success_activation():
    return respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(
        201, json=SUCCESS_BODY, headers=SUCCESS_RESPONSE_HEADERS))


# ── 1-3. The 201 success path is parsed correctly ───────────────────────────

class TestSuccessResponseParsing:
    """A 201 is a success, and every returned field survives the round trip."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_201_is_parsed_as_success_not_an_error(self, tmobile_env):
        """_request only raises at >= 400 — 201 must return the parsed body.

        Worth pinning explicitly: until 2026-07-21 every real activation
        returned 400, so this branch had never run against the true shape.
        """
        _mock_token()
        _mock_success_activation()

        client = taap.TMobileTAAPClient()
        result = await client.activate_subscriber(TEST_ICCID, market_zip="30346")
        await client.close()

        assert result["status"] == "SUCCESS"

    @respx.mock
    @pytest.mark.asyncio
    async def test_result_code_100_is_preserved(self, tmobile_env):
        _mock_token()
        _mock_success_activation()

        client = taap.TMobileTAAPClient()
        result = await client.activate_subscriber(TEST_ICCID, market_zip="30346")
        await client.close()

        assert result["result"] == [{"result": "100", "status": "SUCCESS"}]
        assert result["result"][0]["result"] == "100"

    @respx.mock
    @pytest.mark.asyncio
    async def test_msisdn_and_account_id_are_captured(self, tmobile_env):
        """The MSISDN and generated account ID are the whole point of the call."""
        _mock_token()
        _mock_success_activation()

        client = taap.TMobileTAAPClient()
        result = await client.activate_subscriber(TEST_ICCID, market_zip="30346")
        await client.close()

        assert result["msisdn"] == FAKE_MSISDN
        assert result["accountId"] == FAKE_ACCOUNT_ID
        assert result["iccid"] == TEST_ICCID

    @respx.mock
    @pytest.mark.asyncio
    async def test_204_still_returns_empty_without_json_decode(self, tmobile_env):
        """Guard the neighbouring branch: 204 has no body to parse."""
        _mock_token()
        respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(204))

        client = taap.TMobileTAAPClient()
        result = await client.activate_subscriber(TEST_ICCID, market_zip="30346")
        await client.close()

        assert result == {}


# ── 4-5. A successful evidence bundle: complete trace, zero credentials ─────

class TestSuccessEvidenceBundle:
    @respx.mock
    @pytest.mark.asyncio
    async def test_bundle_carries_every_trace_identifier(self, tmobile_env):
        """A SUCCESS must preserve the same correlation ids a 400 did.

        The failure bundles were the deliverable for GENS-0003; the success
        bundle is the deliverable proving the line was activated, so it must not
        quietly drop identifiers just because nothing went wrong.
        """
        _mock_token()
        _mock_success_activation()

        bundle = await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID,
            market_zip="30346", confirm_live=True,
        )

        assert bundle["ok"] is True
        activation = next(
            x for x in bundle["exchanges"]
            if x["request"]["path"] == ACTIVATE_PATH
        )
        response = activation["response"]
        assert response["status_code"] == 201
        assert response["work_flow_id"] == WORK_FLOW_ID
        assert response["service_transaction_id"] == SERVICE_TXN_ID
        assert response["partner_transaction_id"] == PARTNER_TXN_ID

        # The request-side ids the client generates must be captured too.
        safe = activation["request"]["headers"]["safe_values"]
        assert safe["partner-transaction-id"].startswith("true911-pit-")
        assert safe["X-Correlation-Id"]
        assert safe["partner-id"] == "128"
        assert safe["sender-id"] == "128"

    @respx.mock
    @pytest.mark.asyncio
    async def test_bundle_contains_no_credentials_or_tokens(self, tmobile_env):
        """Success changes the response shape; it must not relax redaction."""
        _mock_token(id_token=ID_TOKEN)
        _mock_success_activation()

        bundle = await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID,
            market_zip="30346", confirm_live=True,
        )
        serialized = json.dumps(bundle) + ev.render_text_report(bundle)

        for secret in (ACCESS_TOKEN, ID_TOKEN, CONSUMER_KEY, CONSUMER_SECRET):
            assert secret not in serialized

        # Credential-bearing headers are presence-only on every exchange.
        for exchange in bundle["exchanges"]:
            presence = exchange["request"]["headers"]["presence"]
            assert set(presence) == set(ev.PRESENCE_ONLY_HEADERS)
            assert "Authorization" not in exchange["request"]["headers"]["safe_values"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_success_body_is_captured_but_credential_keys_masked(
        self, tmobile_env
    ):
        """A body echoing a token must be masked even on the success path."""
        _mock_token()
        respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(
            201,
            json={**SUCCESS_BODY, "access_token": "should-never-appear"},
            headers=SUCCESS_RESPONSE_HEADERS,
        ))

        bundle = await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID,
            market_zip="30346", confirm_live=True,
        )
        serialized = json.dumps(bundle)

        assert "should-never-appear" not in serialized
        assert "SUCCESS" in serialized


# ── 6-7. Partner Foundation stayed inert on the successful request ──────────

class TestPartnerFoundationWasNotNeeded:
    """The activation succeeded with NO Partner Foundation header.

    This closes the leading hypothesis of PR #171 rather than deleting it: the
    config stays inert, and these tests pin that it was inert when the call
    worked.
    """

    @respx.mock
    @pytest.mark.asyncio
    async def test_activation_succeeds_with_foundation_unset(self, tmobile_env):
        _mock_token()
        route = _mock_success_activation()

        client = taap.TMobileTAAPClient()
        assert client.partner_foundation_id == ""
        assert client.partner_foundation_header == ""
        result = await client.activate_subscriber(TEST_ICCID, market_zip="30346")
        await client.close()

        assert result["status"] == "SUCCESS"
        sent = route.calls[0].request
        names = {n.decode().lower() for n, _ in sent.headers.raw}
        assert not any("foundation" in n for n in names)

    @respx.mock
    @pytest.mark.asyncio
    async def test_configuring_it_still_changes_nothing_on_a_success(
        self, tmobile_env, monkeypatch
    ):
        """Even now that activation works, setting the config is inert.

        Wiring the header remains a deliberate code change. A success must not
        be read as licence to start emitting an unconfirmed header.
        """
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PARTNER_FOUNDATION_ID", FOUNDATION_ID)
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PARTNER_FOUNDATION_HEADER",
            "partner-foundation-id")
        _mock_token()
        route = _mock_success_activation()

        client = taap.TMobileTAAPClient()
        await client.activate_subscriber(TEST_ICCID, market_zip="30346")
        await client.close()

        for _, raw_value in route.calls[0].request.headers.raw:
            assert FOUNDATION_ID not in raw_value.decode()
        assert route.calls[0].request.headers["partner-id"] == "128"

    def test_success_fixture_records_no_foundation_header(self):
        """The committed record of the real request must say so explicitly."""
        with open(FIXTURE_PATH, encoding="utf-8") as fh:
            fixture = json.load(fh)

        assert fixture["partner_foundation"]["sent_on_requests"] is False
        assert fixture["partner_foundation"]["configured_value"] is None
        assert fixture["partner_foundation"]["configured_header_name"] is None
        names = [n.lower() for n in fixture["request"]["headers"]["names"]]
        assert not any("foundation" in n for n in names)


# ── The committed success fixture ───────────────────────────────────────────

class TestSuccessFixture:
    """The durable artifact: complete trace, masked identifiers, no secrets."""

    @pytest.fixture
    def fixture(self):
        with open(FIXTURE_PATH, encoding="utf-8") as fh:
            return json.load(fh)

    def test_records_the_activation_outcome(self, fixture):
        assert fixture["schema"] == "true911.tmobile.pit-success/1"
        assert fixture["outcome"] == "SUCCESS"
        assert fixture["http_status"] == 201
        assert fixture["endpoint"] == "POST /wholesale/v1/subscriber/activation"
        assert fixture["activated_at_utc"] == "2026-07-21T03:18:33.694749Z"
        assert fixture["deployment_commit"].startswith("1766f51")
        assert fixture["response"]["status"] == "SUCCESS"
        assert fixture["response"]["result_codes"] == ["100"]

    def test_carries_every_trace_identifier(self, fixture):
        trace = fixture["trace"]
        assert trace["partner_transaction_id"] == PARTNER_TXN_ID
        assert trace["correlation_id"] == CORRELATION_ID
        assert trace["work_flow_id"] == WORK_FLOW_ID
        assert trace["service_transaction_id"] == SERVICE_TXN_ID
        assert trace["oauth_service_transaction_id"] == IDP_SERVICE_TXN_ID

    def test_identifiers_are_masked_to_last_four(self, fixture):
        for key in ("msisdn_masked", "iccid_masked", "account_id_masked"):
            value = fixture["response"][key]
            assert value.startswith("*"), key
            assert len(value.lstrip("*")) == 4, key
        assert fixture["request"]["iccid_masked"].endswith("7538")

    def test_contains_no_credential_material(self, fixture):
        serialized = json.dumps(fixture).lower()
        # Credential-bearing JSON KEYS, not the words — the notes legitimately
        # discuss `id_token` in prose while carrying no token.
        for banned_key in ('"access_token"', '"id_token"', '"refresh_token"',
                           '"client_secret"', '"consumer_secret"', '"cnf"'):
            assert banned_key not in serialized
        for banned_value in ("bearer ", "basic ", "-----begin"):
            assert banned_value not in serialized
        # Credential headers appear as presence flags only, never as values.
        assert "Authorization" not in fixture["request"]["headers"]["safe_values"]
        assert "X-Authorization" not in fixture["request"]["headers"]["safe_values"]

    def test_pins_the_validated_request_contract(self, fixture):
        safe = fixture["request"]["headers"]["safe_values"]
        assert safe["partner-id"] == "128"
        assert safe["sender-id"] == "128"
        assert safe["partner-transaction-id"] == PARTNER_TXN_ID
        assert "call-back-location" in safe
        presence = fixture["request"]["headers"]["presence"]
        assert presence["Authorization"] is True
        assert presence["X-Authorization"] is True

    def test_does_not_overclaim_the_root_cause(self, fixture):
        """The record must not assert what the client cannot observe."""
        notes = " ".join(fixture["notes"]).lower()
        assert "not independently observable" in notes
        assert "gens-0003" in notes


class TestMaskTail:
    def test_keeps_only_the_last_four(self):
        assert ev.mask_tail("8901260963132697538") == "***************7538"
        assert ev.mask_tail("4102406851") == "******6851"

    def test_short_values_are_fully_masked(self):
        assert ev.mask_tail("1234") == "****"
        assert ev.mask_tail("12") == "**"

    def test_missing_value_is_none(self):
        assert ev.mask_tail(None) is None
        assert ev.mask_tail("") is None


# ── 8-9. The operator runner sends exactly one activation ───────────────────

class TestOperatorRunnerNeverRetries:
    @respx.mock
    @pytest.mark.asyncio
    async def test_success_sends_exactly_one_activation(self, tmobile_env):
        _mock_token()
        route = _mock_success_activation()

        await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID,
            market_zip="30346", confirm_live=True,
        )

        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_failure_also_sends_exactly_one_activation(self, tmobile_env):
        """No retry on failure either — a retry would burn a live PIT cycle."""
        _mock_token()
        route = respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(
            400, json={"code": "GENS-0003", "message": "Invalid partnerID"}))

        bundle = await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID,
            market_zip="30346", confirm_live=True,
        )

        assert route.call_count == 1
        assert bundle["ok"] is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_both_gates_are_independent_and_fail_closed(
        self, tmobile_env, monkeypatch
    ):
        """Duplicate-invocation protection is two gates, not one.

        Gate 1 is the operator's ``--confirm-live``; gate 2 is
        ``TMOBILE_PIT_LIVE_CALLS_ENABLED``. Either one closed means nothing is
        sent — which is what makes "set the flag back to false afterwards" an
        effective guard against a second accidental activation.
        """
        _mock_token()
        route = _mock_success_activation()

        # Gate 1 closed.
        with pytest.raises(RuntimeError, match="confirm-live"):
            await ev.run_activation(
                taap.TMobileTAAPClient(), iccid=TEST_ICCID,
                market_zip="30346", confirm_live=False,
            )
        assert route.call_count == 0

        # Gate 2 closed.
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "false")
        with pytest.raises(RuntimeError, match="TMOBILE_PIT_LIVE_CALLS_ENABLED"):
            await ev.run_activation(
                taap.TMobileTAAPClient(), iccid=TEST_ICCID,
                market_zip="30346", confirm_live=True,
            )
        assert route.call_count == 0

    @respx.mock
    @pytest.mark.asyncio
    async def test_preview_mode_sends_nothing_at_all(self, tmobile_env):
        """The safe way to re-inspect the contract after a success."""
        route = _mock_success_activation()
        token_route = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": ACCESS_TOKEN}))

        bundle = await ev.run_activation_preview(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID, market_zip="30346")

        assert bundle["ok"] is True
        assert route.call_count == 0
        assert token_route.call_count == 0


# ── 10. Callback correlation covers every identifier the success returned ───

class TestCallbackCorrelation:
    """The success gives us five ids to correlate a callback on.

    ``capture_response`` is what records them from a T-Mobile response; the
    header-name candidate lists are what let a callback be matched back to this
    activation regardless of which spelling T-Mobile uses.
    """

    def test_workflow_service_and_partner_ids_are_all_extracted(self):
        response = httpx.Response(201, json=SUCCESS_BODY,
                                  headers=SUCCESS_RESPONSE_HEADERS)
        captured = ev.capture_response(response)

        assert captured["work_flow_id"] == WORK_FLOW_ID
        assert captured["service_transaction_id"] == SERVICE_TXN_ID
        assert captured["partner_transaction_id"] == PARTNER_TXN_ID

    @pytest.mark.parametrize("header_name", [
        "work-flow-id", "x-work-flow-id", "workflow-id", "x-workflow-id",
    ])
    def test_workflow_id_matched_under_every_known_spelling(self, header_name):
        captured = ev.capture_response(
            httpx.Response(201, json={}, headers={header_name: WORK_FLOW_ID}))
        assert captured["work_flow_id"] == WORK_FLOW_ID

    @pytest.mark.parametrize("header_name", [
        "service-transaction-id", "x-service-transaction-id",
    ])
    def test_service_transaction_id_matched_under_every_known_spelling(
        self, header_name
    ):
        captured = ev.capture_response(
            httpx.Response(201, json={}, headers={header_name: SERVICE_TXN_ID}))
        assert captured["service_transaction_id"] == SERVICE_TXN_ID

    @pytest.mark.parametrize("header_name", [
        "partner-transaction-id", "x-partner-transaction-id",
        "transaction-id", "x-transaction-id",
    ])
    def test_partner_transaction_id_matched_under_every_known_spelling(
        self, header_name
    ):
        captured = ev.capture_response(
            httpx.Response(201, json={}, headers={header_name: PARTNER_TXN_ID}))
        assert captured["partner_transaction_id"] == PARTNER_TXN_ID

    def test_iccid_correlation_is_available_from_the_response_body(self):
        """The ICCID is the durable key — it survives when a header does not."""
        captured = ev.capture_response(
            httpx.Response(201, json=SUCCESS_BODY))
        body = json.loads(captured["body"])

        assert body["iccid"] == TEST_ICCID
        assert body["accountId"] == FAKE_ACCOUNT_ID
        assert captured["work_flow_id"] is None  # no headers — body still usable

    def test_callback_processor_extracts_the_same_correlation_keys(self):
        """The inbound side must key on what the outbound side recorded."""
        from app.services import tmobile_callback_processor as proc

        for key in ("iccid",):
            assert key in proc._ICCID_KEYS
        for key in ("msisdn",):
            assert key in proc._MSISDN_KEYS
        for key in ("accountId", "account_id"):
            assert key in proc._ACCOUNT_ID_KEYS


class TestSuccessFixtureBuilder:
    """Behavior-level cover for the generator, not just its committed output.

    The committed fixture is checked above. These tests exercise
    ``scripts/tmobile_build_success_fixture.build()`` — the code path that
    produces it — so a regression in the builder is caught even before anyone
    regenerates the file.

    Loaded by path because the script lives outside the package, the same way
    ``test_tmobile_pit_certification.py`` loads the operator CLI.
    """

    @pytest.fixture
    def builder(self):
        import importlib.util
        import pathlib
        path = (pathlib.Path(__file__).resolve().parents[2]
                / "scripts" / "tmobile_build_success_fixture.py")
        spec = importlib.util.spec_from_file_location("tm_fixture_builder", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @pytest.fixture
    def built(self, builder):
        # Fabricated subscriber identifiers — the real ones live only in the
        # restricted operator record and are never needed to exercise the code.
        return builder.build(TEST_ICCID, FAKE_MSISDN, FAKE_ACCOUNT_ID)

    def test_idp_service_transaction_id_survives_into_the_evidence(self, built):
        """The renamed constant must still reach the sanitized record.

        The point of the rename was to stop a scanner false positive WITHOUT
        dropping a trace identifier T-Mobile needs to correlate the request.
        """
        assert built["trace"]["oauth_service_transaction_id"] == IDP_SERVICE_TXN_ID

    def test_the_identifier_matches_the_observed_activation_evidence(
        self, built, builder
    ):
        """Renaming the constant must not have altered the value.

        Cross-checks three independent places: the builder's constant, the
        record it generates, and the committed fixture.
        """
        with open(FIXTURE_PATH, encoding="utf-8") as fh:
            committed = json.load(fh)

        assert builder.IDP_SERVICE_TRANSACTION_ID == IDP_SERVICE_TXN_ID
        assert built["trace"] == committed["trace"]

    def test_every_trace_identifier_is_carried(self, built):
        assert built["trace"] == {
            "partner_transaction_id": PARTNER_TXN_ID,
            "correlation_id": CORRELATION_ID,
            "work_flow_id": WORK_FLOW_ID,
            "service_transaction_id": SERVICE_TXN_ID,
            "oauth_service_transaction_id": IDP_SERVICE_TXN_ID,
        }

    def test_trace_identifiers_are_kept_verbatim_not_masked(self, built):
        """Trace ids are correlation evidence, so they are NOT masked.

        This is the distinction the rename encodes: subscriber identifiers are
        masked because they identify a line; transaction ids are recorded in
        full because T-Mobile needs them to find the call. Treating a trace id
        as a credential would make the bundle useless for its actual purpose.
        """
        for value in built["trace"].values():
            assert "*" not in value

    def test_subscriber_identifiers_are_still_masked(self, built):
        """The naming change must not have relaxed masking."""
        response = built["response"]
        for key in ("msisdn_masked", "iccid_masked", "account_id_masked"):
            assert response[key].startswith("*")
            assert len(response[key].lstrip("*")) == 4
        blob = json.dumps(built)
        for raw in (FAKE_MSISDN, FAKE_ACCOUNT_ID):
            assert raw not in blob

    def test_generated_evidence_carries_no_credential_material(self, built):
        """No token, secret, key, or PoP JWT may reach the generated record."""
        blob = json.dumps(built)
        lowered = blob.lower()

        for banned_key in ('"access_token"', '"id_token"', '"refresh_token"',
                           '"client_secret"', '"consumer_secret"', '"cnf"'):
            assert banned_key not in lowered
        for banned_value in ("bearer ", "basic ", "-----begin"):
            assert banned_value not in lowered
        # A PoP JWT would appear as three base64url segments.
        assert not re.search(r"eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.", blob)
        # Credential headers stay presence-only, never values.
        safe_values = built["request"]["headers"]["safe_values"]
        assert "Authorization" not in safe_values
        assert "X-Authorization" not in safe_values
        assert built["request"]["headers"]["presence"]["Authorization"] is True

    def test_partner_foundation_still_reported_as_never_sent(self, built):
        assert built["partner_foundation"]["sent_on_requests"] is False
