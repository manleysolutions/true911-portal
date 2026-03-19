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

def test_pop_token_structure():
    from app.integrations.tmobile_taap import generate_pop_token

    pop = generate_pop_token(
        uri="https://pit-oauth.t-mobile.com/oauth2/v2/tokens",
        http_method="POST",
        body="grant_type=client_credentials",
    )
    assert isinstance(pop, str)
    assert len(pop) > 100

    # Decode header
    header = jose_jwt.get_unverified_header(pop)
    assert header["alg"] == "RS256"
    assert header["typ"] == "pop"

    # Decode claims
    claims = jose_jwt.get_unverified_claims(pop)
    assert claims["iss"] == "test-consumer-key"
    assert "iat" in claims
    assert "exp" in claims
    assert claims["exp"] - claims["iat"] == 120  # 2 minute expiry
    assert "jti" in claims
    assert claims["at"]["htm"] == "POST"
    assert "htu" in claims["at"]
    assert "ath" in claims["at"]  # body hash present


def test_pop_token_no_body():
    from app.integrations.tmobile_taap import generate_pop_token

    pop = generate_pop_token(
        uri="https://pit-apis.t-mobile.com/wholesale/subscriber/v2/inquiry",
        http_method="GET",
    )
    claims = jose_jwt.get_unverified_claims(pop)
    assert claims["at"]["htm"] == "GET"
    assert "ath" not in claims["at"]  # no body = no hash


def test_pop_token_different_uris_produce_different_tokens():
    from app.integrations.tmobile_taap import generate_pop_token

    pop1 = generate_pop_token(uri="https://example.com/a", http_method="GET")
    pop2 = generate_pop_token(uri="https://example.com/b", http_method="GET")
    assert pop1 != pop2


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

    # Verify the API call included proper headers
    api_call = respx.calls[-1]
    assert "Authorization" in api_call.request.headers
    assert api_call.request.headers["Authorization"].startswith("Bearer ")
    assert "X-Authorization" in api_call.request.headers
    assert api_call.request.headers["X-Authorization"].startswith("PoP ")
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
