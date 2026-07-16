"""Golden tests for T-Mobile's supplied PoP Token Builder contract.

These pin the authoritative wire contract supplied by T-Mobile Engineering, so
the drift that produced the GENS-0003 ("Invalid partnerID / Empty
PartnerID/SenderID") debugging cycle cannot recur.

Authoritative JWT::

    header  {"alg": "RS256", "typ": "JWT"}
    payload {"iat", "exp" (= iat + 60), "ehts", "edts", "jti", "v": "1"}   # no iss

edts rules: preserve ehts insertion order, concatenate the values directly with
NO separator, hash the concatenated UTF-8 bytes ONCE with SHA-256, base64url,
strip "=" padding. The body is NOT separately hashed — its value is the exact
request-body string sent on the wire.

Both the OAuth and the resource PoP sign, in this order::

    Content-Type;Authorization;uri;http-method;body

No real credentials appear here: the RSA key is generated per-test, and the
golden vector uses the literal placeholders "Basic TEST" / "TEST_PUBLIC_KEY"
supplied with the reference.
"""

from __future__ import annotations

import base64
import hashlib
import logging

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

import app.integrations.tmobile_taap as taap

TOKEN_URL = "https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens"
TOKEN_PATH = "/oauth2/v1/tokens"
BASE_URL = "https://wholesaleapi-test.t-mobile.com"
RESOURCE_PATH = "/wholesale/v1/subscriber/inquiry"

EXPECTED_EHTS = "Content-Type;Authorization;uri;http-method;body"

# Distinctive fakes so a substring search over stdout/logs is unambiguous.
CONSUMER_KEY = "TM_TEST_CK_HG7XQ2"
CONSUMER_SECRET = "TM_TEST_CS_PL3JR9"
BASIC_B64 = base64.b64encode(
    f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode("utf-8")
).decode("ascii")
ACCESS_TOKEN = "redacted-token-not-real"
ID_TOKEN = "redacted-id-token-not-real"


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
        "TMOBILE_ACCOUNT_ID": "acct-1",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _claims(pop: str) -> dict:
    return jose_jwt.get_unverified_claims(pop)


def _header(pop: str) -> dict:
    return jose_jwt.get_unverified_header(pop)


def _b64url_sha256(text: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(text.encode("utf-8")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def _mock_token(**extra):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600, **extra}))


# ── A. Generic PoP JWT structure ─────────────────────────────────────────────

class TestPopJwtStructure:
    def test_jwt_header_is_exactly_rs256_jwt(self, signing_key):
        pop = taap.generate_pop_token(ehts_headers=[("uri", "/x")])
        assert _header(pop) == {"alg": "RS256", "typ": "JWT"}

    def test_payload_has_exactly_the_reference_claims(self, signing_key):
        claims = _claims(taap.generate_pop_token(ehts_headers=[("uri", "/x")]))
        assert set(claims) == {"iat", "exp", "ehts", "edts", "jti", "v"}

    def test_no_iss_claim(self, signing_key):
        """iss previously carried the consumer key into a decodable JWT."""
        assert "iss" not in _claims(taap.generate_pop_token(ehts_headers=[("uri", "/x")]))

    def test_v_claim_is_string_one(self, signing_key):
        assert _claims(taap.generate_pop_token(ehts_headers=[("uri", "/x")]))["v"] == "1"

    def test_lifetime_is_exactly_60_seconds(self, signing_key):
        claims = _claims(taap.generate_pop_token(ehts_headers=[("uri", "/x")]))
        assert claims["exp"] - claims["iat"] == 60

    def test_signature_verifies_rs256_round_trip(self, signing_key):
        pop = taap.generate_pop_token(ehts_headers=[("uri", "/x")])
        pub_pem = (
            serialization.load_pem_private_key(signing_key.encode(), password=None)
            .public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        decoded = jose_jwt.decode(
            pop, pub_pem, algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False},
        )
        assert decoded["v"] == "1"


# ── B. OAuth PoP golden vector (supplied reference values) ───────────────────

class TestOauthPopGoldenVector:
    """The exact vector supplied with the reference implementation."""

    def test_oauth_ehts_and_edts_match_the_supplied_vector(self, signing_key):
        pop = taap.create_oauth_pop_token(
            content_type="application/json",
            authorization="Basic TEST",
            uri="/oauth2/v1/tokens",
            http_method="POST",
            body='{"cnf":"TEST_PUBLIC_KEY"}',
        )
        claims = _claims(pop)
        assert claims["ehts"] == EXPECTED_EHTS
        assert claims["edts"] == _b64url_sha256(
            "application/json"
            + "Basic TEST"
            + "/oauth2/v1/tokens"
            + "POST"
            + '{"cnf":"TEST_PUBLIC_KEY"}'
        )

    def test_body_is_not_separately_hashed_before_concatenation(self, signing_key):
        """A builder that pre-hashed the body would produce a different edts."""
        body = '{"cnf":"TEST_PUBLIC_KEY"}'
        pop = taap.create_oauth_pop_token(
            content_type="application/json", authorization="Basic TEST",
            uri="/oauth2/v1/tokens", http_method="POST", body=body,
        )
        pre_hashed = _b64url_sha256(
            "application/json" + "Basic TEST" + "/oauth2/v1/tokens" + "POST"
            + hashlib.sha256(body.encode()).hexdigest()
        )
        assert _claims(pop)["edts"] != pre_hashed

    def test_values_are_concatenated_with_no_separator(self, signing_key):
        """A separator-joined digest must NOT match."""
        parts = ["application/json", "Basic TEST", "/oauth2/v1/tokens", "POST",
                 '{"cnf":"TEST_PUBLIC_KEY"}']
        pop = taap.create_oauth_pop_token(
            content_type=parts[0], authorization=parts[1], uri=parts[2],
            http_method=parts[3], body=parts[4],
        )
        assert _claims(pop)["edts"] != _b64url_sha256(";".join(parts))
        assert _claims(pop)["edts"] != _b64url_sha256("\n".join(parts))


# ── D. ID token / X-Auth-Originator ──────────────────────────────────────────

class TestIdToken:
    @respx.mock
    @pytest.mark.asyncio
    async def test_id_token_is_cached_and_replayed_as_x_auth_originator(self, tmobile_env):
        _mock_token(id_token=ID_TOKEN)
        respx.post(f"{BASE_URL}{RESOURCE_PATH}").mock(
            return_value=httpx.Response(200, json={"ok": True}))

        client = taap.TMobileTAAPClient()
        await client.post_json(RESOURCE_PATH, {"msisdn": "12125551234"})
        assert client._id_token == ID_TOKEN  # cached alongside the access token
        await client.close()

        req = next(c.request for c in respx.calls
                   if c.request.url.path == RESOURCE_PATH)
        assert req.headers["X-Auth-Originator"] == ID_TOKEN

    @respx.mock
    @pytest.mark.asyncio
    async def test_header_omitted_when_no_id_token_returned(self, tmobile_env):
        _mock_token()  # PIT may not return one
        respx.post(f"{BASE_URL}{RESOURCE_PATH}").mock(
            return_value=httpx.Response(200, json={"ok": True}))

        client = taap.TMobileTAAPClient()
        await client.post_json(RESOURCE_PATH, {"msisdn": "12125551234"})
        await client.close()

        req = next(c.request for c in respx.calls
                   if c.request.url.path == RESOURCE_PATH)
        assert "X-Auth-Originator" not in req.headers

    @respx.mock
    @pytest.mark.asyncio
    async def test_id_token_is_not_signed_into_the_resource_pop(self, tmobile_env):
        """X-Auth-Originator is an unsigned header, like partner-id/sender-id."""
        _mock_token(id_token=ID_TOKEN)
        respx.post(f"{BASE_URL}{RESOURCE_PATH}").mock(
            return_value=httpx.Response(200, json={"ok": True}))

        client = taap.TMobileTAAPClient()
        await client.post_json(RESOURCE_PATH, {"msisdn": "12125551234"})
        await client.close()

        req = next(c.request for c in respx.calls
                   if c.request.url.path == RESOURCE_PATH)
        assert _claims(req.headers["X-Authorization"])["ehts"] == EXPECTED_EHTS


# ── E. No-secret guarantees ──────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("debug", ["", "1"])
async def test_no_secret_material_reaches_stdout_or_logs(
    tmobile_env, monkeypatch, capsys, caplog, debug
):
    """Nothing credential-bearing may be printed or logged, debug off OR on."""
    monkeypatch.setenv("TMOBILE_TAAP_DEBUG", debug)
    caplog.set_level(logging.DEBUG, logger="app.integrations.tmobile_taap")

    _mock_token(id_token=ID_TOKEN)
    respx.post(f"{BASE_URL}{RESOURCE_PATH}").mock(
        return_value=httpx.Response(200, json={"ok": True}))

    client = taap.TMobileTAAPClient()
    await client.post_json(RESOURCE_PATH, {"msisdn": "12125551234"})
    await client.close()

    captured = capsys.readouterr()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    haystack = f"{captured.out}\n{captured.err}\n{log_text}"

    assert CONSUMER_KEY not in haystack, "consumer key leaked"
    assert CONSUMER_SECRET not in haystack, "consumer secret leaked"
    assert BASIC_B64 not in haystack, "Base64(key:secret) leaked — reversible"
    assert f"Basic {BASIC_B64}" not in haystack, "Basic Authorization header leaked"
    assert ACCESS_TOKEN not in haystack, "access token leaked"
    assert ID_TOKEN not in haystack, "id_token leaked"
    assert "BEGIN PRIVATE KEY" not in haystack, "private key leaked"
    assert "BEGIN PUBLIC KEY" not in haystack, "cnf public key leaked"

    # The X-Authorization PoP JWT itself must never be printed whole.
    for call in respx.calls:
        pop = call.request.headers.get("X-Authorization")
        if pop:
            assert pop not in haystack, "X-Authorization PoP JWT leaked"
