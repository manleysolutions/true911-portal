"""Internal operations queue for customer self-service requests.

``/api/customer-requests`` — where the operations team reviews what customers
submitted from the Customer Operations Console and moves each request through
its governed lifecycle (under_review / approved / in_progress / waiting_customer
/ completed / rejected).  Every transition is audited (customer activity event +
ActionAudit).

Guard: ``MANAGE_CUSTOMER_REQUESTS`` (internal roles only — no ``CUSTOMER_*`` role
holds it) plus the global ``FEATURE_CUSTOMER_SELF_SERVICE`` kill-switch (404 when
off).  Tenant-scoped to the caller's (acting) tenant, like the E911 review queue.

Moving a request here changes ONLY the request.  Carrier / device / registry
changes are made through their own controlled tools, and completing an E911
verification request does NOT mark E911 verified — the official record changes
only through the existing ``UPDATE_E911`` flow (``/api/e911-changes``).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db, require_permission
from app.models.user import User
from app.services.customer import self_service as ss

router = APIRouter()


def _require_flag(current_user: User = Depends(require_permission("MANAGE_CUSTOMER_REQUESTS"))) -> User:
    if settings.FEATURE_CUSTOMER_SELF_SERVICE != "true":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return current_user


class _TransitionBody(BaseModel):
    to_status: str
    notes: str | None = None


@router.get("")
async def list_customer_requests(
    status_filter: str = Query("open", alias="status"),
    current_user: User = Depends(_require_flag),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The request queue for the acting tenant: ``open`` (default), ``all``, or a
    single status."""
    rows = await ss.load_requests(db, current_user.tenant_id, open_only=(status_filter == "open"))
    if status_filter not in ("open", "all"):
        rows = [r for r in rows if r.status == status_filter]
    return {"count": len(rows), "status_filter": status_filter,
            "requests": [ss.serialize_request(r, internal=True) for r in rows]}


@router.get("/{request_ref}")
async def get_customer_request(
    request_ref: str,
    current_user: User = Depends(_require_flag),
    db: AsyncSession = Depends(get_db),
) -> dict:
    req = await ss.get_request(db, current_user.tenant_id, request_ref)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    history = [e for e in await ss.load_activity(db, current_user.tenant_id, limit=500)
               if e["request_ref"] == request_ref]
    return {"request": ss.serialize_request(req, internal=True), "history": history}


@router.post("/{request_ref}/transition")
async def transition_customer_request(
    request_ref: str, body: _TransitionBody,
    current_user: User = Depends(_require_flag),
    db: AsyncSession = Depends(get_db),
) -> dict:
    req = await ss.get_request(db, current_user.tenant_id, request_ref)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    try:
        data = await ss.operations_transition(db, current_user, req, body.to_status, notes=body.notes)
    except ss.SelfServiceError as exc:
        raise HTTPException(exc.status, exc.as_detail())
    return {"as_of": datetime.now(timezone.utc).isoformat(), "request": data}
