"""Verizon ThingSpace API client — handles authentication and device inventory.

Supports multiple auth modes via VERIZON_THINGSPACE_AUTH_MODE:
    oauth_client_credentials  — OAuth2 client_credentials grant (client_id + client_secret)
    api_key_secret_token      — OAuth2 exchange using API key/secret/token from
                                ThingSpace Key Management
    legacy_short_key_secret   — short key + secret (older ThingSpace accounts)
    username_password_session — session login with username/password (legacy fallback)

Both oauth_client_credentials and api_key_secret_token obtain a real OAuth2
access_token and use Authorization: Bearer on M2M requests.

M2M auth modes (VERIZON_THINGSPACE_M2M_AUTH_MODE):
    /m2m/v1/ endpoints require VZ-M2M-Token to contain a real session GUID
    obtained via POST /session/login — NOT the static api_token.  The
    oauth_plus_session_token mode handles this automatically:
        1. OAuth exchange → Authorization: Bearer <access_token>
        2. Session login  → VZ-M2M-Token: <session_guid>

Environment variables (via Settings):
    VERIZON_THINGSPACE_AUTH_MODE       — one of the auth modes above
    VERIZON_THINGSPACE_BASE_URL        — API base (default: https://thingspace.verizon.com/api)
    VERIZON_THINGSPACE_ACCOUNT_NAME    — M2M account (e.g. "0123456789-00001")
    VERIZON_THINGSPACE_M2M_AUTH_MODE   — how M2M request headers are built
    VERIZON_THINGSPACE_M2M_ACCOUNT_ID  — override account ID for M2M endpoints
    VERIZON_THINGSPACE_M2M_SESSION_LOGIN_PATH — session login endpoint path
    + mode-specific credential vars (see config.py / .env.example)
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("true911.verizon")

# Timeouts
_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 30.0

# Supported auth modes (how we obtain a token)
AUTH_MODES = frozenset({
    "oauth_client_credentials",
    "api_key_secret_token",
    "legacy_short_key_secret",
    "username_password_session",
})

# M2M auth modes (how we present credentials on protected M2M requests)
M2M_AUTH_MODES = frozenset({
    "oauth_plus_session_token",  # Bearer + VZ-M2M-Token from session login (recommended)
    "oauth_plus_vz_m2m",        # Bearer + VZ-M2M-Token (api_token — legacy, won't work for /m2m/v1/)
    "oauth_plus_app_token",     # Bearer + App-Token (api_token)
    "oauth_plus_both",          # Bearer + VZ-M2M-Token + App-Token (diagnostic)
    "bearer_only",              # Bearer only (control test)
})

# Required env vars per auth mode (Settings field names)
_REQUIRED_VARS: dict[str, list[str]] = {
    "oauth_client_credentials": [
        "VERIZON_THINGSPACE_CLIENT_ID",
        "VERIZON_THINGSPACE_CLIENT_SECRET",
    ],
    "api_key_secret_token": [
        "VERIZON_THINGSPACE_API_KEY",
        "VERIZON_THINGSPACE_API_SECRET",
        "VERIZON_THINGSPACE_API_TOKEN",
    ],
    "legacy_short_key_secret": [
        "VERIZON_THINGSPACE_SHORT_KEY",
        "VERIZON_THINGSPACE_SHORT_SECRET",
    ],
    "username_password_session": [
        "VERIZON_THINGSPACE_USERNAME",
        "VERIZON_THINGSPACE_PASSWORD",
    ],
}


def _redact(value: str) -> str:
    """Return a redacted version of a credential for safe logging."""
    if not value or len(value) <= 4:
        return "***"
    return value[:2] + "***" + value[-2:]


class VerizonThingSpaceError(Exception):
    """Raised when the ThingSpace API returns an unexpected response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
        request_method: str | None = None,
        request_url: str | None = None,
        request_headers: list[str] | None = None,
        actual_headers_sent: list[str] | None = None,
        request_params: list[str] | None = None,
        request_body_keys: list[str] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.request_method = request_method
        self.request_url = request_url
        self.request_headers = request_headers          # what we put in the dict
        self.actual_headers_sent = actual_headers_sent  # what httpx actually sent
        self.request_params = request_params
        self.request_body_keys = request_body_keys


class VerizonThingSpaceClient:
    """Low-level client for Verizon ThingSpace M2M / Connectivity Management API.

    Auth mode is selected via VERIZON_THINGSPACE_AUTH_MODE and only the
    credentials required for that mode need to be set.
    """

    def __init__(
        self,
        auth_mode: str | None = None,
        base_url: str | None = None,
        account_name: str | None = None,
        oauth_token_path: str | None = None,
        app_token_header: str | None = None,
        m2m_auth_mode: str | None = None,
        m2m_account_id: str | None = None,
        m2m_session_login_path: str | None = None,
        # oauth_client_credentials
        client_id: str | None = None,
        client_secret: str | None = None,
        # api_key_secret_token
        api_key: str | None = None,
        api_secret: str | None = None,
        api_token: str | None = None,
        # legacy_short_key_secret
        short_key: str | None = None,
        short_secret: str | None = None,
        # username_password_session / M2M session login
        username: str | None = None,
        password: str | None = None,
    ):
        self.auth_mode = (auth_mode or settings.VERIZON_THINGSPACE_AUTH_MODE).strip().lower()
        self.base_url = (base_url or settings.VERIZON_THINGSPACE_BASE_URL).rstrip("/")
        self.account_name = account_name or settings.VERIZON_THINGSPACE_ACCOUNT_NAME
        self.oauth_token_path = (oauth_token_path or settings.VERIZON_THINGSPACE_OAUTH_TOKEN_PATH).strip()
        self.app_token_header = (app_token_header or settings.VERIZON_THINGSPACE_APP_TOKEN_HEADER).strip() or "VZ-M2M-Token"
        # M2M endpoint auth strategy — defaults to oauth_plus_session_token
        raw_m2m = (m2m_auth_mode or settings.VERIZON_THINGSPACE_M2M_AUTH_MODE).strip().lower()
        self.m2m_auth_mode = raw_m2m if raw_m2m in M2M_AUTH_MODES else "oauth_plus_session_token"
        # Optional override for M2M account identifier (may differ from keyset name)
        self.m2m_account_id = (m2m_account_id or settings.VERIZON_THINGSPACE_M2M_ACCOUNT_ID).strip()
        # Session login path for obtaining VZ-M2M-Token GUID
        self.m2m_session_login_path = (
            m2m_session_login_path or settings.VERIZON_THINGSPACE_M2M_SESSION_LOGIN_PATH
        ).strip()

        # Store credentials by mode — only populated for the active mode
        self._creds = {
            "client_id": client_id or settings.VERIZON_THINGSPACE_CLIENT_ID,
            "client_secret": client_secret or settings.VERIZON_THINGSPACE_CLIENT_SECRET,
            "api_key": api_key or settings.VERIZON_THINGSPACE_API_KEY,
            "api_secret": api_secret or settings.VERIZON_THINGSPACE_API_SECRET,
            "api_token": api_token or settings.VERIZON_THINGSPACE_API_TOKEN,
            "short_key": short_key or settings.VERIZON_THINGSPACE_SHORT_KEY,
            "short_secret": short_secret or settings.VERIZON_THINGSPACE_SHORT_SECRET,
            "username": username or settings.VERIZON_THINGSPACE_USERNAME,
            "password": password or settings.VERIZON_THINGSPACE_PASSWORD,
        }

        # Token obtained during primary authentication (oauth / session modes)
        self._session_token: str | None = None
        # Separate M2M session GUID obtained via /session/login
        self._m2m_session_token: str | None = None

    # ── Configuration check ───────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """True if the auth mode is valid and all required credentials are set."""
        if self.auth_mode not in AUTH_MODES:
            return False
        return not self._missing_vars()

    def _missing_vars(self) -> list[str]:
        """Return the list of env var names that are required but empty."""
        required = _REQUIRED_VARS.get(self.auth_mode, [])
        # Map Settings field name -> internal cred key
        field_to_key = {
            "VERIZON_THINGSPACE_CLIENT_ID": "client_id",
            "VERIZON_THINGSPACE_CLIENT_SECRET": "client_secret",
            "VERIZON_THINGSPACE_API_KEY": "api_key",
            "VERIZON_THINGSPACE_API_SECRET": "api_secret",
            "VERIZON_THINGSPACE_API_TOKEN": "api_token",
            "VERIZON_THINGSPACE_SHORT_KEY": "short_key",
            "VERIZON_THINGSPACE_SHORT_SECRET": "short_secret",
            "VERIZON_THINGSPACE_USERNAME": "username",
            "VERIZON_THINGSPACE_PASSWORD": "password",
        }
        missing = []
        for var_name in required:
            key = field_to_key.get(var_name, "")
            if not self._creds.get(key):
                missing.append(var_name)
        # If M2M session token mode, also require username + password
        if self._needs_m2m_session:
            if not self._creds.get("username"):
                missing.append("VERIZON_THINGSPACE_USERNAME")
            if not self._creds.get("password"):
                missing.append("VERIZON_THINGSPACE_PASSWORD")
        return missing

    def _require_configured(self) -> None:
        if self.auth_mode not in AUTH_MODES:
            raise VerizonThingSpaceError(
                f"Unsupported VERIZON_THINGSPACE_AUTH_MODE: '{self.auth_mode}'. "
                f"Supported modes: {', '.join(sorted(AUTH_MODES))}"
            )
        missing = self._missing_vars()
        if missing:
            raise VerizonThingSpaceError(
                f"Missing credentials for auth mode '{self.auth_mode}' "
                f"(m2m_auth_mode={self.m2m_auth_mode}): "
                f"set {', '.join(missing)}"
            )

    @property
    def _needs_m2m_session(self) -> bool:
        """True if the M2M auth mode requires a separate session login.

        Only applies to api_key_secret_token auth mode — other auth modes
        don't use M2M auth mode settings.
        """
        return (
            self.auth_mode == "api_key_secret_token"
            and self.m2m_auth_mode == "oauth_plus_session_token"
        )

    @property
    def _m2m_session_login_url(self) -> str:
        return f"{self.base_url}{self.m2m_session_login_path}"

    def config_summary(self) -> dict[str, Any]:
        """Return a safe (no secrets) summary for diagnostics."""
        is_api_key = self.auth_mode == "api_key_secret_token"
        summary: dict[str, Any] = {
            "auth_mode": self.auth_mode,
            "base_url": self.base_url,
            "oauth_token_url": f"{self.base_url}{self.oauth_token_path}",
            "m2m_auth_mode": self.m2m_auth_mode if is_api_key else "(n/a)",
            "app_token_header": self.app_token_header if is_api_key else "(n/a)",
            "account_name": self.account_name or "(not set)",
            "m2m_account_id": self.m2m_account_id or "(not set — using account_name)",
            "is_configured": self.is_configured,
        }
        if is_api_key and self._needs_m2m_session:
            summary["m2m_session_login_url"] = self._m2m_session_login_url
            summary["m2m_session_credentials_set"] = bool(
                self._creds.get("username") and self._creds.get("password")
            )
        if not self.is_configured:
            if self.auth_mode not in AUTH_MODES:
                summary["error"] = f"Unsupported auth mode '{self.auth_mode}'"
            else:
                summary["missing_vars"] = self._missing_vars()
        return summary

    # ── Authentication dispatch ───────────────────────────────────────

    async def authenticate(self) -> str:
        """Authenticate using the configured mode. Returns a token or sentinel."""
        self._require_configured()

        if self.auth_mode == "oauth_client_credentials":
            return await self._auth_oauth_client_credentials()
        elif self.auth_mode == "api_key_secret_token":
            return await self._auth_api_key_secret_token()
        elif self.auth_mode == "legacy_short_key_secret":
            return await self._auth_legacy_short_key_secret()
        elif self.auth_mode == "username_password_session":
            return await self._auth_username_password_session()
        else:
            raise VerizonThingSpaceError(f"Unsupported auth mode: {self.auth_mode}")

    # ── Mode: OAuth2 client_credentials ───────────────────────────────

    async def _auth_oauth_client_credentials(self) -> str:
        """OAuth2 client_credentials grant — POST to the configured token path."""
        url = f"{self.base_url}{self.oauth_token_path}"
        client_id = self._creds["client_id"]
        client_secret = self._creds["client_secret"]

        logger.info("Verizon OAuth2 client_credentials auth at %s", url)

        async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
            resp = await http.post(
                url,
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            logger.error("Verizon OAuth2 auth failed: status=%d", resp.status_code)
            raise VerizonThingSpaceError(
                f"OAuth2 authentication failed (HTTP {resp.status_code})",
                status_code=resp.status_code,
                body=self._safe_body(resp),
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise VerizonThingSpaceError(
                "OAuth2 response did not contain access_token",
                body={k: v for k, v in data.items() if k != "access_token"},
            )

        self._session_token = token
        logger.info("Verizon OAuth2 authentication successful")
        return token

    # ── Mode: API key + secret + token ────────────────────────────────

    async def _auth_api_key_secret_token(self) -> str:
        """Exchange API key/secret/token for an OAuth2 Bearer access_token.

        ThingSpace Key Management credentials (API key, API secret, API token)
        are NOT static Bearer tokens — they are credentials used to obtain a
        real OAuth2 access_token via the /oauth2/token endpoint.

        Flow:
            POST /oauth2/token
            Authorization: Basic base64(api_key:api_secret)
            VZ-M2M-Token: <api_token>
            Content-Type: application/x-www-form-urlencoded
            Body: grant_type=client_credentials

        Returns the access_token from the OAuth2 response.
        """
        url = f"{self.base_url}{self.oauth_token_path}"
        api_key = self._creds["api_key"]
        api_secret = self._creds["api_secret"]
        api_token = self._creds["api_token"]

        logger.info(
            "Verizon API key/secret/token OAuth2 exchange at %s (key=%s)",
            url, _redact(api_key),
        )

        async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
            resp = await http.post(
                url,
                data={"grant_type": "client_credentials"},
                auth=(api_key, api_secret),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "VZ-M2M-Token": api_token,
                },
            )

        if resp.status_code != 200:
            logger.error(
                "Verizon API-key OAuth2 exchange failed: status=%d",
                resp.status_code,
            )
            raise VerizonThingSpaceError(
                f"API-key OAuth2 token exchange failed (HTTP {resp.status_code})",
                status_code=resp.status_code,
                body=self._safe_body(resp),
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise VerizonThingSpaceError(
                "API-key OAuth2 response did not contain access_token",
                body={k: v for k, v in data.items() if k != "access_token"},
            )

        self._session_token = token
        logger.info("Verizon API-key OAuth2 exchange successful")
        return token

    # ── Mode: Legacy short key + secret ───────────────────────────────

    async def _auth_legacy_short_key_secret(self) -> str:
        """Legacy short key/secret — may use Basic auth header directly."""
        key = self._creds["short_key"]
        secret = self._creds["short_secret"]
        basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
        self._session_token = basic  # store encoded basic value
        logger.info("Verizon legacy short key/secret mode — credentials loaded")
        return self._session_token

    # ── Mode: Username/password session ───────────────────────────────

    async def _auth_username_password_session(self) -> str:
        """Session login with username/password — POST to session login path."""
        url = self._m2m_session_login_url

        logger.info("Verizon username/password session auth at %s", url)

        async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
            resp = await http.post(
                url,
                json={
                    "username": self._creds["username"],
                    "password": self._creds["password"],
                },
                headers={"Content-Type": "application/json"},
            )

        if resp.status_code != 200:
            logger.error("Verizon session auth failed: status=%d", resp.status_code)
            raise VerizonThingSpaceError(
                f"Session authentication failed (HTTP {resp.status_code})",
                status_code=resp.status_code,
                body=self._safe_body(resp),
            )

        data = resp.json()
        token = data.get("sessionToken") or data.get("token")
        if not token:
            raise VerizonThingSpaceError(
                "Session auth response did not contain a session token",
                body={k: v for k, v in data.items() if k not in ("sessionToken", "token")},
            )

        self._session_token = token
        logger.info("Verizon session authentication successful")
        return token

    # ── M2M session token (separate from primary auth) ────────────────

    async def _obtain_m2m_session_token(self) -> str:
        """Obtain a VZ-M2M session GUID via POST /session/login.

        This is separate from the primary OAuth exchange.  /m2m/v1/ endpoints
        require VZ-M2M-Token to be a real session GUID returned by the
        session login endpoint — NOT the static api_token from Key Management.

        Requires VERIZON_THINGSPACE_USERNAME and VERIZON_THINGSPACE_PASSWORD.
        """
        username = self._creds.get("username", "")
        password = self._creds.get("password", "")

        if not username or not password:
            raise VerizonThingSpaceError(
                "oauth_plus_session_token M2M mode requires "
                "VERIZON_THINGSPACE_USERNAME and VERIZON_THINGSPACE_PASSWORD "
                "to obtain a session GUID for VZ-M2M-Token."
            )

        url = self._m2m_session_login_url

        logger.info(
            "Obtaining M2M session token at %s (user=%s)",
            url, _redact(username),
        )

        # The session login endpoint requires the OAuth Bearer token
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._session_token:
            headers["Authorization"] = f"Bearer {self._session_token}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
            resp = await http.post(
                url,
                json={"username": username, "password": password},
                headers=headers,
            )

        if resp.status_code != 200:
            logger.error(
                "M2M session login failed: status=%d url=%s bearer_sent=%s",
                resp.status_code, url, bool(self._session_token),
            )
            raise VerizonThingSpaceError(
                f"M2M session login failed (HTTP {resp.status_code})",
                status_code=resp.status_code,
                body=self._safe_body(resp),
            )

        data = resp.json()
        token = data.get("sessionToken") or data.get("token")
        if not token:
            raise VerizonThingSpaceError(
                "M2M session login response did not contain a session token",
                body={k: v for k, v in data.items() if k not in ("sessionToken", "token")},
            )

        self._m2m_session_token = token
        logger.info("M2M session token obtained (GUID-format)")
        return token

    # ── Auth headers per mode ─────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        """Build request headers for the active auth mode."""
        if not self._session_token:
            raise VerizonThingSpaceError("Not authenticated — call authenticate() first")

        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self.auth_mode == "oauth_client_credentials":
            headers["Authorization"] = f"Bearer {self._session_token}"

        elif self.auth_mode == "api_key_secret_token":
            headers["Authorization"] = f"Bearer {self._session_token}"
            m2m = self.m2m_auth_mode
            if m2m == "oauth_plus_session_token":
                # Use the real session GUID from /session/login
                if self._m2m_session_token:
                    headers["VZ-M2M-Token"] = self._m2m_session_token
                else:
                    logger.warning(
                        "oauth_plus_session_token mode but no session token yet — "
                        "VZ-M2M-Token will be missing"
                    )
            elif m2m == "oauth_plus_vz_m2m":
                headers["VZ-M2M-Token"] = self._creds["api_token"]
            elif m2m == "oauth_plus_app_token":
                headers["App-Token"] = self._creds["api_token"]
            elif m2m == "oauth_plus_both":
                headers["VZ-M2M-Token"] = self._creds["api_token"]
                headers["App-Token"] = self._creds["api_token"]
            elif m2m == "bearer_only":
                pass  # control test — Bearer only
            else:
                headers[self.app_token_header] = self._creds["api_token"]

        elif self.auth_mode == "legacy_short_key_secret":
            headers["Authorization"] = f"Basic {self._session_token}"

        elif self.auth_mode == "username_password_session":
            headers["Authorization"] = f"Bearer {self._session_token}"
            headers["VZ-M2M-Token"] = self._session_token

        return headers

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _safe_body(resp: httpx.Response) -> str:
        """Extract response body for error context without exposing tokens."""
        text = resp.text[:500] if resp.text else ""
        for secret_pattern in ('"access_token"', '"sessionToken"', '"refresh_token"'):
            if secret_pattern in text:
                return f"(response contained {secret_pattern} value — redacted)"
        return text

    @staticmethod
    def _safe_body_from_str(text: str) -> str:
        """Sanitize an already-extracted body string."""
        text = text[:500]
        for secret_pattern in ('"access_token"', '"sessionToken"', '"refresh_token"'):
            if secret_pattern in text:
                return f"(response contained {secret_pattern} value — redacted)"
        return text

    @property
    def _can_reauth(self) -> bool:
        """True if the auth mode supports re-authentication on 401."""
        return self.auth_mode in (
            "oauth_client_credentials",
            "api_key_secret_token",
            "username_password_session",
        )

    @staticmethod
    def _is_session_token_error(resp: httpx.Response) -> bool:
        """True if the response indicates an invalid/missing session token."""
        if resp.status_code != 400:
            return False
        text = resp.text[:500] if resp.text else ""
        return "SessionToken" in text or "session token" in text.lower()

    # ── Generic request wrapper ───────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        """Make an authenticated request to ThingSpace."""
        if not self._session_token:
            await self.authenticate()
        if self._needs_m2m_session and not self._m2m_session_token:
            await self._obtain_m2m_session_token()

        url = f"{self.base_url}{path}"
        headers = self._auth_headers()

        async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
            resp = await http.request(method, url, headers=headers, json=json, params=params)

        # 401 retry: re-authenticate (OAuth + session token if needed)
        if resp.status_code == 401 and self._can_reauth:
            logger.info("ThingSpace 401 on %s %s — re-authenticating", method, path)
            await self.authenticate()
            if self._needs_m2m_session:
                self._m2m_session_token = None
                await self._obtain_m2m_session_token()
            headers = self._auth_headers()
            async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
                resp = await http.request(method, url, headers=headers, json=json, params=params)

        # Session token invalid retry: refresh just the session GUID
        if self._is_session_token_error(resp) and self._needs_m2m_session:
            logger.info(
                "ThingSpace session token rejected on %s %s — refreshing",
                method, path,
            )
            self._m2m_session_token = None
            await self._obtain_m2m_session_token()
            headers = self._auth_headers()
            async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
                resp = await http.request(method, url, headers=headers, json=json, params=params)

        if resp.status_code >= 400:
            header_names = sorted(headers.keys())
            actual_sent: list[str] | None = None
            if resp.request is not None:
                try:
                    actual_sent = sorted(set(resp.request.headers.keys()))
                except Exception:
                    pass
            body_keys = sorted(json.keys()) if json else None
            param_keys = sorted(params.keys()) if params else None
            logger.error(
                "ThingSpace request failed: %s %s status=%d "
                "intended_headers=%s actual_wire_headers=%s body=%s",
                method, url, resp.status_code, header_names,
                actual_sent, self._safe_body(resp),
            )
            raise VerizonThingSpaceError(
                f"ThingSpace API error: {method} {path} returned {resp.status_code}",
                status_code=resp.status_code,
                body=self._safe_body(resp),
                request_method=method,
                request_url=url,
                request_headers=header_names,
                actual_headers_sent=actual_sent,
                request_params=param_keys,
                request_body_keys=body_keys,
            )

        return resp.json()

    # ── Connection test ───────────────────────────────────────────────

    async def test_connection(self) -> dict[str, Any]:
        """Authenticate and return basic account info.

        This is a safe, read-only call that proves credentials work.
        Returns rich diagnostics about every step, including auth failures.
        """
        self._require_configured()

        token_url = f"{self.base_url}{self.oauth_token_path}"
        session_login_url = self._m2m_session_login_url if self._needs_m2m_session else None

        # Step 1: Primary auth (OAuth exchange)
        try:
            await self.authenticate()
        except VerizonThingSpaceError as e:
            return {
                "authenticated": False,
                "oauth_token_obtained": False,
                "auth_mode": self.auth_mode,
                "m2m_auth_mode": self.m2m_auth_mode,
                "account_name": self.account_name,
                "base_url": self.base_url,
                "oauth_token_url": token_url,
                "oauth_token_status": e.status_code,
                "oauth_token_body": self._safe_body_from_str(
                    e.body if isinstance(e.body, str) else str(e.body or "")
                ),
                "m2m_session_login_url": session_login_url,
                "note": (
                    f"OAuth token exchange failed at {token_url} "
                    f"(HTTP {e.status_code or '?'}). "
                    f"Try a different VERIZON_THINGSPACE_OAUTH_TOKEN_PATH."
                ),
            }

        # Step 2: M2M session token (if oauth_plus_session_token mode)
        m2m_session_obtained: bool | None = None
        m2m_session_status: int | None = None
        m2m_session_body: str | None = None
        if self._needs_m2m_session:
            try:
                await self._obtain_m2m_session_token()
                m2m_session_obtained = True
            except VerizonThingSpaceError as e:
                m2m_session_obtained = False
                m2m_session_status = e.status_code
                m2m_session_body = self._safe_body_from_str(
                    e.body if isinstance(e.body, str) else str(e.body or "")
                )

        # Build headers probe now that both tokens may be set
        probe_headers = self._auth_headers()
        safe_header_names = sorted(probe_headers.keys())

        result: dict[str, Any] = {
            "authenticated": True,
            "oauth_token_obtained": True,
            "auth_mode": self.auth_mode,
            "m2m_auth_mode": self.m2m_auth_mode,
            "account_name": self.account_name,
            "m2m_account_id": self.m2m_account_id or None,
            "base_url": self.base_url,
            "oauth_token_url": token_url,
            "m2m_session_login_url": session_login_url,
            "m2m_session_token_obtained": m2m_session_obtained,
            "m2m_session_login_status": m2m_session_status,
            "m2m_session_login_body": m2m_session_body,
            "token_type": "oauth2_access_token" if self.auth_mode in (
                "oauth_client_credentials", "api_key_secret_token",
            ) else "session",
            "request_headers_sent": safe_header_names,
        }

        # If session token failed, report but don't try M2M endpoints
        if m2m_session_obtained is False:
            result["note"] = (
                f"OAuth token obtained but M2M session login failed at "
                f"{session_login_url} (HTTP {m2m_session_status or '?'}). "
                f"Check VERIZON_THINGSPACE_USERNAME / PASSWORD and "
                f"VERIZON_THINGSPACE_M2M_SESSION_LOGIN_PATH."
            )
            return result

        # Step 3: Try to fetch account info
        acct_id = self.m2m_account_id or self.account_name
        if acct_id:
            acct_path = f"/m2m/v1/accounts/{acct_id}"
            acct_url = f"{self.base_url}{acct_path}"
            try:
                acct = await self._request("GET", acct_path)
                result["account_info"] = acct
            except VerizonThingSpaceError as e:
                result["account_info"] = None
                result["account_info_endpoint"] = e.request_url or acct_url
                result["account_info_status"] = e.status_code
                result["account_info_body"] = self._safe_body_from_str(
                    e.body if isinstance(e.body, str) else str(e.body or "")
                )
                result["m2m_request_method"] = e.request_method or "GET"
                result["m2m_request_url"] = e.request_url or acct_url
                result["m2m_request_headers"] = e.request_headers or safe_header_names
                result["m2m_actual_headers_sent"] = e.actual_headers_sent
                result["m2m_request_params"] = e.request_params
                result["m2m_request_body_keys"] = e.request_body_keys
                intended = e.request_headers or safe_header_names
                actual = e.actual_headers_sent
                header_note = ""
                if actual and set(intended) != set(actual):
                    header_note = (
                        f" WARNING: intended headers {intended} differ from "
                        f"actual wire headers {actual}."
                    )
                result["note"] = (
                    f"Auth OK but M2M endpoint returned HTTP {e.status_code or '?'}. "
                    f"M2M auth mode: {self.m2m_auth_mode}. "
                    f"Headers: {intended}. Account: '{acct_id}'.{header_note}"
                )

        return result

    # ── Device / line inventory ───────────────────────────────────────

    # Verizon ThingSpace API enforces maxNumberOfDevices between 500 and 2000.
    # We always request at least VZ_MIN_PAGE_SIZE from Verizon, then trim
    # the results to the caller's requested display_count on our side.
    VZ_MIN_PAGE_SIZE = 500
    VZ_MAX_PAGE_SIZE = 2000

    async def fetch_devices(
        self,
        *,
        account_name: str | None = None,
        display_count: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch device list from ThingSpace Connectivity Management API.

        Uses POST /m2m/v1/devices/actions/list which supports filtering.

        Args:
            account_name: Override account identifier.
            display_count: How many devices the *caller* wants back.  Verizon's
                API requires maxNumberOfDevices between 500 and 2000, so we may
                fetch more from Verizon than we return.  The caller receives at
                most ``display_count`` devices.
        """
        acct = account_name or self.m2m_account_id or self.account_name
        if not acct:
            raise VerizonThingSpaceError(
                "Account name required. Set VERIZON_THINGSPACE_M2M_ACCOUNT_ID "
                "or VERIZON_THINGSPACE_ACCOUNT_NAME."
            )

        # Clamp the Verizon page size to their allowed range (500–2000).
        vz_page_size = max(self.VZ_MIN_PAGE_SIZE, min(display_count, self.VZ_MAX_PAGE_SIZE))

        all_devices: list[dict] = []
        last_seen_id: str | None = None
        page = 0

        while True:
            body: dict[str, Any] = {
                "accountName": acct,
                "resourceType": "device",
                "maxNumberOfDevices": vz_page_size,
            }
            if last_seen_id:
                body["lastSeenDeviceId"] = last_seen_id

            data = await self._request(
                "POST",
                "/m2m/v1/devices/actions/list",
                json=body,
            )

            devices = data.get("devices") or data.get("resultList") or []
            all_devices.extend(devices)
            page += 1

            has_more = data.get("hasMoreData", False)
            if not has_more or len(all_devices) >= display_count or not devices:
                break

            last_device = devices[-1]
            last_seen_id = (
                last_device.get("deviceId")
                or last_device.get("id")
                or last_device.get("deviceIds", [{}])[0].get("id")
            )
            if not last_seen_id:
                break

        # Trim to the caller's requested count (may be less than Verizon's page)
        all_devices = all_devices[:display_count]

        logger.info(
            "Fetched %d devices from ThingSpace (account=%s, pages=%d, vz_page_size=%d)",
            len(all_devices), acct, page, vz_page_size,
        )
        return all_devices

    async def fetch_device_by_identifier(
        self,
        *,
        kind: str = "ICCID",
        identifier: str,
        account_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch a single device by ICCID, IMEI, MDN, or MSISDN."""
        acct = account_name or self.m2m_account_id or self.account_name
        if not acct:
            raise VerizonThingSpaceError("Account name required.")

        body = {
            "accountName": acct,
            "deviceId": {"kind": kind.upper(), "id": identifier},
        }

        try:
            data = await self._request(
                "POST",
                "/m2m/v1/devices/actions/list",
                json=body,
            )
            devices = data.get("devices") or data.get("resultList") or []
            return devices[0] if devices else None
        except VerizonThingSpaceError as e:
            if e.status_code == 404:
                return None
            raise


# ── Normalizer ────────────────────────────────────────────────────────────

def normalize_verizon_device(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a ThingSpace device record into the carrier-agnostic shape."""
    device_ids = raw.get("deviceIds") or raw.get("deviceIdentifiers") or []
    id_map: dict[str, str] = {}
    for did in device_ids:
        kind = (did.get("kind") or "").upper()
        val = did.get("id") or ""
        if kind and val:
            id_map[kind] = val

    conn_status = (
        raw.get("connectionStatus")
        or raw.get("state")
        or raw.get("status")
        or ""
    )
    activation_status = raw.get("activationStatus") or raw.get("state") or conn_status

    sim_status = raw.get("simStatus") or ""
    if not sim_status and conn_status:
        sim_status = "active" if conn_status.lower() in ("connected", "active") else conn_status

    usage_mb: float | None = None
    usage_data = raw.get("usage") or raw.get("dataTotalUsage")
    if isinstance(usage_data, (int, float)):
        usage_mb = float(usage_data)
    elif isinstance(usage_data, dict):
        usage_mb = usage_data.get("totalMB") or usage_data.get("dataTotalMB")

    last_seen: str | None = None
    for ts_field in ("lastConnectionDate", "lastActivationDate", "lastStatusChangeDate", "lastStatusTime"):
        if raw.get(ts_field):
            last_seen = raw[ts_field]
            break

    # Extract user-defined label from ThingSpace customFields
    # Verizon stores these as [{"key": "...", "value": "..."}] or as a flat dict
    custom_label = None
    custom_fields = raw.get("customFields") or raw.get("custom") or []
    if isinstance(custom_fields, list):
        for cf in custom_fields:
            if isinstance(cf, dict):
                k = (cf.get("key") or "").lower()
                v = cf.get("value") or ""
                if k in ("label", "name", "location", "site", "description", "customername") and v:
                    custom_label = v
                    break
        # Fallback: use the first non-empty custom field value
        if not custom_label:
            for cf in custom_fields:
                if isinstance(cf, dict) and cf.get("value"):
                    custom_label = cf["value"]
                    break
    elif isinstance(custom_fields, dict):
        custom_label = custom_fields.get("label") or custom_fields.get("name") or custom_fields.get("location")

    # Also check groupName, deviceName, deviceLabel — common ThingSpace fields
    if not custom_label:
        for field in ("groupName", "deviceName", "deviceLabel", "billingName", "customerName"):
            if raw.get(field):
                custom_label = raw[field]
                break

    return {
        "carrier": "verizon",
        "external_id": id_map.get("MDN") or id_map.get("IMEI") or raw.get("id", ""),
        "imei": id_map.get("IMEI"),
        "iccid": id_map.get("ICCID"),
        "msisdn": id_map.get("MDN") or id_map.get("MSISDN"),
        "sim_status": sim_status,
        "line_status": conn_status,
        "activation_status": activation_status,
        "usage_data_mb": usage_mb,
        "last_seen_at": last_seen,
        "custom_label": custom_label,
        "raw_payload": raw,
    }


# ── Convenience singleton ────────────────────────────────────────────────

_client: VerizonThingSpaceClient | None = None


def get_verizon_client() -> VerizonThingSpaceClient:
    """Return a module-level client (lazy singleton)."""
    global _client
    if _client is None:
        _client = VerizonThingSpaceClient()
    return _client


def reset_verizon_client() -> None:
    """Reset the singleton — used after config changes or in tests."""
    global _client
    _client = None
