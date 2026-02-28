"""Base provider client with shared httpx patterns."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger("true911.integrations")


class ProviderError(Exception):
    """Raised when a provider API call fails."""

    def __init__(self, provider: str, status_code: int | None, message: str):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {status_code}: {message}")


class BaseProviderClient(ABC):
    """Abstract base for all provider HTTP clients.

    Subclasses set ``provider_name`` and ``base_url`` and implement
    domain-specific methods.  Shared concerns (auth headers, timeouts,
    idempotency keys, error mapping) live here.
    """

    provider_name: str = "base"
    base_url: str = ""

    def __init__(self, api_key: str, api_secret: str | None = None, timeout: float = 30.0):
        self.api_key = api_key
        self.api_secret = api_secret
        self._timeout = timeout

    # ── Auth header (override per-provider) ──────────────────────

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    # ── Idempotency ──────────────────────────────────────────────

    @staticmethod
    def _idempotency_key() -> str:
        return str(uuid.uuid4())

    # ── Core HTTP ────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        extra_headers: dict | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        headers = {
            **self._auth_headers(),
            "Content-Type": "application/json",
            "X-Idempotency-Key": self._idempotency_key(),
        }
        if extra_headers:
            headers.update(extra_headers)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.request(method, url, json=json, params=params, headers=headers)
            except httpx.TimeoutException:
                raise ProviderError(self.provider_name, None, f"Timeout calling {method} {path}")
            except httpx.RequestError as exc:
                raise ProviderError(self.provider_name, None, str(exc))

        if resp.status_code >= 400:
            body = resp.text[:500]
            logger.warning("%s API error %s %s: %s", self.provider_name, resp.status_code, path, body)
            raise ProviderError(self.provider_name, resp.status_code, body)

        if resp.status_code == 204:
            return {}
        return resp.json()

    async def get(self, path: str, **kwargs: Any) -> dict:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> dict:
        return await self._request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> dict:
        return await self._request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> dict:
        return await self._request("DELETE", path, **kwargs)
