from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class NotificationRuleOut(BaseModel):
    id: int
    rule_id: str
    tenant_id: str
    rule_name: str
    rule_type: str
    threshold_value: float
    threshold_unit: str
    scope: str
    channels: list[str]
    enabled: bool
    escalation_steps: list[Any]
    trigger_count: int
    last_triggered: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationRuleCreate(BaseModel):
    rule_id: str
    rule_name: str
    rule_type: str
    threshold_value: float
    threshold_unit: str
    scope: str
    channels: list[str] = []
    enabled: bool = True
    escalation_steps: list[Any] = []
    trigger_count: int = 0
    tenant_id: Optional[str] = None  # ignored, set server-side


class NotificationRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    rule_type: Optional[str] = None
    threshold_value: Optional[float] = None
    threshold_unit: Optional[str] = None
    scope: Optional[str] = None
    channels: Optional[list[str]] = None
    enabled: Optional[bool] = None
    escalation_steps: Optional[list[Any]] = None
    trigger_count: Optional[int] = None
    last_triggered: Optional[datetime] = None
