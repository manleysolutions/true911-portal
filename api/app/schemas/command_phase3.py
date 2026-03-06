from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# -- Notifications --

class NotificationOut(BaseModel):
    id: int
    channel: str
    severity: str
    title: str
    body: Optional[str] = None
    incident_id: Optional[str] = None
    site_id: Optional[str] = None
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationMarkRead(BaseModel):
    notification_ids: list[int]


# -- Escalation Rules --

class EscalationRuleCreate(BaseModel):
    name: str
    severity: str = "critical"
    escalate_after_minutes: int = 30
    escalation_target: Optional[str] = None
    notify_channel: str = "in_app"
    enabled: bool = True


class EscalationRuleUpdate(BaseModel):
    name: Optional[str] = None
    severity: Optional[str] = None
    escalate_after_minutes: Optional[int] = None
    escalation_target: Optional[str] = None
    notify_channel: Optional[str] = None
    enabled: Optional[bool] = None


class EscalationRuleOut(BaseModel):
    id: int
    tenant_id: str
    name: str
    severity: str
    escalate_after_minutes: int
    escalation_target: Optional[str] = None
    notify_channel: str
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Telemetry Ingest --

class TelemetryIngest(BaseModel):
    device_id: str
    site_id: Optional[str] = None
    signal_strength: Optional[float] = None
    battery_pct: Optional[float] = None
    uptime_seconds: Optional[int] = None
    temperature_c: Optional[float] = None
    error_count: Optional[int] = None
    firmware_version: Optional[str] = None
    metadata_json: Optional[str] = None


class TelemetryOut(BaseModel):
    id: int
    device_id: str
    site_id: Optional[str] = None
    signal_strength: Optional[float] = None
    battery_pct: Optional[float] = None
    uptime_seconds: Optional[int] = None
    temperature_c: Optional[float] = None
    error_count: Optional[int] = None
    firmware_version: Optional[str] = None
    recorded_at: datetime

    model_config = {"from_attributes": True}


# -- Report request --

class ReportRequest(BaseModel):
    report_type: str = "portfolio"  # portfolio | site
    site_id: Optional[str] = None
    format: str = "csv"  # csv only for now
