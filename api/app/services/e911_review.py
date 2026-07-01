"""Customer E911 confirmation + correction workflow (append-only, safe).

Lets CUSTOMER_* users **confirm** an emergency record is correct or **request a
correction** — WITHOUT ever overwriting the official E911 record.  Every action
(customer confirm/correction, internal approve/reject/apply) is an append-only
``ActionAudit`` event; the review's current state is derived from its event
chain (keyed by ``review_id``).  This is migration-free (no new table) and makes
the audit trail intrinsic.

Data safety (hard rules):
  * Customer submissions NEVER write ``Site.e911_*`` / ServiceUnit / Line.  A
    correction is a *request*, stored as data — applying it stays a controlled,
    Manley-gated step (the existing UPDATE_E911 `/api/e911-changes` flow).
  * Confirm snapshots the record the SERVER currently shows (not client-supplied
    content), so we log exactly what was confirmed.
  * Tenant-scoped throughout; opaque refs only at the API edge.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_audit import ActionAudit

CONFIRM = "e911_customer_confirm"
CORRECTION = "e911_correction_request"
APPROVE = "e911_review_approve"
REJECT = "e911_review_reject"
APPLY = "e911_review_apply"
CREATE_ACTIONS = (CONFIRM, CORRECTION)
DECISION_ACTIONS = (APPROVE, REJECT, APPLY)
ALL_ACTIONS = CREATE_ACTIONS + DECISION_ACTIONS

_VERIFIED = {"validated", "verified"}


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


async def _audit(db: AsyncSession, user, action_type: str, site_id: str, details: dict) -> ActionAudit:
    now = datetime.now(timezone.utc)
    original_tid = getattr(user, "_original_tenant_id", user.tenant_id)
    row = ActionAudit(
        audit_id=_uid("AUD"), request_id=_uid("REQ"), tenant_id=user.tenant_id,
        user_email=user.email, requester_name=getattr(user, "name", None), role=user.role,
        action_type=action_type, site_id=site_id, timestamp=now, result="ok",
        details=json.dumps(details), original_tenant_id=original_tid,
        acting_as_tenant_id=(user.tenant_id if user.tenant_id != original_tid else None))
    db.add(row)
    await db.commit()
    return row


# ── Customer submissions (never touch official records) ──────────────
async def record_confirmation(db, user, site, *, snapshot: dict, note: str = "") -> dict:
    review_id = _uid("REV")
    await _audit(db, user, CONFIRM, site.site_id, {
        "review_id": review_id, "type": "confirm",
        "address_snapshot": snapshot.get("emergency_dispatch_address"),
        "endpoints_snapshot": snapshot.get("emergency_endpoints", []),
        "verification_snapshot": snapshot.get("verification", {}),
        "user_id": str(getattr(user, "id", "") or ""), "note": note or "",
    })
    return {"review_id": review_id, "status": "pending",
            "message": "Customer confirmed — pending Manley verification"}


async def record_correction(db, user, site, *, corrected: dict, snapshot: dict, note: str = "") -> dict:
    review_id = _uid("REV")
    await _audit(db, user, CORRECTION, site.site_id, {
        "review_id": review_id, "type": "correction",
        "corrected": corrected,   # requested values only — NOT applied
        "address_snapshot": snapshot.get("emergency_dispatch_address"),
        "user_id": str(getattr(user, "id", "") or ""), "note": note or "",
    })
    return {"review_id": review_id, "status": "pending",
            "message": "Correction submitted — under Manley review"}


# ── Event → review derivation ────────────────────────────────────────
async def _events(db, tenant_id, *, site_id=None):
    q = select(ActionAudit).where(
        ActionAudit.tenant_id == tenant_id, ActionAudit.action_type.in_(ALL_ACTIONS))
    if site_id is not None:
        q = q.where(ActionAudit.site_id == site_id)
    return (await db.execute(q.order_by(ActionAudit.id.asc()))).scalars().all()


def _build_reviews(events) -> list[dict]:
    reviews: dict = {}
    for e in events:
        try:
            d = json.loads(e.details or "{}")
        except Exception:
            continue
        rid = d.get("review_id")
        if not rid:
            continue
        if e.action_type in CREATE_ACTIONS:
            reviews[rid] = {
                "review_id": rid, "type": d.get("type"), "site_id": e.site_id,
                "created_by": e.requester_name or e.user_email,
                "created_at": e.timestamp.isoformat() if e.timestamp else None,
                "note": d.get("note") or None, "corrected": d.get("corrected"),
                "address_snapshot": d.get("address_snapshot"),
                "endpoints_snapshot": d.get("endpoints_snapshot"),
                "status": "pending", "decisions": [],
            }
        elif rid in reviews:
            r = reviews[rid]
            r["status"] = {"e911_review_approve": "approved", "e911_review_reject": "rejected",
                           "e911_review_apply": "applied"}.get(e.action_type, r["status"])
            r["decisions"].append({
                "decision": e.action_type.replace("e911_review_", ""),
                "by": e.requester_name or e.user_email,
                "at": e.timestamp.isoformat() if e.timestamp else None,
                "note": d.get("note") or None})
    return sorted(reviews.values(), key=lambda r: r["created_at"] or "", reverse=True)


# ── Customer-facing status (calm, customer-safe) ─────────────────────
def _friendly_state(verified: bool, latest: dict | None) -> str:
    if verified:
        return "Verified"
    if latest is None:
        return "Not yet verified"
    if latest["status"] == "rejected":
        return "Not yet verified"
    if latest["status"] in ("approved", "applied"):
        return "Under Manley review"
    return "Correction requested" if latest["type"] == "correction" else "Customer confirmed"


async def location_review_status(db, tenant_id: str, site) -> dict:
    reviews = _build_reviews(await _events(db, tenant_id, site_id=site.site_id))
    latest = reviews[0] if reviews else None
    verified = (site.e911_status or "").lower() in _VERIFIED
    return {
        "state": _friendly_state(verified, latest),
        "verified": verified,
        "review_count": len(reviews),
        "latest_review": ({k: latest[k] for k in ("review_id", "type", "status", "created_at")}
                          if latest else None),
    }


# ── Internal review queue + decisions ────────────────────────────────
async def list_reviews(db, tenant_id: str, *, status: str = "pending") -> dict:
    reviews = _build_reviews(await _events(db, tenant_id))
    if status and status != "all":
        reviews = [r for r in reviews if r["status"] == status]
    return {"count": len(reviews), "status_filter": status, "reviews": reviews}


async def find_review(db, tenant_id: str, review_id: str) -> dict | None:
    for r in _build_reviews(await _events(db, tenant_id)):
        if r["review_id"] == review_id:
            return r
    return None


async def decide(db, user, review_id: str, *, decision: str, note: str = "", apply: bool = False) -> dict | None:
    """Approve or reject a review (tenant-scoped).  ``apply`` additionally logs an
    apply event (the operator asserts the change was made through the controlled
    UPDATE_E911 flow) — this NEVER writes the official record here."""
    r = await find_review(db, user.tenant_id, review_id)
    if r is None:
        return None
    action = APPROVE if decision == "approve" else REJECT
    await _audit(db, user, action, r["site_id"], {"review_id": review_id, "decision": decision, "note": note or ""})
    out = {"review_id": review_id, "decision": decision,
           "status": "approved" if decision == "approve" else "rejected"}
    if decision == "approve" and apply:
        await _audit(db, user, APPLY, r["site_id"], {"review_id": review_id, "note": note or "", "applied": True})
        out["status"] = "applied"
    return out
