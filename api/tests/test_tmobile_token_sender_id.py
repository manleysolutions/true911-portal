"""T-Mobile OAuth token request — sender-id, grant-type, and the signed set.

``sender-id`` is an **unsigned OAuth request HTTP header** (Aman, confirmed). It
travels as the exact lowercase header ``sender-id: 128`` and must **not** appear
in the PoP ``ehts``.

Per T-Mobile's supplied reference builder, the OAuth PoP signs::

    Content-Type;Authorization;uri;http-method;body

over the Basic Authorization value, the token URL PATH, "POST", and the exact
compact body. The grant type is an unsigned ``grant-type`` header, NOT a body
property.

Supersedes PRs #165–#168, which pinned ``Content-Type;uri;http-method`` and
asserted Authorization was excluded — both reconstructed from partial evidence.

No real credentials: the RSA key is generated per-test and HTTP is mocked.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

import app.integrations.tmobile_taap as taap

# The real PIT token URL — pinned here so a change to it fails this test.
TOKEN_URL = "https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens"
TOKEN_PATH = "/oauth2/v1/tokens"

SENDER_ID = "128"
PARTNER_ID = "128"

# The reference OAuth PoP signed set, in exact order.
EXPECTED_EHTS = "Content-Type;Authorization;uri;http-method;body"

# Distinctive sentinels so a substring search over stdout/logs is unambiguous.
CONSUMER_KEY = "TM_TEST_CK_HG7XQ2"
CONSUMER_SECRET = "TM_TEST_CS_PL3JR9"
BASIC_B64 = base64.b64encode(
    f"{CONSUMER_KEY}:{CONSUMER_SECRET}".encode("utf-8")
).decode("ascii")

ACCESS_TOKEN = "redacted-token-not-real"


@pytest.fixture
def signing_key(monkeypatch):
    """Throwaway RSA key wired into the PoP signer (no env / no secrets)."""
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
    """PIT settings with sender-id configured."""
    for name, value in {
        "TMOBILE_ENV": "pit",
        "TMOBILE_TOKEN_URL": TOKEN_URL,
        "TMOBILE_CONSUMER_KEY": CONSUMER_KEY,
        "TMOBILE_CONSUMER_SECRET": CONSUMER_SECRET,
        "TMOBILE_PARTNER_ID": PARTNER_ID,
        "TMOBILE_SENDER_ID": SENDER_ID,
        "TMOBILE_ACCOUNT_ID": "",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _mock_token():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600}))


async def _send_token_request(**client_kwargs) -> httpx.Request:
    """Drive one OAuth token POST and return the request actually sent."""
    _mock_token()
    client = taap.TMobileTAAPClient(**client_kwargs)
    await client.get_access_token()
    await client.close()
    for call in respx.calls:
        if call.request.url.path == TOKEN_PATH:
            return call.request
    raise AssertionError("token request was not sent")


def _claims(pop: str) -> dict:
    return jose_jwt.get_unverified_claims(pop)


def _expected_edts(digest_input: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(digest_input.encode()).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


# ── 1. sender-id travels as a wire header ────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_token_request_sends_sender_id_header(tmobile_env):
    """Aman's ask: the OAuth token request must carry sender-id: 128."""
    req = await _send_token_request()
    assert req.headers["sender-id"] == SENDER_ID


@respx.mock
@pytest.mark.asyncio
async def test_sender_id_header_name_is_lowercase_on_the_wire(tmobile_env):
    """T-Mobile spells the header lowercase — assert the raw wire bytes.

    httpx header lookup is case-insensitive, so read raw_headers to prove the
    literal name sent is b"sender-id".
    """
    req = await _send_token_request()
    raw_names = [name for name, _ in req.headers.raw]
    assert b"sender-id" in raw_names


@respx.mock
@pytest.mark.asyncio
async def test_grant_type_is_an_unsigned_wire_header(tmobile_env):
    """The grant type moved from the JSON body to a `grant-type` HTTP header."""
    req = await _send_token_request()
    assert req.headers["grant-type"] == "client_credentials"
    assert "grant-type" not in _claims(req.headers["X-Authorization"])["ehts"]


@respx.mock
@pytest.mark.asyncio
async def test_oauth_body_is_compact_and_cnf_only(tmobile_env):
    """Body is exactly {"cnf":"..."} — compact, and with no grant_type."""
    req = await _send_token_request()
    body = req.content.decode()

    assert list(json.loads(body)) == ["cnf"], "body must carry cnf and nothing else"
    assert "grant_type" not in body
    # Compact separators: no ", " or ": " anywhere.
    assert body.startswith('{"cnf":"')
    assert body.endswith('"}')
    assert ", " not in body and '": ' not in body


@respx.mock
@pytest.mark.asyncio
async def test_token_url_is_unchanged(tmobile_env):
    """DNS stays put — T-Mobile routes on the header, not a new hostname."""
    req = await _send_token_request()
    assert str(req.url) == TOKEN_URL


@respx.mock
@pytest.mark.asyncio
async def test_token_request_still_sends_basic_authorization(tmobile_env):
    """Authorization: Basic remains a wire header (just not a signed one)."""
    req = await _send_token_request()
    assert req.headers["Authorization"] == f"Basic {BASIC_B64}"


# ── 2. sender-id is UNSIGNED — it stays out of the token PoP ehts ────────────

@respx.mock
@pytest.mark.asyncio
async def test_token_pop_ehts_excludes_sender_id(tmobile_env):
    """sender-id is unsigned — it must not appear in the token PoP ehts."""
    req = await _send_token_request()
    assert "sender-id" not in _claims(req.headers["X-Authorization"])["ehts"]


@respx.mock
@pytest.mark.asyncio
async def test_token_pop_ehts_is_the_reference_set(tmobile_env):
    """The signed set is pinned — even with sender-id configured."""
    req = await _send_token_request()
    assert _claims(req.headers["X-Authorization"])["ehts"] == EXPECTED_EHTS


@respx.mock
@pytest.mark.asyncio
async def test_token_pop_edts_covers_reference_values_not_sender_id(tmobile_env):
    """edts hashes the five reference values — the sender-id value is absent.

    Reproduced independently here so a silent change to either the ehts order
    or the digest canonicalization fails loudly.
    """
    req = await _send_token_request()
    edts = _claims(req.headers["X-Authorization"])["edts"]
    body = req.content.decode()
    assert edts == _expected_edts(
        "application/json" + f"Basic {BASIC_B64}" + TOKEN_PATH + "POST" + body
    )
    # A digest that appended the sender-id value must NOT match.
    assert edts != _expected_edts(
        "application/json" + f"Basic {BASIC_B64}" + TOKEN_PATH + "POST" + body
        + SENDER_ID
    )


@respx.mock
@pytest.mark.asyncio
async def test_token_pop_signs_the_basic_authorization_value(tmobile_env):
    """The reference OAuth PoP DOES sign Authorization (the Basic value).

    This reverses the superseded PR #165–#168 finding that Authorization was
    excluded from the token PoP.
    """
    ehts = _claims((await _send_token_request()).headers["X-Authorization"])["ehts"]
    assert "Authorization" in ehts.split(";")


# ── 3. empty / padded sender-id handling ─────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_token_request_omits_sender_id_when_unset(tmobile_env, monkeypatch):
    """An empty sender id omits the HTTP header; the ehts set is unaffected."""
    monkeypatch.setattr("app.config.settings.TMOBILE_SENDER_ID", "")
    req = await _send_token_request()

    assert "sender-id" not in req.headers
    claims = _claims(req.headers["X-Authorization"])
    assert claims["ehts"] == EXPECTED_EHTS
    assert claims["edts"] == _expected_edts(
        "application/json" + f"Basic {BASIC_B64}" + TOKEN_PATH + "POST"
        + req.content.decode()
    )


@respx.mock
@pytest.mark.asyncio
async def test_whitespace_only_sender_id_is_treated_as_unset(tmobile_env, monkeypatch):
    """A stray-whitespace env value must not send a blank header."""
    monkeypatch.setattr("app.config.settings.TMOBILE_SENDER_ID", "   ")
    req = await _send_token_request()

    assert "sender-id" not in req.headers
    assert _claims(req.headers["X-Authorization"])["ehts"] == EXPECTED_EHTS


@respx.mock
@pytest.mark.asyncio
async def test_sender_id_whitespace_is_stripped_before_sending(tmobile_env):
    """A padded env value must reach the wire stripped — "128", not "  128  ".

    T-Mobile routes on the exact header value, so surrounding whitespace from a
    .env file must never travel.
    """
    req = await _send_token_request(sender_id=f"  {SENDER_ID}  ")
    assert req.headers["sender-id"] == SENDER_ID
    # Still unsigned regardless of the padding.
    assert _claims(req.headers["X-Authorization"])["ehts"] == EXPECTED_EHTS


# ── 4. no secrets or tokens leak to stdout / logs ────────────────────────────

@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("debug", ["", "1"])
async def test_no_secrets_logged_when_sending_sender_id(
    tmobile_env, monkeypatch, capsys, caplog, debug
):
    """Adding sender-id must not widen the credential-logging surface.

    Runs with TMOBILE_TAAP_DEBUG both off and on: the consumer key/secret, the
    reversible Base64 Basic blob, and the issued access token must never appear
    in stdout, stderr, or log records.  sender-id itself is a non-secret partner
    identifier, so no assertion forbids it.
    """
    monkeypatch.setenv("TMOBILE_TAAP_DEBUG", debug)
    caplog.set_level(logging.DEBUG, logger="app.integrations.tmobile_taap")

    await _send_token_request()

    captured = capsys.readouterr()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    haystack = f"{captured.out}\n{captured.err}\n{log_text}"

    assert CONSUMER_KEY not in haystack, "consumer_key leaked to stdout/logs"
    assert CONSUMER_SECRET not in haystack, "consumer_secret leaked to stdout/logs"
    assert BASIC_B64 not in haystack, "Base64(key:secret) leaked — reversible"
    assert f"Basic {BASIC_B64}" not in haystack, "Basic header leaked"
    assert ACCESS_TOKEN not in haystack, "issued access token leaked to stdout/logs"
