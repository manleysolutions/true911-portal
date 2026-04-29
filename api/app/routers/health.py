"""System health endpoint.

GET /api/health/system — a lightweight probe operators (or a load
balancer) can poll to confirm the app, database, and JWT signing
configuration are usable. Output is intentionally high-level: status
strings only, never connection strings, secrets, exception details,
or query plans.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from jose import jwt as _jwt
from sqlalchemy import text

from ..config import settings
from ..database import AsyncSessionLocal

logger = logging.getLogger("true911.health")
router = APIRouter()


async def _check_db() -> str:
    """Round-trip a `SELECT 1` against the configured database."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        # Detail logged for ops; only "error" reaches the response body.
        logger.warning("health_system: db check failed", exc_info=True)
        return "error"


def _check_auth() -> str:
    """Verify JWT signing configuration without using a real token.

    Confirms that JWT_SECRET is non-empty and that the configured
    algorithm can encode + decode a synthetic, non-identity payload
    end-to-end. No real user token is created or read.
    """
    try:
        if not settings.JWT_SECRET or not settings.JWT_ALGORITHM:
            return "error"
        probe = _jwt.encode(
            {"probe": "health"},
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )
        _jwt.decode(probe, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return "ok"
    except Exception:
        logger.warning("health_system: auth check failed", exc_info=True)
        return "error"


@router.get("/health/system")
async def health_system():
    """High-level system health probe.

    Returns 200 when every check is "ok"; 503 when any check is
    "error". The response body never contains secrets, connection
    strings, exception details, or stack traces — only status strings.
    """
    checks = {
        "app": "ok",
        "db": await _check_db(),
        "auth": _check_auth(),
    }
    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    code = 200 if overall == "ok" else 503
    return JSONResponse(status_code=code, content={"status": overall, "checks": checks})
