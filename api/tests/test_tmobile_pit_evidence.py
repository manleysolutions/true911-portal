"""T-Mobile PIT evidence capture, Partner Foundation inertness, and comparison.

Covers the preparation work done while awaiting T-Mobile's Partner Foundation ID
contract:

  - the Partner Foundation config is INERT — configured but never transmitted
  - evidence capture records the safe fields and redacts every credential
  - the runner modes send exactly what they claim (and nothing more)
  - the comparison tool catches the mismatches that matter

No real credentials: the RSA key is generated per-test and HTTP is mocked.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.integrations.tmobile_evidence as ev
import app.integrations.tmobile_taap as taap
from app.integrations.tmobile_contract_compare import compare_requests

TOKEN_URL = "https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens"
TOKEN_PATH = "/oauth2/v1/tokens"
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
FOUNDATION_ID = "FOUNDATION_VALUE_UNCONFIRMED"


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
        "TMOBILE_PIT_LIVE_CALLS_ENABLED": "false",
        "TMOBILE_PARTNER_FOUNDATION_ID": "",
        "TMOBILE_PARTNER_FOUNDATION_HEADER": "",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _mock_token(**extra):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600, **extra}))


# ── 1-2. Partner Foundation config is inert ─────────────────────────────────

class TestPartnerFoundationIsInert:
    def test_unset_by_default(self, tmobile_env):
        client = taap.TMobileTAAPClient()
        assert client.partner_foundation_id == ""
        assert client.partner_foundation_header == ""

    def test_whitespace_is_stripped(self, tmobile_env, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PARTNER_FOUNDATION_ID", f"  {FOUNDATION_ID}  ")
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PARTNER_FOUNDATION_HEADER", "  x-foo  ")
        client = taap.TMobileTAAPClient()
        assert client.partner_foundation_id == FOUNDATION_ID
        assert client.partner_foundation_header == "x-foo"

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_foundation_header_sent_even_when_fully_configured(
        self, tmobile_env, monkeypatch
    ):
        """THE load-bearing test: configuring it must change NOTHING on the wire.

        The header name and semantics are unconfirmed by T-Mobile. Wiring it up is
        a deliberate code change, never a config toggle.
        """
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PARTNER_FOUNDATION_ID", FOUNDATION_ID)
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PARTNER_FOUNDATION_HEADER", "partner-foundation-id")
        _mock_token()
        respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

        client = taap.TMobileTAAPClient()
        await client.post_json(ACTIVATE_PATH, {"iccid": TEST_ICCID})
        await client.close()

        for call in respx.calls:
            names = {n.decode().lower() for n, _ in call.request.headers.raw}
            assert "partner-foundation-id" not in names
            # ...and the value must not appear under ANY header name.
            for _, raw_value in call.request.headers.raw:
                assert FOUNDATION_ID not in raw_value.decode()

    @respx.mock
    @pytest.mark.asyncio
    async def test_foundation_value_is_not_mapped_onto_partner_id(
        self, tmobile_env, monkeypatch
    ):
        """partner-id must stay 128 — never silently replaced."""
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PARTNER_FOUNDATION_ID", FOUNDATION_ID)
        _mock_token()
        respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(200, json={"ok": True}))

        client = taap.TMobileTAAPClient()
        await client.post_json(ACTIVATE_PATH, {"iccid": TEST_ICCID})
        await client.close()

        req = next(c.request for c in respx.calls if c.request.url.path == ACTIVATE_PATH)
        assert req.headers["partner-id"] == "128"

    def test_status_reports_configured_but_not_sent(self, tmobile_env, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PARTNER_FOUNDATION_ID", FOUNDATION_ID)
        status = ev.partner_foundation_status(taap.TMobileTAAPClient())
        assert status["configured_value"] == FOUNDATION_ID
        assert status["sent_on_requests"] is False


# ── 3-4. Evidence capture: required fields + redaction ──────────────────────

class TestEvidenceCapture:
    @respx.mock
    @pytest.mark.asyncio
    async def test_capture_includes_required_safe_fields(self, tmobile_env):
        _mock_token()
        bundle = await ev.run_token_only(taap.TMobileTAAPClient())
        req = bundle["exchanges"][0]["request"]

        assert req["captured_at_utc"].endswith("Z")
        assert req["method"] == "POST"
        assert req["path"] == TOKEN_PATH
        assert req["environment"] == BASE_URL
        assert "sender-id" in req["headers"]["names"]
        assert req["headers"]["safe_values"]["sender-id"] == "128"
        assert req["headers"]["safe_values"]["grant-type"] == "client_credentials"
        assert req["headers"]["presence"]["Authorization"] is True
        assert req["headers"]["presence"]["X-Authorization"] is True
        assert req["body"]["byte_length"] > 0
        assert len(req["body"]["sha256"]) == 64
        assert req["pop"]["ehts_names"] == [
            "Content-Type", "Authorization", "uri", "http-method", "body"]
        assert req["pop"]["jwt_header"] == {"alg": "RS256", "typ": "JWT"}
        assert req["pop"]["lifetime_seconds"] == 60
        assert req["pop"]["edts"]
        assert bundle["exchanges"][0]["response"]["status_code"] == 200

    @respx.mock
    @pytest.mark.asyncio
    async def test_capture_redacts_every_credential_bearing_field(self, tmobile_env):
        _mock_token(id_token=ID_TOKEN)
        client = taap.TMobileTAAPClient()
        bundle = await ev.run_token_only(client)
        blob = json.dumps(bundle)

        assert CONSUMER_KEY not in blob
        assert CONSUMER_SECRET not in blob
        assert ACCESS_TOKEN not in blob, "access token leaked into evidence"
        assert ID_TOKEN not in blob, "id_token leaked into evidence"
        assert "Basic " not in blob, "Basic Authorization value leaked"
        assert "BEGIN PRIVATE KEY" not in blob
        assert "BEGIN PUBLIC KEY" not in blob, "cnf public key leaked"
        # The PoP JWT is never recorded — only its decoded safe structure.
        for call in respx.calls:
            pop = call.request.headers.get("X-Authorization")
            if pop:
                assert pop not in blob, "PoP JWT leaked into evidence"

    @respx.mock
    @pytest.mark.asyncio
    async def test_text_report_carries_no_secrets(self, tmobile_env):
        _mock_token(id_token=ID_TOKEN)
        bundle = await ev.run_token_only(taap.TMobileTAAPClient())
        report = ev.render_text_report(bundle)

        for secret in (CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ID_TOKEN):
            assert secret not in report
        assert "<present, redacted>" in report

    def test_unknown_headers_are_redacted_by_default(self):
        """Allowlist, not denylist: an unlisted header's value is never captured."""
        captured = ev.sanitize_headers({"X-Future-Secret": "super-secret-value"})
        assert "X-Future-Secret" in captured["names"]
        assert "X-Future-Secret" not in captured["safe_values"]
        assert "super-secret-value" not in json.dumps(captured)

    def test_query_values_are_redacted_from_urls(self):
        out = ev._redact_url("https://x.invalid/p?token=abc123&id=9")
        assert "abc123" not in out
        assert "token=<redacted>" in out
        assert "/p" in out

    def test_response_body_masks_credential_keys(self):
        body = json.dumps({"access_token": "secret1", "id_token": "secret2",
                           "error": "GENS-0003"})
        out = ev._redact_body_text(body)
        assert "secret1" not in out and "secret2" not in out
        assert "GENS-0003" in out  # the diagnostic content survives

    def test_unexpected_pop_claims_are_dropped_not_echoed(self, signing_key):
        """A resurrected `iss` (the consumer key) must not reach the bundle."""
        import time
        from jose import jwt as jose_jwt
        rogue = jose_jwt.encode(
            {"iat": int(time.time()), "exp": int(time.time()) + 60, "ehts": "uri",
             "edts": "x", "jti": "j", "v": "1", "iss": CONSUMER_KEY},
            signing_key, algorithm="RS256", headers={"alg": "RS256", "typ": "JWT"},
        )
        described = ev.describe_pop(rogue)
        assert "iss" not in described["claims"]
        assert described["unexpected_claims_dropped"] == ["iss"]
        assert CONSUMER_KEY not in json.dumps(described)


# ── 5-8. Runner modes ───────────────────────────────────────────────────────

class TestRunnerModes:
    @respx.mock
    @pytest.mark.asyncio
    async def test_token_only_performs_no_resource_call(self, tmobile_env):
        _mock_token()
        activate = respx.post(ACTIVATE_URL).mock(
            return_value=httpx.Response(200, json={"ok": True}))

        bundle = await ev.run_token_only(taap.TMobileTAAPClient())

        assert not activate.called, "token-only must never touch a resource endpoint"
        assert len(bundle["exchanges"]) == 1
        assert bundle["exchanges"][0]["request"]["path"] == TOKEN_PATH

    @respx.mock
    @pytest.mark.asyncio
    async def test_activation_preview_performs_no_network_call(self, tmobile_env):
        token = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": ACCESS_TOKEN}))
        activate = respx.post(ACTIVATE_URL).mock(
            return_value=httpx.Response(200, json={"ok": True}))

        bundle = await ev.run_activation_preview(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID, market_zip="30346")

        assert not token.called, "preview must not fetch a token"
        assert not activate.called, "preview must not send an activation"
        assert bundle["exchanges"] == []
        p = bundle["request_preview"]
        assert p["body"]["byte_length"] > 0
        assert p["expected_pop_ehts"] == "Content-Type;Authorization;uri;http-method;body"

    @respx.mock
    @pytest.mark.asyncio
    async def test_preview_body_digest_matches_what_would_be_sent(self, tmobile_env):
        """The preview's hash must equal the real request's — else it is fiction."""
        preview = await ev.run_activation_preview(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID, market_zip="30346")

        _mock_token()
        respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        client = taap.TMobileTAAPClient()
        client._require_live_calls_enabled = lambda: None  # bypass gate for the mock
        await client.activate_subscriber(TEST_ICCID, market_zip="30346")
        await client.close()

        sent = next(c.request for c in respx.calls if c.request.url.path == ACTIVATE_PATH)
        import hashlib
        assert (preview["request_preview"]["body"]["sha256"]
                == hashlib.sha256(sent.content).hexdigest())

    @pytest.mark.asyncio
    async def test_activate_requires_confirm_live_flag(self, tmobile_env, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "true")
        with pytest.raises(RuntimeError, match="--confirm-live"):
            await ev.run_activation(
                taap.TMobileTAAPClient(), iccid=TEST_ICCID,
                market_zip="30346", confirm_live=False)

    @pytest.mark.asyncio
    async def test_activate_requires_live_calls_env(self, tmobile_env):
        """Env gate stays enforced even WITH --confirm-live."""
        with pytest.raises(RuntimeError, match="TMOBILE_PIT_LIVE_CALLS_ENABLED"):
            await ev.run_activation(
                taap.TMobileTAAPClient(), iccid=TEST_ICCID,
                market_zip="30346", confirm_live=True)

    @respx.mock
    @pytest.mark.asyncio
    async def test_both_gates_closed_sends_nothing(self, tmobile_env):
        token = respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"access_token": ACCESS_TOKEN}))
        activate = respx.post(ACTIVATE_URL).mock(
            return_value=httpx.Response(200, json={"ok": True}))
        with pytest.raises(RuntimeError):
            await ev.run_activation(
                taap.TMobileTAAPClient(), iccid=TEST_ICCID,
                market_zip="30346", confirm_live=False)
        assert not token.called and not activate.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_activate_sends_exactly_one_request_and_never_retries(
        self, tmobile_env, monkeypatch
    ):
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "true")
        _mock_token()
        activate = respx.post(ACTIVATE_URL).mock(
            return_value=httpx.Response(400, json={"code": "GENS-0003"}))

        await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID,
            market_zip="30346", confirm_live=True)

        assert activate.call_count == 1, "a 400 must NOT trigger an automatic retry"

    @respx.mock
    @pytest.mark.asyncio
    async def test_bundle_survives_400_and_preserves_correlation_ids(
        self, tmobile_env, monkeypatch
    ):
        """The 400 bundle IS the deliverable — every id T-Mobile needs must survive."""
        monkeypatch.setattr(
            "app.config.settings.TMOBILE_PIT_LIVE_CALLS_ENABLED", "true")
        _mock_token()
        respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(
            400,
            json={"code": "GENS-0003", "message": "Invalid partnerID"},
            headers={
                "work-flow-id": "8e5f9dcb-c62c-443c-8f7b-1d45eb0d691e_P",
                "service-transaction-id": "f7542c0d-8eaf-9d43-a826-4a4b757b3977",
            },
        ))

        bundle = await ev.run_activation(
            taap.TMobileTAAPClient(), iccid=TEST_ICCID,
            market_zip="30346", confirm_live=True)

        assert bundle["ok"] is False
        exchange = next(e for e in bundle["exchanges"]
                        if e["request"]["path"] == ACTIVATE_PATH)
        resp = exchange["response"]
        assert resp["status_code"] == 400
        assert resp["work_flow_id"] == "8e5f9dcb-c62c-443c-8f7b-1d45eb0d691e_P"
        assert resp["service_transaction_id"] == "f7542c0d-8eaf-9d43-a826-4a4b757b3977"
        assert "GENS-0003" in resp["body"]
        # partner-transaction-id / X-Correlation-Id are ours, on the REQUEST.
        safe = exchange["request"]["headers"]["safe_values"]
        assert safe["partner-transaction-id"].startswith("true911-pit-")
        assert safe["X-Correlation-Id"]
        assert bundle["iccid"] == TEST_ICCID
        # The report must render a failed bundle without blowing up.
        assert "GENS-0003" in ev.render_text_report(bundle)

    @respx.mock
    @pytest.mark.asyncio
    async def test_evidence_files_are_written_and_contain_no_secrets(
        self, tmobile_env, tmp_path
    ):
        _mock_token(id_token=ID_TOKEN)
        bundle = await ev.run_token_only(taap.TMobileTAAPClient())
        json_path, txt_path = ev.write_evidence(bundle, str(tmp_path))

        for path in (json_path, txt_path):
            content = open(path, encoding="utf-8").read()
            for secret in (CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ID_TOKEN):
                assert secret not in content, f"{secret[:8]}… leaked into {path}"
        assert json.loads(open(json_path, encoding="utf-8").read())["mode"] == "token-only"


# ── 10. Comparison tool ─────────────────────────────────────────────────────

def _capture(**overrides) -> dict:
    base = {
        "method": "POST",
        "path": TOKEN_PATH,
        "url": TOKEN_URL,
        "headers": {
            "names": ["Content-Type", "Authorization", "grant-type", "sender-id"],
            "safe_values": {"Content-Type": "application/json",
                            "grant-type": "client_credentials", "sender-id": "128"},
            "presence": {"Authorization": True, "X-Authorization": True,
                         "X-Auth-Originator": False},
        },
        "body": {"byte_length": 100, "sha256": "a" * 64},
        "pop": {
            "present": True,
            "jwt_header": {"alg": "RS256", "typ": "JWT"},
            "ehts_names": ["Content-Type", "Authorization", "uri", "http-method", "body"],
            "claims": {"iat": 1, "exp": 61, "ehts": "x", "edts": "y", "jti": "j", "v": "1"},
            "lifetime_seconds": 60,
            "edts": "y",
        },
    }
    base.update(overrides)
    return base


class TestComparisonTool:
    def test_identical_requests_report_no_differences(self):
        assert compare_requests(_capture(), _capture()) == []

    def test_catches_missing_header(self):
        ours = _capture()
        ours["headers"] = json.loads(json.dumps(ours["headers"]))
        ours["headers"]["names"].remove("grant-type")
        del ours["headers"]["safe_values"]["grant-type"]

        diffs = compare_requests(ours, _capture())
        assert any(d["field"] == "header:grant-type" and d["severity"] == "missing"
                   for d in diffs)

    def test_catches_wrong_header_name_case(self):
        """T-Mobile requires lowercase `sender-id` — casing is contractual."""
        ours = json.loads(json.dumps(_capture()))
        ours["headers"]["names"] = ["Content-Type", "Authorization", "grant-type",
                                    "Sender-Id"]
        diffs = compare_requests(ours, _capture())
        assert any(d["field"] == "header-name-case:sender-id" for d in diffs)

    def test_catches_wrong_ehts_order(self):
        ours = json.loads(json.dumps(_capture()))
        ours["pop"]["ehts_names"] = ["Authorization", "Content-Type", "uri",
                                     "http-method", "body"]
        diffs = compare_requests(ours, _capture())
        ordering = [d for d in diffs if d["severity"] == "ordering"]
        assert ordering and ordering[0]["field"] == "pop.ehts"

    def test_catches_body_hash_mismatch(self):
        ours = _capture(body={"byte_length": 100, "sha256": "b" * 64})
        diffs = compare_requests(ours, _capture())
        assert any(d["field"] == "body.sha256" for d in diffs)
        # Same length + different hash is the whitespace/key-order signature.
        assert not any(d["field"] == "body.byte_length" for d in diffs)

    def test_catches_unexpected_signed_sender_id(self):
        ours = json.loads(json.dumps(_capture()))
        ours["pop"]["ehts_names"].append("sender-id")
        diffs = compare_requests(ours, _capture())
        extra = next(d for d in diffs if d["field"] == "pop.ehts:sender-id")
        assert extra["severity"] == "extra"
        assert "UNSIGNED" in extra["note"]

    def test_flags_unverifiable_body_as_assumption_not_match(self):
        blank = _capture(body={"byte_length": None, "sha256": None})
        diffs = compare_requests(blank, blank)
        assert any(d["severity"] == "assumption" for d in diffs)

    def test_report_renders_without_secrets(self):
        ours = _capture(body={"byte_length": 100, "sha256": "b" * 64})
        from app.integrations.tmobile_contract_compare import render_report
        report = render_report(compare_requests(ours, _capture()))
        assert "body.sha256" in report
        assert "Basic " not in report


# ── 11. Nothing leaks to stdout/logs ────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("debug", ["", "1"])
async def test_evidence_run_logs_no_secrets(
    tmobile_env, monkeypatch, capsys, caplog, debug
):
    monkeypatch.setenv("TMOBILE_TAAP_DEBUG", debug)
    caplog.set_level(logging.DEBUG, logger="app.integrations.tmobile_taap")
    _mock_token(id_token=ID_TOKEN)

    await ev.run_token_only(taap.TMobileTAAPClient())

    captured = capsys.readouterr()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    haystack = f"{captured.out}\n{captured.err}\n{log_text}"

    for secret in (CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ID_TOKEN):
        assert secret not in haystack
    assert "BEGIN PRIVATE KEY" not in haystack
    assert "BEGIN PUBLIC KEY" not in haystack
