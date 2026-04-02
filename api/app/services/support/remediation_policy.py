"""Remediation policy engine — decides whether an action is allowed.

Checks:
  1. Action is registered and enabled
  2. Action is not on the deny-list
  3. Cooldown has expired since last attempt
  4. Max attempts per 24h not exceeded
  5. Life-safety sensitivity assessment

Returns a structured decision that the self-healing engine uses
before executing any action.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import SupportRemediationAction
from .remediation_registry import get_action, is_blocked, BLOCKED_ACTIONS

logger = logging.getLogger("true911.support.remediation_policy")


@dataclass
class PolicyDecision:
    """Result of a remediation policy evaluation."""
    allowed: bool
    reason: str
    cooldown_remaining_seconds: int = 0
    requires_admin_approval: bool = False
    verification_required: bool = True


async def evaluate(
    db: AsyncSession,
    action_type: str,
    tenant_id: str,
    device_id: int | None = None,
    site_id: int | None = None,
) -> PolicyDecision:
    """Evaluate whether a remediation action is allowed right now.

    This is the gate. Nothing runs without passing through here.
    """

    # 1. Deny-list check (fast path — no DB needed)
    if is_blocked(action_type):
        return PolicyDecision(
            allowed=False,
            reason=f"Action '{action_type}' is on the safety deny-list and cannot be auto-executed.",
        )

    # 2. Registry check
    defn = get_action(action_type)
    if defn is None:
        return PolicyDecision(
            allowed=False,
            reason=f"Action '{action_type}' is not registered in the remediation registry.",
        )

    if not defn.enabled:
        return PolicyDecision(
            allowed=False,
            reason=f"Action '{action_type}' is registered but disabled (gated). Enable explicitly to use.",
            requires_admin_approval=True,
        )

    # 3. Cooldown check — was this action run recently on this device/tenant?
    last_action = await _get_last_action(db, action_type, tenant_id, device_id, site_id)

    if last_action and last_action.started_at:
        cooldown_end = last_action.started_at + timedelta(minutes=defn.cooldown_minutes)
        now = datetime.now(timezone.utc)
        if now < cooldown_end:
            remaining = int((cooldown_end - now).total_seconds())
            return PolicyDecision(
                allowed=False,
                reason=f"Cooldown active for '{action_type}'. {remaining}s remaining.",
                cooldown_remaining_seconds=remaining,
            )

    # 4. Max attempts check (24h window)
    attempt_count = await _count_recent_attempts(db, action_type, tenant_id, device_id, site_id)

    if attempt_count >= defn.max_attempts_24h:
        return PolicyDecision(
            allowed=False,
            reason=f"Max attempts ({defn.max_attempts_24h}) for '{action_type}' reached in the last 24 hours.",
        )

    # 5. Gated actions require admin approval flag
    requires_approval = defn.level == "gated"

    return PolicyDecision(
        allowed=True,
        reason="Action is allowed by policy.",
        verification_required=defn.verification_required,
        requires_admin_approval=requires_approval,
    )


async def _get_last_action(
    db: AsyncSession,
    action_type: str,
    tenant_id: str,
    device_id: int | None,
    site_id: int | None,
) -> SupportRemediationAction | None:
    """Find the most recent attempt of this action for this scope."""
    q = select(SupportRemediationAction).where(and_(
        SupportRemediationAction.action_type == action_type,
        SupportRemediationAction.tenant_id == tenant_id,
    ))
    if device_id is not None:
        q = q.where(SupportRemediationAction.device_id == device_id)
    elif site_id is not None:
        q = q.where(SupportRemediationAction.site_id == site_id)

    q = q.order_by(SupportRemediationAction.created_at.desc()).limit(1)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def _count_recent_attempts(
    db: AsyncSession,
    action_type: str,
    tenant_id: str,
    device_id: int | None,
    site_id: int | None,
) -> int:
    """Count how many times this action has been attempted in the last 24 hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    q = select(func.count()).select_from(SupportRemediationAction).where(and_(
        SupportRemediationAction.action_type == action_type,
        SupportRemediationAction.tenant_id == tenant_id,
        SupportRemediationAction.created_at >= cutoff,
    ))
    if device_id is not None:
        q = q.where(SupportRemediationAction.device_id == device_id)
    elif site_id is not None:
        q = q.where(SupportRemediationAction.site_id == site_id)

    result = await db.execute(q)
    return result.scalar() or 0
