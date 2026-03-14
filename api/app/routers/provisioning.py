"""Provisioning Queue — review and link unassigned infrastructure to sites."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.device import Device
from app.models.line import Line
from app.models.provisioning_queue import ProvisioningQueueItem
from app.models.sim import Sim
from app.models.site import Site
from app.models.user import User

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class QueueItemOut(BaseModel):
    id: int
    tenant_id: str
    item_type: str
    item_id: int
    external_ref: Optional[str] = None
    source_provider: Optional[str] = None
    current_site_id: Optional[str] = None
    current_device_id: Optional[str] = None
    suggested_tenant_id: Optional[str] = None
    suggested_site_id: Optional[str] = None
    suggested_site_name: Optional[str] = None
    suggested_device_id: Optional[str] = None
    suggested_unit_type: Optional[str] = None
    suggestion_confidence: Optional[float] = None
    suggestion_reason: Optional[str] = None
    missing_e911: bool = False
    missing_site: bool = True
    missing_customer: bool = False
    needs_compliance_review: bool = False
    status: str = "new"
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_site_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    site_id: str


class LinkRequest(BaseModel):
    site_id: str


# ── Endpoints ────────────────────────────────────────────────────

@router.get("", response_model=list[QueueItemOut])
async def list_queue(
    limit: int = Query(100, le=500),
    item_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List provisioning queue items."""
    q = select(ProvisioningQueueItem).where(
        ProvisioningQueueItem.tenant_id == current_user.tenant_id
    )
    if item_type:
        q = q.where(ProvisioningQueueItem.item_type == item_type)
    if status_filter:
        q = q.where(ProvisioningQueueItem.status == status_filter)
    else:
        # Default: show actionable items
        q = q.where(ProvisioningQueueItem.status.in_(["new", "suggested", "needs_review"]))
    q = q.order_by(ProvisioningQueueItem.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return [QueueItemOut.model_validate(i) for i in result.scalars().all()]


@router.get("/summary")
async def queue_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return counts by type and status."""
    q = select(
        ProvisioningQueueItem.item_type,
        ProvisioningQueueItem.status,
        func.count().label("count"),
    ).where(
        ProvisioningQueueItem.tenant_id == current_user.tenant_id,
    ).group_by(
        ProvisioningQueueItem.item_type,
        ProvisioningQueueItem.status,
    )
    result = await db.execute(q)
    rows = result.all()

    by_type = {}
    by_status = {}
    total = 0
    actionable = 0
    for item_type, st, count in rows:
        by_type[item_type] = by_type.get(item_type, 0) + count
        by_status[st] = by_status.get(st, 0) + count
        total += count
        if st in ("new", "suggested", "needs_review"):
            actionable += count

    return {
        "total": total,
        "actionable": actionable,
        "by_type": by_type,
        "by_status": by_status,
    }


@router.post("/scan")
async def scan_queue(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scan for unlinked infrastructure and populate the queue."""
    from app.services.provisioning_engine import scan_and_enqueue
    result = await scan_and_enqueue(db, current_user.tenant_id, current_user.email)
    return result


@router.post("/{item_id}/approve", response_model=QueueItemOut)
async def approve_suggestion(
    item_id: int,
    body: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a suggestion — link the item to the specified site."""
    item = await _get_item(db, item_id, current_user.tenant_id)

    # Verify site exists
    site_result = await db.execute(select(Site).where(Site.site_id == body.site_id))
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    # Apply the linkage
    await _link_item_to_site(db, item, body.site_id)

    item.status = "linked"
    item.resolved_by = current_user.email
    item.resolved_at = datetime.now(timezone.utc)
    item.resolved_site_id = body.site_id
    await db.commit()
    await db.refresh(item)
    return QueueItemOut.model_validate(item)


@router.post("/{item_id}/link", response_model=QueueItemOut)
async def link_to_site(
    item_id: int,
    body: LinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually link a queue item to a site (operator override)."""
    item = await _get_item(db, item_id, current_user.tenant_id)

    site_result = await db.execute(select(Site).where(Site.site_id == body.site_id))
    if not site_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    await _link_item_to_site(db, item, body.site_id)

    item.status = "linked"
    item.resolved_by = current_user.email
    item.resolved_at = datetime.now(timezone.utc)
    item.resolved_site_id = body.site_id
    await db.commit()
    await db.refresh(item)
    return QueueItemOut.model_validate(item)


@router.post("/{item_id}/ignore", response_model=QueueItemOut)
async def ignore_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark item as ignored."""
    item = await _get_item(db, item_id, current_user.tenant_id)
    item.status = "ignored"
    item.resolved_by = current_user.email
    item.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return QueueItemOut.model_validate(item)


# ── Helpers ──────────────────────────────────────────────────────

async def _get_item(db: AsyncSession, item_id: int, tenant_id: str) -> ProvisioningQueueItem:
    result = await db.execute(
        select(ProvisioningQueueItem).where(
            ProvisioningQueueItem.id == item_id,
            ProvisioningQueueItem.tenant_id == tenant_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Queue item not found")
    return item


async def _link_item_to_site(db: AsyncSession, item: ProvisioningQueueItem, site_id: str):
    """Apply the actual linkage: update the underlying SIM/device/line record."""
    if item.item_type == "sim":
        result = await db.execute(select(Sim).where(Sim.id == item.item_id))
        sim = result.scalar_one_or_none()
        if sim:
            sim.site_id = site_id
    elif item.item_type == "device":
        result = await db.execute(select(Device).where(Device.id == item.item_id))
        dev = result.scalar_one_or_none()
        if dev:
            dev.site_id = site_id
    elif item.item_type == "line":
        result = await db.execute(select(Line).where(Line.id == item.item_id))
        line = result.scalar_one_or_none()
        if line:
            line.site_id = site_id
