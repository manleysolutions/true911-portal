"""T-Mobile partner-transaction-id header (Aman, 2026-06).

T-Mobile requested a per-request ``partner-transaction-id`` header carrying a
unique random string (format ``true911-pit-<uuid4>``) so they can correlate the
transaction to their server-side logs.

Proves:
  * the ``partner-transaction-id`` header exists on outbound TAAP requests
  * the value matches ``true911-pit-<uuid4>`` and is unique per request
  * the value is logged alongside correlation_id / method / path
  * the value is sent on activation requests specifically

No real credentials: RSA key generated, HTTP mocked. OAuth/PoP/payload/endpoint
unchanged — only a header is added.
"""

from __future__ import annotations

import json
import logging
import uuid

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import app.integrations.tmobile_taap as taap

TOKEN_URL = "https://pit-oauth.t-mobile.com/oauth2/v2/tokens"
BASE_URL = "https://pit-apis.t-mobile.com"
TEST_PATH = "/wholesale/v1/ptxn-test"
TEST_URL = f"{BASE_URL}{TEST_PATH}"
ACTIVATE_PATH = "/wholesale/v1/subscriber/activation"
ACTIVATE_URL = f"{BASE_URL}{ACTIVATE_PATH}"
LOGGER_NAME = "true911.integrations.tmobile_taap"
PREFIX = "true911-pit-"


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
        "TMOBILE_PARTNER_ID": "128",
        "TMOBILE_SENDER_ID": "128",
        "TMOBILE_ACCOUNT_ID": "",
        "TMOBILE_PIT_LIVE_CALLS_ENABLED": "true",
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _mock_token():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": "tok", "expires_in": 3600}))


def _requests_for(path):
    return [c.request for c in respx.calls if c.request.url.path == path]


def _assert_valid_format(value: str):
    assert value.startswith(PREFIX), f"missing prefix: {value!r}"
    uuid.UUID(value[len(PREFIX):])  # remainder is a valid uuid4


@respx.mock
@pytest.mark.asyncio
async def test_header_exists_and_well_formed(tmobile_env):
    _mock_token()
    respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = taap.TMobileTAAPClient()
    await client.post_json(TEST_PATH, {"hello": "world"})
    await client.close()

    req = _requests_for(TEST_PATH)[0]
    assert "partner-transaction-id" in req.headers
    _assert_valid_format(req.headers["partner-transaction-id"])


@respx.mock
@pytest.mark.asyncio
async def test_value_is_unique_per_request(tmobile_env):
    _mock_token()
    respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = taap.TMobileTAAPClient()
    await client.post_json(TEST_PATH, {"n": 1})
    await client.post_json(TEST_PATH, {"n": 2})
    await client.close()

    reqs = _requests_for(TEST_PATH)
    assert len(reqs) == 2
    v1 = reqs[0].headers["partner-transaction-id"]
    v2 = reqs[1].headers["partner-transaction-id"]
    _assert_valid_format(v1)
    _assert_valid_format(v2)
    assert v1 != v2  # unique per request


@respx.mock
@pytest.mark.asyncio
async def test_value_is_logged(tmobile_env, caplog):
    _mock_token()
    respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = taap.TMobileTAAPClient()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await client.post_json(TEST_PATH, {"hello": "world"})
    await client.close()

    sent = _requests_for(TEST_PATH)[0].headers["partner-transaction-id"]
    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "partner_transaction_id" in msgs
    assert sent in msgs  # the exact sent value is logged


@respx.mock
@pytest.mark.asyncio
async def test_header_sent_on_activation(tmobile_env):
    _mock_token()
    respx.post(ACTIVATE_URL).mock(return_value=httpx.Response(200, json={"status": "accepted"}))
    client = taap.TMobileTAAPClient()
    await client.activate_subscriber(
        iccid="8901240204219434247", market_zip="30346",
        callback_location="https://cb.example/hook")
    await client.close()

    req = _requests_for(ACTIVATE_PATH)[0]
    # OAuth/PoP/payload unchanged: still the nested body, plus the new header.
    body = json.loads(req.content)
    assert body["iccid"] == "8901240204219434247"
    assert "partner-transaction-id" in req.headers
    _assert_valid_format(req.headers["partner-transaction-id"])


def test_dry_run_preview_shows_header(tmobile_env):
    client = taap.TMobileTAAPClient()
    preview = client.build_activation_preview(
        iccid="8901240204219434247", market_zip="30346",
        callback_location="https://cb.example/hook")
    assert "partner-transaction-id" in preview["headers"]
    assert preview["headers"]["partner-transaction-id"].startswith(PREFIX)
