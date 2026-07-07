"""Diagnostic-logging tests for outbound T-Mobile TAAP requests.

Proves the minimal logging slice (no behavior/payload/endpoint change):
  * X-Correlation-Id is generated and sent on every outbound request
  * the correlation id is logged (info) per request and (warning) on failure
  * a T-Mobile partner / transaction id response header is surfaced when present
  * response headers are redacted of auth/cookie material when logged

No real credentials: the RSA key is generated and HTTP is mocked. Exercises the
generic ``_request`` path via ``post_json`` so activation behavior is untouched.
"""

from __future__ import annotations

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
TEST_PATH = "/wholesale/v1/diagnostic-test"
TEST_URL = f"{BASE_URL}{TEST_PATH}"
LOGGER_NAME = "true911.integrations.tmobile_taap"


@pytest.fixture
def tmobile_env(monkeypatch):
    """Generated RSA key + mocked T-Mobile settings (creds + hosts)."""
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
    }.items():
        monkeypatch.setattr(f"app.config.settings.{name}", value)


def _mock_token():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(
        200, json={"access_token": "tok", "expires_in": 3600}))


def _sent_request():
    for call in respx.calls:
        if call.request.url.path == TEST_PATH:
            return call.request
    raise AssertionError("diagnostic request was not sent")


# ── pure helpers ─────────────────────────────────────────────────────
def test_redact_response_headers_masks_sensitive():
    raw = httpx.Headers({
        "Authorization": "Bearer SECRET",
        "Set-Cookie": "sess=SECRET",
        "Content-Type": "application/json",
        "partner-transaction-id": "TXN-9",
    })
    safe = taap._redact_response_headers(raw)
    assert safe["authorization"] == "<redacted>"
    assert safe["set-cookie"] == "<redacted>"
    assert safe["content-type"] == "application/json"
    assert safe["partner-transaction-id"] == "TXN-9"
    assert "SECRET" not in str(safe)


def test_partner_transaction_id_extracted():
    assert taap._partner_transaction_id(
        httpx.Headers({"partner-transaction-id": "TXN-42"})) == "TXN-42"
    # case-insensitive + alternate header name
    assert taap._partner_transaction_id(
        httpx.Headers({"X-Transaction-Id": "TXN-7"})) == "TXN-7"
    assert taap._partner_transaction_id(httpx.Headers({})) is None


# ── outbound request behavior ─────────────────────────────────────────
@respx.mock
@pytest.mark.asyncio
async def test_correlation_id_generated_and_sent(tmobile_env):
    _mock_token()
    respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = taap.TMobileTAAPClient()
    await client.post_json(TEST_PATH, {"hello": "world"})
    await client.close()

    cid = _sent_request().headers["X-Correlation-Id"]
    uuid.UUID(cid)  # generated as a valid uuid4 and sent on the wire


@respx.mock
@pytest.mark.asyncio
async def test_correlation_id_logged_on_request(tmobile_env, caplog):
    _mock_token()
    respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    client = taap.TMobileTAAPClient()
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await client.post_json(TEST_PATH, {"hello": "world"})
    await client.close()

    cid = _sent_request().headers["X-Correlation-Id"]
    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "T-Mobile TAAP request" in msgs
    assert cid in msgs


@respx.mock
@pytest.mark.asyncio
async def test_failure_logs_correlation_partner_txn_and_redacts(tmobile_env, caplog):
    _mock_token()
    respx.post(TEST_URL).mock(return_value=httpx.Response(
        400,
        json={"code": "GENS-0003", "userMessage": "Invalid partnerID"},
        headers={
            "partner-transaction-id": "TXN-ABC123",
            "Authorization": "Bearer LEAK",
            "Set-Cookie": "sess=LEAK",
        },
    ))
    client = taap.TMobileTAAPClient()
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        with pytest.raises(RuntimeError) as exc:
            await client.post_json(TEST_PATH, {"hello": "world"})
    await client.close()

    cid = _sent_request().headers["X-Correlation-Id"]
    warning = "\n".join(
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    )
    # correlation id + status + partner transaction id surfaced on failure
    assert cid in warning
    assert "400" in warning
    assert "TXN-ABC123" in warning
    # response body surfaced AND the raised error is unchanged
    assert "GENS-0003" in warning
    assert "GENS-0003" in str(exc.value)
    assert str(exc.value).startswith("T-Mobile API error (400)")
    # sensitive response headers redacted — secrets never logged
    assert "<redacted>" in warning
    assert "LEAK" not in warning


@respx.mock
@pytest.mark.asyncio
async def test_failure_logs_workflow_and_service_transaction_ids(tmobile_env, caplog):
    """A GENS-0003-style failure surfaces the work-flow-id / service-transaction-id
    T-Mobile asks for when correlating a failed activation to its server logs."""
    _mock_token()
    respx.post(TEST_URL).mock(return_value=httpx.Response(
        400,
        json={"code": "GENS-0003", "userMessage": "Invalid partnerID"},
        headers={
            "work-flow-id": "99a2b4f7-cdd3-499f-951b-915d98efe819_P",
            "service-transaction-id": "9b8f65ad-48ac-973f-9687-cd5ed75ad991",
        },
    ))
    client = taap.TMobileTAAPClient()
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        with pytest.raises(RuntimeError):
            await client.post_json(TEST_PATH, {"hello": "world"})
    await client.close()

    warning = "\n".join(
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    )
    assert "99a2b4f7-cdd3-499f-951b-915d98efe819_P" in warning
    assert "9b8f65ad-48ac-973f-9687-cd5ed75ad991" in warning
    assert "work_flow_id=" in warning
    assert "service_transaction_id=" in warning
