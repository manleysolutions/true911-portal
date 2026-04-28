"""Tests for T-Mobile TAAP/PoP token generation and client.

No real T-Mobile credentials needed — all crypto and HTTP are tested
with generated keys and mocked responses.
"""

from __future__ import annotations

import json
import os
import time

import httpx
import pytest
import respx
from jose import jwt as jose_jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from unittest import mock


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_settings(tmp_path):
    """Provide a test RSA key and mock T-Mobile settings."""
    # Generate a test RSA key
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    key_file = tmp_path / "test_private.pem"
    key_file.write_text(pem)

    with mock.patch.multiple(
        "app.config.settings",
        TMOBILE_ENV="pit",
        TMOBILE_BASE_URL="https://pit-apis.t-mobile.com",
        TMOBILE_TOKEN_URL="https://pit-oauth.t-mobile.com/oauth2/v2/tokens",
        TMOBILE_CONSUMER_KEY="test-consumer-key",
        TMOBILE_CONSUMER_SECRET="test-consumer-secret",
        TMOBILE_PARTNER_ID="test-partner",
        TMOBILE_SENDER_ID="test-sender",
        TMOBILE_ACCOUNT_ID="test-account",
        TMOBILE_PRIVATE_KEY_PATH=str(key_file),
        TMOBILE_PRIVATE_KEY_PEM="",
    ):
        yield


# ── Key Loading ─────────────────────────────────────────────────────────────

def test_load_private_key_from_file():
    from app.integrations.tmobile_taap import _load_private_key
    pem = _load_private_key()
    assert "BEGIN PRIVATE KEY" in pem


def test_load_private_key_from_env():
    from app.integrations.tmobile_taap import _load_private_key

    # Generate a test key for env var
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    with mock.patch("app.config.settings.TMOBILE_PRIVATE_KEY_PEM", pem_bytes), \
         mock.patch("app.config.settings.TMOBILE_PRIVATE_KEY_PATH", ""):
        result = _load_private_key()
        assert "BEGIN PRIVATE KEY" in result


def test_load_private_key_missing_raises():
    from app.integrations.tmobile_taap import _load_private_key
    with mock.patch("app.config.settings.TMOBILE_PRIVATE_KEY_PEM", ""), \
         mock.patch("app.config.settings.TMOBILE_PRIVATE_KEY_PATH", ""):
        with pytest.raises(RuntimeError, match="No private key configured"):
            _load_private_key()


# ── PoP Token Generation ───────────────────────────────────────────────────
#
# T-Mobile TAAP uses Apigee's PopTokenBuilder, NOT RFC 9449 DPoP.
# generate_pop_token now takes a single keyword-only ``ehts_headers``
# list of (header_name, header_value) tuples.  The token claims are:
#   iss / iat / exp / jti — standard
#   ehts                  — comma-separated list of header NAMES
#   edts                  — base64url(sha256(values joined by '\n'))
# There is no claims["at"] — that was the older DPoP shape.

import base64
import hashlib


def _expected_edts(headers: list[tuple[str, str]]) -> str:
    """Reproduce the production digest exactly so the test pins the
    canonicalization rule: header values only, joined by '\n'."""
    digest_input = "\n".join(value for _, value in headers).encode("utf-8")
    return (
        base64.urlsafe_b64encode(hashlib.sha256(digest_input).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def test_pop_token_structure():
    from app.integrations.tmobile_taap import generate_pop_token

    headers = [
        ("Authorization", "Basic dGVzdC1jb25zdW1lci1rZXk6dGVzdC1jb25zdW1lci1zZWNyZXQ="),
        ("Content-Type", "application/x-www-form-urlencoded"),
    ]
    pop = generate_pop_token(ehts_headers=headers)
    assert isinstance(pop, str)
    assert len(pop) > 100

    # JWT header
    header = jose_jwt.get_unverified_header(pop)
    assert header["alg"] == "RS256"
    assert header["typ"] == "pop"

    # Claims
    claims = jose_jwt.get_unverified_claims(pop)
    assert claims["iss"] == "test-consumer-key"
    assert "iat" in claims
    assert "exp" in claims
    assert claims["exp"] - claims["iat"] == 120  # 2 minute expiry
    assert "jti" in claims
    assert claims["ehts"] == "Authorization,Content-Type"
    assert claims["edts"] == _expected_edts(headers)
    # The new shape never includes a claims["at"] block (that was DPoP).
    assert "at" not in claims


def test_pop_token_single_header():
    """A single header still produces a valid token; ehts has no comma
    and edts hashes just that one value."""
    from app.integrations.tmobile_taap import generate_pop_token

    headers = [("Authorization", "Bearer test-access-token")]
    pop = generate_pop_token(ehts_headers=headers)
    claims = jose_jwt.get_unverified_claims(pop)
    assert claims["ehts"] == "Authorization"
    assert claims["edts"] == _expected_edts(headers)
    assert "at" not in claims


def test_pop_token_different_headers_produce_different_tokens():
    """Distinct ehts header sets must yield distinct tokens (jti also
    differs, so this is a stronger inequality than just edts)."""
    from app.integrations.tmobile_taap import generate_pop_token

    pop1 = generate_pop_token(
        ehts_headers=[("Authorization", "Bearer aaa")],
    )
    pop2 = generate_pop_token(
        ehts_headers=[("Authorization", "Bearer bbb")],
    )
    assert pop1 != pop2

    claims1 = jose_jwt.get_unverified_claims(pop1)
    claims2 = jose_jwt.get_unverified_claims(pop2)
    assert claims1["edts"] != claims2["edts"]


def test_pop_token_requires_ehts_headers():
    """generate_pop_token is keyword-only and ehts_headers is required;
    callers that forgot to pass it should fail loudly rather than
    sign an empty digest."""
    from app.integrations.tmobile_taap import generate_pop_token

    with pytest.raises(TypeError):
        generate_pop_token()  # type: ignore[call-arg]


def test_pop_token_edts_canonicalization_is_values_only():
    """Pin the canonicalization rule: edts hashes only the header
    values joined by '\\n', NOT 'name=value' pairs and NOT including
    the request body.  Apigee PopTokenBuilder convention."""
    from app.integrations.tmobile_taap import generate_pop_token

    headers = [("X-One", "alpha"), ("X-Two", "beta")]
    pop = generate_pop_token(ehts_headers=headers)
    claims = jose_jwt.get_unverified_claims(pop)

    # Independently compute the digest the same way the test helper does.
    expected = _expected_edts(headers)
    assert claims["edts"] == expected

    # And confirm the alternative ("name=value&name=value") form
    # produces a DIFFERENT digest, so we know the production code
    # isn't accidentally matching that older convention.
    alt_input = "&".join(f"{n}={v}" for n, v in headers).encode("utf-8")
    alt_digest = (
        base64.urlsafe_b64encode(hashlib.sha256(alt_input).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert claims["edts"] != alt_digest


# ── Client Configuration ───────────────────────────────────────────────────

def test_client_is_configured():
    from app.integrations.tmobile_taap import TMobileTAAPClient
    client = TMobileTAAPClient()
    assert client.is_configured is True


def test_client_not_configured():
    from app.integrations.tmobile_taap import TMobileTAAPClient
    with mock.patch("app.config.settings.TMOBILE_CONSUMER_KEY", ""), \
         mock.patch("app.config.settings.TMOBILE_CONSUMER_SECRET", ""):
        client = TMobileTAAPClient()
        assert client.is_configured is False


def test_client_pit_defaults():
    from app.integrations.tmobile_taap import TMobileTAAPClient
    client = TMobileTAAPClient()
    assert "pit-apis" in client.base_url
    assert "pit-oauth" in client.token_url
    assert client.partner_id == "test-partner"
    assert client.account_id == "test-account"


# ── Access Token (mocked HTTP) ─────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_get_access_token():
    from app.integrations.tmobile_taap import TMobileTAAPClient

    respx.post("https://pit-oauth.t-mobile.com/oauth2/v2/tokens").mock(
        return_value=httpx.Response(200, json={
            "access_token": "test-access-token-123",
            "token_type": "Bearer",
            "expires_in": 3600,
        })
    )

    client = TMobileTAAPClient()
    token = await client.get_access_token()
    assert token == "test-access-token-123"
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_access_token_cached():
    from app.integrations.tmobile_taap import TMobileTAAPClient

    route = respx.post("https://pit-oauth.t-mobile.com/oauth2/v2/tokens").mock(
        return_value=httpx.Response(200, json={
            "access_token": "cached-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        })
    )

    client = TMobileTAAPClient()
    t1 = await client.get_access_token()
    t2 = await client.get_access_token()
    assert t1 == t2 == "cached-token"
    assert route.call_count == 1  # only called once
    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_access_token_failure():
    from app.integrations.tmobile_taap import TMobileTAAPClient

    respx.post("https://pit-oauth.t-mobile.com/oauth2/v2/tokens").mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"})
    )

    client = TMobileTAAPClient()
    with pytest.raises(RuntimeError, match="token request failed"):
        await client.get_access_token()
    await client.close()


# ── API Call (mocked HTTP) ──────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_subscriber_inquiry():
    from app.integrations.tmobile_taap import TMobileTAAPClient

    # Mock token endpoint
    respx.post("https://pit-oauth.t-mobile.com/oauth2/v2/tokens").mock(
        return_value=httpx.Response(200, json={
            "access_token": "test-token",
            "expires_in": 3600,
        })
    )

    # Mock subscriber inquiry
    respx.post("https://pit-apis.t-mobile.com/wholesale/subscriber/v2/inquiry").mock(
        return_value=httpx.Response(200, json={
            "msisdn": "12125551234",
            "status": "active",
            "iccid": "8901234567890123456",
        })
    )

    client = TMobileTAAPClient()
    result = await client.subscriber_inquiry("12125551234")
    assert result["msisdn"] == "12125551234"
    assert result["status"] == "active"

    # Verify the API call included proper headers.  The X-Authorization
    # value is the bare PoP JWT (no "PoP " prefix) — that is the format
    # T-Mobile's PIT validator accepts; an earlier "PoP " prefix was
    # tried and removed.  Assert it's a JWT (three base64url segments).
    api_call = respx.calls[-1]
    assert "Authorization" in api_call.request.headers
    assert api_call.request.headers["Authorization"].startswith("Bearer ")
    assert "X-Authorization" in api_call.request.headers
    x_auth = api_call.request.headers["X-Authorization"]
    assert x_auth.count(".") == 2, f"X-Authorization not a JWT: {x_auth!r}"
    assert all(seg for seg in x_auth.split(".")), "JWT segments must be non-empty"
    assert api_call.request.headers.get("X-Partner-Id") == "test-partner"
    assert api_call.request.headers.get("X-Sender-Id") == "test-sender"
    assert api_call.request.headers.get("X-Account-Id") == "test-account"
    assert "X-Correlation-Id" in api_call.request.headers

    await client.close()


@respx.mock
@pytest.mark.asyncio
async def test_api_error_handling():
    from app.integrations.tmobile_taap import TMobileTAAPClient

    respx.post("https://pit-oauth.t-mobile.com/oauth2/v2/tokens").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )
    respx.post("https://pit-apis.t-mobile.com/wholesale/subscriber/v2/inquiry").mock(
        return_value=httpx.Response(404, json={"error": "subscriber not found"})
    )

    client = TMobileTAAPClient()
    with pytest.raises(RuntimeError, match="T-Mobile API error"):
        await client.subscriber_inquiry("12125550000")
    await client.close()
