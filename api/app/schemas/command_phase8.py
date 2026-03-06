"""Phase 8 — Autonomous Infrastructure Operations schemas."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Autonomous Actions ──────────────────────────────────────────────

class AutonomousActionOut(BaseModel):
    id: int
    action_id: str
    tenant_id: str
    action_type: str
    trigger_source: str
    site_id: Optional[str] = None
    device_id: Optional[str] = None
    incident_id: Optional[str] = None
    summary: str
    detail_json: Optional[str] = None
    status: str
    result: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Operational Digests ─────────────────────────────────────────────

class OperationalDigestOut(BaseModel):
    id: int
    digest_id: str
    tenant_id: str
    digest_type: str
    period_start: datetime
    period_end: datetime
    summary_json: str
    created_at: datetime

    class Config:
        from_attributes = True


class GenerateDigestRequest(BaseModel):
    digest_type: str = "daily"  # daily or weekly


# ── Engine Run Result ───────────────────────────────────────────────

class EngineRunResult(BaseModel):
    rules_evaluated: int
    rules_fired: int
    incidents_created: int
    diagnostics_run: int
    self_heals_attempted: int
    escalations_processed: int
    verifications_scheduled: int
    readiness_recalculated: int
    actions_logged: int


# ── Autonomous Dashboard ───────────────────────────────────────────

class AutoOpsSummary(BaseModel):
    total_actions_24h: int
    incidents_auto_created: int
    diagnostics_run: int
    self_heals_attempted: int
    self_heals_resolved: int
    escalations_triggered: int
    verifications_scheduled: int
    recent_actions: List[AutonomousActionOut]
