"""Provisioning Queue — review and link unassigned infrastructure to sites."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.audit_log_entry import AuditLogEntry
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


class LinkRequest(BaseModel):
    site_id: str


class BulkLinkRequest(BaseModel):
    item_ids: list[int]
    site_id: str


class BulkIgnoreRequest(BaseModel):
    item_ids: list[int]


# ── Helpers ──────────────────────────────────────────────────────

def _is_superadmin(user: User) -> bool:
    return (user.role or "").lower() in ("superadmin",)


def _tenant_filter(q, user: User):
    """Scope query to tenant unless SuperAdmin."""
    if _is_superadmin(user):
        return q  # SuperAdmin sees all
    return q.where(ProvisioningQueueItem.tenant_id == user.tenant_id)


# ── Endpoints ────────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[QueueItemOut],
    dependencies=[Depends(require_permission("VIEW_PROVISIONING_QUEUE"))],
)
async def list_queue(
    limit: int = Query(200, le=500),
    item_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = _tenant_filter(select(ProvisioningQueueItem), current_user)
    if item_type:
        q = q.where(ProvisioningQueueItem.item_type == item_type)
    if status_filter:
        q = q.where(ProvisioningQueueItem.status == status_filter)
    else:
        q = q.where(ProvisioningQueueItem.status.in_(["new", "suggested", "needs_review"]))
    q = q.order_by(ProvisioningQueueItem.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return [QueueItemOut.model_validate(i) for i in result.scalars().all()]


@router.get(
    "/summary",
    dependencies=[Depends(require_permission("VIEW_PROVISIONING_QUEUE"))],
)
async def queue_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(
        ProvisioningQueueItem.item_type,
        ProvisioningQueueItem.status,
        func.count().label("count"),
    )
    q = _tenant_filter(q, current_user)
    q = q.group_by(ProvisioningQueueItem.item_type, ProvisioningQueueItem.status)
    result = await db.execute(q)

    by_type = {}
    by_status = {}
    total = 0
    actionable = 0
    for item_type, st, count in result.all():
        by_type[item_type] = by_type.get(item_type, 0) + count
        by_status[st] = by_status.get(st, 0) + count
        total += count
        if st in ("new", "suggested", "needs_review"):
            actionable += count

    return {"total": total, "actionable": actionable, "by_type": by_type, "by_status": by_status}


@router.post(
    "/scan",
    dependencies=[Depends(require_permission("MANAGE_PROVISIONING"))],
)
async def scan_queue(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.provisioning_engine import scan_and_enqueue
    result = await scan_and_enqueue(
        db,
        tenant_id=current_user.tenant_id,
        initiated_by=current_user.email,
        is_superadmin=_is_superadmin(current_user),
    )

    audit = AuditLogEntry(
        entry_id=f"prov-scan-{uuid.uuid4().hex[:12]}",
        tenant_id=current_user.tenant_id,
        category="provisioning",
        action="provisioning_scan",
        actor=current_user.email,
        target_type="provisioning_queue",
        summary=f"Provisioning scan by {current_user.email} — {result.get('created', 0)} new, {result.get('skipped', 0)} skipped",
        detail_json=json.dumps({"created": result.get("created", 0), "skipped": result.get("skipped", 0)}),
    )
    db.add(audit)
    await db.commit()
    return result


@router.post(
    "/{item_id}/link",
    response_model=QueueItemOut,
    dependencies=[Depends(require_permission("MANAGE_PROVISIONING"))],
)
async def link_to_site(
    item_id: int,
    body: LinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link a queue item to a site."""
    item = await _get_item(db, item_id, current_user)
    site_result = await db.execute(select(Site).where(Site.site_id == body.site_id))
    if not site_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    await _link_item_to_site(db, item, body.site_id)
    item.status = "linked"
    item.resolved_by = current_user.email
    item.resolved_at = datetime.now(timezone.utc)
    item.resolved_site_id = body.site_id

    audit = AuditLogEntry(
        entry_id=f"prov-link-{uuid.uuid4().hex[:12]}",
        tenant_id=current_user.tenant_id,
        category="provisioning",
        action="provisioning_link",
        actor=current_user.email,
        target_type=item.item_type,
        target_id=str(item.item_id),
        site_id=body.site_id,
        summary=f"{item.item_type} {item.external_ref} linked to site {body.site_id} by {current_user.email}",
        detail_json=json.dumps({"item_id": item.id, "item_type": item.item_type, "external_ref": item.external_ref, "site_id": body.site_id}),
    )
    db.add(audit)
    await db.commit()
    await db.refresh(item)
    return QueueItemOut.model_validate(item)


@router.post(
    "/{item_id}/approve",
    response_model=QueueItemOut,
    dependencies=[Depends(require_permission("MANAGE_PROVISIONING"))],
)
async def approve_suggestion(
    item_id: int,
    body: LinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve — same as link but semantically confirms a suggestion."""
    return await link_to_site(item_id, body, db, current_user)


@router.post(
    "/{item_id}/ignore",
    response_model=QueueItemOut,
    dependencies=[Depends(require_permission("MANAGE_PROVISIONING"))],
)
async def ignore_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await _get_item(db, item_id, current_user)
    item.status = "ignored"
    item.resolved_by = current_user.email
    item.resolved_at = datetime.now(timezone.utc)

    audit = AuditLogEntry(
        entry_id=f"prov-ignore-{uuid.uuid4().hex[:12]}",
        tenant_id=current_user.tenant_id,
        category="provisioning",
        action="provisioning_ignore",
        actor=current_user.email,
        target_type=item.item_type,
        target_id=str(item.item_id),
        summary=f"{item.item_type} {item.external_ref} ignored by {current_user.email}",
        detail_json=json.dumps({"item_id": item.id, "item_type": item.item_type, "external_ref": item.external_ref}),
    )
    db.add(audit)
    await db.commit()
    await db.refresh(item)
    return QueueItemOut.model_validate(item)


@router.post(
    "/bulk-link",
    dependencies=[Depends(require_permission("MANAGE_PROVISIONING"))],
)
async def bulk_link(
    body: BulkLinkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link multiple queue items to a site in one operation."""
    site_result = await db.execute(select(Site).where(Site.site_id == body.site_id))
    if not site_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")

    q = select(ProvisioningQueueItem).where(ProvisioningQueueItem.id.in_(body.item_ids))
    if not _is_superadmin(current_user):
        q = q.where(ProvisioningQueueItem.tenant_id == current_user.tenant_id)
    result = await db.execute(q)
    items = result.scalars().all()

    now = datetime.now(timezone.utc)
    linked = 0
    for item in items:
        if item.status in ("linked", "ignored"):
            continue
        await _link_item_to_site(db, item, body.site_id)
        item.status = "linked"
        item.resolved_by = current_user.email
        item.resolved_at = now
        item.resolved_site_id = body.site_id
        linked += 1

    audit = AuditLogEntry(
        entry_id=f"prov-bulk-link-{uuid.uuid4().hex[:12]}",
        tenant_id=current_user.tenant_id,
        category="provisioning",
        action="provisioning_bulk_link",
        actor=current_user.email,
        target_type="provisioning_queue",
        site_id=body.site_id,
        summary=f"Bulk link: {linked} items linked to site {body.site_id} by {current_user.email}",
        detail_json=json.dumps({"linked": linked, "site_id": body.site_id, "item_ids": body.item_ids}),
    )
    db.add(audit)
    await db.commit()
    return {"linked": linked, "site_id": body.site_id}


@router.post(
    "/bulk-ignore",
    dependencies=[Depends(require_permission("MANAGE_PROVISIONING"))],
)
async def bulk_ignore(
    body: BulkIgnoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ignore multiple queue items."""
    q = select(ProvisioningQueueItem).where(ProvisioningQueueItem.id.in_(body.item_ids))
    if not _is_superadmin(current_user):
        q = q.where(ProvisioningQueueItem.tenant_id == current_user.tenant_id)
    result = await db.execute(q)
    items = result.scalars().all()

    now = datetime.now(timezone.utc)
    ignored = 0
    for item in items:
        if item.status in ("linked", "ignored"):
            continue
        item.status = "ignored"
        item.resolved_by = current_user.email
        item.resolved_at = now
        ignored += 1

    audit = AuditLogEntry(
        entry_id=f"prov-bulk-ignore-{uuid.uuid4().hex[:12]}",
        tenant_id=current_user.tenant_id,
        category="provisioning",
        action="provisioning_bulk_ignore",
        actor=current_user.email,
        target_type="provisioning_queue",
        summary=f"Bulk ignore: {ignored} items ignored by {current_user.email}",
        detail_json=json.dumps({"ignored": ignored, "item_ids": body.item_ids}),
    )
    db.add(audit)
    await db.commit()
    return {"ignored": ignored}


# ── Internal helpers ─────────────────────────────────────────────

async def _get_item(db, item_id: int, user: User) -> ProvisioningQueueItem:
    q = select(ProvisioningQueueItem).where(ProvisioningQueueItem.id == item_id)
    if not _is_superadmin(user):
        q = q.where(ProvisioningQueueItem.tenant_id == user.tenant_id)
    result = await db.execute(q)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Queue item not found")
    return item


async def _link_item_to_site(db, item: ProvisioningQueueItem, site_id: str):
    if item.item_type == "sim":
        result = await db.execute(select(Sim).where(Sim.id == item.item_id))
        obj = result.scalar_one_or_none()
        if obj:
            obj.site_id = site_id
    elif item.item_type == "device":
        result = await db.execute(select(Device).where(Device.id == item.item_id))
        obj = result.scalar_one_or_none()
        if obj:
            obj.site_id = site_id
    elif item.item_type == "line":
        result = await db.execute(select(Line).where(Line.id == item.item_id))
        obj = result.scalar_one_or_none()
        if obj:
            obj.site_id = site_id
