"""T-Mobile resource-call PoP structure — reference PoP Token Builder contract.

T-Mobile Engineering supplied the complete reference builder. The resource PoP
signs, in this exact order::

    Content-Type;Authorization;uri;http-method;body

where ``Authorization`` is the ``Bearer <access_token>`` value, ``uri`` is the
resource URL PATH ONLY, ``http-method`` is the uppercase verb, and ``body`` is
the exact compact JSON string transmitted on the wire.

Partner / sender identity is NOT carried in the PoP. It reaches the wholesale
gateway as the ``senderId`` / ``channelId`` claims that T-Mobile's authorization
server mints into the access token. ``partner-id`` / ``sender-id`` remain
UNSIGNED HTTP headers, which T-Mobile asked for explicitly.

Supersedes the speculative sets from PRs #165–#168 (``ehts="Authorization"``
alone, and ``partner-id``/``sender-id`` PoP claims), which were reconstructed
from partial evidence during GENS-0003 debugging.

No real credentials: the RSA key is generated per-test and HTTP is mocked. Uses
the non-secret PIT identifiers (128 / 128).
"""

from __future__ import annotations

import base64
import hashlib
import json

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
ACTIVATE_PATH = "/wholesale/v1/subscriber/activation"
ACTIVATE_URL = f"{BASE_URL}{ACTIVATE_PATH}"

ACCESS_TOKEN = "tok"

# Non-secret PIT identifiers from the 2026-07-07 live failure.
PARTNER_ID = "128"
SENDER_ID = "128"

RESOURCE_BODY_OBJ = {"iccid": "8901260963132697538"}
# The exact compact string the client must both sign and send.
RESOURCE_BODY_STR = json.dumps(RESOURCE_BODY_OBJ, separators=(",", ":"))

EXPECTED_EHTS = "Content-Type;Authorization;uri;http-method;body"


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


def _mock_token(**extra):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": ACCESS_TOKEN, "expires_in": 3600, **extra}))


async def _send_resource_request() -> httpx.Request:
    """Drive one resource POST and return the request actually sent."""
    _mock_token()
    respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = taap.TMobileTAAPClient()
    await client.post_json(ACTIVATE_PATH, dict(RESOURCE_BODY_OBJ))
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


# ── resource-call PoP matches the reference builder exactly ──────────────────

@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_ehts_is_reference_order(tmobile_env):
    """ehts is exactly Content-Type;Authorization;uri;http-method;body."""
    req = await _send_resource_request()
    assert _claims(req.headers["X-Authorization"])["ehts"] == EXPECTED_EHTS


@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_edts_is_reference_digest(tmobile_env):
    """edts reproduces base64url(SHA-256(concatenated values, no separator)).

    Reproduced independently from the five reference values so a change to the
    order or the canonicalization fails loudly.
    """
    req = await _send_resource_request()
    edts = _claims(req.headers["X-Authorization"])["edts"]
    assert edts == _expected_edts(
        "application/json"
        + f"Bearer {ACCESS_TOKEN}"
        + ACTIVATE_PATH
        + "POST"
        + RESOURCE_BODY_STR
    )
    # The superseded Authorization-only digest must NOT still match.
    assert edts != _expected_edts(f"Bearer {ACCESS_TOKEN}")


@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_signs_bearer_authorization_value(tmobile_env):
    """The signed Authorization value is the Bearer one actually sent."""
    req = await _send_resource_request()
    assert req.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert "Authorization" in _claims(req.headers["X-Authorization"])["ehts"].split(";")


@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_claims_are_exactly_the_reference_set(tmobile_env):
    """Six claims, no iss — partner/sender identity never travels in the PoP."""
    claims = _claims((await _send_resource_request()).headers["X-Authorization"])
    assert set(claims) == {"iat", "exp", "ehts", "edts", "jti", "v"}


@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_signs_uri_path_only_and_uppercase_method(tmobile_env):
    """uri is the path (no scheme/host/query); http-method is uppercase."""
    ehts = _claims((await _send_resource_request()).headers["X-Authorization"])["ehts"]
    assert ehts.split(";")[2:4] == ["uri", "http-method"]
    # Proven by the edts oracle above, which uses the bare path and "POST".


@respx.mock
@pytest.mark.asyncio
async def test_resource_signed_body_is_byte_identical_to_sent_body(tmobile_env):
    """The signed body value and the transmitted content are the SAME string.

    This is the invariant that a whitespace difference would silently break.
    """
    req = await _send_resource_request()
    sent = req.content.decode()
    assert sent == RESOURCE_BODY_STR
    assert " " not in sent  # compact separators — no ", " or ": "
    edts = _claims(req.headers["X-Authorization"])["edts"]
    assert edts == _expected_edts(
        "application/json" + f"Bearer {ACCESS_TOKEN}" + ACTIVATE_PATH + "POST" + sent
    )


def test_body_whitespace_change_changes_the_signature_input(signing_key):
    """Negative control: non-compact JSON produces a DIFFERENT edts.

    Proves the body genuinely participates in the digest, so a future regression
    that serializes with default spaces cannot go unnoticed.
    """
    compact = json.dumps(RESOURCE_BODY_OBJ, separators=(",", ":"))
    spaced = json.dumps(RESOURCE_BODY_OBJ)  # default ", " / ": "
    assert compact != spaced

    def _edts_for(body: str) -> str:
        pop = taap.create_api_pop_token(
            content_type="application/json",
            authorization=f"Bearer {ACCESS_TOKEN}",
            uri=ACTIVATE_PATH,
            http_method="POST",
            body=body,
        )
        return _claims(pop)["edts"]

    assert _edts_for(compact) != _edts_for(spaced)


# ── HTTP headers still carry the identifiers (unsigned) ──────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_resource_http_headers_still_carry_partner_and_sender(tmobile_env):
    """The HTTP headers are unchanged — identifiers travel on the wire."""
    req = await _send_resource_request()
    assert req.headers["partner-id"] == PARTNER_ID
    assert req.headers["sender-id"] == SENDER_ID


@respx.mock
@pytest.mark.asyncio
async def test_partner_and_sender_are_absent_from_resource_ehts(tmobile_env):
    """They are unsigned — do not add them without new T-Mobile instruction."""
    ehts = _claims((await _send_resource_request()).headers["X-Authorization"])["ehts"]
    assert "partner-id" not in ehts
    assert "sender-id" not in ehts


# ── token-endpoint PoP signs the same key set, over its own values ───────────

@respx.mock
@pytest.mark.asyncio
async def test_token_endpoint_pop_signs_reference_set(tmobile_env):
    """The OAuth PoP signs the same five keys, over the Basic value and body."""
    _mock_token()
    client = taap.TMobileTAAPClient()
    await client.get_access_token()
    await client.close()

    token_req = next(
        c.request for c in respx.calls if c.request.url.path == TOKEN_PATH
    )
    assert _claims(token_req.headers["X-Authorization"])["ehts"] == EXPECTED_EHTS
    # ...while sender-id still reaches the wire, just unsigned.
    assert token_req.headers["sender-id"] == SENDER_ID


# ── dry-run preview reflects the real signed set ─────────────────────────────

def test_preview_pop_signed_ehts_matches_request(tmobile_env):
    """build_activation_preview() reports the ehts _request() actually signs."""
    preview = taap.TMobileTAAPClient().build_activation_preview(
        "8901260963132697538", market_zip="30346",
        callback_location="https://example.invalid/cb",
    )
    assert preview["pop_signed_ehts"] == EXPECTED_EHTS.split(";")
