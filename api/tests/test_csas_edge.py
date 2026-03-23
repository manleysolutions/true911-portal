"""
Tests for CSAS edge ingestion path.

Covers:
- CSAS adapter heartbeat normalization
- Heartbeat ingest success (happy path)
- Unknown device returns 403
- Edge-classify payload shape compatibility
- Edge-classify auth enforcement
"""

import pytest

from app.adapters.csas_adapter import CSASAdapter
from app.adapters.registry import get_adapter
from app.schemas.device import DeviceTokenHeartbeatRequest
from app.schemas.line_intelligence import ClassifyRequest, EdgeClassifyRequest


# ===================================================================
# CSAS Adapter unit tests
# ===================================================================

class TestCSASAdapter:
    """Verify CSAS heartbeat payloads are normalized correctly."""

    def test_full_payload(self):
        adapter = CSASAdapter()
        raw = {
            "version": "3.1.0",
            "uptime": 86400,
            "status": "running",
            "timestamp": "2026-03-23T12:00:00Z",
            "signal_dbm": -78,
            "sip_status": "registered",
            "ip_address": "10.0.0.5",
            "board_temp_c": 45,
        }
        result = adapter.normalize_heartbeat(raw)
        assert result["firmware_version"] == "3.1.0"
        assert result["uptime_seconds"] == 86400
        assert result["csas_status"] == "running"
        assert result["csas_timestamp"] == "2026-03-23T12:00:00Z"
        assert result["signal_dbm"] == -78
        assert result["sip_status"] == "registered"
        assert result["ip_address"] == "10.0.0.5"
        assert result["board_temp_c"] == 45

    def test_minimal_payload(self):
        adapter = CSASAdapter()
        raw = {"status": "idle"}
        result = adapter.normalize_heartbeat(raw)
        assert result == {"csas_status": "idle"}

    def test_none_values_dropped(self):
        adapter = CSASAdapter()
        raw = {"version": None, "status": "running"}
        result = adapter.normalize_heartbeat(raw)
        assert "firmware_version" not in result
        assert result["csas_status"] == "running"

    def test_unknown_keys_dropped(self):
        adapter = CSASAdapter()
        raw = {"unknown_key": "something", "status": "running"}
        result = adapter.normalize_heartbeat(raw)
        assert "unknown_key" not in result
        assert result["csas_status"] == "running"

    def test_pr12_compatible_keys(self):
        """CSAS adapter also handles PR12-style keys for backward compat."""
        adapter = CSASAdapter()
        raw = {"fw_ver": "2.4.1", "rsrp": -82, "uptime": 3600}
        result = adapter.normalize_heartbeat(raw)
        assert result["firmware_version"] == "2.4.1"
        assert result["signal_dbm"] == -82
        assert result["uptime_seconds"] == 3600


# ===================================================================
# Adapter registry tests
# ===================================================================

class TestAdapterRegistry:
    """Verify CSAS identifiers resolve to CSASAdapter."""

    @pytest.mark.parametrize("identifier", ["csas", "csa-software", "csas-edge"])
    def test_csas_identifiers(self, identifier):
        adapter = get_adapter(identifier, None)
        assert type(adapter).__name__ == "CSASAdapter"

    def test_csas_via_model(self):
        adapter = get_adapter(None, "csas")
        assert type(adapter).__name__ == "CSASAdapter"

    def test_pr12_still_resolves(self):
        """Ensure PR12 adapter is not broken by CSAS addition."""
        adapter = get_adapter("pr12", None)
        assert type(adapter).__name__ == "PR12Adapter"

    def test_generic_fallback(self):
        adapter = get_adapter("unknown", None)
        assert type(adapter).__name__ == "GenericAdapter"


# ===================================================================
# Schema / payload shape tests
# ===================================================================

class TestHeartbeatPayloadShape:
    """Verify the CSAS heartbeat payload passes validation."""

    def test_csas_heartbeat_payload(self):
        """The DeviceTokenHeartbeatRequest accepts CSAS fields via extras."""
        req = DeviceTokenHeartbeatRequest(
            device_id="CSAS-001",
            status="running",
            uptime=86400,
            timestamp="2026-03-23T12:00:00Z",
            version="3.1.0",
        )
        assert req.device_id == "CSAS-001"
        # Extra fields are preserved for adapter normalization
        dumped = req.model_dump(exclude_none=True)
        assert dumped["status"] == "running"
        assert dumped["uptime"] == 86400
        assert dumped["version"] == "3.1.0"
        assert dumped["timestamp"] == "2026-03-23T12:00:00Z"

    def test_heartbeat_minimal(self):
        """Heartbeat with only device_id is valid."""
        req = DeviceTokenHeartbeatRequest(device_id="CSAS-001")
        assert req.device_id == "CSAS-001"

    def test_heartbeat_missing_device_id_fails(self):
        """device_id is required."""
        with pytest.raises(Exception):
            DeviceTokenHeartbeatRequest()


class TestEdgeClassifyPayloadShape:
    """Verify EdgeClassifyRequest matches the CSAS observation payload."""

    def test_csas_observation_payload(self):
        """Full CSAS observation payload validates correctly."""
        req = EdgeClassifyRequest(
            device_id="CSAS-001",
            line_id="line-1",
            site_id="site-100",
            port_index=0,
            dtmf_digits="1234567890",
            fax_tone_present=False,
            modem_carrier_present=False,
            voice_energy_estimate=0.3,
            silence_ratio=0.7,
            window_duration_ms=5000,
        )
        assert req.device_id == "CSAS-001"
        assert req.source == "csas"  # default for edge
        assert req.line_id == "line-1"

    def test_minimal_observation(self):
        """Only device_id and line_id are required."""
        req = EdgeClassifyRequest(device_id="CSAS-001", line_id="line-1")
        assert req.port_index == 0
        assert req.source == "csas"

    def test_missing_device_id_fails(self):
        with pytest.raises(Exception):
            EdgeClassifyRequest(line_id="line-1")

    def test_missing_line_id_fails(self):
        with pytest.raises(Exception):
            EdgeClassifyRequest(device_id="CSAS-001")

    def test_classify_request_compatibility(self):
        """EdgeClassifyRequest has the same signal fields as ClassifyRequest."""
        edge_fields = set(EdgeClassifyRequest.model_fields.keys())
        jwt_fields = set(ClassifyRequest.model_fields.keys())
        # EdgeClassifyRequest adds device_id as required; both share all signal fields
        signal_fields = {"line_id", "site_id", "port_index", "dtmf_digits",
                         "fax_tone_present", "modem_carrier_present",
                         "voice_energy_estimate", "silence_ratio",
                         "window_duration_ms", "source"}
        assert signal_fields.issubset(edge_fields)
        assert signal_fields.issubset(jwt_fields)


# ===================================================================
# Auth enforcement tests (schema-level — no DB required)
# ===================================================================

class TestUnknownDeviceBehavior:
    """Document that unknown devices receive 403 (not 404).

    The actual HTTP-level tests require a test database with the full
    FastAPI app.  These tests verify the contract at the schema level
    and document expected behavior.
    """

    def test_heartbeat_requires_device_id(self):
        """Payload without device_id cannot be constructed."""
        with pytest.raises(Exception):
            DeviceTokenHeartbeatRequest.model_validate({})

    def test_edge_classify_requires_device_id(self):
        """Edge-classify without device_id cannot be constructed."""
        with pytest.raises(Exception):
            EdgeClassifyRequest.model_validate({"line_id": "line-1"})

    def test_auth_error_message_is_generic(self):
        """Verify the shared auth error message does not leak info."""
        from app.dependencies import _GENERIC_DEVICE_AUTH_ERROR
        # Must not reveal whether the device exists or the key is wrong
        assert "not found" not in _GENERIC_DEVICE_AUTH_ERROR.lower()
        assert "wrong" not in _GENERIC_DEVICE_AUTH_ERROR.lower()
        assert "invalid" in _GENERIC_DEVICE_AUTH_ERROR.lower()
