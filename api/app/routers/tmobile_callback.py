"""Temporary T-Mobile Wholesale PIT callback endpoint.

Bring-up probe: accepts the callback, logs everything, returns 200.
No business logic, no auth — intentional for initial connectivity test.
Signing/auth verification will be added once T-Mobile confirms the scheme.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger("true911.tmobile_callback")
router = APIRouter()


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
        dict(request.headers),
        body_preview,
    )

    return {"success": True, "message": "callback received"}


@router.get("/callback")
async def tmobile_wholesale_callback_probe(request: Request):
    """Manual liveness probe (curl/browser). Not used by T-Mobile."""
    logger.info(
        "T-Mobile PIT callback GET probe | query=%s | headers=%s",
        dict(request.query_params),
        dict(request.headers),
    )
    return {"success": True, "message": "callback received"}
