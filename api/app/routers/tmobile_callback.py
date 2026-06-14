"""T-Mobile Wholesale PIT callback endpoints.

Includes the original generic /callback (single bring-up probe) plus the
six event-specific paths T-Mobile uses for callback validation against
https://pit-api.manleysolutions.com.

Reachability probes (GET) are unauthenticated so T-Mobile's callback
validator can confirm DNS/TLS/routing reach the target paths.

Authenticity of state-changing POSTs is gated at the INGEST step (C2):
when FEATURE_TMOBILE_CALLBACK_AUTH is on, a callback is only archived +
enqueued (i.e. allowed to mutate Device state) if it presents the shared
secret (X-True911-Callback-Token header or ?token= query) and, when
TMOBILE_CALLBACK_IP_ENFORCE is on, arrives from an allowlisted source.
A failed check is logged and dropped; the handler still returns HTTP 200
to preserve the validator contract.  HMAC signature verification remains
deferred until T-Mobile publishes a callback-signing spec.  See
app/security/tmobile_callback_auth.py and docs/TMOBILE_CALLBACK_AUTH.md.

Logging policy (per requirement #7):
  Log method, path, event, query params, and a safe body preview.
  Never log Authorization, cookies, tokens, consumer keys, or any
  header whose name matches /auth|token|secret|key|cookie|password/i.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models.integration_payload import IntegrationPayload
from app.security.tmobile_callback_auth import check_callback_auth
from app.services import job_service

logger = logging.getLogger("true911.tmobile_callback")
router = APIRouter()


# ── Archive helper (flag-gated) ──────────────────────────────────
# When FEATURE_TMOBILE_CALLBACK_INGEST is on, every event-specific
# POST handler additionally archives the payload to IntegrationPayload
# and enqueues a webhook.tmobile job.  The worker's handle_webhook
# (sim_service.py) then delegates to tmobile_callback_processor for
# the SIM match + Device.last_network_event promotion that feeds the
# Health Normalizer.
#
# When the flag is off this helper is never called and behavior is
# byte-identical to the pre-MVP code (log + 200 ack only).


def _ingest_enabled() -> bool:
    """Flag check, strip+lower for env-var whitespace tolerance."""
    return settings.FEATURE_TMOBILE_CALLBACK_INGEST.strip().lower() == "true"


async def _archive_tmobile_callback(
    request: Request,
    event_type: str,
    db: AsyncSession,
) -> str | None:
    """Persist the callback body to IntegrationPayload + enqueue a job.

    Returns the payload_id on success, ``None`` on any failure (the
    caller still returns HTTP 200 so the PIT validator never sees a
    failure — we'd rather lose one archived payload than have T-Mobile
    retry-storm us).

    The event_type is injected as a synthetic
    ``x-true911-tmobile-event-type`` header in the stored payload
    record so the worker can recover URL-path event type without
    re-parsing the URL.
    """
    raw = await request.body()
    body_text = raw.decode("utf-8", errors="replace") if raw else ""
    body_json: Any = None
    if body_text:
        try:
            body_json = json.loads(body_text)
        except (json.JSONDecodeError, ValueError):
            body_json = None

    captured_headers = dict(request.headers)
    # Carry the event type forward without mutating the original headers.
    captured_headers["x-true911-tmobile-event-type"] = event_type

    payload_id = f"wh-{uuid.uuid4().hex[:12]}"
    ip = IntegrationPayload(
        payload_id=payload_id,
        source="tmobile",
        direction="inbound",
        headers=captured_headers,
        body=body_json if isinstance(body_json, dict) else None,
        raw_body=body_text if not isinstance(body_json, dict) else None,
        processed=False,
    )
    db.add(ip)
    await db.flush()

    job = await job_service.create_and_enqueue(
        db,
        job_type="webhook.tmobile",
        queue="default",
        payload={"payload_id": payload_id, "source": "tmobile",
                 "event_type": event_type},
    )
    await db.commit()
    logger.info(
        "T-Mobile callback archived | payload_id=%s | event=%s | job_id=%s",
        payload_id, event_type, job.id,
    )
    return payload_id


async def _maybe_archive(
    request: Request, event_type: str, db: AsyncSession
) -> None:
    """Wrapper that gates the archive call on the feature flag and
    swallows all failures.  PIT-validator HTTP 200 contract is the
    operational priority — losing one archived payload is recoverable;
    T-Mobile retry-storming a healthy endpoint is not.
    """
    if not _ingest_enabled():
        return
    # C2: authenticity gate.  When FEATURE_TMOBILE_CALLBACK_AUTH is off this
    # is always authentic (byte-identical to pre-C2).  When on, an
    # unauthenticated callback is logged and dropped here — never archived,
    # never promoted to Device state — while the handler still returns 200.
    auth = check_callback_auth(request)
    if not auth.authentic:
        logger.warning(
            "T-Mobile callback ingest DENIED | event=%s | reason=%s | "
            "method=%s | path=%s — skipping archive, returning 200",
            event_type, auth.reason, request.method, request.url.path,
        )
        return
    try:
        await _archive_tmobile_callback(request, event_type, db)
    except Exception:
        # Deliberately broad — see docstring above.
        logger.exception(
            "T-Mobile callback archive failed (event=%s) — returning 200 anyway",
            event_type,
        )


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


def _safe_query(query_params) -> dict[str, str]:
    """Return query params with auth/token/secret-like values redacted.

    The C2 callback-auth token may travel as ``?token=...`` in the URL we
    register with T-Mobile, so query params must be scrubbed before
    logging exactly as headers are — otherwise the shared secret would
    leak into the log stream.
    """
    redacted: dict[str, str] = {}
    for name, value in query_params.items():
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
        _safe_query(request.query_params),
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
        _safe_query(request.query_params),
        _safe_headers(request.headers),
        body_preview,
    )

    return {"success": True, "message": "callback received"}


@router.get("/callback")
async def tmobile_wholesale_callback_probe(request: Request):
    """Manual liveness probe (curl/browser). Not used by T-Mobile."""
    logger.info(
        "T-Mobile PIT callback GET probe | query=%s | headers=%s",
        _safe_query(request.query_params),
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
async def cb_provisioning_post(
    request: Request, db: AsyncSession = Depends(get_db)
):
    await _log_callback(request, "provisioning", include_body=True)
    await _maybe_archive(request, "provisioning", db)
    return _ack("provisioning")


@router.get("/callback/usage")
async def cb_usage_get(request: Request):
    await _log_callback(request, "usage", include_body=False)
    return _ack("usage")


@router.post("/callback/usage")
async def cb_usage_post(
    request: Request, db: AsyncSession = Depends(get_db)
):
    await _log_callback(request, "usage", include_body=True)
    await _maybe_archive(request, "usage", db)
    return _ack("usage")


@router.get("/callback/device-change")
async def cb_device_change_get(request: Request):
    await _log_callback(request, "device_change", include_body=False)
    return _ack("device_change")


@router.post("/callback/device-change")
async def cb_device_change_post(
    request: Request, db: AsyncSession = Depends(get_db)
):
    await _log_callback(request, "device_change", include_body=True)
    await _maybe_archive(request, "device_change", db)
    return _ack("device_change")


@router.get("/callback/subscriber-status")
async def cb_subscriber_status_get(request: Request):
    await _log_callback(request, "subscriber_status", include_body=False)
    return _ack("subscriber_status")


@router.post("/callback/subscriber-status")
async def cb_subscriber_status_post(
    request: Request, db: AsyncSession = Depends(get_db)
):
    await _log_callback(request, "subscriber_status", include_body=True)
    await _maybe_archive(request, "subscriber_status", db)
    return _ack("subscriber_status")


@router.get("/callback/static-ip")
async def cb_static_ip_get(request: Request):
    await _log_callback(request, "static_ip", include_body=False)
    return _ack("static_ip")


@router.post("/callback/static-ip")
async def cb_static_ip_post(
    request: Request, db: AsyncSession = Depends(get_db)
):
    await _log_callback(request, "static_ip", include_body=True)
    await _maybe_archive(request, "static_ip", db)
    return _ack("static_ip")


@router.get("/callback/cim")
async def cb_cim_get(request: Request):
    await _log_callback(request, "cim", include_body=False)
    return _ack("cim")


@router.post("/callback/cim")
async def cb_cim_post(
    request: Request, db: AsyncSession = Depends(get_db)
):
    await _log_callback(request, "cim", include_body=True)
    await _maybe_archive(request, "cim", db)
    return _ack("cim")
