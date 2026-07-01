"""Customer Contribution Workflow — the collaborative Building Workspace (Phase 2/6).

Lets a customer continuously improve their Digital Twin (add contacts, record
inspections, note details, request service, submit document/photo/procedure
metadata) WITHOUT ever writing protected data directly.  Every contribution is an
append-only ``ActionAudit`` event routed through a submission → review workflow:
the customer sees "submitted", an operator reviews it later.  This is migration-
free and makes the audit/workflow trail intrinsic — the same pattern as the E911
review and service-classification workflows.

Hard rules:
  * NO direct writes to protected data (Site / ServiceUnit / Line / E911).  A
    contribution is a *request*, stored as data — applying it is a controlled step.
  * File uploads (photo/document/procedure) record METADATA only here (name,
    category, note); real blob storage is a future step (nothing is fabricated).
  * Tenant-scoped; opaque location refs only.  No operating-company references.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_audit import ActionAudit

CONTRIBUTION_ACTION = "customer_contribution"
CONTRIBUTION_TYPES = (
    "contact", "inspection", "photo", "document", "procedure", "note", "service_request",
)
# Human labels for the submitted-contribution acknowledgement (neutral wording).
_ACK = {
    "contact": "Contact submitted — awaiting review",
    "inspection": "Inspection record submitted — awaiting review",
    "photo": "Photo submitted — awaiting review",
    "document": "Document submitted — awaiting review",
    "procedure": "Emergency procedure submitted — awaiting review",
    "note": "Note added",
    "service_request": "Service request created — awaiting review",
}


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


async def record_contribution(db: AsyncSession, user, site, *, ctype: str,
                              payload: dict, note: str = "") -> dict:
    """Record a customer contribution as an append-only workflow submission.
    Never writes protected data.  Raises ValueError for an unknown type."""
    if ctype not in CONTRIBUTION_TYPES:
        raise ValueError(f"Unknown contribution type '{ctype}'")
    contribution_id = _uid("CTR")
    now = datetime.now(timezone.utc)
    original_tid = getattr(user, "_original_tenant_id", user.tenant_id)
    db.add(ActionAudit(
        audit_id=_uid("AUD"), request_id=_uid("REQ"), tenant_id=user.tenant_id,
        user_email=user.email, requester_name=getattr(user, "name", None), role=user.role,
        action_type=CONTRIBUTION_ACTION, site_id=site.site_id, timestamp=now, result="ok",
        details=json.dumps({"contribution_id": contribution_id, "type": ctype,
                            "payload": payload or {}, "note": note or "",
                            "status": "submitted",
                            "user_id": str(getattr(user, "id", "") or "")}),
        original_tenant_id=original_tid,
        acting_as_tenant_id=(user.tenant_id if user.tenant_id != original_tid else None)))
    await db.commit()
    # 'note' contributions are self-serve and need no review; the rest are pending.
    status = "recorded" if ctype == "note" else "submitted"
    return {"contribution_id": contribution_id, "type": ctype, "status": status,
            "message": _ACK.get(ctype, "Submitted — awaiting review")}


async def _events(db: AsyncSession, tenant_id: str, site_id: str):
    return (await db.execute(
        select(ActionAudit).where(
            ActionAudit.tenant_id == tenant_id, ActionAudit.site_id == site_id,
            ActionAudit.action_type == CONTRIBUTION_ACTION,
        ).order_by(ActionAudit.id.desc()))).scalars().all()


def _parse(rows) -> list[dict]:
    out = []
    for r in rows:
        try:
            d = json.loads(r.details or "{}")
        except Exception:
            continue
        out.append({
            "contribution_id": d.get("contribution_id"),
            "type": d.get("type"),
            "status": d.get("status", "submitted"),
            "payload": d.get("payload") or {},
            "note": d.get("note") or None,
            "by": r.requester_name or r.user_email,
            "when": r.timestamp.isoformat() if r.timestamp else None,
        })
    return out


async def list_contributions(db: AsyncSession, tenant_id: str, site_id: str) -> dict:
    """A location's contribution log (newest first) + counts by type."""
    items = _parse(await _events(db, tenant_id, site_id))
    counts: dict = {}
    for it in items:
        counts[it["type"]] = counts.get(it["type"], 0) + 1
    return {"count": len(items), "by_type": counts, "contributions": items}


async def contribution_counts(db: AsyncSession, tenant_id: str, site_id: str) -> dict:
    """Just the by-type counts (for completeness / maturity signals)."""
    return (await list_contributions(db, tenant_id, site_id))["by_type"]
