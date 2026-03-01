"""Tests for HMAC webhook signature verification."""

import hashlib
import hmac
import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.webhook_auth import compute_signature, verify_webhook_signature


FAKE_SECRET = "test-webhook-secret-12345"


def _make_sig(body: bytes, secret: str = FAKE_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestComputeSignature:
    def test_produces_sha256_prefix(self):
        sig = compute_signature(b"hello", FAKE_SECRET)
        assert sig.startswith("sha256=")
        assert len(sig) == 7 + 64  # sha256= + 64 hex chars

    def test_deterministic(self):
        body = b'{"event_type":"test"}'
        assert compute_signature(body, FAKE_SECRET) == compute_signature(body, FAKE_SECRET)

    def test_different_body_different_sig(self):
        assert compute_signature(b"a", FAKE_SECRET) != compute_signature(b"b", FAKE_SECRET)

    def test_different_secret_different_sig(self):
        body = b"same"
        assert compute_signature(body, "secret1") != compute_signature(body, "secret2")


class TestVerifyWebhookSignature:
    @patch("app.services.webhook_auth.settings")
    def test_valid_signature_passes(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = FAKE_SECRET
        mock_settings.INTEGRATION_HMAC_SKEW_SECONDS = 300
        body = b'{"test": true}'
        sig = _make_sig(body)
        # Should not raise
        verify_webhook_signature(body, sig)

    @patch("app.services.webhook_auth.settings")
    def test_missing_signature_header(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = FAKE_SECRET
        with pytest.raises(HTTPException) as exc_info:
            verify_webhook_signature(b"body", None)
        assert exc_info.value.status_code == 401
        assert "Missing" in str(exc_info.value.detail)

    @patch("app.services.webhook_auth.settings")
    def test_invalid_signature_format(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = FAKE_SECRET
        with pytest.raises(HTTPException) as exc_info:
            verify_webhook_signature(b"body", "md5=abc123")
        assert exc_info.value.status_code == 401
        assert "Invalid signature format" in str(exc_info.value.detail)

    @patch("app.services.webhook_auth.settings")
    def test_wrong_signature_rejected(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = FAKE_SECRET
        body = b'{"test": true}'
        wrong_sig = "sha256=" + ("a" * 64)
        with pytest.raises(HTTPException) as exc_info:
            verify_webhook_signature(body, wrong_sig)
        assert exc_info.value.status_code == 401
        assert "Invalid webhook signature" in str(exc_info.value.detail)

    @patch("app.services.webhook_auth.settings")
    def test_tampered_body_rejected(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = FAKE_SECRET
        original_body = b'{"amount": 100}'
        sig = _make_sig(original_body)
        tampered_body = b'{"amount": 999}'
        with pytest.raises(HTTPException) as exc_info:
            verify_webhook_signature(tampered_body, sig)
        assert exc_info.value.status_code == 401

    @patch("app.services.webhook_auth.settings")
    def test_empty_secret_raises_500(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = ""
        with pytest.raises(HTTPException) as exc_info:
            verify_webhook_signature(b"body", "sha256=abc")
        assert exc_info.value.status_code == 500

    @patch("app.services.webhook_auth.settings")
    def test_replay_protection_valid_timestamp(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = FAKE_SECRET
        mock_settings.INTEGRATION_HMAC_SKEW_SECONDS = 300
        body = b'{"test": 1}'
        sig = _make_sig(body)
        ts = str(int(time.time()))
        # Should not raise
        verify_webhook_signature(body, sig, ts)

    @patch("app.services.webhook_auth.settings")
    def test_replay_protection_expired_timestamp(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = FAKE_SECRET
        mock_settings.INTEGRATION_HMAC_SKEW_SECONDS = 300
        body = b'{"test": 1}'
        sig = _make_sig(body)
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        with pytest.raises(HTTPException) as exc_info:
            verify_webhook_signature(body, sig, old_ts)
        assert exc_info.value.status_code == 401
        assert "timestamp" in str(exc_info.value.detail).lower()

    @patch("app.services.webhook_auth.settings")
    def test_replay_protection_invalid_timestamp_format(self, mock_settings):
        mock_settings.INTEGRATION_WEBHOOK_SECRET = FAKE_SECRET
        mock_settings.INTEGRATION_HMAC_SKEW_SECONDS = 300
        body = b'{"test": 1}'
        sig = _make_sig(body)
        with pytest.raises(HTTPException) as exc_info:
            verify_webhook_signature(body, sig, "not-a-number")
        assert exc_info.value.status_code == 401
