"""HTTP middleware shared by the FastAPI app."""

from __future__ import annotations

import ipaddress
import logging
import time
import uuid
from functools import lru_cache

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import settings

logger = logging.getLogger("true911.request")

REQUEST_ID_HEADER = "X-Request-ID"

TMOBILE_CALLBACK_PATH_PREFIX = "/tmobile/wholesale/callback"
CF_CONNECTING_IP_HEADER = "CF-Connecting-IP"
audit_logger = logging.getLogger("true911.tmobile_callback_audit")


class RequestVisibilityMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every request/response and log basic metrics.

    - Preserves X-Request-ID from the incoming request when supplied;
      otherwise generates a new uuid4 hex.
    - Sets X-Request-ID on the response.
    - Logs method, path, status_code, duration_ms, and request_id at INFO.

    Deliberately omits headers, cookies, query strings, and request bodies so
    tokens, passwords, and PII never enter the log stream.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            # request.state may have user_id/tenant_id if get_current_user
            # ran successfully before the failure; otherwise both are None.
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%.2f request_id=%s "
                "user_id=%s tenant_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
                getattr(request.state, "user_id", None),
                getattr(request.state, "tenant_id", None),
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request method=%s path=%s status_code=%d duration_ms=%.2f request_id=%s "
            "user_id=%s tenant_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
            getattr(request.state, "user_id", None),
            getattr(request.state, "tenant_id", None),
        )
        return response


@lru_cache(maxsize=8)
def _parse_allowlist(spec: str) -> tuple[tuple[int, int], ...]:
    """Parse an allowlist spec into a tuple of (low, high) integer pairs.

    Accepts comma-separated entries of three forms:
      * single IPv4:      ``206.29.176.74``
      * inclusive range:  ``206.29.176.74-206.29.176.79``
      * CIDR:             ``206.29.176.64/27``

    Malformed entries are skipped with a warning so a single bad value
    in the env var cannot disable the entire allowlist.  Result is
    cached because the spec rarely changes at runtime.
    """
    ranges: list[tuple[int, int]] = []
    for raw in spec.split(","):
        entry = raw.strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                net = ipaddress.IPv4Network(entry, strict=False)
                ranges.append((int(net.network_address), int(net.broadcast_address)))
            elif "-" in entry:
                low_s, high_s = entry.split("-", 1)
                low = int(ipaddress.IPv4Address(low_s.strip()))
                high = int(ipaddress.IPv4Address(high_s.strip()))
                if low > high:
                    low, high = high, low
                ranges.append((low, high))
            else:
                v = int(ipaddress.IPv4Address(entry))
                ranges.append((v, v))
        except (ValueError, ipaddress.AddressValueError) as exc:
            audit_logger.warning(
                "tmobile_callback_ip_audit: ignoring malformed allowlist entry "
                "%r (%s)",
                entry, exc,
            )
    return tuple(ranges)


def _ip_in_allowlist(ip_text: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    """True if ``ip_text`` parses as an IPv4 inside any (low, high) range."""
    try:
        v = int(ipaddress.IPv4Address(ip_text.strip()))
    except (ValueError, ipaddress.AddressValueError):
        return False
    return any(low <= v <= high for low, high in ranges)


class TmobileCallbackAuditMiddleware(BaseHTTPMiddleware):
    """Passive IP-audit for T-Mobile PIT callback URLs.

    Scoped to ``/tmobile/wholesale/callback/*`` only — every other path
    is an immediate pass-through with zero overhead beyond a string
    prefix check.

    Behavior when ``FEATURE_TMOBILE_CALLBACK_IP_AUDIT=true``:

      * If ``CF-Connecting-IP`` is missing → silent (local dev / direct
        origin hit with no Cloudflare in front; cannot make a claim).
      * If the header value is inside ``TMOBILE_CALLBACK_SOURCE_IPS`` →
        silent (the expected case for real T-Mobile traffic).
      * If the header value is outside the allowlist → emit one
        structured WARNING line via the ``true911.tmobile_callback_audit``
        logger.  Never alters the response.

    Behavior when the flag is "false" (default) or any other value:
    pure pass-through.  Off-mode is identical to not installing the
    middleware at all — safe to register unconditionally.

    Enforcement is the Cloudflare WAF rule.  This middleware exists to
    detect rule misconfiguration and the ``*.onrender.com`` origin
    bypass.  Response code is never changed, so the HTTP 200 contract
    for the PIT validator is preserved end-to-end.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith(TMOBILE_CALLBACK_PATH_PREFIX):
            return await call_next(request)

        if settings.FEATURE_TMOBILE_CALLBACK_IP_AUDIT.strip().lower() != "true":
            return await call_next(request)

        cf_ip = request.headers.get(CF_CONNECTING_IP_HEADER)
        if cf_ip:
            ranges = _parse_allowlist(settings.TMOBILE_CALLBACK_SOURCE_IPS)
            if ranges and not _ip_in_allowlist(cf_ip, ranges):
                audit_logger.warning(
                    "tmobile_callback_ip_audit: cf_connecting_ip=%s path=%s "
                    "method=%s outside_allowlist=true",
                    cf_ip, path, request.method,
                )

        return await call_next(request)
