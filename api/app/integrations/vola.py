"""VolaCloud / Flying Voice TR-069 client.

Ported from true911-vola-connector to run inside true911-prod directly.
Provides: auth, org listing, device listing, reboot, parameter get/set,
task polling, and safety controls (allowlist / denylist / dangerous prefix).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("true911.integrations.vola")

# ── Module-level token cache ────────────────────────────────────────────────

_token: str | None = None
_token_obtained_at: float = 0.0
_TOKEN_LIFETIME_SECONDS: int = 24 * 60 * 60  # 24 h
_TOKEN_REFRESH_BUFFER: int = 5 * 60           # 5 min

# ── Safety controls ─────────────────────────────────────────────────────────

MAX_PARAMETER_NAMES: int = 50
MAX_SET_PARAMETER_VALUES: int = 50

# Default safe read prefixes (empty = allow all in dev)
DEFAULT_ALLOWED_PARAM_PREFIXES: list[str] = []

# Default safe write prefixes
DEFAULT_ALLOWED_SET_PREFIXES: list[str] = [
    "Device.DeviceInfo.ProvisioningCode",
    "Device.DeviceInfo.X_",
    "Device.ManagementServer.PeriodicInformInterval",
    "Device.Time.",
    "InternetGatewayDevice.DeviceInfo.ProvisioningCode",
    "InternetGatewayDevice.ManagementServer.PeriodicInformInterval",
    "InternetGatewayDevice.Time.",
]

DEFAULT_BLOCKED_SET_PREFIXES: list[str] = [
    "Device.Users.",
    "Device.Security.",
]

DEFAULT_DENYLIST_EXACT: set[str] = {
    "Device.ManagementServer.URL",
    "Device.ManagementServer.Username",
    "Device.ManagementServer.Password",
    "InternetGatewayDevice.ManagementServer.URL",
    "InternetGatewayDevice.ManagementServer.Username",
    "InternetGatewayDevice.ManagementServer.Password",
}

# Hardcoded dangerous prefixes that are always blocked unless explicitly allowed
HARDCODED_DANGEROUS_PREFIXES: list[str] = [
    "Device.Security.",
    "Device.Users.",
    "InternetGatewayDevice.UserInterface.",
    "InternetGatewayDevice.DeviceInfo.X_Password",
]


def _token_expired() -> bool:
    if _token is None:
        return True
    age = time.time() - _token_obtained_at
    return age >= (_TOKEN_LIFETIME_SECONDS - _TOKEN_REFRESH_BUFFER)


def _invalidate_token() -> None:
    global _token, _token_obtained_at
    _token = None
    _token_obtained_at = 0.0


# ── HTTP helpers ────────────────────────────────────────────────────────────

_http: httpx.AsyncClient | None = None


async def _client() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(timeout=30.0)
    return _http


async def close_client() -> None:
    global _http
    if _http and not _http.is_closed:
        await _http.aclose()
        _http = None


class VolaClient:
    """Stateful VOLA API client scoped to specific credentials."""

    def __init__(
        self,
        base_url: str,
        email: str,
        password: str,
        org_id: str | None = None,
        allowed_param_prefixes: list[str] | None = None,
        allowed_set_prefixes: list[str] | None = None,
        blocked_set_prefixes: list[str] | None = None,
        denylist_exact: set[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.org_id = org_id

        # Safety controls
        self.allowed_param_prefixes = allowed_param_prefixes if allowed_param_prefixes is not None else DEFAULT_ALLOWED_PARAM_PREFIXES
        self.allowed_set_prefixes = allowed_set_prefixes if allowed_set_prefixes is not None else DEFAULT_ALLOWED_SET_PREFIXES
        self.blocked_set_prefixes = blocked_set_prefixes if blocked_set_prefixes is not None else DEFAULT_BLOCKED_SET_PREFIXES
        self.denylist_exact = denylist_exact if denylist_exact is not None else DEFAULT_DENYLIST_EXACT

        # Per-instance token cache
        self._token: str | None = None
        self._token_obtained_at: float = 0.0

    def _token_expired(self) -> bool:
        if self._token is None:
            return True
        age = time.time() - self._token_obtained_at
        return age >= (_TOKEN_LIFETIME_SECONDS - _TOKEN_REFRESH_BUFFER)

    def _invalidate_token(self) -> None:
        self._token = None
        self._token_obtained_at = 0.0

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def _authed_headers(self) -> dict[str, str]:
        token = await self.get_access_token()
        return {"accessToken": token, "Content-Type": "application/json"}

    async def _post(self, path: str, payload: dict[str, Any], *, retry_on_401: bool = True) -> dict[str, Any]:
        """POST to Vola API with automatic 401 retry (re-auth once)."""
        client = await _client()
        headers = await self._authed_headers()
        url = self._build_url(path)

        logger.debug("POST %s  payload=%s", url, payload)
        resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code == 401 and retry_on_401:
            logger.info("Got 401 – refreshing token and retrying")
            self._invalidate_token()
            headers = await self._authed_headers()
            resp = await client.post(url, json=payload, headers=headers)

        resp.raise_for_status()
        return resp.json()

    # ── Auth ────────────────────────────────────────────────────────────────

    async def get_access_token(self) -> str:
        """Return a cached token or fetch a fresh one."""
        if not self._token_expired():
            return self._token  # type: ignore[return-value]

        if not self.email or not self.password:
            raise RuntimeError("VOLA_EMAIL and VOLA_PASSWORD must be set")

        client = await _client()
        url = self._build_url("/user-mgmt-api/get-access-token")
        payload = {"email": self.email, "password": self.password}

        logger.info("Authenticating as %s against %s", self.email, self.base_url)
        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        body = resp.json()

        data = body.get("data", body)
        self._token = data["accessToken"]
        self._token_obtained_at = time.time()
        logger.info("VOLA token obtained successfully")
        return self._token  # type: ignore[return-value]

    # ── Orgs ────────────────────────────────────────────────────────────────

    async def get_org_list(self) -> list[dict[str, Any]]:
        """Fetch organizations the authenticated user belongs to."""
        body = await self._post("/user-mgmt-api/user-operation", {
            "operation": "getOrgList",
        })
        data = body.get("data", body)
        if isinstance(data, list):
            return data
        return data.get("orgList", []) if isinstance(data, dict) else []

    async def switch_org(self, org_id: str) -> dict[str, Any]:
        """Switch the session context to a different org."""
        body = await self._post("/user-mgmt-api/user-operation", {
            "operation": "switchOrg",
            "orgId": org_id,
        })
        data = body.get("data", body)
        if isinstance(data, dict) and "accessToken" in data:
            self._token = data["accessToken"]
            self._token_obtained_at = time.time()
        return data

    # ── Devices ─────────────────────────────────────────────────────────────

    async def get_device_list(self, usage_status: str = "inUse") -> dict[str, Any]:
        """Return device list filtered by usage status."""
        if self.org_id:
            await self.switch_org(self.org_id)

        body = await self._post("/org-mgmt-api/device-list", {
            "usageStatus": usage_status,
            "pageNum": 1,
            "pageSize": 500,
        })
        return body.get("data", body)

    # ── Tasks ───────────────────────────────────────────────────────────────

    async def create_reboot_task(self, device_sn: str) -> dict[str, Any]:
        """Create a reboot task for a single device."""
        body = await self._post("/org-mgmt-api/device-task-operation", {
            "operation": "createTask",
            "name": "reboot",
            "deviceSNList": [device_sn],
        })
        return body.get("data", body)

    async def get_task_results(self, task_ids: list[str]) -> list[dict[str, Any]]:
        """Poll task results for one or more task IDs."""
        body = await self._post("/org-mgmt-api/device-task-operation", {
            "operation": "getTaskResult",
            "taskIdList": task_ids,
        })
        data = body.get("data", body)
        if isinstance(data, list):
            return data
        return data.get("taskList", [data]) if isinstance(data, dict) else [data]

    async def get_task_result_raw(self, task_ids: list[str]) -> dict[str, Any]:
        """Return the raw 'data' envelope from getTaskResult."""
        body = await self._post("/org-mgmt-api/device-task-operation", {
            "operation": "getTaskResult",
            "taskIdList": task_ids,
        })
        return body.get("data", body)

    # ── Parameter read (TR-069 getParameterValues) ──────────────────────────

    async def create_get_parameter_values_task(
        self, device_sn: str, parameter_names: list[str]
    ) -> dict[str, Any]:
        body = await self._post("/org-mgmt-api/device-task-operation", {
            "operation": "createTask",
            "parameterBody": {
                "deviceSN": device_sn,
                "name": "getParameterValues",
                "parameterNames": parameter_names,
                "parameterValues": [],
            },
        })
        return body.get("data", body)

    # ── Parameter write (TR-069 setParameterValues) ─────────────────────────

    async def create_set_parameter_values_task(
        self, device_sn: str, parameter_values: list[list[str]]
    ) -> dict[str, Any]:
        body = await self._post("/org-mgmt-api/device-task-operation", {
            "operation": "createTask",
            "parameterBody": {
                "deviceSN": device_sn,
                "name": "setParameterValues",
                "parameterNames": [],
                "parameterValues": parameter_values,
            },
        })
        return body.get("data", body)

    # ── Sync helpers (poll until done) ──────────────────────────────────────

    async def poll_task_sync(
        self, task_id: str, timeout_seconds: int = 20, poll_interval: float = 1.0
    ) -> dict[str, Any]:
        """Poll a task until success, failure, or timeout."""
        elapsed = 0.0
        timeout = float(timeout_seconds)

        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            raw_data = await self.get_task_result_raw([task_id])
            if not isinstance(raw_data, dict):
                continue

            success_list = raw_data.get("successList", [])
            failed_list = raw_data.get("failedList", [])

            for item in (success_list or []):
                item_tid = item.get("taskId", item.get("id", ""))
                if item_tid == task_id or not item_tid:
                    return {"status": "success", "result": item}

            for item in (failed_list or []):
                item_tid = item.get("taskId", item.get("id", ""))
                if item_tid == task_id or not item_tid:
                    return {"status": "failed", "result": item}

        return {"status": "timeout", "result": None}

    # ── Safety validation ───────────────────────────────────────────────────

    def validate_param_names(self, names: list[str]) -> str | None:
        """Return error message if invalid, None if OK."""
        if not names:
            return "parameter_names must not be empty"
        if len(names) > MAX_PARAMETER_NAMES:
            return f"Too many parameter_names ({len(names)}); max is {MAX_PARAMETER_NAMES}"
        if self.allowed_param_prefixes:
            for name in names:
                if not any(name.startswith(pfx) for pfx in self.allowed_param_prefixes):
                    return f"Parameter '{name}' not allowed. Permitted prefixes: {self.allowed_param_prefixes}"
        return None

    def validate_set_param_values(self, values: list[list[str]]) -> str | None:
        """Return error message if invalid, None if OK."""
        if not values:
            return "parameter_values must not be empty"
        if len(values) > MAX_SET_PARAMETER_VALUES:
            return f"Too many parameter_values ({len(values)}); max is {MAX_SET_PARAMETER_VALUES}"

        for pair in values:
            if not isinstance(pair, list) or len(pair) != 2:
                return f"Each parameter_value must be a [node, value] pair; got: {pair!r}"

        nodes = [pair[0] for pair in values]

        # 1. Exact denylist
        if self.denylist_exact:
            for node in nodes:
                if node in self.denylist_exact:
                    return f"Parameter '{node}' is explicitly denied"

        # 2. Blocked prefixes (always checked)
        for node in nodes:
            for pfx in self.blocked_set_prefixes:
                if node.startswith(pfx):
                    return f"Parameter '{node}' matches blocked prefix '{pfx}'"

        # 3. Hardcoded dangerous prefixes
        for node in nodes:
            for dpfx in HARDCODED_DANGEROUS_PREFIXES:
                if node.startswith(dpfx):
                    if not any(node.startswith(a) for a in self.allowed_set_prefixes):
                        return f"Parameter '{node}' matches dangerous prefix '{dpfx}' and is not in allowed set prefixes"

        # 4. Allowlist (if configured)
        if self.allowed_set_prefixes:
            for node in nodes:
                if not any(node.startswith(pfx) for pfx in self.allowed_set_prefixes):
                    return f"Parameter '{node}' not in allowed set prefixes: {self.allowed_set_prefixes}"

        return None


def extract_parameter_values(raw: Any) -> dict[str, str]:
    """Best-effort extraction of TR-069 parameter name/value pairs from task result."""
    values: dict[str, str] = {}
    if raw is None:
        return values

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if "name" in obj and "value" in obj:
                values[str(obj["name"])] = str(obj["value"])
            for key in ("parameterValues", "parameterValue", "parameterList", "result", "data"):
                child = obj.get(key)
                if child is not None:
                    _walk(child)
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    try:
        _walk(raw)
    except Exception:
        logger.warning("Could not extract parameter values from raw result", exc_info=True)
    return values


def normalize_vola_device(raw: dict) -> dict[str, Any]:
    """Normalize a raw Vola device dict into a consistent shape."""
    return {
        "device_sn": raw.get("deviceSN", raw.get("sn", "")),
        "mac": raw.get("mac", ""),
        "model": raw.get("model", raw.get("deviceModel", "")),
        "firmware_version": raw.get("firmwareVersion", raw.get("version", "")),
        "ip": raw.get("ip", raw.get("lanIp", "")),
        "status": raw.get("status", ""),
        "usage_status": raw.get("usageStatus", ""),
        "org_id": raw.get("orgId", ""),
        "org_name": raw.get("orgName", ""),
    }
