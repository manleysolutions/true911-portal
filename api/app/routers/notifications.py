from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_db, get_current_user, require_permission
from ..models.notification_rule import NotificationRule
from ..models.user import User
from ..schemas.notification_rule import (
    NotificationRuleOut,
    NotificationRuleCreate,
    NotificationRuleUpdate,
)

router = APIRouter(prefix="/notification-rules", tags=["notification-rules"])


@router.get("", response_model=list[NotificationRuleOut])
async def list_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(NotificationRule)
        .where(NotificationRule.tenant_id == current_user.tenant_id)
        .order_by(desc(NotificationRule.created_at))
    )
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.post("", response_model=NotificationRuleOut, dependencies=[Depends(require_permission("MANAGE_NOTIFICATIONS"))])
async def create_rule(
    body: NotificationRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = NotificationRule(
        rule_id=body.rule_id,
        tenant_id=current_user.tenant_id,
        rule_name=body.rule_name,
        rule_type=body.rule_type,
        threshold_value=body.threshold_value,
        threshold_unit=body.threshold_unit,
        scope=body.scope,
        channels=body.channels,
        escalation_steps=body.escalation_steps,
        enabled=body.enabled if body.enabled is not None else True,
        trigger_count=body.trigger_count or 0,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=NotificationRuleOut, dependencies=[Depends(require_permission("MANAGE_NOTIFICATIONS"))])
async def update_rule(
    rule_id: int,
    body: NotificationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(NotificationRule).where(
        NotificationRule.id == rule_id,
        NotificationRule.tenant_id == current_user.tenant_id,
    )
    rule = (await db.execute(q)).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, val)

    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", dependencies=[Depends(require_permission("MANAGE_NOTIFICATIONS"))])
async def delete_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(NotificationRule).where(
        NotificationRule.id == rule_id,
        NotificationRule.tenant_id == current_user.tenant_id,
    )
    rule = (await db.execute(q)).scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    await db.delete(rule)
    await db.commit()
    return {"ok": True}
