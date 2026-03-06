"""
True911 Command — Notification center & escalation rules.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.notification import CommandNotification
from ..models.escalation_rule import EscalationRule
from ..models.user import User
from ..schemas.command_phase3 import (
    NotificationOut,
    NotificationMarkRead,
    EscalationRuleCreate,
    EscalationRuleUpdate,
    EscalationRuleOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Notification center
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(30, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notifications for the current user's tenant."""
    q = (
        select(CommandNotification)
        .where(CommandNotification.tenant_id == current_user.tenant_id)
        .where(
            (CommandNotification.target_user == current_user.email)
            | (CommandNotification.target_user.is_(None))
        )
        .where(
            (CommandNotification.target_role == current_user.role)
            | (CommandNotification.target_role.is_(None))
        )
        .order_by(CommandNotification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        q = q.where(CommandNotification.read == False)  # noqa: E712
    result = await db.execute(q)
    return [NotificationOut.model_validate(n) for n in result.scalars().all()]


@router.get("/notifications/count")
async def notification_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return unread notification count for the bell badge."""
    q = (
        select(func.count())
        .select_from(CommandNotification)
        .where(
            CommandNotification.tenant_id == current_user.tenant_id,
            CommandNotification.read == False,  # noqa: E712
        )
        .where(
            (CommandNotification.target_user == current_user.email)
            | (CommandNotification.target_user.is_(None))
        )
        .where(
            (CommandNotification.target_role == current_user.role)
            | (CommandNotification.target_role.is_(None))
        )
    )
    result = await db.execute(q)
    return {"unread": result.scalar() or 0}


@router.post("/notifications/read")
async def mark_notifications_read(
    body: NotificationMarkRead,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark notifications as read."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(CommandNotification)
        .where(
            CommandNotification.id.in_(body.notification_ids),
            CommandNotification.tenant_id == current_user.tenant_id,
        )
        .values(read=True, read_by=current_user.email, read_at=now)
    )
    await db.commit()
    return {"marked": len(body.notification_ids)}


@router.post("/notifications/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all notifications as read for the current user."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(CommandNotification)
        .where(
            CommandNotification.tenant_id == current_user.tenant_id,
            CommandNotification.read == False,  # noqa: E712
        )
        .where(
            (CommandNotification.target_user == current_user.email)
            | (CommandNotification.target_user.is_(None))
        )
        .where(
            (CommandNotification.target_role == current_user.role)
            | (CommandNotification.target_role.is_(None))
        )
        .values(read=True, read_by=current_user.email, read_at=now)
    )
    await db.commit()
    return {"marked": result.rowcount}


# ---------------------------------------------------------------------------
# Escalation rules CRUD
# ---------------------------------------------------------------------------

@router.get("/escalation-rules", response_model=list[EscalationRuleOut])
async def list_escalation_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_ESCALATION")),
):
    result = await db.execute(
        select(EscalationRule)
        .where(EscalationRule.tenant_id == current_user.tenant_id)
        .order_by(EscalationRule.severity, EscalationRule.escalate_after_minutes)
    )
    return [EscalationRuleOut.model_validate(r) for r in result.scalars().all()]


@router.post("/escalation-rules", response_model=EscalationRuleOut)
async def create_escalation_rule(
    body: EscalationRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_ESCALATION")),
):
    rule = EscalationRule(
        tenant_id=current_user.tenant_id,
        name=body.name,
        severity=body.severity,
        escalate_after_minutes=body.escalate_after_minutes,
        escalation_target=body.escalation_target,
        notify_channel=body.notify_channel,
        enabled=body.enabled,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return EscalationRuleOut.model_validate(rule)


@router.put("/escalation-rules/{rule_id}", response_model=EscalationRuleOut)
async def update_escalation_rule(
    rule_id: int,
    body: EscalationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_ESCALATION")),
):
    result = await db.execute(
        select(EscalationRule).where(
            EscalationRule.id == rule_id,
            EscalationRule.tenant_id == current_user.tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Escalation rule not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, val)
    rule.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(rule)
    return EscalationRuleOut.model_validate(rule)


@router.delete("/escalation-rules/{rule_id}")
async def delete_escalation_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("COMMAND_MANAGE_ESCALATION")),
):
    result = await db.execute(
        select(EscalationRule).where(
            EscalationRule.id == rule_id,
            EscalationRule.tenant_id == current_user.tenant_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Escalation rule not found")
    await db.delete(rule)
    await db.commit()
    return {"deleted": rule_id}
