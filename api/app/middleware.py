"""HTTP middleware shared by the FastAPI app."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("true911.request")

REQUEST_ID_HEADER = "X-Request-ID"


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
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%.2f request_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request method=%s path=%s status_code=%d duration_ms=%.2f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
