"""T-Mobile PoP partner-id / sender-id in signed claims + ehts (2026-07-07).

T-Mobile Engineering (Aman) reviewed the live PIT activation and reported that
the sender-id was NOT present in the PoP auth claims — the implementation sent
partner-id / sender-id only as HTTP headers. The activation failed with
``400 GENS-0003 "Invalid partnerID"``.

Fix under test: for RESOURCE calls, partner-id / sender-id (when configured) are
now included in BOTH:
  * the signed ``ehts`` set — ``Authorization;uri;http-method;partner-id;sender-id``
  * the PoP JWT claims — ``partner-id`` / ``sender-id``
while the HTTP headers, the token-endpoint PoP, and the no-extra-claims PoP shape
are all left unchanged.

No real credentials: the RSA key is generated and HTTP is mocked. Uses the exact
PIT identifiers (128 / 128) from the failed activation.
"""

from __future__ import annotations

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
        200, json={"access_token": "tok", "expires_in": 3600}))


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


# ── generate_pop_token(extra_claims=...) ─────────────────────────────────────

def test_generate_pop_token_includes_extra_claims(signing_key):
    """extra_claims are merged into the signed PoP payload."""
    pop = taap.generate_pop_token(
        ehts_headers=[
            ("Authorization", "Bearer x"),
            ("uri", "/wholesale/v1/subscriber/activate"),
            ("http-method", "POST"),
        ],
        extra_claims={"partner-id": PARTNER_ID, "sender-id": SENDER_ID},
    )
    claims = _claims(pop)
    assert claims["partner-id"] == PARTNER_ID
    assert claims["sender-id"] == SENDER_ID


def test_generate_pop_token_without_extra_claims_unchanged(signing_key):
    """Omitting extra_claims yields exactly the standard claim set — the
    pre-existing token-generation behavior is unchanged."""
    pop = taap.generate_pop_token(
        ehts_headers=[
            ("Content-Type", "application/json"),
            ("uri", TOKEN_PATH),
            ("http-method", "POST"),
        ],
    )
    claims = _claims(pop)
    assert set(claims) == {"iss", "iat", "exp", "jti", "ehts", "edts"}
    assert "partner-id" not in claims
    assert "sender-id" not in claims


def test_generate_pop_token_extra_claims_cannot_clobber_reserved(signing_key):
    """Reserved claims are protected — extra_claims can never overwrite the
    standard PoP shape (ehts/edts/iss/…)."""
    pop = taap.generate_pop_token(
        ehts_headers=[("Authorization", "Bearer x")],
        extra_claims={"ehts": "HIJACKED", "edts": "HIJACKED", "partner-id": PARTNER_ID},
    )
    claims = _claims(pop)
    assert claims["ehts"] == "Authorization"          # not overwritten
    assert claims["edts"] != "HIJACKED"                # not overwritten
    assert claims["partner-id"] == PARTNER_ID          # non-reserved merged


# ── resource-call PoP (both identifiers configured) ──────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_ehts_signs_partner_and_sender(tmobile_env):
    req = await _send_resource_request()
    ehts = _claims(req.headers["X-Authorization"])["ehts"]
    assert ehts == "Authorization;uri;http-method;partner-id;sender-id"


@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_claims_include_partner_and_sender(tmobile_env):
    req = await _send_resource_request()
    claims = _claims(req.headers["X-Authorization"])
    assert claims["partner-id"] == PARTNER_ID
    assert claims["sender-id"] == SENDER_ID


@respx.mock
@pytest.mark.asyncio
async def test_resource_http_headers_still_carry_partner_and_sender(tmobile_env):
    """The HTTP headers are unchanged — identifiers travel on the wire too."""
    req = await _send_resource_request()
    assert req.headers["partner-id"] == PARTNER_ID
    assert req.headers["sender-id"] == SENDER_ID


# ── token-endpoint PoP is UNCHANGED ──────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_token_endpoint_pop_unchanged(tmobile_env):
    """The token request PoP still signs exactly Content-Type;uri;http-method
    and carries NO partner-id / sender-id claims — only resource calls changed."""
    _mock_token()
    client = taap.TMobileTAAPClient()
    await client.get_access_token()
    await client.close()

    token_req = next(
        c.request for c in respx.calls if c.request.url.path == TOKEN_PATH
    )
    claims = _claims(token_req.headers["X-Authorization"])
    assert claims["ehts"] == "Content-Type;uri;http-method"
    assert "partner-id" not in claims
    assert "sender-id" not in claims


# ── partial / no configuration ───────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_resource_pop_omits_identifiers_when_unconfigured(monkeypatch, signing_key):
    """With neither identifier configured, the signed ehts is unchanged from
    the historical Authorization;uri;http-method set."""
    for name, value in {
        "TMOBILE_ENV": "pit",
        "TMOBILE_BASE_URL": BASE_URL,
        "TMOBILE_TOKEN_URL": TOKEN_URL,
        "TMOBILE_CONSUMER_KEY": "ck",
        "TMOBILE_CONSUMER_SECRET": "cs",
        "TMOBILE_PARTNER_ID": "",
        "TMOBILE_SENDER_ID": "",
        "TMOBILE_ACCOUNT_ID": "",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)

    req = await _send_resource_request()
    claims = _claims(req.headers["X-Authorization"])
    assert claims["ehts"] == "Authorization;uri;http-method"
    assert "partner-id" not in claims
    assert "sender-id" not in claims
