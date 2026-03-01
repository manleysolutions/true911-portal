"""Reconciliation engine — compares deployed lines vs billed lines vs active subscriptions.

Produces a ReconciliationSnapshot with detailed mismatches for admin review.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.job import Job
from app.models.line import Line
from app.models.reconciliation_snapshot import ReconciliationSnapshot
from app.models.subscription import Subscription

logger = logging.getLogger("true911.reconciliation")

# Statuses that count as "deployed" for lines
_DEPLOYED_LINE_STATUSES = {"active", "provisioning"}

# Statuses that count as "active" for subscriptions
_ACTIVE_SUB_STATUSES = {"active", "trialing"}


async def run_reconciliation(db: AsyncSession, job: Job) -> dict[str, Any]:
    """Execute reconciliation and persist snapshot.

    Called by the worker for job_type='integration.reconcile'.
    """
    payload = job.payload or {}
    org_id = payload.get("org_id")
    if not org_id:
        return {"error": "Missing org_id"}

    logger.info("Running reconciliation for org %s", org_id)

    # ── Gather data ──────────────────────────────────────────────

    # All customers
    customers = (await db.execute(
        select(Customer).where(Customer.tenant_id == org_id)
    )).scalars().all()

    # All subscriptions
    subscriptions = (await db.execute(
        select(Subscription).where(Subscription.tenant_id == org_id)
    )).scalars().all()

    # Deployed line counts per subscription
    deployed_by_sub = {}
    deployed_no_sub = 0

    lines = (await db.execute(
        select(Line).where(
            Line.tenant_id == org_id,
            Line.status.in_(_DEPLOYED_LINE_STATUSES),
        )
    )).scalars().all()

    for line in lines:
        if line.subscription_id:
            deployed_by_sub.setdefault(line.subscription_id, 0)
            deployed_by_sub[line.subscription_id] += 1
        else:
            deployed_no_sub += 1

    # Also count lines that have a device_id as deployed
    # (even if status isn't explicitly in the set, having a device implies deployment)
    lines_with_device = (await db.execute(
        select(Line).where(
            Line.tenant_id == org_id,
            Line.device_id.isnot(None),
            Line.device_id != "",
        )
    )).scalars().all()
    total_deployed_by_device = len(lines_with_device)

    # ── Compute mismatches ───────────────────────────────────────

    mismatches = []
    sub_map = {s.id: s for s in subscriptions}
    cust_map = {c.id: c for c in customers}

    for sub in subscriptions:
        deployed = deployed_by_sub.get(sub.id, 0)
        billed = sub.qty_lines
        is_active = sub.status in _ACTIVE_SUB_STATUSES
        customer_name = cust_map.get(sub.customer_id, None)
        cust_name = customer_name.name if customer_name else "Unknown"

        if is_active and billed > deployed:
            mismatches.append({
                "type": "billed_gt_deployed",
                "customer": cust_name,
                "customer_id": sub.customer_id,
                "subscription_id": sub.id,
                "plan": sub.plan_name,
                "billed": billed,
                "deployed": deployed,
                "delta": billed - deployed,
                "message": f"Billed {billed} lines but only {deployed} deployed",
            })
        elif is_active and deployed > billed:
            mismatches.append({
                "type": "deployed_gt_billed",
                "customer": cust_name,
                "customer_id": sub.customer_id,
                "subscription_id": sub.id,
                "plan": sub.plan_name,
                "billed": billed,
                "deployed": deployed,
                "delta": deployed - billed,
                "message": f"Deployed {deployed} lines but only billing for {billed}",
            })

        if is_active and deployed == 0 and billed > 0:
            mismatches.append({
                "type": "active_sub_no_lines",
                "customer": cust_name,
                "customer_id": sub.customer_id,
                "subscription_id": sub.id,
                "plan": sub.plan_name,
                "billed": billed,
                "deployed": 0,
                "message": f"Active subscription ({sub.plan_name}) with {billed} billed lines but none deployed",
            })

    # Lines active but no active subscription
    for line in lines:
        if line.subscription_id and line.subscription_id in sub_map:
            sub = sub_map[line.subscription_id]
            if sub.status not in _ACTIVE_SUB_STATUSES:
                cust_name = cust_map.get(sub.customer_id, None)
                mismatches.append({
                    "type": "line_active_no_sub",
                    "customer": cust_name.name if cust_name else "Unknown",
                    "customer_id": sub.customer_id,
                    "subscription_id": sub.id,
                    "line_id": line.line_id,
                    "message": f"Line {line.line_id} is active but subscription is '{sub.status}'",
                })

    # Unlinked deployed lines (no subscription at all)
    if deployed_no_sub > 0:
        mismatches.append({
            "type": "unlinked_deployed_lines",
            "count": deployed_no_sub,
            "message": f"{deployed_no_sub} deployed lines have no subscription linked",
        })

    # ── Persist snapshot ─────────────────────────────────────────

    total_billed = sum(s.qty_lines for s in subscriptions if s.status in _ACTIVE_SUB_STATUSES)
    total_deployed = sum(1 for l in lines if l.status in _DEPLOYED_LINE_STATUSES)

    snapshot = ReconciliationSnapshot(
        org_id=org_id,
        total_customers=len(customers),
        total_subscriptions=len(subscriptions),
        total_billed_lines=total_billed,
        total_deployed_lines=total_deployed,
        mismatches_count=len(mismatches),
        results_json={
            "mismatches": mismatches,
            "summary": {
                "total_customers": len(customers),
                "active_subscriptions": sum(1 for s in subscriptions if s.status in _ACTIVE_SUB_STATUSES),
                "total_billed_lines": total_billed,
                "total_deployed_lines": total_deployed,
                "deployed_with_device": total_deployed_by_device,
                "unlinked_deployed": deployed_no_sub,
            },
        },
    )
    db.add(snapshot)
    await db.flush()

    logger.info(
        "Reconciliation complete for %s: %d customers, %d subs, %d billed, %d deployed, %d mismatches",
        org_id, len(customers), len(subscriptions), total_billed, total_deployed, len(mismatches),
    )

    return {
        "snapshot_id": snapshot.id,
        "mismatches_count": len(mismatches),
        "total_billed": total_billed,
        "total_deployed": total_deployed,
    }
