"""T-Mobile Wholesale PIT callback endpoints.

Includes the original generic /callback (single bring-up probe) plus the
six event-specific paths T-Mobile uses for callback validation against
https://pit-api.manleysolutions.com.

These endpoints are intentionally unauthenticated for now — they exist
so T-Mobile's callback validator can confirm DNS/TLS/routing reach the
target paths. Signature/IP validation will be added once T-Mobile
provides their final callback signing requirements.

Logging policy (per requirement #7):
  Log method, path, event, query params, and a safe body preview.
  Never log Authorization, cookies, tokens, consumer keys, or any
  header whose name matches /auth|token|secret|key|cookie|password/i.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Request

logger = logging.getLogger("true911.tmobile_callback")
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────

_SENSITIVE_HEADER_RE = re.compile(
    r"auth|token|secret|key|cookie|password", re.IGNORECASE
)


def _safe_headers(headers) -> dict[str, str]:
    """Return a header dict with sensitive values redacted."""
    redacted: dict[str, str] = {}
    for name, value in headers.items():
        if _SENSITIVE_HEADER_RE.search(name):
            redacted[name] = "[REDACTED]"
        else:
            redacted[name] = value
    return redacted


async def _safe_body_preview(request: Request) -> Any:
    """Return a JSON-decoded body if possible, else a UTF-8 preview, else None.
    Never raises — empty/invalid JSON resolves to None.
    """
    try:
        raw = await request.body()
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        try:
            return raw.decode("utf-8", errors="replace")[:1000]
        except Exception:
            return None


def _ack(event: str) -> dict[str, str]:
    """Standard 200 acknowledgement payload for callback validators."""
    return {
        "status": "ok",
        "provider": "t-mobile",
        "event": event,
        "message": "Callback endpoint reachable",
    }


async def _log_callback(request: Request, event: str, *, include_body: bool) -> None:
    body_preview: Any = None
    if include_body:
        body_preview = await _safe_body_preview(request)
    logger.info(
        "T-Mobile callback | method=%s | path=%s | event=%s | query=%s | headers=%s | body=%s",
        request.method,
        request.url.path,
        event,
        dict(request.query_params),
        _safe_headers(request.headers),
        body_preview,
    )


# ── Original generic probe (kept for backwards compatibility) ────

@router.post("/callback")
async def tmobile_wholesale_callback(request: Request):
    raw_body = await request.body()
    try:
        body_preview = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_preview = repr(raw_body)

    logger.info(
        "T-Mobile PIT callback received | method=%s | query=%s | headers=%s | body=%s",
        request.method,
        dict(request.query_params),
        _safe_headers(request.headers),
        body_preview,
    )

    return {"success": True, "message": "callback received"}


@router.get("/callback")
async def tmobile_wholesale_callback_probe(request: Request):
    """Manual liveness probe (curl/browser). Not used by T-Mobile."""
    logger.info(
        "T-Mobile PIT callback GET probe | query=%s | headers=%s",
        dict(request.query_params),
        _safe_headers(request.headers),
    )
    return {"success": True, "message": "callback received"}


# ── Event-specific callback validators ────────────────────────────
#
# T-Mobile requires unique, reachable callback URLs for each event type.
# Each pair below answers GET (validator probe) and POST (event payload)
# with HTTP 200 and a fixed JSON acknowledgement. No business logic runs
# here yet — these are receipt confirmations only.

_CALLBACK_EVENTS = {
    "provisioning":       "provisioning",
    "usage":              "usage",
    "device-change":      "device_change",
    "subscriber-status":  "subscriber_status",
    "static-ip":          "static_ip",
    "cim":                "cim",
}


@router.get("/callback/provisioning")
async def cb_provisioning_get(request: Request):
    await _log_callback(request, "provisioning", include_body=False)
    return _ack("provisioning")


@router.post("/callback/provisioning")
async def cb_provisioning_post(request: Request):
    await _log_callback(request, "provisioning", include_body=True)
    return _ack("provisioning")


@router.get("/callback/usage")
async def cb_usage_get(request: Request):
    await _log_callback(request, "usage", include_body=False)
    return _ack("usage")


@router.post("/callback/usage")
async def cb_usage_post(request: Request):
    await _log_callback(request, "usage", include_body=True)
    return _ack("usage")


@router.get("/callback/device-change")
async def cb_device_change_get(request: Request):
    await _log_callback(request, "device_change", include_body=False)
    return _ack("device_change")


@router.post("/callback/device-change")
async def cb_device_change_post(request: Request):
    await _log_callback(request, "device_change", include_body=True)
    return _ack("device_change")


@router.get("/callback/subscriber-status")
async def cb_subscriber_status_get(request: Request):
    await _log_callback(request, "subscriber_status", include_body=False)
    return _ack("subscriber_status")


@router.post("/callback/subscriber-status")
async def cb_subscriber_status_post(request: Request):
    await _log_callback(request, "subscriber_status", include_body=True)
    return _ack("subscriber_status")


@router.get("/callback/static-ip")
async def cb_static_ip_get(request: Request):
    await _log_callback(request, "static_ip", include_body=False)
    return _ack("static_ip")


@router.post("/callback/static-ip")
async def cb_static_ip_post(request: Request):
    await _log_callback(request, "static_ip", include_body=True)
    return _ack("static_ip")


@router.get("/callback/cim")
async def cb_cim_get(request: Request):
    await _log_callback(request, "cim", include_body=False)
    return _ack("cim")


@router.post("/callback/cim")
async def cb_cim_post(request: Request):
    await _log_callback(request, "cim", include_body=True)
    return _ack("cim")
