"""Unified audit logger for infrastructure events.

Categories:
  device      — registration, status changes, firmware updates
  firmware    — firmware version changes
  verification — test execution and results
  incident    — creation, escalation, resolution
  config      — configuration changes
  network     — carrier events, connectivity changes

All entries are tenant-scoped and exportable for compliance.
"""

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_entry import AuditLogEntry


async def log_audit(
    db: AsyncSession,
    tenant_id: str,
    category: str,
    action: str,
    summary: str,
    *,
    actor: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    site_id: Optional[str] = None,
    device_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        entry_id=f"au-{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        category=category,
        action=action,
        actor=actor,
        target_type=target_type,
        target_id=target_id,
        site_id=site_id,
        device_id=device_id,
        summary=summary,
        detail_json=json.dumps(detail) if detail else None,
    )
    db.add(entry)
    return entry


async def export_audit_csv(
    db: AsyncSession,
    tenant_id: str,
    *,
    category: Optional[str] = None,
    limit: int = 5000,
) -> str:
    """Export audit log entries as CSV string."""

    q = select(AuditLogEntry).where(
        AuditLogEntry.tenant_id == tenant_id,
    ).order_by(AuditLogEntry.created_at.desc()).limit(limit)

    if category:
        q = q.where(AuditLogEntry.category == category)

    rows = (await db.execute(q)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "entry_id", "timestamp", "category", "action", "actor",
        "target_type", "target_id", "site_id", "device_id", "summary",
    ])
    for r in rows:
        writer.writerow([
            r.entry_id,
            r.created_at.isoformat() if r.created_at else "",
            r.category,
            r.action,
            r.actor or "",
            r.target_type or "",
            r.target_id or "",
            r.site_id or "",
            r.device_id or "",
            r.summary,
        ])
    return output.getvalue()
