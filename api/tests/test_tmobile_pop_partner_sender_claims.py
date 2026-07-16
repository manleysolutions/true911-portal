"""T-Mobile resource-call PoP structure (2026-07-09).

T-Mobile Engineering (Aman) supplied a reference request whose PoP token carried
``ehts="Authorization"`` and nothing else.  Its ``edts`` reproduces exactly as
``base64url(SHA-256("Bearer " + access_token))`` — verified against the paired
access token from the same request.  Neither ``uri``, ``http-method``,
``partner-id`` nor ``sender-id`` appear in T-Mobile's own signed set.

Partner / sender identity is NOT carried in the PoP.  It reaches the wholesale
gateway as the ``senderId`` / ``channelId`` claims that T-Mobile's authorization
server mints into the access token from the consumer key's app registration.
The speculative ``partner-id`` / ``sender-id`` PoP claims and ehts entries added
on 2026-07-07 are therefore removed here; the HTTP headers are kept, since
T-Mobile asked for those explicitly.

No real credentials: the RSA key is generated and HTTP is mocked.  Uses the exact
PIT identifiers (128 / 128) from the failed activation.
"""

from __future__ import annotations

import base64
import hashlib

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

import app.integrations.tmobile_taap as taap

TOKEN_URL = "https://pit-oauth.t-mobile.com/oauth2/v2/tokens"
TOKEN_PATH = "/oauth2/v2/tokens"
BASE_URL = "https://pit-apis.t-mobile.com"
ACTIVATE_PATH = "/wholesale/v1/subscriber/activate"
ACTIVATE_URL = f"{BASE_URL}{ACTIVATE_PATH}"

ACCESS_TOKEN = "tok"

# The exact identifiers from the 2026-07-07 live PIT failure.
PARTNER_ID = "128"
SENDER_ID = "128"


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
    for name, value in {
        "TMOBILE_ENV": "pit",
        "TMOBILE_BASE_URL": BASE_URL,
        "TMOBILE_TOKEN_URL": TOKEN_URL,
        "TMOBILE_CONSUMER_KEY": "ck",
        "TMOBILE_CONSUMER_SECRET": "cs",
        "TMOBILE_PARTNER_ID": PARTNER_ID,
        "TMOBILE_SENDER_ID": SENDER_ID,
        "TMOBILE_ACCOUNT_ID": "",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _claims(pop: str) -> dict:
    return jose_jwt.get_unverified_claims(pop)


def _mock_token():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600}))


async def _send_resource_request() -> httpx.Request:
    """Drive one resource POST and return the request actually sent."""
    _mock_token()
    respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = taap.TMobileTAAPClient()
    await client.post_json(ACTIVATE_PATH, {"iccid": "8901260963132697538"})
    await client.close()
    for call in respx.calls:
        if call.request.url.path == ACTIVATE_PATH:
            return call.request
    raise AssertionError("resource request was not sent")


def _expected_edts(digest_input: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(digest_input.encode()).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


# ── resource-call PoP matches T-Mobile's reference exactly ───────────────────

@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_signs_only_authorization(tmobile_env):
    """ehts is exactly "Authorization" — matching T-Mobile's reference PoP."""
    req = await _send_resource_request()
    assert _claims(req.headers["X-Authorization"])["ehts"] == "Authorization"


@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_edts_hashes_bearer_prefixed_access_token(tmobile_env):
    """edts == base64url(SHA-256("Bearer " + access_token)).

    The "Bearer " prefix (with its trailing space) is part of the digest input.
    Derived by reproducing the edts of T-Mobile's reference PoP from the access
    token issued for that same request.
    """
    req = await _send_resource_request()
    edts = _claims(req.headers["X-Authorization"])["edts"]
    assert edts == _expected_edts(f"Bearer {ACCESS_TOKEN}")
    assert edts != _expected_edts(ACCESS_TOKEN)  # prefix is NOT omitted


@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_carries_no_partner_or_sender_claims(tmobile_env):
    """Partner/sender identity does not travel in the PoP — T-Mobile's
    authorization server mints senderId/channelId into the access token."""
    claims = _claims((await _send_resource_request()).headers["X-Authorization"])
    assert set(claims) == {"iss", "iat", "exp", "jti", "ehts", "edts"}


@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_does_not_sign_uri_or_method(tmobile_env):
    """uri / http-method are absent from the signed set (reference has neither)."""
    ehts = _claims((await _send_resource_request()).headers["X-Authorization"])["ehts"]
    assert "uri" not in ehts
    assert "http-method" not in ehts


# ── HTTP headers still carry the identifiers ─────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_resource_http_headers_still_carry_partner_and_sender(tmobile_env):
    """The HTTP headers are unchanged — identifiers travel on the wire."""
    req = await _send_resource_request()
    assert req.headers["partner-id"] == PARTNER_ID
    assert req.headers["sender-id"] == SENDER_ID


# ── token-endpoint PoP keeps its own (different) signed set ──────────────────

@respx.mock
@pytest.mark.asyncio
async def test_token_endpoint_pop_signs_its_own_set(tmobile_env):
    """The token request PoP signs exactly Content-Type;uri;http-method.

    Distinct from the resource call's ehts="Authorization" — the two flows have
    genuinely different signed sets and this pins that they stay separate.
    sender-id travels on the token request as an UNSIGNED header (Aman,
    2026-07-16) and is covered in detail by tests/test_tmobile_token_sender_id.py.
    """
    _mock_token()
    client = taap.TMobileTAAPClient()
    await client.get_access_token()
    await client.close()

    token_req = next(
        c.request for c in respx.calls if c.request.url.path == TOKEN_PATH
    )
    assert _claims(token_req.headers["X-Authorization"])["ehts"] == (
        "Content-Type;uri;http-method"
    )
    # ...while sender-id still reaches the wire, just unsigned.
    assert token_req.headers["sender-id"] == SENDER_ID


# ── dry-run preview reflects the real signed set ─────────────────────────────

def test_preview_pop_signed_ehts_matches_request(tmobile_env):
    """build_activation_preview() reports the ehts _request() actually signs."""
    preview = taap.TMobileTAAPClient().build_activation_preview(
        "8901260963132697538", market_zip="30346",
        callback_location="https://example.invalid/cb",
    )
    assert preview["pop_signed_ehts"] == ["Authorization"]
