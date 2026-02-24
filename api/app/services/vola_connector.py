"""HTTP client for the True911 Vola Connector microservice."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import settings

log = logging.getLogger("vola_connector")

# Reusable client — created lazily, closed on shutdown.
_client: httpx.AsyncClient | None = None

# Generous read timeout: the sync endpoints poll Vola internally and can
# take up to ~25 s before they return.
_TIMEOUT = httpx.Timeout(connect=5.0, read=35.0, write=10.0, pool=5.0)


def _base_url() -> str:
    url = settings.VOLA_CONNECTOR_BASE_URL
    if not url:
        raise HTTPException(503, "Vola connector is not configured (VOLA_CONNECTOR_BASE_URL is empty)")
    return url.rstrip("/")


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if settings.VOLA_CONNECTOR_API_KEY:
        h["x-api-key"] = settings.VOLA_CONNECTOR_API_KEY
    return h


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


async def close() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


def _map_error(exc: httpx.HTTPStatusError) -> HTTPException:
    """Convert upstream connector HTTP errors to FastAPI exceptions."""
    code = exc.response.status_code
    try:
        detail = exc.response.json().get("detail", exc.response.text)
    except Exception:
        detail = exc.response.text
    if code == 504:
        return HTTPException(504, detail)
    if code == 502:
        return HTTPException(502, detail)
    if 400 <= code < 500:
        return HTTPException(code, detail)
    return HTTPException(502, f"Vola connector returned {code}: {detail}")


async def get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET from the connector and return parsed JSON."""
    client = await _get_client()
    url = f"{_base_url()}{path}"
    try:
        resp = await client.get(url, params=params, headers=_headers())
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _map_error(exc)
    except httpx.RequestError as exc:
        log.error("Connector unreachable: %s", exc)
        raise HTTPException(502, f"Vola connector unreachable: {exc}")
    return resp.json()


async def post(path: str, json: dict[str, Any] | None = None) -> Any:
    """POST to the connector and return parsed JSON."""
    client = await _get_client()
    url = f"{_base_url()}{path}"
    try:
        resp = await client.post(url, json=json, headers=_headers())
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise _map_error(exc)
    except httpx.RequestError as exc:
        log.error("Connector unreachable: %s", exc)
        raise HTTPException(502, f"Vola connector unreachable: {exc}")
    return resp.json()
