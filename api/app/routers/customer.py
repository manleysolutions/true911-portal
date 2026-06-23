"""Customer API namespace — /api/customer/* (RH Go-Live Phase 3).

PR-C1 ships the gated scaffold only.  Data endpoints (dashboard, locations,
services, equipment, e911, billing, reports, support) land in PR-C2+ and all
compose the existing engines through the allow-list serializer in
``app.services.customer.serialize``.

Every endpoint here uses ``require_customer_api`` (two-key flag gate, 404 when
off) IN ADDITION to a dedicated ``CUSTOMER_*`` permission guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.user import User
from app.services.customer.gate import require_customer_api

router = APIRouter()


@router.get("/_health")
async def customer_api_health(current_user: User = Depends(require_customer_api)) -> dict:
    """Liveness probe proving the two-key gate.  Returns 404 unless
    FEATURE_CUSTOMER_API is on AND the caller's tenant is allowlisted; returns
    200 otherwise.  Carries no tenant data."""
    return {"ok": True, "namespace": "customer"}
