"""
True911 — Automation Analytics.

Aggregation queries over autonomous_actions for the Automation Dashboard.
All queries are tenant-scoped and efficient (single-pass aggregations).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.autonomous_action import AutonomousAction


async def get_automation_dashboard(
    db: AsyncSession,
    tenant_id: str,
    hours: int = 24,
) -> dict:
    """Build the full automation dashboard payload in minimal queries.

    Returns:
        summary: KPI counts
        recommendations: active items sorted by severity
        by_status: lifecycle breakdown
        by_type: automation type distribution
        by_reason: top reason codes
        by_site: top affected sites
        recent: last 20 events
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    auto_filter = AutonomousAction.action_type.like("automation_%")
    tenant_filter = AutonomousAction.tenant_id == tenant_id
    time_filter = AutonomousAction.created_at >= cutoff

    base = and_(tenant_filter, auto_filter, time_filter)

    # ── 1. Status breakdown (single query) ─────────────────────────
    status_q = await db.execute(
        select(
            AutonomousAction.status,
            func.count().label("cnt"),
        )
        .where(base)
        .group_by(AutonomousAction.status)
    )
    by_status = {row.status: row.cnt for row in status_q.all()}

    active = by_status.get("suggested", 0) + by_status.get("queued", 0)
    suppressed = by_status.get("suppressed", 0)
    resolved = by_status.get("resolved", 0)
    total = sum(by_status.values())
    noise_pct = round((suppressed / max(total, 1)) * 100)

    # Count critical escalations (action_type = automation_escalate, status in suggested/queued)
    escalation_q = await db.execute(
        select(func.count())
        .select_from(AutonomousAction)
        .where(and_(
            base,
            AutonomousAction.action_type == "automation_escalate",
            AutonomousAction.status.in_(["suggested", "queued"]),
        ))
    )
    escalations = escalation_q.scalar() or 0

    summary = {
        "active_recommendations": active,
        "critical_escalations": escalations,
        "queued_actions": by_status.get("queued", 0),
        "suppressed_events": suppressed,
        "resolved_today": resolved,
        "noise_reduction_pct": noise_pct,
        "total_events": total,
    }

    # ── 2. Type breakdown ──────────────────────────────────────────
    type_q = await db.execute(
        select(
            AutonomousAction.action_type,
            func.count().label("cnt"),
        )
        .where(base)
        .group_by(AutonomousAction.action_type)
        .order_by(func.count().desc())
    )
    by_type = [
        {"type": row.action_type.replace("automation_", ""), "count": row.cnt}
        for row in type_q.all()
    ]

    # ── 3. Top reason codes (from detail_json) ─────────────────────
    # Query recent events and aggregate in Python (detail_json is TEXT)
    recent_q = await db.execute(
        select(AutonomousAction)
        .where(base)
        .order_by(AutonomousAction.created_at.desc())
        .limit(200)
    )
    recent_rows = recent_q.scalars().all()

    reason_counts: dict[str, int] = {}
    site_counts: dict[str, dict] = {}
    severity_counts: dict[str, int] = {}

    for row in recent_rows:
        detail = {}
        if row.detail_json:
            try:
                detail = json.loads(row.detail_json)
            except (json.JSONDecodeError, TypeError):
                pass

        reason = detail.get("reason_code", "unknown")
        severity = detail.get("severity", "info")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

        if row.site_id:
            if row.site_id not in site_counts:
                site_counts[row.site_id] = {"site_id": row.site_id, "count": 0, "latest_summary": ""}
            site_counts[row.site_id]["count"] += 1
            if not site_counts[row.site_id]["latest_summary"]:
                site_counts[row.site_id]["latest_summary"] = row.summary or ""

    by_reason = sorted(
        [{"reason": k, "count": v} for k, v in reason_counts.items()],
        key=lambda x: -x["count"],
    )[:10]

    by_site = sorted(
        list(site_counts.values()),
        key=lambda x: -x["count"],
    )[:10]

    by_severity = [
        {"severity": k, "count": v}
        for k, v in sorted(severity_counts.items(), key=lambda x: -x[1])
    ]

    # ── 4. Active recommendations (suggested + queued, most recent) ─
    active_q = await db.execute(
        select(AutonomousAction)
        .where(and_(
            tenant_filter, auto_filter,
            AutonomousAction.status.in_(["suggested", "queued"]),
            AutonomousAction.created_at >= now - timedelta(hours=48),
        ))
        .order_by(AutonomousAction.created_at.desc())
        .limit(20)
    )
    active_items = []
    for row in active_q.scalars().all():
        detail = {}
        if row.detail_json:
            try:
                detail = json.loads(row.detail_json)
            except (json.JSONDecodeError, TypeError):
                pass
        active_items.append({
            "id": row.action_id,
            "site_id": row.site_id,
            "device_id": row.device_id,
            "automation_type": row.action_type.replace("automation_", ""),
            "status": row.status,
            "summary": row.summary,
            "detail": detail.get("recommendation_detail", ""),
            "reason_code": detail.get("reason_code", ""),
            "severity": detail.get("severity", "info"),
            "execution_mode": detail.get("execution_mode", "manual"),
            "recipient_scopes": detail.get("recipient_scopes", []),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    # ── 5. Recent events (last 20 of any status) ──────────────────
    recent_items = []
    for row in recent_rows[:20]:
        detail = {}
        if row.detail_json:
            try:
                detail = json.loads(row.detail_json)
            except (json.JSONDecodeError, TypeError):
                pass
        recent_items.append({
            "id": row.action_id,
            "site_id": row.site_id,
            "automation_type": row.action_type.replace("automation_", ""),
            "status": row.status,
            "result": row.result,
            "summary": row.summary,
            "severity": detail.get("severity", "info"),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    # ── 6. Suppression details ─────────────────────────────────────
    suppressed_reasons: dict[str, int] = {}
    suppressed_sites: dict[str, int] = {}
    for row in recent_rows:
        if row.status != "suppressed":
            continue
        detail = {}
        if row.detail_json:
            try:
                detail = json.loads(row.detail_json)
            except (json.JSONDecodeError, TypeError):
                pass
        r = detail.get("reason_code", "unknown")
        suppressed_reasons[r] = suppressed_reasons.get(r, 0) + 1
        if row.site_id:
            suppressed_sites[row.site_id] = suppressed_sites.get(row.site_id, 0) + 1

    suppression_detail = {
        "total": suppressed,
        "top_reasons": sorted(
            [{"reason": k, "count": v} for k, v in suppressed_reasons.items()],
            key=lambda x: -x["count"],
        )[:5],
        "top_sites": sorted(
            [{"site_id": k, "count": v} for k, v in suppressed_sites.items()],
            key=lambda x: -x["count"],
        )[:5],
    }

    return {
        "summary": summary,
        "recommendations": active_items,
        "by_status": by_status,
        "by_type": by_type,
        "by_reason": by_reason,
        "by_severity": by_severity,
        "by_site": by_site,
        "suppression": suppression_detail,
        "recent": recent_items,
        "period_hours": hours,
    }
