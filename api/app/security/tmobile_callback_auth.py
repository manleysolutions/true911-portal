"""Authenticity check for T-Mobile PIT callback ingest.

This is **not** a FastAPI dependency that raises 401 — the callback
endpoints have a hard "always return HTTP 200" contract (the PIT
validator and T-Mobile retry logic must never see a non-200).  Instead
this returns a decision the callback router uses to gate the *ingest*
(archive + enqueue) step only.  An unauthenticated callback is logged
and dropped; the handler still answers 200.

Authentication is T-Mobile-agnostic because T-Mobile has not published a
callback-signing spec.  We rely on what we control:

  1. A shared secret we embed in the call-back-location URL we register
     (``?token=...``) or that T-Mobile sends as the
     ``X-True911-Callback-Token`` header (preferred — keeps the secret
     out of URLs/logs).  Compared in constant time.
  2. Optional source-IP enforcement (CF-Connecting-IP inside
     ``TMOBILE_CALLBACK_SOURCE_IPS``), reusing the allowlist parser the
     passive IP-audit middleware already uses.

Fail-closed: if ``FEATURE_TMOBILE_CALLBACK_AUTH`` is on but no token is
configured, the decision is "deny" with reason ``token_not_configured``
(the caller logs an error and skips ingest — it never raises / 500s).

See docs/TMOBILE_CALLBACK_AUTH.md.
"""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass

from starlette.requests import Request

from app.config import settings
from app.middleware import (
    CF_CONNECTING_IP_HEADER,
    _ip_in_allowlist,
    _parse_allowlist,
)

logger = logging.getLogger("true911.tmobile_callback_auth")

CALLBACK_TOKEN_HEADER = "X-True911-Callback-Token"
CALLBACK_TOKEN_QUERY = "token"


@dataclass(frozen=True)
class CallbackAuthResult:
    """Outcome of the authenticity check.

    ``authentic`` is the only field the gate needs; ``reason`` is a short
    machine-stable string for structured logging (never includes the
    token value).
    """

    authentic: bool
    reason: str


def _auth_enabled() -> bool:
    return settings.FEATURE_TMOBILE_CALLBACK_AUTH.strip().lower() == "true"


def _ip_enforce_enabled() -> bool:
    return settings.TMOBILE_CALLBACK_IP_ENFORCE.strip().lower() == "true"


def _extract_token(request: Request) -> str | None:
    """Return the presented token from header (preferred) or query, or None."""
    header_token = request.headers.get(CALLBACK_TOKEN_HEADER)
    if header_token:
        return header_token
    query_token = request.query_params.get(CALLBACK_TOKEN_QUERY)
    if query_token:
        return query_token
    return None


def check_callback_auth(request: Request) -> CallbackAuthResult:
    """Decide whether this callback request may be ingested.

    Never raises.  When ``FEATURE_TMOBILE_CALLBACK_AUTH`` is off this
    returns ``authentic=True`` so behavior is byte-identical to the
    pre-C2 ingest path (the ingest flag remains the only gate).
    """
    if not _auth_enabled():
        return CallbackAuthResult(True, "auth_disabled")

    expected = settings.TMOBILE_CALLBACK_TOKEN.strip()
    if not expected:
        # Fail closed: misconfiguration must not silently accept spoofed input.
        logger.error(
            "tmobile_callback_auth: FEATURE_TMOBILE_CALLBACK_AUTH is on but "
            "TMOBILE_CALLBACK_TOKEN is not configured — denying ingest (fail closed)"
        )
        return CallbackAuthResult(False, "token_not_configured")

    presented = _extract_token(request)
    if not presented:
        return CallbackAuthResult(False, "token_missing")

    if not hmac.compare_digest(presented, expected):
        return CallbackAuthResult(False, "token_mismatch")

    # Optional defense-in-depth: source-IP enforcement.
    if _ip_enforce_enabled():
        cf_ip = request.headers.get(CF_CONNECTING_IP_HEADER)
        if not cf_ip:
            return CallbackAuthResult(False, "ip_enforce_no_source_ip")
        ranges = _parse_allowlist(settings.TMOBILE_CALLBACK_SOURCE_IPS)
        if not ranges or not _ip_in_allowlist(cf_ip, ranges):
            return CallbackAuthResult(False, "ip_not_allowlisted")

    return CallbackAuthResult(True, "ok")
