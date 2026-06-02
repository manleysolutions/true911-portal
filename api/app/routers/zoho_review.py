"""Read-only admin review surface for staged Zoho lifecycle data — Phase 3.

These endpoints let an operator inspect what Zoho has sent and what WOULD change
BEFORE any production record is touched.  They are strictly read-only: no
endpoint here writes, promotes, or mutates sites/devices/lines/customers.  Data
comes only from the Phase 0/1/2 staging tables.

Routes (JWT + RBAC ``VIEW_INTEGRATIONS``, tenant-scoped):
    GET /api/integrations/zoho/review/subscriptions   — staged subscription records
    GET /api/integrations/zoho/review/unmapped         — records not yet confirm-mapped
    GET /api/integrations/zoho/review/observations     — sanitized inbound payloads
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_permission
from app.models.external_record_map import ExternalRecordMap
from app.models.user import User
from app.models.zoho_payload_observation import ZohoPayloadObservation
from app.models.zoho_subscription_record import ZohoSubscriptionRecord
from app.services.zoho_status_normalizer import presents_as_active_monitoring

router = APIRouter()

_READ_ONLY_NOTE = (
    "Review-only view of staged Zoho records. No production records are "
    "modified by these endpoints."
)


def serialize_review_row(
    rec: ZohoSubscriptionRecord, rec_map: Optional[ExternalRecordMap]
) -> dict[str, Any]:
    """Shape a (subscription record, optional map) pair for the review UI — pure."""
    map_status = rec_map.map_status if rec_map is not None else "unmapped"
    linked: Optional[dict[str, Any]] = None
    if rec_map is not None and map_status != "unmapped":
        linked = {
            "customer_id": rec_map.customer_id,
            "subscription_id": rec_map.subscription_id,
            "linked_tenant_id": rec_map.linked_tenant_id,
            "site_id": rec_map.site_id,
            "device_id": rec_map.device_id,
            "line_id": rec_map.line_id,
        }
    return {
        "id": rec.id,
        "subscription_mgmt_id": rec.subscription_mgmt_id,
        "account_name": rec.account_name,
        "facility_name": rec.facility_name,
        "msisdn": rec.msisdn,
        # Raw Zoho commercial status, verbatim.
        "device_activation_status": rec.device_activation_status,
        # Normalized lifecycle state (may be null if the normalizer flag is off).
        "lifecycle_state": rec.lifecycle_state,
        # Lifecycle is a SEPARATE axis from operational status; only `active`
        # presents as healthy active monitoring.
        "presents_as_active_monitoring": presents_as_active_monitoring(rec.lifecycle_state),
        "connection_type": rec.connection_type,
        "subscription_type": rec.subscription_type,
        "mrc": float(rec.mrc) if rec.mrc is not None else None,
        "service_term_ends": rec.service_term_ends.isoformat() if rec.service_term_ends else None,
        "map_status": map_status,
        "linked": linked,
        "last_event_id": rec.last_event_id,
        "first_seen_at": rec.first_seen_at.isoformat() if rec.first_seen_at else None,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


def serialize_observation(obs: ZohoPayloadObservation) -> dict[str, Any]:
    """Shape a sanitized payload observation for the review UI — pure."""
    return {
        "id": obs.id,
        "module": obs.module,
        "event_type": obs.event_type,
        "matched_subscription": obs.matched_subscription,
        "top_level_keys": obs.top_level_keys,
        "sanitized_payload": obs.sanitized_payload,
        "integration_event_id": obs.integration_event_id,
        "created_at": obs.created_at.isoformat() if obs.created_at else None,
    }


async def _count(db: AsyncSession, base_query) -> int:
    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar()
    return total or 0


@router.get("/zoho/review/subscriptions")
async def list_zoho_subscription_review(
    lifecycle_state: str | None = Query(None),
    map_status: str | None = Query(None),
    q: str | None = Query(None, description="search account/facility/msisdn/subscription id"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_INTEGRATIONS")),
):
    """List staged Zoho subscription records with raw + normalized status."""
    base = (
        select(ZohoSubscriptionRecord, ExternalRecordMap)
        .outerjoin(
            ExternalRecordMap,
            ZohoSubscriptionRecord.external_record_map_id == ExternalRecordMap.id,
        )
        .where(ZohoSubscriptionRecord.org_id == current_user.tenant_id)
    )
    if lifecycle_state:
        base = base.where(ZohoSubscriptionRecord.lifecycle_state == lifecycle_state)
    if map_status:
        base = base.where(ExternalRecordMap.map_status == map_status)
    if q:
        like = f"%{q}%"
        base = base.where(
            or_(
                ZohoSubscriptionRecord.account_name.ilike(like),
                ZohoSubscriptionRecord.facility_name.ilike(like),
                ZohoSubscriptionRecord.msisdn.ilike(like),
                ZohoSubscriptionRecord.subscription_mgmt_id.ilike(like),
            )
        )

    rows = (
        await db.execute(
            base.order_by(desc(ZohoSubscriptionRecord.updated_at)).offset(offset).limit(limit)
        )
    ).all()
    items = [serialize_review_row(rec, rec_map) for rec, rec_map in rows]
    total = await _count(db, base)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "read_only": True,
        "note": _READ_ONLY_NOTE,
    }


@router.get("/zoho/review/unmapped")
async def list_zoho_unmapped_review(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_INTEGRATIONS")),
):
    """List staged records not yet confirm-mapped to a True911 entity.

    These are the records that need an operator to confirm a mapping before a
    later, gated phase could promote a lifecycle_status.
    """
    base = (
        select(ZohoSubscriptionRecord, ExternalRecordMap)
        .outerjoin(
            ExternalRecordMap,
            ZohoSubscriptionRecord.external_record_map_id == ExternalRecordMap.id,
        )
        .where(ZohoSubscriptionRecord.org_id == current_user.tenant_id)
        .where(
            or_(
                ExternalRecordMap.id.is_(None),
                ExternalRecordMap.map_status != "confirmed",
            )
        )
    )
    rows = (
        await db.execute(
            base.order_by(desc(ZohoSubscriptionRecord.updated_at)).offset(offset).limit(limit)
        )
    ).all()
    items = [serialize_review_row(rec, rec_map) for rec, rec_map in rows]
    total = await _count(db, base)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "read_only": True,
        "note": _READ_ONLY_NOTE,
    }


@router.get("/zoho/review/observations")
async def list_zoho_observations(
    matched: bool | None = Query(None, description="filter on whether routing matched a subscription event"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("VIEW_INTEGRATIONS")),
):
    """List sanitized inbound Zoho payload observations (contract discovery)."""
    base = select(ZohoPayloadObservation).where(
        ZohoPayloadObservation.org_id == current_user.tenant_id
    )
    if matched is not None:
        base = base.where(ZohoPayloadObservation.matched_subscription == matched)

    rows = (
        await db.execute(
            base.order_by(desc(ZohoPayloadObservation.created_at)).offset(offset).limit(limit)
        )
    ).scalars().all()
    items = [serialize_observation(o) for o in rows]
    total = await _count(db, base)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "read_only": True,
        "note": _READ_ONLY_NOTE,
    }
