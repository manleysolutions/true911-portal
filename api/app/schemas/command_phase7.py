"""Phase 7 — Network & Public Safety Integration schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Network Events ──────────────────────────────────────────────────

class NetworkEventCreate(BaseModel):
    device_id: str
    carrier: Optional[str] = None
    event_type: str
    severity: str = "info"
    summary: str
    detail_json: Optional[str] = None
    signal_dbm: Optional[float] = None
    network_status: Optional[str] = None
    roaming: Optional[bool] = False


class NetworkEventOut(BaseModel):
    id: int
    event_id: str
    tenant_id: str
    device_id: str
    site_id: Optional[str] = None
    carrier: Optional[str] = None
    event_type: str
    severity: str
    summary: str
    signal_dbm: Optional[float] = None
    network_status: Optional[str] = None
    roaming: Optional[bool] = None
    resolved: bool
    resolved_at: Optional[datetime] = None
    incident_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Carrier Telemetry Ingest ────────────────────────────────────────

class CarrierTelemetryIngest(BaseModel):
    device_id: str
    carrier: str
    signal_dbm: Optional[float] = None
    network_status: Optional[str] = None
    roaming: Optional[bool] = None
    data_usage_mb: Optional[float] = None
    network_tech: Optional[str] = None


# ── Infrastructure Tests ────────────────────────────────────────────

class InfraTestCreate(BaseModel):
    name: str
    test_type: str  # voice_path, emergency_call, heartbeat_verify, radio_coverage, connectivity
    description: Optional[str] = None
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    schedule_cron: Optional[str] = None
    run_after_provision: bool = False
    config_json: Optional[str] = None


class InfraTestUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    schedule_cron: Optional[str] = None
    run_after_provision: Optional[bool] = None
    enabled: Optional[bool] = None
    config_json: Optional[str] = None


class InfraTestOut(BaseModel):
    id: int
    test_id: str
    tenant_id: str
    name: str
    test_type: str
    description: Optional[str] = None
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    schedule_cron: Optional[str] = None
    run_after_provision: bool
    enabled: bool
    last_run_at: Optional[datetime] = None
    last_result: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class InfraTestResultOut(BaseModel):
    id: int
    result_id: str
    test_id: str
    tenant_id: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    detail_json: Optional[str] = None
    error_message: Optional[str] = None
    triggered_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RunTestRequest(BaseModel):
    triggered_by: str = "manual"


# ── Audit Log ───────────────────────────────────────────────────────

class AuditLogEntryOut(BaseModel):
    id: int
    entry_id: str
    tenant_id: str
    category: str
    action: str
    actor: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    summary: str
    detail_json: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── NG911 Site Fields ───────────────────────────────────────────────

class SiteNG911Update(BaseModel):
    psap_id: Optional[str] = None
    emergency_class: Optional[str] = None
    ng911_uri: Optional[str] = None


# ── Network Dashboard ──────────────────────────────────────────────

class NetworkSummary(BaseModel):
    total_devices: int
    connected: int
    disconnected: int
    degraded: int
    carrier_distribution: dict
    recent_network_events: List[NetworkEventOut]
    signal_distribution: dict
