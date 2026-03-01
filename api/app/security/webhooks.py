"""Webhook authentication dependencies.

Provides a FastAPI dependency that validates an ``X-Webhook-Secret`` header
against the ``ZOHO_WEBHOOK_SECRET`` env var using constant-time comparison.
This is intentionally decoupled from JWT/OAuth2 so webhook routes stay
public from the OpenAPI security-scheme perspective.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, status

from app.config import settings

logger = logging.getLogger("true911.integrations")


def require_webhook_secret(
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
) -> str:
    """Validate the ``X-Webhook-Secret`` header against the configured secret.

    Returns the validated secret on success (useful for downstream logging of
    "auth passed" without leaking the value).

    Raises:
        HTTPException 500 – secret not configured (fail closed).
        HTTPException 401 – header missing or does not match.
    """
    expected = settings.ZOHO_WEBHOOK_SECRET
    if not expected:
        logger.error("ZOHO_WEBHOOK_SECRET is not configured — failing closed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    if not x_webhook_secret:
        logger.warning("Webhook auth failed: missing X-Webhook-Secret header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    if not hmac.compare_digest(x_webhook_secret, expected):
        logger.warning("Webhook auth failed: X-Webhook-Secret mismatch")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    return x_webhook_secret
