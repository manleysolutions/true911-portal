"""Hardware-agnostic device-health API (read-only).

Endpoints (all tenant-scoped; gated by FEATURE_DEVICE_HEALTH):

  GET /api/device-health                      Global device health (this tenant)
  GET /api/device-health/property/{site_id}   Customer property health (simple language)
  GET /api/device-health/service-unit/{unit_id}  One service unit's device health
  GET /api/device-health/adapters             Vendor adapter status (admin)

These read persisted DB fields only — they never make live vendor calls, so a
page load never blocks on Vola / T-Mobile.  Live enrichment is done by the
sync command (``python -m app.sync_device_health``).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.services.device_health.adapters import adapter_status_summary
from app.services.device_health.service import build_device_health
from app.services.device_health.status import NormalizedStatus

router = APIRouter()


def _feature_enabled() -> None:
    """404 the whole router when the feature flag is off."""
    if settings.FEATURE_DEVICE_HEALTH.strip().lower() not in ("1", "true", "yes", "on"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device health feature not enabled")


def _status_counts(healths) -> dict[str, int]:
    counts = {s.value: 0 for s in NormalizedStatus}
    for h in healths:
        counts[h.status.value] = counts.get(h.status.value, 0) + 1
    return counts


def _rollup(healths) -> str:
    """Property/site-level status from its devices (worst-wins, simple)."""
    if not healths:
        return NormalizedStatus.UNKNOWN.value
    statuses = {h.status for h in healths}
    if NormalizedStatus.ATTENTION in statuses:
        return NormalizedStatus.ATTENTION.value
    if NormalizedStatus.OFFLINE in statuses:
        return NormalizedStatus.OFFLINE.value
    if statuses == {NormalizedStatus.ONLINE}:
        return NormalizedStatus.ONLINE.value
    return NormalizedStatus.UNKNOWN.value


@router.get("", dependencies=[Depends(_feature_enabled),
                              Depends(require_permission("VIEW_DEVICES"))])
async def global_device_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Normalized health for every device in the caller's tenant."""
    healths = await build_device_health(db, current_user.tenant_id)
    return {
        "tenant_id": current_user.tenant_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": _status_counts(healths),
        "devices": [h.to_dict() for h in healths],
    }


@router.get("/property/{site_id}",
            dependencies=[Depends(_feature_enabled),
                          Depends(require_permission("VIEW_SITES"))])
async def property_health(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Customer-friendly property health (simple language)."""
    healths = await build_device_health(db, current_user.tenant_id, site_id=site_id)
    if not healths:
        # Either the site has no devices or it isn't this tenant's site —
        # both look the same to the caller (no cross-tenant leak).
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No devices found for this property")
    property_name = next((h.site_name for h in healths if h.site_name), site_id)
    return {
        "property": property_name,
        "site_id": site_id,
        "status": _rollup(healths),
        "summary": _status_counts(healths),
        "units": [h.to_customer_view() for h in healths],
    }


@router.get("/service-unit/{unit_id}",
            dependencies=[Depends(_feature_enabled),
                          Depends(require_permission("VIEW_DEVICES"))])
async def service_unit_health(
    unit_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Health for the device behind one service unit (e.g. an elevator phone)."""
    healths = await build_device_health(db, current_user.tenant_id)
    match = next((h for h in healths if h.service_unit_id == unit_id), None)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service unit not found")
    return match.to_dict()


@router.get("/adapters",
            dependencies=[Depends(_feature_enabled),
                          Depends(require_permission("MANAGE_INTEGRATIONS"))])
async def adapter_status(
    current_user: User = Depends(get_current_user),
):
    """Which vendor adapters are configured / available (no secrets)."""
    return {
        "feature_enabled": True,
        "adapters": adapter_status_summary(),
    }
