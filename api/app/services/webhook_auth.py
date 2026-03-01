"""HMAC SHA-256 webhook signature verification.

Expected headers:
    X-True911-Signature: sha256=<hex digest>
    X-True911-Timestamp: <unix epoch seconds>  (optional, for replay protection)

The signature is computed over the raw request body using the shared secret
from INTEGRATION_WEBHOOK_SECRET env var.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import HTTPException, Request, status

from app.config import settings


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, timestamp_header: str | None = None) -> None:
    """Verify HMAC-SHA256 signature and optional replay protection.

    Raises HTTPException(401) on failure.
    """
    secret = settings.INTEGRATION_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTEGRATION_WEBHOOK_SECRET not configured",
        )

    if not signature_header:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-True911-Signature header")

    # Parse "sha256=<hex>"
    if not signature_header.startswith("sha256="):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature format (expected sha256=<hex>)")

    provided_hex = signature_header[7:]

    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(provided_hex, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")

    # Replay protection (optional)
    if timestamp_header:
        try:
            ts = int(timestamp_header)
        except (ValueError, TypeError):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-True911-Timestamp")

        skew = settings.INTEGRATION_HMAC_SKEW_SECONDS
        now = int(time.time())
        if abs(now - ts) > skew:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                f"Request timestamp too old or too far in the future (skew limit: {skew}s)",
            )


def compute_signature(body: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 signature for testing / external callers."""
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
