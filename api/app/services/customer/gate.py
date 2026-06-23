"""Two-key feature gate for the customer API namespace.

A /api/customer/* route is reachable only when BOTH hold:
  * FEATURE_CUSTOMER_API == "true"  (global kill-switch), and
  * the caller's tenant_id is in CUSTOMER_API_TENANT_ALLOWLIST.

Otherwise the route returns 404 (not 403) so the surface is indistinguishable
from "not built" when disabled — no existence leak.  Default OFF everywhere.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.config import settings
from app.dependencies import get_current_user
from app.models.user import User


def require_customer_api(current_user: User = Depends(get_current_user)) -> User:
    """Auth + two-key flag gate.  Returns the user when enabled for their
    tenant; raises 404 otherwise.  Use as the auth dependency on every
    customer endpoint, in addition to a CUSTOMER_* permission guard."""
    if (
        settings.FEATURE_CUSTOMER_API != "true"
        or current_user.tenant_id not in settings.customer_api_tenant_id_set
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return current_user
