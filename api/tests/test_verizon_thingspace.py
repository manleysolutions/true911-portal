"""Tests for Verizon ThingSpace client, normalizer, and auth mode dispatch."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.verizon_thingspace import (
    AUTH_MODES,
    M2M_AUTH_MODES,
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

    def test_config_summary_shows_oauth_token_url(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k",
            api_secret="s",
            api_token="t",
            base_url="https://example.com/api",
        )
        summary = client.config_summary()
        assert summary["oauth_token_url"] == "https://example.com/api/ts/v1/oauth2/token"
        assert summary["app_token_header"] == "VZ-M2M-Token"
        assert summary["m2m_auth_mode"] == "oauth_plus_vz_m2m"

    def test_config_summary_app_token_header_na_for_other_modes(self):
        client = VerizonThingSpaceClient(
            auth_mode="oauth_client_credentials",
            client_id="cid",
            client_secret="csec",
        )
        summary = client.config_summary()
        assert summary["app_token_header"] == "(n/a)"
        assert summary["m2m_auth_mode"] == "(n/a)"

    def test_custom_oauth_token_path(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k",
            api_secret="s",
            api_token="t",
            base_url="https://example.com/api",
            oauth_token_path="/oauth2/token",
        )
        assert client.oauth_token_path == "/oauth2/token"
        summary = client.config_summary()
        assert summary["oauth_token_url"] == "https://example.com/api/oauth2/token"

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
    async def test_api_key_authenticate_does_oauth_exchange(self):
        """api_key_secret_token mode exchanges key/secret/token for an OAuth access_token."""
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="my-api-key",
            api_secret="my-api-secret",
            api_token="my-api-token",
            base_url="https://test.example.com/api",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "real-oauth-tok", "token_type": "Bearer"}

        with patch("app.services.verizon_thingspace.httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_response
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_ctx

            token = await client.authenticate()

            # Verify OAuth endpoint was called with correct auth and VZ-M2M-Token
            mock_ctx.post.assert_called_once()
            call_kwargs = mock_ctx.post.call_args
            assert call_kwargs[0][0] == "https://test.example.com/api/ts/v1/oauth2/token"
            assert call_kwargs[1]["auth"] == ("my-api-key", "my-api-secret")
            assert call_kwargs[1]["headers"]["VZ-M2M-Token"] == "my-api-token"

        assert token == "real-oauth-tok"
        assert client._session_token == "real-oauth-tok"

    @pytest.mark.asyncio
    async def test_api_key_authenticate_failure(self):
        """api_key_secret_token OAuth exchange failure raises."""
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="bad-key",
            api_secret="bad-secret",
            api_token="bad-token",
            base_url="https://test.example.com/api",
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid credentials"

        with patch("app.services.verizon_thingspace.httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_response
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_ctx

            with pytest.raises(VerizonThingSpaceError, match="API-key OAuth2 token exchange failed"):
                await client.authenticate()

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

    @pytest.mark.asyncio
    async def test_test_connection_returns_diagnostics_on_auth_failure(self):
        """test_connection() should return structured diagnostics (not raise) on auth failure."""
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k",
            api_secret="s",
            api_token="t",
            base_url="https://test.example.com/api",
        )

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch("app.services.verizon_thingspace.httpx.AsyncClient") as MockClient:
            mock_ctx = AsyncMock()
            mock_ctx.post.return_value = mock_response
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_ctx

            result = await client.test_connection()

        assert result["authenticated"] is False
        assert result["oauth_token_url"] == "https://test.example.com/api/ts/v1/oauth2/token"
        assert result["oauth_token_status"] == 404
        assert "VERIZON_THINGSPACE_OAUTH_TOKEN_PATH" in result["note"]


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

    def test_api_key_headers_default_vz_m2m(self):
        """Default m2m_auth_mode sends Bearer + VZ-M2M-Token."""
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="mykey",
            api_secret="mysecret",
            api_token="original-app-token",
        )
        client._session_token = "real-access-token-from-exchange"
        assert client.m2m_auth_mode == "oauth_plus_vz_m2m"
        headers = client._auth_headers()
        assert headers["Authorization"] == "Bearer real-access-token-from-exchange"
        assert headers["VZ-M2M-Token"] == "original-app-token"
        assert "App-Token" not in headers

    def test_api_key_headers_m2m_app_token(self):
        """oauth_plus_app_token sends Bearer + App-Token."""
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="mykey",
            api_secret="mysecret",
            api_token="original-app-token",
            m2m_auth_mode="oauth_plus_app_token",
        )
        client._session_token = "real-access-token"
        headers = client._auth_headers()
        assert headers["Authorization"] == "Bearer real-access-token"
        assert headers["App-Token"] == "original-app-token"
        assert "VZ-M2M-Token" not in headers

    def test_api_key_headers_m2m_both(self):
        """oauth_plus_both sends Bearer + VZ-M2M-Token + App-Token."""
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="mykey",
            api_secret="mysecret",
            api_token="the-token",
            m2m_auth_mode="oauth_plus_both",
        )
        client._session_token = "real-access-token"
        headers = client._auth_headers()
        assert headers["Authorization"] == "Bearer real-access-token"
        assert headers["VZ-M2M-Token"] == "the-token"
        assert headers["App-Token"] == "the-token"

    def test_api_key_headers_bearer_only(self):
        """bearer_only sends only Authorization Bearer."""
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k",
            api_secret="s",
            api_token="t",
            m2m_auth_mode="bearer_only",
        )
        client._session_token = "access-tok"
        headers = client._auth_headers()
        assert headers["Authorization"] == "Bearer access-tok"
        assert "VZ-M2M-Token" not in headers
        assert "App-Token" not in headers

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

    def test_can_reauth_api_key(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k", api_secret="s", api_token="t",
        )
        assert client._can_reauth is True

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

    def test_safe_body_does_not_redact_error_messages(self):
        """Error messages mentioning header names like VZ-M2M-Token should NOT be redacted."""
        mock_resp = MagicMock()
        mock_resp.text = (
            '{"error":"Required request header \'VZ-M2M-Token\' or '
            '\'App-Token\' is not present in the request"}'
        )
        result = VerizonThingSpaceClient._safe_body(mock_resp)
        assert "VZ-M2M-Token" in result
        assert "App-Token" in result
        assert "redacted" not in result.lower()

    def test_safe_body_from_str_does_not_redact_error_messages(self):
        text = "Required request header 'VZ-M2M-Token' or 'App-Token' is not present"
        result = VerizonThingSpaceClient._safe_body_from_str(text)
        assert "VZ-M2M-Token" in result
        assert "redacted" not in result.lower()


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


# ── Error diagnostics tests ──────────────────────────────────────────────


class TestErrorDiagnostics:
    """Tests for request-level diagnostics on VerizonThingSpaceError."""

    def test_error_carries_request_info(self):
        err = VerizonThingSpaceError(
            "test error",
            status_code=400,
            body="some body",
            request_method="POST",
            request_url="https://example.com/api/m2m/v1/devices/actions/list",
            request_headers=["Authorization", "Content-Type", "VZ-M2M-Token"],
            actual_headers_sent=["authorization", "content-type", "vz-m2m-token"],
            request_body_keys=["accountName", "resourceType"],
        )
        assert err.request_method == "POST"
        assert err.request_url == "https://example.com/api/m2m/v1/devices/actions/list"
        assert "VZ-M2M-Token" in err.request_headers
        assert err.actual_headers_sent is not None
        assert err.request_body_keys == ["accountName", "resourceType"]

    def test_error_defaults_none(self):
        err = VerizonThingSpaceError("basic error")
        assert err.request_method is None
        assert err.request_url is None
        assert err.request_headers is None
        assert err.actual_headers_sent is None
        assert err.request_body_keys is None


# ── M2M auth mode tests ────────────────────────────────────────────────


class TestM2MAuthModes:
    """Tests for M2M auth mode configuration."""

    def test_supported_m2m_modes(self):
        assert "oauth_plus_vz_m2m" in M2M_AUTH_MODES
        assert "oauth_plus_app_token" in M2M_AUTH_MODES
        assert "oauth_plus_both" in M2M_AUTH_MODES
        assert "bearer_only" in M2M_AUTH_MODES
        assert "session_token_legacy" in M2M_AUTH_MODES

    def test_default_m2m_mode(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k", api_secret="s", api_token="t",
        )
        assert client.m2m_auth_mode == "oauth_plus_vz_m2m"

    def test_invalid_m2m_mode_falls_back(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k", api_secret="s", api_token="t",
            m2m_auth_mode="bogus",
        )
        assert client.m2m_auth_mode == "oauth_plus_vz_m2m"

    def test_m2m_account_id_used(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k", api_secret="s", api_token="t",
            account_name="keyset_12345",
            m2m_account_id="0123456789-00001",
        )
        assert client.m2m_account_id == "0123456789-00001"
        summary = client.config_summary()
        assert summary["m2m_account_id"] == "0123456789-00001"

    def test_m2m_account_id_empty_fallback(self):
        client = VerizonThingSpaceClient(
            auth_mode="api_key_secret_token",
            api_key="k", api_secret="s", api_token="t",
            account_name="keyset_12345",
            m2m_account_id="",
        )
        assert client.m2m_account_id == ""
        summary = client.config_summary()
        assert "using account_name" in summary["m2m_account_id"]
