"""Tests for Verizon ThingSpace client, normalizer, and auth mode dispatch."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.verizon_thingspace import (
    AUTH_MODES,
    VerizonThingSpaceClient,
    VerizonThingSpaceError,
    normalize_verizon_device,
    _redact,
)


# ── Normalizer tests ──────────────────────────────────────────────────────


class TestNormalizeVerizonDevice:
    """Tests for normalize_verizon_device()."""

    def test_full_device(self):
        raw = {
            "deviceIds": [
                {"kind": "ICCID", "id": "89148000005639206873"},
                {"kind": "IMEI", "id": "353456789012345"},
                {"kind": "MDN", "id": "5551234567"},
            ],
            "connectionStatus": "Connected",
            "activationStatus": "Active",
            "simStatus": "active",
            "lastConnectionDate": "2025-12-01T12:00:00Z",
        }
        result = normalize_verizon_device(raw)

        assert result["carrier"] == "verizon"
        assert result["iccid"] == "89148000005639206873"
        assert result["imei"] == "353456789012345"
        assert result["msisdn"] == "5551234567"
        assert result["sim_status"] == "active"
        assert result["line_status"] == "Connected"
        assert result["activation_status"] == "Active"
        assert result["last_seen_at"] == "2025-12-01T12:00:00Z"
        assert result["raw_payload"] == raw

    def test_minimal_device(self):
        raw = {
            "deviceIds": [{"kind": "ICCID", "id": "89148000000000000001"}],
            "state": "preactive",
        }
        result = normalize_verizon_device(raw)

        assert result["carrier"] == "verizon"
        assert result["iccid"] == "89148000000000000001"
        assert result["imei"] is None
        assert result["msisdn"] is None
        assert result["line_status"] == "preactive"

    def test_empty_device(self):
        result = normalize_verizon_device({})
        assert result["carrier"] == "verizon"
        assert result["iccid"] is None
        assert result["imei"] is None
        assert result["external_id"] == ""

    def test_usage_numeric(self):
        raw = {"dataTotalUsage": 125.5, "deviceIds": []}
        result = normalize_verizon_device(raw)
        assert result["usage_data_mb"] == 125.5

    def test_usage_dict(self):
        raw = {
            "usage": {"totalMB": 42.0, "otherField": "x"},
            "deviceIds": [],
        }
        result = normalize_verizon_device(raw)
        assert result["usage_data_mb"] == 42.0

    def test_external_id_falls_back_to_imei(self):
        raw = {
            "deviceIds": [{"kind": "IMEI", "id": "111222333444555"}],
        }
        result = normalize_verizon_device(raw)
        assert result["external_id"] == "111222333444555"

    def test_sim_status_derived_from_connection(self):
        raw = {
            "deviceIds": [],
            "connectionStatus": "Disconnected",
        }
        result = normalize_verizon_device(raw)
        assert result["sim_status"] == "Disconnected"


# ── Auth mode configuration tests ────────────────────────────────────────


class TestAuthModeConfig:
    """Tests for auth mode validation, required vars, and config_summary."""

    def test_supported_auth_modes(self):
        assert "oauth_client_credentials" in AUTH_MODES
        assert "api_key_secret_token" in AUTH_MODES
        assert "legacy_short_key_secret" in AUTH_MODES
        assert "username_password_session" in AUTH_MODES

    def test_unsupported_auth_mode(self):
        client = VerizonThingSpaceClient(auth_mode="bogus_mode")
        assert client.is_configured is False
        with pytest.raises(VerizonThingSpaceError, match="Unsupported"):
            client._require_configured()

    def test_empty_auth_mode(self):
        client = VerizonThingSpaceClient(auth_mode="")
        assert client.is_configured is False

    # ── oauth_client_credentials ──

    def test_oauth_configured(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="cid-123",
            client_secret="csecret-456",
        )
        assert client.is_configured is True
        assert client._missing_vars() == []

    def test_oauth_missing_secret(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="cid-123",
            client_secret="",
        )
        assert client.is_configured is False
        assert "VERIZON_THINGSPACE_CLIENT_SECRET" in client._missing_vars()

    def test_oauth_missing_both(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="",
            client_secret="",
        )
        missing = client._missing_vars()
        assert "VERIZON_THINGSPACE_CLIENT_ID" in missing
        assert "VERIZON_THINGSPACE_CLIENT_SECRET" in missing

    # ── api_key_secret_token ──

    def test_api_key_configured(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="key-1",
            api_secret="sec-2",
            api_token="tok-3",
        )
        assert client.is_configured is True

    def test_api_key_missing_token(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="key-1",
            api_secret="sec-2",
            api_token="",
        )
        assert client.is_configured is False
        assert "VERIZON_THINGSPACE_API_TOKEN" in client._missing_vars()

    # ── legacy_short_key_secret ──

    def test_legacy_configured(self):
        client = VerizonThingSpaceClient(
            auth_mode="legacy_short_key_secret",
            short_key="sk-1",
            short_secret="ss-2",
        )
        assert client.is_configured is True

    def test_legacy_missing_secret(self):
        client = VerizonThingSpaceClient(
            auth_mode="legacy_short_key_secret",
            short_key="sk-1",
            short_secret="",
        )
        assert client.is_configured is False
        assert "VERIZON_THINGSPACE_SHORT_SECRET" in client._missing_vars()

    # ── username_password_session ──

    def test_session_configured(self):
        client = VerizonThingSpaceClient(
            auth_mode="username_password_session",
            username="user@example.com",
            password="pass123",
        )
        assert client.is_configured is True

    def test_session_missing_password(self):
        client = VerizonThingSpaceClient(
            auth_mode="username_password_session",
            username="user@example.com",
            password="",
        )
        assert client.is_configured is False
        assert "VERIZON_THINGSPACE_PASSWORD" in client._missing_vars()

    # ── config_summary safety ──

    def test_config_summary_no_secrets(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="SUPER-SECRET-KEY",
            api_secret="SUPER-SECRET-SEC",
            api_token="SUPER-SECRET-TOK",
            account_name="acct-001",
        )
        summary = client.config_summary()
        summary_str = str(summary)
        assert "SUPER-SECRET" not in summary_str
        assert summary["auth_mode"] == "api_key_secret_token"
        assert summary["account_name"] == "acct-001"
        assert summary["is_configured"] is True

    def test_config_summary_missing_vars(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="",
            client_secret="",
        )
        summary = client.config_summary()
        assert summary["is_configured"] is False
        assert "VERIZON_THINGSPACE_CLIENT_ID" in summary["missing_vars"]

    def test_config_summary_bad_mode(self):
        client = VerizonThingSpaceClient(auth_mode="invalid")
        summary = client.config_summary()
        assert summary["is_configured"] is False
        assert "error" in summary


# ── Auth dispatch tests ──────────────────────────────────────────────────


class TestAuthDispatch:
    """Tests for authenticate() dispatching to the right strategy."""

    @pytest.mark.asyncio
    async def test_oauth_authenticate_success(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="cid",
            client_secret="csec",
            base_url="https://test.example.com/api",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "oauth-tok-123", "token_type": "Bearer"}

        with patch("app.services.verizon_thingspace.httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_response
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_ctx

            token = await client.authenticate()

        assert token == "oauth-tok-123"
        assert client._session_token == "oauth-tok-123"

    @pytest.mark.asyncio
    async def test_oauth_authenticate_failure(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="bad",
            client_secret="creds",
            base_url="https://test.example.com/api",
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("app.services.verizon_thingspace.httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_response
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_ctx

            with pytest.raises(VerizonThingSpaceError, match="OAuth2 authentication failed"):
                await client.authenticate()

    @pytest.mark.asyncio
    async def test_api_key_authenticate_no_network(self):
        """api_key_secret_token mode should not make any HTTP call."""
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k",
            api_secret="s",
            api_token="t",
        )
        # No mocking needed — should not call httpx at all
        token = await client.authenticate()
        assert token == "t"
        assert client._session_token == "t"

    @pytest.mark.asyncio
    async def test_legacy_authenticate_no_network(self):
        """legacy_short_key_secret mode should not make any HTTP call."""
        client = VerizonThingSpaceClient(
            auth_mode="legacy_short_key_secret",
            short_key="sk",
            short_secret="ss",
        )
        token = await client.authenticate()
        assert token  # base64 encoded
        assert client._session_token is not None

    @pytest.mark.asyncio
    async def test_session_authenticate_success(self):
        client = VerizonThingSpaceClient(
            auth_mode="username_password_session",
            username="user",
            password="pass",
            base_url="https://test.example.com/api",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sessionToken": "sess-tok-456"}

        with patch("app.services.verizon_thingspace.httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_response
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_ctx

            token = await client.authenticate()

        assert token == "sess-tok-456"

    @pytest.mark.asyncio
    async def test_unsupported_mode_raises(self):
        client = VerizonThingSpaceClient(auth_mode="bogus")
        with pytest.raises(VerizonThingSpaceError, match="Unsupported"):
            await client.authenticate()


# ── Auth headers tests ───────────────────────────────────────────────────


class TestAuthHeaders:
    """Tests for _auth_headers() building correct headers per mode."""

    def test_oauth_headers(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="x", client_secret="y",
        )
        client._session_token = "oauth-token"
        headers = client._auth_headers()
        assert headers["Authorization"] == "Bearer oauth-token"
        assert "VZ-M2M-Token" not in headers

    def test_api_key_headers(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="mykey",
            api_secret="mysecret",
            api_token="mytoken",
        )
        client._session_token = "mytoken"
        headers = client._auth_headers()
        assert headers["VZ-M2M-Token"] == "mytoken"
        assert headers["X-API-Key"] == "mykey"
        assert headers["X-API-Secret"] == "mysecret"
        assert "Authorization" not in headers

    def test_legacy_headers(self):
        client = VerizonThingSpaceClient(
            auth_mode="legacy_short_key_secret",
            short_key="sk", short_secret="ss",
        )
        client._session_token = "base64val"
        headers = client._auth_headers()
        assert headers["Authorization"] == "Basic base64val"

    def test_session_headers(self):
        client = VerizonThingSpaceClient(
            auth_mode="username_password_session",
            username="u", password="p",
        )
        client._session_token = "sess-tok"
        headers = client._auth_headers()
        assert headers["Authorization"] == "Bearer sess-tok"
        assert headers["VZ-M2M-Token"] == "sess-tok"

    def test_not_authenticated_raises(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="x", client_secret="y",
        )
        with pytest.raises(VerizonThingSpaceError, match="Not authenticated"):
            client._auth_headers()


# ── Re-auth behavior tests ──────────────────────────────────────────────


class TestReauthBehavior:
    def test_can_reauth_oauth(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="x", client_secret="y",
        )
        assert client._can_reauth is True

    def test_can_reauth_session(self):
        client = VerizonThingSpaceClient(
            auth_mode="username_password_session",
            username="u", password="p",
        )
        assert client._can_reauth is True

    def test_cannot_reauth_api_key(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k", api_secret="s", api_token="t",
        )
        assert client._can_reauth is False

    def test_cannot_reauth_legacy(self):
        client = VerizonThingSpaceClient(
            auth_mode="legacy_short_key_secret",
            short_key="sk", short_secret="ss",
        )
        assert client._can_reauth is False


# ── Secret safety tests ─────────────────────────────────────────────────


class TestSecretSafety:
    def test_redact_short(self):
        assert _redact("ab") == "***"
        assert _redact("") == "***"

    def test_redact_normal(self):
        result = _redact("abcdefgh")
        assert result == "ab***gh"
        assert "cdef" not in result

    def test_error_does_not_contain_secrets(self):
        """VerizonThingSpaceError should not embed raw credentials."""
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="",
            client_secret="SUPER_SECRET_VALUE",
        )
        try:
            client._require_configured()
            assert False, "Should have raised"
        except VerizonThingSpaceError as e:
            assert "SUPER_SECRET_VALUE" not in str(e)

    def test_safe_body_redacts_tokens(self):
        mock_resp = MagicMock()
        mock_resp.text = '{"access_token":"secret123","expires_in":3600}'
        result = VerizonThingSpaceClient._safe_body(mock_resp)
        assert "secret123" not in result
        assert "redacted" in result.lower()


# ── Sync status mapping tests ────────────────────────────────────────────


class TestStatusMapping:
    def test_active_statuses(self):
        from app.routers.carrier_verizon import _map_verizon_status

        assert _map_verizon_status("Active") == "active"
        assert _map_verizon_status("connected") == "active"
        assert _map_verizon_status("Activated") == "active"

    def test_suspended(self):
        from app.routers.carrier_verizon import _map_verizon_status

        assert _map_verizon_status("Suspended") == "suspended"

    def test_terminated(self):
        from app.routers.carrier_verizon import _map_verizon_status

        assert _map_verizon_status("Deactivated") == "terminated"
        assert _map_verizon_status("disconnected") == "terminated"

    def test_inventory(self):
        from app.routers.carrier_verizon import _map_verizon_status

        assert _map_verizon_status("ready") == "inventory"
        assert _map_verizon_status("preactive") == "inventory"

    def test_none(self):
        from app.routers.carrier_verizon import _map_verizon_status

        assert _map_verizon_status(None) is None

    def test_unknown_defaults_inventory(self):
        from app.routers.carrier_verizon import _map_verizon_status

        assert _map_verizon_status("weird_status") == "inventory"
