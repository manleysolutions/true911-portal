"""Write endpoints for Zoho lifecycle mapping + promotion — Phase 5 (Admin only).

Two explicit operator actions, both RBAC ``MANAGE_INTEGRATIONS``:

  POST /api/integrations/zoho/mappings/{record_map_id}/confirm
      Confirm an operator-reviewed mapping (sets links + map_status="confirmed").
      Writes ONLY the staging external_record_map row — no production change.

  POST /api/integrations/zoho/promote?dry_run=true
      Promote confirmed-mapped lifecycle_state onto sites.lifecycle_status.
      dry_run (default true) returns the plan and writes nothing.  Applying
      (dry_run=false) requires FEATURE_ZOHO_LIFECYCLE_PROMOTION=true and writes
      ONLY the additive lifecycle columns — never sites.status, never a delete.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission
from app.models.external_record_map import ExternalRecordMap
from app.models.site import Site
from app.models.user import User
from app.services import zoho_lifecycle_promotion as promo

router = APIRouter()


class ConfirmMappingBody(BaseModel):
    site_id: Optional[str] = None
    customer_id: Optional[int] = None
    subscription_id: Optional[int] = None
    device_id: Optional[str] = None
    line_id: Optional[str] = None
    linked_tenant_id: Optional[str] = None


def _serialize_map(m: ExternalRecordMap) -> dict:
    return {
        "id": m.id,
        "source": m.source,
        "module": m.module,
        "external_record_id": m.external_record_id,
        "map_status": m.map_status,
        "customer_id": m.customer_id,
        "subscription_id": m.subscription_id,
        "linked_tenant_id": m.linked_tenant_id,
        "site_id": m.site_id,
        "device_id": m.device_id,
        "line_id": m.line_id,
    }


@router.post("/zoho/mappings/{record_map_id}/confirm")
async def confirm_mapping(
    record_map_id: int,
    body: ConfirmMappingBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_INTEGRATIONS")),
):
    """Confirm an operator-reviewed Zoho mapping (staging write only)."""
    result = await db.execute(
        select(ExternalRecordMap).where(ExternalRecordMap.id == record_map_id)
    )
    rec_map = result.scalar_one_or_none()
    if rec_map is None or rec_map.org_id != current_user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mapping not found")

    # If a site link is supplied, it must be a real site in this tenant.
    if body.site_id is not None:
        site = (
            await db.execute(
                select(Site).where(
                    Site.site_id == body.site_id,
                    Site.tenant_id == current_user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if site is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Site '{body.site_id}' not found in this tenant",
            )
        rec_map.site_id = body.site_id

    for field in ("customer_id", "subscription_id", "device_id", "line_id", "linked_tenant_id"):
        val = getattr(body, field)
        if val is not None:
            setattr(rec_map, field, val)

    rec_map.map_status = "confirmed"
    await db.flush()
    await db.commit()
    return {"ok": True, "mapping": _serialize_map(rec_map)}


@router.post("/zoho/promote")
async def promote_lifecycle(
    dry_run: bool = Query(True, description="Preview only (default). Set false to apply."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("MANAGE_INTEGRATIONS")),
):
    """Promote confirmed-mapped lifecycle_state onto sites.lifecycle_status.

    Default is a dry run that writes nothing.  Applying requires the feature flag.
    """
    plan = await promo.plan_site_promotion(db, current_user.tenant_id)
    would_change = [p for p in plan if p["would_change"]]

    if dry_run:
        return {
            "dry_run": True,
            "applied": False,
            "promotion_enabled": promo.promotion_enabled(),
            "would_change_count": len(would_change),
            "plan": plan,
            "note": "Dry run — nothing written. Only sites.lifecycle_status would change; sites.status is never modified.",
        }

    if not promo.promotion_enabled():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Promotion is disabled. Set FEATURE_ZOHO_LIFECYCLE_PROMOTION=true to apply.",
        )

    result = await promo.apply_site_promotion(db, current_user.tenant_id)
    await db.commit()
    return {
        "dry_run": False,
        "applied": True,
        "applied_count": result["applied_count"],
        "changes": result["applied"],
        "note": "Only sites.lifecycle_status was written; sites.status (operational) is unchanged.",
    }
