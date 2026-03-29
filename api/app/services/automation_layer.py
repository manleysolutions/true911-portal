"""
True911 — Automation Layer.

Consumes Attention Engine output and produces structured automation
decisions: notifications, recommendations, escalations, and safe action
suggestions.

Key capabilities:
  - Deterministic dedupe keys prevent duplicate noise
  - Suppression windows prevent spam for unresolved conditions
  - Role-scoped recommendations (different visibility per role)
  - Lifecycle tracking via AutonomousAction audit records
  - Extensible for future ticketing, webhooks, and self-healing

The engine is stateless per evaluation — deduplication state comes from
querying recent AutonomousAction records.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.autonomous_action import AutonomousAction
from .attention_engine import (
    AttentionItem, SiteAttention, CanonicalStatus, Severity,
)
from .automation_policy import get_policy, AutomationPolicy


# ═══════════════════════════════════════════════════════════════════
# OUTPUT DATACLASS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AutomationDecision:
    """A single automation decision produced by the layer."""
    id: str
    tenant_id: str
    object_type: str          # site | device
    object_id: str
    site_id: str | None
    site_name: str | None
    reason_code: str
    severity: str
    automation_type: str      # escalate | notify | suggest_ping | suggest_reboot | follow_up | report_flag
    automation_status: str    # suggested | suppressed | queued | triggered
    execution_mode: str       # manual | assisted | automatic
    recipient_scopes: list[str]
    recommendation_title: str
    recommendation_detail: str
    dedupe_key: str
    suppress_until: str | None
    created_at: str
    route_hint: str | None = None


# ═══════════════════════════════════════════════════════════════════
# DEDUPE KEY GENERATION
# ═══════════════════════════════════════════════════════════════════

def _dedupe_key(object_type: str, object_id: str, reason_code: str, automation_type: str) -> str:
    """Deterministic key for deduplication.

    Format: {object_type}:{object_id}:{reason_code}:{automation_type}
    Same condition on same object produces the same key.
    """
    return f"{object_type}:{object_id}:{reason_code}:{automation_type}"


# ═══════════════════════════════════════════════════════════════════
# TEMPLATE FORMATTING
# ═══════════════════════════════════════════════════════════════════

def _format_template(template: str, item: AttentionItem) -> str:
    """Format a policy template string with attention item data."""
    try:
        return template.format(
            site_name=item.site_name or item.object_id,
            object_id=item.object_id,
            reason_text=item.technical_summary or item.friendly_summary or "",
            severity=item.severity,
        )
    except (KeyError, IndexError):
        return template


# ═══════════════════════════════════════════════════════════════════
# EVALUATION (pure, no DB writes)
# ═══════════════════════════════════════════════════════════════════

def evaluate_attention_items(
    items: list[AttentionItem],
    recent_keys: dict[str, datetime],
    now: datetime | None = None,
) -> list[AutomationDecision]:
    """Evaluate attention items against automation policies.

    Args:
        items: AttentionItem list from the attention engine
        recent_keys: {dedupe_key: last_created_at} of recent automation
                     events, used for suppression checks
        now: evaluation timestamp

    Returns:
        List of AutomationDecision objects (some may be suppressed)
    """
    now = now or datetime.now(timezone.utc)
    decisions: list[AutomationDecision] = []

    for item in items:
        # Only evaluate items that need attention
        if item.canonical_status == CanonicalStatus.CONNECTED.value:
            continue

        # Look up policy for the primary reason
        policy = get_policy(item.primary_reason, item.severity)
        if not policy:
            continue

        # Build dedupe key
        dk = _dedupe_key(item.object_type, item.object_id, item.primary_reason, policy.automation_type)

        # Check suppression
        status = "suggested"
        suppress_until_dt = None
        if dk in recent_keys:
            last_seen = recent_keys[dk]
            suppress_until_dt = last_seen + timedelta(minutes=policy.suppress_minutes)
            if now < suppress_until_dt:
                status = "suppressed"

        # Elevate to "queued" for automatic execution mode
        if status == "suggested" and policy.execution_mode == "automatic":
            status = "queued"

        decisions.append(AutomationDecision(
            id=f"auto-{uuid.uuid4().hex[:10]}",
            tenant_id=item.tenant_id,
            object_type=item.object_type,
            object_id=item.object_id,
            site_id=item.site_id,
            site_name=item.site_name,
            reason_code=item.primary_reason,
            severity=item.severity,
            automation_type=policy.automation_type,
            automation_status=status,
            execution_mode=policy.execution_mode,
            recipient_scopes=policy.recipient_scopes,
            recommendation_title=_format_template(policy.recommendation_title, item),
            recommendation_detail=_format_template(policy.recommendation_detail, item),
            dedupe_key=dk,
            suppress_until=suppress_until_dt.isoformat() if suppress_until_dt else None,
            created_at=now.isoformat(),
            route_hint=item.route_hint,
        ))

    return decisions


# ═══════════════════════════════════════════════════════════════════
# PERSISTENCE (load recent + record new decisions)
# ═══════════════════════════════════════════════════════════════════

async def load_recent_automation_keys(
    db: AsyncSession,
    tenant_id: str,
    lookback_hours: int = 24,
) -> dict[str, datetime]:
    """Load dedupe keys of recent automation events for suppression checks.

    Returns {dedupe_key: created_at} for events within the lookback window.
    Uses the trigger_source field to store the dedupe key.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    q = await db.execute(
        select(AutonomousAction.trigger_source, AutonomousAction.created_at)
        .where(
            and_(
                AutonomousAction.tenant_id == tenant_id,
                AutonomousAction.action_type.like("automation_%"),
                AutonomousAction.created_at >= cutoff,
            )
        )
        .order_by(AutonomousAction.created_at.desc())
    )
    result = {}
    for key, ts in q.all():
        if key and key not in result:  # Keep most recent per key
            result[key] = ts
    return result


async def persist_decisions(
    db: AsyncSession,
    decisions: list[AutomationDecision],
    tenant_id: str,
) -> int:
    """Persist non-suppressed automation decisions as AutonomousAction records.

    Only records decisions with status != 'suppressed'.
    Returns count of records created.
    """
    count = 0
    for d in decisions:
        if d.automation_status == "suppressed":
            continue

        db.add(AutonomousAction(
            action_id=d.id,
            tenant_id=tenant_id,
            action_type=f"automation_{d.automation_type}",
            trigger_source=d.dedupe_key,
            site_id=d.site_id,
            device_id=d.object_id if d.object_type == "device" else None,
            summary=d.recommendation_title,
            detail_json=json.dumps({
                "recommendation_detail": d.recommendation_detail,
                "reason_code": d.reason_code,
                "severity": d.severity,
                "execution_mode": d.execution_mode,
                "recipient_scopes": d.recipient_scopes,
                "automation_status": d.automation_status,
            }),
            status=d.automation_status,
            result=None,
        ))
        count += 1

    return count


# ═══════════════════════════════════════════════════════════════════
# RESOLUTION (clear resolved conditions)
# ═══════════════════════════════════════════════════════════════════

async def resolve_cleared_conditions(
    db: AsyncSession,
    tenant_id: str,
    current_attention_keys: set[str],
) -> int:
    """Mark automation events as resolved when their conditions have cleared.

    Checks recent non-resolved automation events. If their dedupe key
    no longer appears in the current attention feed, marks them resolved.

    Returns count of resolved events.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    q = await db.execute(
        select(AutonomousAction)
        .where(
            and_(
                AutonomousAction.tenant_id == tenant_id,
                AutonomousAction.action_type.like("automation_%"),
                AutonomousAction.status.in_(["suggested", "queued"]),
                AutonomousAction.created_at >= cutoff,
            )
        )
    )
    resolved = 0
    for action in q.scalars().all():
        if action.trigger_source and action.trigger_source not in current_attention_keys:
            action.status = "resolved"
            action.result = "condition_cleared"
            resolved += 1
    return resolved


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

async def run_automation(
    db: AsyncSession,
    tenant_id: str,
    attention_feed: list[AttentionItem],
) -> dict:
    """Run the full automation cycle for a tenant.

    1. Load recent automation keys for dedup
    2. Evaluate attention items against policies
    3. Persist new non-suppressed decisions
    4. Resolve cleared conditions
    5. Return summary + decisions for API consumption

    Args:
        db: async database session
        tenant_id: tenant scope
        attention_feed: list of AttentionItem from attention engine

    Returns dict with:
        decisions: list of serialized AutomationDecision
        active_count: number of new actionable decisions
        suppressed_count: number of suppressed duplicates
        resolved_count: number of previously active items now resolved
    """
    # 1. Load recent dedupe keys
    recent_keys = await load_recent_automation_keys(db, tenant_id)

    # 2. Evaluate
    decisions = evaluate_attention_items(attention_feed, recent_keys)

    # 3. Persist non-suppressed
    persisted = await persist_decisions(db, decisions, tenant_id)

    # 4. Resolve cleared
    current_keys = {d.dedupe_key for d in decisions if d.automation_status != "suppressed"}
    resolved = await resolve_cleared_conditions(db, tenant_id, current_keys)

    # 5. Summarize
    active = [d for d in decisions if d.automation_status in ("suggested", "queued")]
    suppressed = [d for d in decisions if d.automation_status == "suppressed"]

    return {
        "decisions": [_serialize_decision(d) for d in decisions],
        "active": [_serialize_decision(d) for d in active],
        "suppressed_count": len(suppressed),
        "active_count": len(active),
        "resolved_count": resolved,
        "persisted_count": persisted,
    }


# ═══════════════════════════════════════════════════════════════════
# SERIALIZATION
# ═══════════════════════════════════════════════════════════════════

def _serialize_decision(d: AutomationDecision) -> dict:
    return {
        "id": d.id,
        "object_type": d.object_type,
        "object_id": d.object_id,
        "site_id": d.site_id,
        "site_name": d.site_name,
        "reason_code": d.reason_code,
        "severity": d.severity,
        "automation_type": d.automation_type,
        "automation_status": d.automation_status,
        "execution_mode": d.execution_mode,
        "recipient_scopes": d.recipient_scopes,
        "recommendation_title": d.recommendation_title,
        "recommendation_detail": d.recommendation_detail,
        "dedupe_key": d.dedupe_key,
        "suppress_until": d.suppress_until,
        "created_at": d.created_at,
        "route_hint": d.route_hint,
    }


def filter_for_role(decisions: list[dict], role: str) -> list[dict]:
    """Filter automation decisions to those visible for a given role.

    SuperAdmin sees everything.
    Other roles only see decisions where their role is in recipient_scopes.
    """
    r = role.lower()
    if r == "superadmin":
        return decisions
    return [d for d in decisions if r in d.get("recipient_scopes", [])]
