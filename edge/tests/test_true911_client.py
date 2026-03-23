"""
Tests for the CSAS True911 client.

Uses unittest.mock to patch requests.post so no real HTTP calls are made.

Covers:
- Heartbeat payload shape and auth header
- Observation payload shape and endpoint path
- Graceful handling of HTTP errors (403, 500)
- Graceful handling of network failures
- Config defaults
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from edge.csas.true911_client import True911Client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_client(**overrides) -> True911Client:
    defaults = {
        "base_url": "https://test.example.com",
        "device_id": "CSAS-TEST-001",
        "device_api_key": "t91_testkey123",
        "site_id": "site-99",
        "timeout": 5,
    }
    defaults.update(overrides)
    return True911Client(**defaults)


def _mock_response(status_code: int = 200, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = json.dumps(json_data or {})
    return resp


# ===================================================================
# Heartbeat tests
# ===================================================================

class TestHeartbeat:

    @patch("edge.csas.true911_client.requests.post")
    def test_heartbeat_success(self, mock_post):
        """Heartbeat posts to /api/heartbeat with correct payload and header."""
        mock_post.return_value = _mock_response(200, {
            "ok": True,
            "device_id": "CSAS-TEST-001",
            "next_heartbeat_seconds": 60,
        })

        client = _make_client()
        result = client.send_heartbeat(
            status="running",
            uptime=3600,
            version="3.1.0",
            extra={"signal_dbm": -78},
        )

        assert result is not None
        assert result["ok"] is True
        assert result["next_heartbeat_seconds"] == 60

        # Verify the HTTP call
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://test.example.com/api/heartbeat"
        assert kwargs["headers"]["X-Device-Key"] == "t91_testkey123"

        payload = kwargs["json"]
        assert payload["device_id"] == "CSAS-TEST-001"
        assert payload["status"] == "running"
        assert payload["uptime"] == 3600
        assert payload["version"] == "3.1.0"
        assert payload["signal_dbm"] == -78
        assert "timestamp" in payload  # auto-generated ISO timestamp

    @patch("edge.csas.true911_client.requests.post")
    def test_heartbeat_minimal(self, mock_post):
        """Heartbeat with only defaults still sends device_id and status."""
        mock_post.return_value = _mock_response(200, {"ok": True, "device_id": "CSAS-TEST-001", "next_heartbeat_seconds": 60})

        client = _make_client()
        client.send_heartbeat()

        payload = mock_post.call_args.kwargs["json"]
        assert payload["device_id"] == "CSAS-TEST-001"
        assert payload["status"] == "running"
        assert "timestamp" in payload
        assert "uptime" not in payload
        assert "version" not in payload

    @patch("edge.csas.true911_client.requests.post")
    def test_heartbeat_403_returns_none(self, mock_post):
        """Unknown or bad device key returns None gracefully."""
        mock_post.return_value = _mock_response(403, {"detail": "Invalid device credentials"})

        client = _make_client()
        result = client.send_heartbeat(status="running")

        assert result is None

    @patch("edge.csas.true911_client.requests.post")
    def test_heartbeat_500_returns_none(self, mock_post):
        """Server error returns None gracefully."""
        mock_post.return_value = _mock_response(500, {"detail": "Internal server error"})

        client = _make_client()
        result = client.send_heartbeat(status="running")

        assert result is None


# ===================================================================
# Observation / edge-classify tests
# ===================================================================

class TestObservation:

    @patch("edge.csas.true911_client.requests.post")
    def test_observation_success(self, mock_post):
        """Observation posts to /api/line-intelligence/edge-classify."""
        mock_post.return_value = _mock_response(200, {
            "decision_id": "dec-abc",
            "line_id": "line-1",
            "classification": {
                "line_type": "contact_id",
                "confidence_score": 0.95,
                "confidence_tier": "high",
                "is_actionable": True,
                "fallback_applied": False,
                "evidence": [],
            },
            "assigned_profile": {
                "profile_id": "prof-cid",
                "profile_name": "Contact ID",
                "line_type": "contact_id",
            },
            "manual_override": False,
            "pipeline_version": "1.0.0",
        })

        client = _make_client()
        result = client.send_observation(
            line_id="line-1",
            port_index=0,
            dtmf_digits="*1234567890#",
            fax_tone_present=False,
            modem_carrier_present=False,
            voice_energy_estimate=0.05,
            silence_ratio=0.85,
            window_duration_ms=5000,
        )

        assert result is not None
        assert result["classification"]["line_type"] == "contact_id"

        # Verify endpoint path
        args, kwargs = mock_post.call_args
        assert args[0] == "https://test.example.com/api/line-intelligence/edge-classify"
        assert kwargs["headers"]["X-Device-Key"] == "t91_testkey123"

        # Verify payload matches EdgeClassifyRequest schema
        payload = kwargs["json"]
        assert payload["device_id"] == "CSAS-TEST-001"
        assert payload["line_id"] == "line-1"
        assert payload["site_id"] == "site-99"  # from client default
        assert payload["port_index"] == 0
        assert payload["dtmf_digits"] == "*1234567890#"
        assert payload["fax_tone_present"] is False
        assert payload["modem_carrier_present"] is False
        assert payload["voice_energy_estimate"] == 0.05
        assert payload["silence_ratio"] == 0.85
        assert payload["window_duration_ms"] == 5000
        assert payload["source"] == "csas"

    @patch("edge.csas.true911_client.requests.post")
    def test_observation_site_override(self, mock_post):
        """Per-call site_id overrides the client default."""
        mock_post.return_value = _mock_response(200, {})

        client = _make_client(site_id="default-site")
        client.send_observation(line_id="line-1", site_id="override-site")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["site_id"] == "override-site"

    @patch("edge.csas.true911_client.requests.post")
    def test_observation_no_site(self, mock_post):
        """When no site_id is configured, it is omitted from payload."""
        mock_post.return_value = _mock_response(200, {})

        client = _make_client(site_id="")
        client.send_observation(line_id="line-1")

        payload = mock_post.call_args.kwargs["json"]
        assert "site_id" not in payload

    @patch("edge.csas.true911_client.requests.post")
    def test_observation_403_returns_none(self, mock_post):
        """Bad device credentials returns None gracefully."""
        mock_post.return_value = _mock_response(403, {"detail": "Invalid device credentials"})

        client = _make_client()
        result = client.send_observation(line_id="line-1")

        assert result is None

    @patch("edge.csas.true911_client.requests.post")
    def test_observation_404_feature_disabled(self, mock_post):
        """Line Intelligence feature disabled returns None gracefully."""
        mock_post.return_value = _mock_response(404, {"detail": "Line Intelligence is not enabled."})

        client = _make_client()
        result = client.send_observation(line_id="line-1")

        assert result is None


# ===================================================================
# Network failure tests
# ===================================================================

class TestNetworkFailure:

    @patch("edge.csas.true911_client.requests.post")
    def test_connection_error_heartbeat(self, mock_post):
        """Network failure during heartbeat returns None, does not raise."""
        import requests as req
        mock_post.side_effect = req.ConnectionError("Connection refused")

        client = _make_client()
        result = client.send_heartbeat(status="running")

        assert result is None

    @patch("edge.csas.true911_client.requests.post")
    def test_timeout_observation(self, mock_post):
        """Timeout during observation returns None, does not raise."""
        import requests as req
        mock_post.side_effect = req.Timeout("Read timed out")

        client = _make_client()
        result = client.send_observation(line_id="line-1")

        assert result is None

    @patch("edge.csas.true911_client.requests.post")
    def test_dns_failure(self, mock_post):
        """DNS resolution failure returns None, does not raise."""
        import requests as req
        mock_post.side_effect = req.ConnectionError("Name or service not known")

        client = _make_client()
        result = client.send_heartbeat(status="running")

        assert result is None


# ===================================================================
# Config / construction tests
# ===================================================================

class TestClientConfig:

    def test_trailing_slash_stripped(self):
        client = True911Client(
            base_url="https://example.com/",
            device_id="d",
            device_api_key="k",
        )
        assert client.base_url == "https://example.com"

    def test_defaults_from_config(self):
        """Client picks up module-level config defaults."""
        # Just verify construction doesn't crash with empty config
        client = True911Client(
            base_url="http://localhost:8000",
            device_id="test",
            device_api_key="key",
        )
        assert client.device_id == "test"

    @patch("edge.csas.true911_client.requests.post")
    def test_payload_validates_against_server_schema(self, mock_post):
        """The observation payload the client builds should validate
        against EdgeClassifyRequest on the server side."""
        from api.app.schemas.line_intelligence import EdgeClassifyRequest

        mock_post.return_value = _mock_response(200, {})

        client = _make_client()
        client.send_observation(
            line_id="line-1",
            port_index=2,
            dtmf_digits="123",
            fax_tone_present=True,
            voice_energy_estimate=0.5,
            silence_ratio=0.3,
            window_duration_ms=10000,
        )

        payload = mock_post.call_args.kwargs["json"]
        # This will raise ValidationError if the shape is wrong
        req = EdgeClassifyRequest.model_validate(payload)
        assert req.device_id == "CSAS-TEST-001"
        assert req.line_id == "line-1"
        assert req.port_index == 2
        assert req.source == "csas"
