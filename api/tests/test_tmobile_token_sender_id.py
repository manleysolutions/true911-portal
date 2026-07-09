"""T-Mobile OAuth token request carries sender-id (2026-07-09).

T-Mobile Engineering (Aman, 2026-07-09):

    "Please pass the sender-id from your end.  You can continue to use
    https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens as DNS and we
    handle the backend routing internally."

So the token request now sends ``sender-id`` as a wire header AND appends it to
the signed PoP ``ehts`` set (``Content-Type;uri;http-method;sender-id``), while
the token URL is untouched and ``Authorization: Basic`` stays an unsigned wire
header.  When ``TMOBILE_SENDER_ID`` is unset, the request is byte-for-byte what
it was before this change.

No real credentials: the RSA key is generated per-test and HTTP is mocked.
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

# The real PIT token URL — pinned here so a change to it fails this test.
TOKEN_URL = "https://wholesaleapi-test.t-mobile.com/oauth2/v1/tokens"
TOKEN_PATH = "/oauth2/v1/tokens"

SENDER_ID = "128"
PARTNER_ID = "128"

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
    """Aman's ask: the OAuth token request must carry sender-id."""
    req = await _send_token_request()
    assert req.headers["sender-id"] == SENDER_ID


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


# ── 2. sender-id is inside the signed PoP ehts ───────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_token_pop_ehts_includes_sender_id(tmobile_env):
    """ehts == "Content-Type;uri;http-method;sender-id" — sender-id last."""
    req = await _send_token_request()
    assert _claims(req.headers["X-Authorization"])["ehts"] == (
        "Content-Type;uri;http-method;sender-id"
    )


@respx.mock
@pytest.mark.asyncio
async def test_token_pop_edts_covers_sender_id_value(tmobile_env):
    """edts hashes the ehts VALUES in order, with the sender-id value last.

    Reproduced independently here so a silent change to either the ehts order
    or the digest canonicalization fails loudly.
    """
    req = await _send_token_request()
    edts = _claims(req.headers["X-Authorization"])["edts"]
    assert edts == _expected_edts(
        "application/json" + TOKEN_PATH + "POST" + SENDER_ID
    )
    # And the pre-change digest (no sender-id) must NOT still match.
    assert edts != _expected_edts("application/json" + TOKEN_PATH + "POST")


@respx.mock
@pytest.mark.asyncio
async def test_token_pop_does_not_sign_authorization(tmobile_env):
    """Basic auth stays out of the signed set — matches T-Mobile's reference."""
    ehts = _claims((await _send_token_request()).headers["X-Authorization"])["ehts"]
    assert "Authorization" not in ehts


# ── 3. behavior is unchanged when sender-id is not configured ────────────────

@respx.mock
@pytest.mark.asyncio
async def test_token_request_omits_sender_id_when_unset(tmobile_env, monkeypatch):
    """No sender-id configured -> no header, and the ehts set is the old one."""
    monkeypatch.setattr("app.config.settings.TMOBILE_SENDER_ID", "")
    req = await _send_token_request()

    assert "sender-id" not in req.headers
    claims = _claims(req.headers["X-Authorization"])
    assert claims["ehts"] == "Content-Type;uri;http-method"
    assert claims["edts"] == _expected_edts("application/json" + TOKEN_PATH + "POST")


@respx.mock
@pytest.mark.asyncio
async def test_whitespace_only_sender_id_is_treated_as_unset(tmobile_env, monkeypatch):
    """A stray-whitespace env value must not sign an empty ehts entry."""
    monkeypatch.setattr("app.config.settings.TMOBILE_SENDER_ID", "   ")
    req = await _send_token_request()

    assert "sender-id" not in req.headers
    assert _claims(req.headers["X-Authorization"])["ehts"] == (
        "Content-Type;uri;http-method"
    )


@respx.mock
@pytest.mark.asyncio
async def test_sender_id_is_stripped_before_signing_and_sending(tmobile_env):
    """The wire header and the edts digest use the SAME stripped value.

    A padded env var would otherwise sign one value and send another, which
    T-Mobile's PoP validator rejects.
    """
    req = await _send_token_request(sender_id=f"  {SENDER_ID}  ")
    assert req.headers["sender-id"] == SENDER_ID
    assert _claims(req.headers["X-Authorization"])["edts"] == _expected_edts(
        "application/json" + TOKEN_PATH + "POST" + SENDER_ID
    )


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
