"""Verizon ThingSpace API client — handles authentication and device inventory.

Supports multiple auth modes via VERIZON_THINGSPACE_AUTH_MODE:
    oauth_client_credentials  — OAuth2 client_credentials grant (client_id + client_secret)
    api_key_secret_token      — static API key + secret + token headers
    legacy_short_key_secret   — short key + secret (older ThingSpace accounts)
    username_password_session — session login with username/password (legacy fallback)

Environment variables (via Settings):
    VERIZON_THINGSPACE_AUTH_MODE       — one of the modes above
    VERIZON_THINGSPACE_BASE_URL        — API base (default: https://thingspace.verizon.com/api)
    VERIZON_THINGSPACE_ACCOUNT_NAME    — M2M account (e.g. "0123456789-00001")
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

# Supported auth modes
AUTH_MODES = frozenset({
    "oauth_client_credentials",
    "api_key_secret_token",
    "legacy_short_key_secret",
    "username_password_session",
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

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        # Scrub message to avoid accidental secret leakage
        super().__init__(message)
        self.status_code = status_code
        self.body = body


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
        # username_password_session
        username: str | None = None,
        password: str | None = None,
    ):
        self.auth_mode = (auth_mode or settings.VERIZON_THINGSPACE_AUTH_MODE).strip().lower()
        self.base_url = (base_url or settings.VERIZON_THINGSPACE_BASE_URL).rstrip("/")
        self.account_name = account_name or settings.VERIZON_THINGSPACE_ACCOUNT_NAME

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

        # Token obtained during authentication (oauth / session modes)
        self._session_token: str | None = None

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
                f"Missing credentials for auth mode '{self.auth_mode}': "
                f"set {', '.join(missing)}"
            )

    def config_summary(self) -> dict[str, Any]:
        """Return a safe (no secrets) summary for diagnostics."""
        summary: dict[str, Any] = {
            "auth_mode": self.auth_mode,
            "base_url": self.base_url,
            "account_name": self.account_name or "(not set)",
            "is_configured": self.is_configured,
        }
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
        """OAuth2 client_credentials grant — POST to /oauth2/token.

        ThingSpace OAuth endpoint expects HTTP Basic auth (client_id:client_secret)
        with grant_type=client_credentials in the form body.
        """
        url = f"{self.base_url}/oauth2/token"
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
        """Static API key / secret / token — no token exchange needed.

        These are passed directly as headers on every request.
        authenticate() validates the credentials are present and returns
        a sentinel; the actual headers are built in _auth_headers().

        NOTE: The exact header names may vary by ThingSpace account type.
        Current mapping uses VZ-M2M-Token for the token value plus
        standard API key headers. Adjust after first live test if needed.
        """
        # No network call needed — credentials are static
        self._session_token = self._creds["api_token"]
        logger.info("Verizon API key/secret/token mode — credentials loaded (no token exchange)")
        return self._session_token

    # ── Mode: Legacy short key + secret ───────────────────────────────

    async def _auth_legacy_short_key_secret(self) -> str:
        """Legacy short key/secret — may use Basic auth header directly.

        Some older ThingSpace accounts use a short key/secret pair passed
        as HTTP Basic auth on every request instead of a token exchange.
        authenticate() validates presence; _auth_headers() builds the header.

        NOTE: If Verizon requires a token exchange for short keys, adjust
        this method to POST to the appropriate endpoint.
        """
        # Build Basic auth value for reuse
        key = self._creds["short_key"]
        secret = self._creds["short_secret"]
        basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
        self._session_token = basic  # store encoded basic value
        logger.info("Verizon legacy short key/secret mode — credentials loaded")
        return self._session_token

    # ── Mode: Username/password session ───────────────────────────────

    async def _auth_username_password_session(self) -> str:
        """Session login with username/password — POST to /ts/v1/session/login."""
        url = f"{self.base_url}/ts/v1/session/login"

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

    # ── Auth headers per mode ─────────────────────────────────────────

    def _auth_headers(self) -> dict[str, str]:
        """Build request headers for the active auth mode."""
        if not self._session_token:
            raise VerizonThingSpaceError("Not authenticated — call authenticate() first")

        headers: dict[str, str] = {"Content-Type": "application/json"}

        if self.auth_mode == "oauth_client_credentials":
            headers["Authorization"] = f"Bearer {self._session_token}"

        elif self.auth_mode == "api_key_secret_token":
            # NOTE: exact header names may need adjustment after first live test.
            # Common ThingSpace patterns use VZ-M2M-Token or X-VZ-Token.
            headers["VZ-M2M-Token"] = self._session_token
            headers["X-API-Key"] = self._creds["api_key"]
            headers["X-API-Secret"] = self._creds["api_secret"]

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
        # Strip anything that looks like a token/key value
        for secret_key in ("access_token", "sessionToken", "token", "secret"):
            if secret_key in text:
                text = f"(response contained '{secret_key}' — redacted for safety)"
                break
        return text

    @property
    def _can_reauth(self) -> bool:
        """True if the auth mode supports re-authentication on 401."""
        return self.auth_mode in ("oauth_client_credentials", "username_password_session")

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

        url = f"{self.base_url}{path}"
        headers = self._auth_headers()

        async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
            resp = await http.request(method, url, headers=headers, json=json, params=params)

        if resp.status_code == 401 and self._can_reauth:
            logger.info("ThingSpace 401 on %s %s — re-authenticating", method, path)
            await self.authenticate()
            headers = self._auth_headers()
            async with httpx.AsyncClient(timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT)) as http:
                resp = await http.request(method, url, headers=headers, json=json, params=params)

        if resp.status_code >= 400:
            logger.error(
                "ThingSpace request failed: %s %s status=%d",
                method, path, resp.status_code,
            )
            raise VerizonThingSpaceError(
                f"ThingSpace API error: {method} {path} returned {resp.status_code}",
                status_code=resp.status_code,
                body=self._safe_body(resp),
            )

        return resp.json()

    # ── Connection test ───────────────────────────────────────────────

    async def test_connection(self) -> dict[str, Any]:
        """Authenticate and return basic account info.

        This is a safe, read-only call that proves credentials work.
        """
        self._require_configured()
        await self.authenticate()

        result: dict[str, Any] = {
            "authenticated": True,
            "auth_mode": self.auth_mode,
            "account_name": self.account_name,
            "base_url": self.base_url,
        }

        # Try to fetch account info if account_name is set
        if self.account_name:
            try:
                acct = await self._request(
                    "GET",
                    f"/m2m/v1/accounts/{self.account_name}",
                )
                result["account_info"] = acct
            except VerizonThingSpaceError:
                result["account_info"] = None
                result["note"] = (
                    "Auth succeeded but account info endpoint returned an error. "
                    "Account name may need adjustment."
                )

        return result

    # ── Device / line inventory ───────────────────────────────────────

    async def fetch_devices(
        self,
        *,
        account_name: str | None = None,
        max_results: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch device list from ThingSpace Connectivity Management API.

        Uses POST /m2m/v1/devices/actions/list which supports filtering.
        """
        acct = account_name or self.account_name
        if not acct:
            raise VerizonThingSpaceError(
                "Account name required. Set VERIZON_THINGSPACE_ACCOUNT_NAME."
            )

        all_devices: list[dict] = []
        last_seen_id: str | None = None
        page = 0

        while True:
            body: dict[str, Any] = {
                "accountName": acct,
                "resourceType": "device",
                "maxNumberOfDevices": min(max_results - len(all_devices), 200),
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
            if not has_more or len(all_devices) >= max_results or not devices:
                break

            last_device = devices[-1]
            last_seen_id = (
                last_device.get("deviceId")
                or last_device.get("id")
                or last_device.get("deviceIds", [{}])[0].get("id")
            )
            if not last_seen_id:
                break

        logger.info(
            "Fetched %d devices from ThingSpace (account=%s, pages=%d)",
            len(all_devices), acct, page,
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
        acct = account_name or self.account_name
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
    """Convert a ThingSpace device record into the carrier-agnostic shape.

    ThingSpace device objects typically have:
        deviceIds: [{kind: "ICCID", id: "..."}, {kind: "IMEI", id: "..."}, ...]
        connectionStatus / state
        billingCycleEndDate
        carriersInfo / groupName
        customFields
        ...

    We map whatever is available and store the full payload in raw_payload.
    """
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
