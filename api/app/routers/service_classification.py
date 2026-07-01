"""Internal Operations — Life-Safety service classification (Phase 8).

Review + approve / override / merge / split the inferred service classification
for a site.  INTERNAL only: guarded by ``MANAGE_SERVICE_CLASSIFICATION`` (no
customer role holds it).  Every override is logged (append-only ActionAudit).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_user, get_db, require_permission
from ..models.user import User
from ..services import service_classification as svc

router = APIRouter(prefix="/service-classification", tags=["service-classification"])

_GUARD = [Depends(require_permission("MANAGE_SERVICE_CLASSIFICATION"))]


class OverrideBody(BaseModel):
    site_id: str
    service_type: str
    device_ids: list[str] = Field(default_factory=list)
    device_id: str | None = None          # convenience for a single device
    operation: str = "override"           # approve | override | merge | split
    reason: str = ""


@router.get("/{site_id}", dependencies=_GUARD)
async def get_classification(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Inferred Life-Safety services for a site (with device detail + confidence
    + current overrides) — the Operations review view."""
    data = await svc.infer_site_classification(db, current_user.tenant_id, site_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return data


@router.post("/override", dependencies=_GUARD)
async def override_classification(
    body: OverrideBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Approve / override / merge / split a service classification.  Writes an
    append-only audit record per device (every override is logged) that the
    customer inference engine then applies."""
    device_ids = list(body.device_ids)
    if body.device_id and body.device_id not in device_ids:
        device_ids.append(body.device_id)
    if not device_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "device_ids (or device_id) required")
    # Confirm the site belongs to the caller's tenant before writing.
    if await svc._site(db, current_user.tenant_id, body.site_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    try:
        return await svc.record_override(
            db, current_user, site_id=body.site_id, service_type=body.service_type,
            device_ids=device_ids, operation=body.operation, reason=body.reason)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("/{site_id}/overrides", dependencies=_GUARD)
async def override_history(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Override audit trail for a site (every approve/override/merge/split)."""
    return await svc.list_overrides(db, current_user.tenant_id, site_id)
