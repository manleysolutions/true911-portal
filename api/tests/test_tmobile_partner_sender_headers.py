"""T-Mobile partner/sender header-name compliance (Aman, 2026-06).

T-Mobile requires the lowercase header names ``partner-id`` / ``sender-id``
(previously sent as ``X-Partner-Id`` / ``X-Sender-Id``, which T-Mobile rejected
with ``400 GENS-0003 Invalid partnerID``).

Proves:
  * ``partner-id`` is sent, sourced from ``TMOBILE_PARTNER_ID``
  * ``sender-id`` is sent, sourced from ``TMOBILE_SENDER_ID``
  * the old ``X-Partner-Id`` / ``X-Sender-Id`` names are NOT sent
  * the dry-run activation preview uses the same header names

No real credentials: the RSA key is generated and HTTP is mocked. Uses distinct
partner/sender values so the env-origin is unambiguous.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.integrations.tmobile_taap as taap

TOKEN_URL = "https://pit-oauth.t-mobile.com/oauth2/v2/tokens"
BASE_URL = "https://pit-apis.t-mobile.com"
TEST_PATH = "/wholesale/v1/header-test"
TEST_URL = f"{BASE_URL}{TEST_PATH}"


@pytest.fixture
def tmobile_env(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    monkeypatch.setattr(taap, "_load_private_key", lambda: pem)
    for name, value in {
        "TMOBILE_ENV": "pit",
        "TMOBILE_BASE_URL": BASE_URL,
        "TMOBILE_TOKEN_URL": TOKEN_URL,
        "TMOBILE_CONSUMER_KEY": "ck",
        "TMOBILE_CONSUMER_SECRET": "cs",
        # Distinct, non-128 values so env-origin is unambiguous.
        "TMOBILE_PARTNER_ID": "PARTNER-XYZ",
        "TMOBILE_SENDER_ID": "SENDER-XYZ",
        "TMOBILE_ACCOUNT_ID": "",
        "TMOBILE_PIT_LIVE_CALLS_ENABLED": "true",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _mock_token():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": "tok", "expires_in": 3600}))


def _sent_request():
    for call in respx.calls:
        if call.request.url.path == TEST_PATH:
            return call.request
    raise AssertionError("request was not sent")


@respx.mock
@pytest.mark.asyncio
async def test_partner_and_sender_use_lowercase_header_names(tmobile_env):
    _mock_token()
    respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = taap.TMobileTAAPClient()
    await client.post_json(TEST_PATH, {"hello": "world"})
    await client.close()

    req = _sent_request()
    # Required lowercase header names, values from the env vars.
    assert req.headers["partner-id"] == "PARTNER-XYZ"   # TMOBILE_PARTNER_ID
    assert req.headers["sender-id"] == "SENDER-XYZ"      # TMOBILE_SENDER_ID
    # The rejected names must NOT be present (X- prefix is a distinct name).
    assert "X-Partner-Id" not in req.headers
    assert "X-Sender-Id" not in req.headers


def test_activation_preview_uses_lowercase_header_names(tmobile_env):
    client = taap.TMobileTAAPClient()
    preview = client.build_activation_preview(
        iccid="8901240204219434247", market_zip="30346",
        callback_location="https://cb.example/hook",
    )
    headers = preview["headers"]
    assert headers["partner-id"] == "PARTNER-XYZ"
    assert headers["sender-id"] == "SENDER-XYZ"
    assert "X-Partner-Id" not in headers
    assert "X-Sender-Id" not in headers
